import { expect, test } from "@playwright/test";
import { adaptCommercialCoverage } from "../src/integration/CommercialCoverage";
import { fieldKeys } from "../src/integration/workspace-adapter";

// Contract tests only: all values below are synthetic, with no browser/API access.
function coverage() {
  return {
    schema_version: "kiki-saved-field-coverage-v1",
    ecomm_id: "7518949",
    workspace_version: 6,
    total_fields: 18,
    commercial_completion_certified: false,
    publication_allowed: false,
    fingerprint: "a".repeat(64),
    states: {
      APPROVED_BACKED: 0,
      FILLED_UNBACKED: 0,
      BLOCKED: 0,
      PENDING_REVIEW: 18,
    },
    fields: fieldKeys.map((field) => ({
      field,
      state: "PENDING_REVIEW",
      filled: false,
      field_review_required: true,
      evidence_ids: [] as string[],
      citations: [] as Record<string, unknown>[],
      reasons: ["Falta revisión"],
      lineage: null,
      limits: {
        maximum: 180,
        length: 0,
        unit: "characters",
        valid: true,
        reasons: [],
      },
    })),
  };
}
test("18 actual fields reconcile without certifying publication", () => {
  const result = adaptCommercialCoverage(coverage(), "7518949", 6);
  expect(result.fields).toHaveLength(18);
  expect(result.publication_allowed).toBe(false);
});
test("mixed identity, stale version, partial rows and false totals fail closed", () => {
  for (const mutate of [
    (data: ReturnType<typeof coverage>) => {
      data.ecomm_id = "7518950";
    },
    (data: ReturnType<typeof coverage>) => {
      data.workspace_version = 5;
    },
    (data: ReturnType<typeof coverage>) => {
      data.fields.pop();
    },
    (data: ReturnType<typeof coverage>) => {
      data.states.PENDING_REVIEW = 17;
    },
    (data: ReturnType<typeof coverage>) => {
      data.fields[1].field = data.fields[0].field;
    },
  ]) {
    const data = coverage();
    mutate(data);
    expect(() => adaptCommercialCoverage(data, "7518949", 6)).toThrow();
  }
});
test("green content needs current approved citations for every evidence ID", () => {
  const data = coverage();
  data.states.APPROVED_BACKED = 1;
  data.states.PENDING_REVIEW = 17;
  const row = data.fields.find((field) => field.field === "title")!;
  row.state = "APPROVED_BACKED";
  row.filled = true;
  row.evidence_ids = ["synthetic-name"];
  expect(() => adaptCommercialCoverage(data, "7518949", 6)).toThrow();
  const citation = {
    fact_id: "synthetic-name",
    document_id: "synthetic-doc",
    document_version: 1,
    document_hash: "b".repeat(64),
    document_sha256: "c".repeat(64),
    quote: "Nombre documental de prueba",
    location: "texto/linea/1",
    current: true,
    state: "APPROVED",
  };
  row.citations.push(citation);
  expect(
    adaptCommercialCoverage(data, "7518949", 6).fields.find(
      (field) => field.field === "title",
    )?.state,
  ).toBe("APPROVED_BACKED");
  citation.current = false;
  expect(() => adaptCommercialCoverage(data, "7518949", 6)).toThrow();
  citation.current = true;
  citation.state = "PENDING";
  expect(() => adaptCommercialCoverage(data, "7518949", 6)).toThrow();
});
test("rights citations are distinct from factual claims and retain original hash", () => {
  const data = coverage();
  data.states.APPROVED_BACKED = 1;
  data.states.PENDING_REVIEW = 17;
  const row = data.fields.find((field) => field.field === "media")!;
  row.state = "APPROVED_BACKED";
  row.filled = true;
  const citation = {
    evidence_kind: "MEDIA_RIGHTS",
    fact_id: null,
    document_id: "synthetic-licence",
    document_version: 1,
    document_hash: "b".repeat(64),
    document_sha256: "c".repeat(64),
    quote: "Autorización comercial sintética",
    location: "texto/linea/10",
    current: true,
    state: "APPROVED",
  };
  row.citations.push(citation);
  expect(
    adaptCommercialCoverage(data, "7518949", 6).fields.find(
      (field) => field.field === "media",
    )?.citations[0].fact_id,
  ).toBeNull();
  citation.evidence_kind = "FACT";
  expect(() => adaptCommercialCoverage(data, "7518949", 6)).toThrow();
});
