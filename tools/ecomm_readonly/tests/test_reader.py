from copy import deepcopy
import io
import json
import unittest
from contextlib import redirect_stdout

from ecomm_reader.catalog import decode, gtin_valid, presentation, variant_id
from ecomm_reader.cli import main
from ecomm_reader.policy import BARCODE, HOST
from ecomm_reader.reader import InventoryReader
from ecomm_reader.safety import Code, Failure
from ecomm_reader.simulated import (
    FakeContext,
    FakeDNS,
    FakeFactory,
    demo_reader,
    envelope,
    http_reply,
    item,
)
from ecomm_reader.wire import Credential, PinnedGetWire


def make_reader(*responses):
    factory = FakeFactory([http_reply(value) for value in responses])
    dns = FakeDNS()
    wire = PinnedGetWire(socket_factory=factory, context=FakeContext())
    return (
        InventoryReader(dns, wire, Credential("NON_SECRET_READER_FIXTURE")),
        factory,
        dns,
    )


def variants(count=50, start=910000):
    return [item(start + i, description="200 ml", brand=None) for i in range(count)]


class Identity(unittest.TestCase):
    def row(self, value):
        reader, _, _ = make_reader(envelope([value]))
        return reader.read()["candidates"][0]

    def test_id_is_nested_variant_not_sku_parent_or_warehouse(self):
        value = item(918273645012345678901234567890)
        value["id"] = 42
        value["variants"][0]["warehouses"] = [{"id": 99}]
        row = self.row(value)
        self.assertEqual(row["response_variant_id"], "918273645012345678901234567890")
        self.assertEqual(row["id_source_path"], "data.items[0].variants[0].id")
        self.assertTrue(row["eligible_for_human_review"])
        self.assertFalse(row["binding_permitted"])

    def test_invalid_null_placeholder_ids_fail_the_entire_response(self):
        for ident in (
            None,
            "",
            " ",
            "None",
            "null",
            "NULL",
            "undefined",
            "0",
            0,
            -1,
            True,
            False,
            1.5,
            1.0,
            [],
            {},
            "001",
            "1e3",
            "١",
            "a",
            "1\n",
            "9" * 121,
        ):
            with self.subTest(ident=ident), self.assertRaises(Failure) as caught:
                self.row(item(ident))
            self.assertEqual(caught.exception.code, Code.ID)

    def test_valid_ids_preserve_canonical_string(self):
        for ident in (1234, "1234", "9" * 120):
            self.assertEqual(variant_id(ident), str(ident))

    def test_missing_variant_id_has_no_parent_or_sku_fallback(self):
        value = item()
        del value["variants"][0]["id"]
        value["id"] = 919191
        with self.assertRaises(Failure):
            self.row(value)

    def test_barcode_gtin_disagreement_is_visible_and_blocks_review(self):
        row = self.row(item(gtin="8851876201433"))
        self.assertEqual(row["source_fields"]["barcode"], BARCODE)
        self.assertEqual(row["source_fields"]["gtin"], "8851876201433")
        self.assertIn("BARCODE_GTIN_CONFLICT", row["blockers"])
        self.assertFalse(row["eligible_for_human_review"])

    def test_invalid_missing_or_dun_codes_cannot_identify_individual(self):
        self.assertTrue(gtin_valid(BARCODE))
        for code in (None, "", "7794940000797", 7794940000796, "97794940000799"):
            with self.subTest(code=code):
                if isinstance(code, int):
                    with self.assertRaises(Failure):
                        self.row(item(barcode=code, gtin=code))
                else:
                    row = self.row(item(barcode=code, gtin=code))
                    self.assertFalse(row["eligible_for_human_review"])

    def test_ean_alone_never_suffices(self):
        value = item(description="200 ml", brand=None, combo=None)
        value["description"] = "7794940000796"
        value["variants"][0]["sku"] = None
        row = self.row(value)
        self.assertTrue(
            {
                "SKU_MISSING",
                "NAME_NOT_CONFIRMED",
                "BRAND_NOT_CONFIRMED",
                "COMMERCIAL_UNIT_COUNT_NOT_CONFIRMED",
                "COMBO_NOT_CONFIRMED_AS_FALSE",
            }.issubset(row["blockers"])
        )
        self.assertFalse(row["eligible_for_human_review"])

    def test_brand_name_presentation_sku_each_independently_required(self):
        mutations = (
            ("variant", "brand", None, "BRAND_NOT_CONFIRMED"),
            ("variant", "brand", "Otra marca", "BRAND_NOT_CONFIRMED"),
            ("parent", "description", "Hileret Zucra", "NAME_NOT_CONFIRMED"),
            (
                "variant",
                "variant_description",
                "Unidad de 400 ml",
                "PRESENTATION_NOT_CONFIRMED",
            ),
            ("variant", "sku", "", "SKU_MISSING"),
        )
        for where, key, value, blocker in mutations:
            candidate = item()
            (candidate if where == "parent" else candidate["variants"][0])[key] = value
            with self.subTest(key=key, value=value):
                row = self.row(candidate)
                self.assertIn(blocker, row["blockers"])
                self.assertFalse(row["eligible_for_human_review"])

    def test_brand_is_not_inferred_from_the_name_or_sku(self):
        candidate = item(brand=None)
        candidate["variants"][0]["sku"] = "Hileret-Stevia-200ml"
        self.assertIn("BRAND_NOT_CONFIRMED", self.row(candidate)["blockers"])
        candidate["brand"] = "Hileret"
        self.assertTrue(self.row(candidate)["eligible_for_human_review"])
        candidate["variants"][0]["brand"] = "Otra marca"
        self.assertIn("BRAND_CONFLICT", self.row(candidate)["blockers"])

    def test_unknown_false_like_or_true_combo_is_never_false(self):
        for combo in (None, True, 0, "false", "False", "", []):
            row = self.row(item(combo=combo))
            self.assertIn("COMBO_NOT_CONFIRMED_AS_FALSE", row["blockers"])
            self.assertFalse(row["eligible_for_human_review"])
        candidate = item()
        candidate["is_combo"] = True
        self.assertIn("PARENT_COMBO_REQUIRES_REVIEW", self.row(candidate)["blockers"])

    def test_stock_and_sku_are_not_commercial_quantity(self):
        candidate = item(description="200 ml")
        candidate["variants"][0].update(
            total_stock=1, sku="Hileret_unidad_1", warehouses=[{"quantity": 1}]
        )
        self.assertIn(
            "COMMERCIAL_UNIT_COUNT_NOT_CONFIRMED", self.row(candidate)["blockers"]
        )

    def test_unit_pack_six_box_nine_are_never_merged_by_shared_ean(self):
        result = demo_reader().read()
        self.assertEqual(
            [r["commercial_units_from_presentation"] for r in result["candidates"]],
            [1, 6, 9],
        )
        self.assertEqual(
            [r["eligible_for_human_review"] for r in result["candidates"]],
            [True, False, False],
        )
        self.assertEqual(
            len({r["response_variant_id"] for r in result["candidates"]}), 3
        )
        self.assertIsNone(result["authentic_ecomm_id"])
        self.assertFalse(result["binding_permitted"])
        self.assertEqual(result["real_requests"], 0)

    def test_same_parent_variants_remain_distinct_and_multiple_compatible_block(self):
        candidate = item()
        candidate["variants"].append(item(900002)["variants"][0])
        reader, _, _ = make_reader(envelope([candidate]))
        rows = reader.read()["candidates"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(
            all("MULTIPLE_COMPATIBLE_VARIANTS" in row["blockers"] for row in rows)
        )
        self.assertEqual(rows[1]["id_source_path"], "data.items[0].variants[1].id")
        self.assertTrue(all(not row["eligible_for_human_review"] for row in rows))

    def test_conflicting_presentations_are_preserved_and_blocked(self):
        candidate = item()
        candidate["variants"][0]["description"] = "Pack x6 de 200 ml"
        row = self.row(candidate)
        self.assertIn("PRESENTATION_CONFLICT", row["blockers"])
        self.assertEqual(row["source_fields"]["description"], "Pack x6 de 200 ml")

    def test_cc_liters_and_explicit_unit_are_recognized_without_guessing(self):
        for text in (
            "Unidad de 200 cc",
            "Unidad individual de 0,2 l",
            "Botella individual 200 ml",
        ):
            self.assertTrue(
                self.row(item(description=text))["eligible_for_human_review"]
            )
        self.assertEqual(presentation("Caja 9 × 200 ml")[1], 9)
        for text in (
            "200 ml",
            "200 ml / 400 ml",
            "Hileret 200 ml",
            "un envase",
            "Pack x6",
        ):
            self.assertFalse(
                self.row(item(description=text))["eligible_for_human_review"]
            )


class PaginationAndSchema(unittest.TestCase):
    def test_one_page_is_the_default_and_reader_is_one_use(self):
        reader, factory, dns = make_reader(envelope())
        result = reader.read()
        self.assertEqual(result["simulated_gets"], 1)
        self.assertEqual(result["scope"], "FILTERED_QUERY_COMPLETE")
        self.assertEqual(dns.calls, [HOST, HOST])
        self.assertEqual(len(factory.channels), 1)
        with self.assertRaises(Failure):
            reader.read()
        self.assertEqual(len(factory.channels), 1)

    def test_missing_pagination_never_authorizes_second_or_claims_completeness(self):
        data = envelope()
        del data["data"]["paginacion"]
        reader, factory, _ = make_reader(data)
        result = reader.read()
        self.assertEqual(result["scope"], "PAGINATION_UNCONFIRMED")
        self.assertEqual(len(factory.channels), 1)
        self.assertIn("QUERY_SCOPE_UNCONFIRMED", result["candidates"][0]["blockers"])

    def test_empty_query_is_not_a_claim_of_product_absence(self):
        reader, factory, _ = make_reader(envelope([], total=0))
        result = reader.read()
        self.assertEqual(result["candidates"], [])
        self.assertIsNone(result["authentic_ecomm_id"])
        self.assertFalse(result["binding_permitted"])
        self.assertEqual(len(factory.channels), 1)

    def test_only_a_validated_second_page_is_requested(self):
        reader, factory, _ = make_reader(
            envelope(variants(), total=51), envelope([item()], page=2, total=51)
        )
        result = reader.read()
        self.assertEqual(result["simulated_gets"], 2)
        self.assertEqual(len(result["candidates"]), 51)
        self.assertEqual(result["scope"], "FILTERED_QUERY_COMPLETE")
        self.assertTrue(result["candidates"][-1]["eligible_for_human_review"])
        self.assertEqual(result["candidates"][-1]["response_page"], 2)
        self.assertIn(b"page=2&limit=50", factory.channels[1].sent)

    def test_more_than_two_pages_is_incomplete_and_never_requests_a_third(self):
        reader, factory, _ = make_reader(
            envelope(variants(), total=101),
            envelope([item()] + variants(49, 920000), page=2, total=101),
        )
        result = reader.read()
        self.assertEqual(len(factory.channels), 2)
        self.assertEqual(result["scope"], "QUERY_TRUNCATED_AT_TWO_PAGES")
        self.assertIn("QUERY_SCOPE_UNCONFIRMED", result["candidates"][50]["blockers"])
        with self.assertRaises(Failure):
            reader._page(3)

    def test_second_page_cannot_be_requested_without_pagination(self):
        reader, factory, _ = make_reader(envelope())
        with self.assertRaises(Failure):
            reader._page(2)
        self.assertEqual(factory.channels, [])

    def test_invalid_pagination_stops_before_second_request(self):
        for change in (
            {"page": 2},
            {"total": 51, "total_pages": 2},
            {"total_pages": 0},
            {"per_page": 100},
            {"total": "1"},
            {"page": True},
            {"total": -1},
        ):
            data = envelope()
            data["data"]["paginacion"].update(change)
            reader, factory, _ = make_reader(data)
            with self.subTest(change=change), self.assertRaises(Failure) as caught:
                reader.read()
            self.assertEqual(caught.exception.code, Code.PAGINATION)
            self.assertEqual(len(factory.channels), 1)

    def test_pagination_change_or_missing_second_metadata_is_blocked(self):
        for change in ({"total": 52}, {"page": 1}, {"total_pages": 3}, None):
            second = envelope([item()], page=2, total=51)
            if change is None:
                del second["data"]["paginacion"]
            else:
                second["data"]["paginacion"].update(change)
            reader, factory, _ = make_reader(envelope(variants(), total=51), second)
            with self.assertRaises(Failure) as caught:
                reader.read()
            self.assertEqual(caught.exception.code, Code.PAGINATION)
            self.assertEqual(len(factory.channels), 2)

    def test_duplicate_id_on_same_or_second_page_fails_without_merging(self):
        for first, second in (
            (envelope([item(), item()], total=2), None),
            (
                envelope(variants(), total=51),
                envelope([item(910000)], page=2, total=51),
            ),
        ):
            reader, _, _ = make_reader(*([first, second] if second else [first]))
            with self.assertRaises(Failure) as caught:
                reader.read()
            self.assertEqual(caught.exception.code, Code.ID)

    def test_conflicting_metadata_aliases_are_not_silently_preferred(self):
        data = envelope()
        data["data"]["pagination"] = deepcopy(data["data"]["paginacion"])
        reader, _, _ = make_reader(data)
        with self.assertRaises(Failure) as caught:
            reader.read()
        self.assertEqual(caught.exception.code, Code.PAGINATION)

    def test_unknown_envelopes_never_use_loose_fallbacks(self):
        for data in (
            {"items": []},
            {"data": []},
            {"data": {"items": {}}},
            {"data": {"items": [{"variants": []}]}},
            {"data": {"items": [item()]}, "error": "raw NON_SECRET_PROVIDER_CONTROL"},
        ):
            reader, _, _ = make_reader(data)
            with self.assertRaises(Failure) as caught:
                reader.read()
            self.assertNotIn("NON_SECRET_PROVIDER_CONTROL", str(caught.exception))

    def test_json_utf8_duplicates_constants_depth_and_work_are_bounded(self):
        for body in (
            b"<html>not json</html>",
            b"\xff",
            b'{"data":{"items":[]},"data":{"items":[]}}',
            b'{"data":{"items":[],"x":NaN}}',
            b'{"data":{"items":[],"x":1e999}}',
            json.dumps({"data": {"items": [], "x": "x" * 10001}}).encode(),
            json.dumps({"data": {"items": [], "x": "\u202e"}}).encode(),
        ):
            with self.assertRaises(Failure):
                decode(body)
        nested = {}
        for _ in range(34):
            nested = {"x": nested}
        with self.assertRaises(Failure):
            decode(json.dumps({"data": {"items": [], "x": nested}}).encode())

    def test_non_simulated_transports_and_resolvers_are_rejected(self):
        for resolver, wire in (
            (object(), object()),
            (FakeDNS(), object()),
            (
                object(),
                PinnedGetWire(socket_factory=FakeFactory([]), context=FakeContext()),
            ),
        ):
            with self.assertRaises(Failure) as caught:
                InventoryReader(resolver, wire, Credential("NON_SECRET_FIXTURE"))
            self.assertEqual(caught.exception.code, Code.OFFLINE_ONLY)

    def test_json_escaped_credential_echo_is_never_returned(self):
        sentinel = "NON_SECRET_READER_FIXTURE"
        value = item()
        value["variants"][0]["description"] = sentinel
        body = (
            json.dumps(envelope([value]))
            .replace(sentinel, "".join("\\u%04x" % ord(c) for c in sentinel))
            .encode()
        )
        factory = FakeFactory([http_reply(body=body)])
        reader = InventoryReader(
            FakeDNS(),
            PinnedGetWire(socket_factory=factory, context=FakeContext()),
            Credential(sentinel),
        )
        with self.assertRaises(Failure) as caught:
            reader.read()
        self.assertEqual(caught.exception.code, Code.SECRET)
        self.assertNotIn(sentinel, str(caught.exception))

    def test_cli_demo_reports_only_simulated_ids_and_no_binding(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["demo"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["mode"], "SIMULATED_RESPONSES_ONLY")
        self.assertEqual(result["real_requests"], 0)
        self.assertFalse(result["external_writes"])
        self.assertIsNone(result["authentic_ecomm_id"])
        self.assertTrue(
            all(
                row["source_fields"]["sku"].startswith("SIMULATED")
                for row in result["candidates"]
            )
        )
