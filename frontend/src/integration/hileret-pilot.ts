import { request, type Variant } from "./catalog-adapter";
import type { EcommEditableFields } from "../types/ecomm-app";
import { mamaPilotId } from "./mama-pilot";

export const hileretUnitId = "PILOT-HILERET-200-UNIT-SYNTHETIC";
export const hileretPackId = "PILOT-HILERET-200-PACK6-SYNTHETIC";
export const hileretPilotPath = "/api/test-commercial-pilot/hileret-200";
export const hileretOriginalSha =
  "bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291";
export const hileretOriginalSize = 6232081;
export const isHileret = (id: string) =>
  [hileretUnitId, hileretPackId].includes(id);
export const isAuxiliaryPilot = (id: string) =>
  id === mamaPilotId || isHileret(id);
export type HileretCase = {
  test_id: string;
  test_id_is_synthetic: true;
  authentic_ecomm_id: null;
  binding_status: "PENDING";
  variant: Variant;
  initial_fields: EcommEditableFields;
  current_fields: EcommEditableFields;
  workspace_version: number;
  approved_fact_count: number;
  ean_verified_in_test: boolean;
  logistics_verified_in_test: Record<string, string>;
  pending_evidence: string[];
  blocked_fields: string[];
  original_pdf_available: boolean;
  references: {
    excel: {
      row: number;
      name: string;
      presentation: string;
      ean_declared: string;
      source: string;
    };
    brochure: {
      url: string;
      reported_page: number;
      reported_product: string;
      reported_unit_ean: string;
      reported_unit_volume: string;
      reported_logistic_units: number;
      reported_logistic_dun: string;
      source: string;
    };
    sale_units: number;
    missing_evidence: string[];
  };
  documents: {
    id: string;
    version: number;
    kind: "FILE" | "URL";
    parse_status: string;
    original: null | {
      filename: string;
      sha256: string;
      size: number;
      content_type: string;
    };
    source_review_state: string;
    locations: string[];
    issues: string[];
  }[];
};
export type HileretReport = {
  cases: HileretCase[];
  network_enabled: false;
  external_writes_enabled: false;
  automatic_discovery_enabled: false;
};

export async function loadHileret(
  signal?: AbortSignal,
  csrf?: string,
): Promise<HileretReport> {
  const r = await request(
    hileretPilotPath + (csrf ? "/prepare" : ""),
    csrf
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: "{}",
        }
      : { signal },
  );
  const value = (await r.json()) as HileretReport;
  if (
    value.network_enabled !== false ||
    value.external_writes_enabled !== false ||
    value.automatic_discovery_enabled !== false ||
    !Array.isArray(value.cases) ||
    value.cases.length > 2 ||
    new Set(value.cases.map((c) => c.test_id)).size !== value.cases.length ||
    value.cases.some(
      (c) =>
        !isHileret(c.test_id) ||
        c.test_id_is_synthetic !== true ||
        c.authentic_ecomm_id !== null ||
        c.variant.id !== c.test_id ||
        c.variant.gtin !== null,
    )
  )
    throw new Error(
      "El expediente Hileret no acredita su identidad sintética o aislamiento.",
    );
  return value;
}
