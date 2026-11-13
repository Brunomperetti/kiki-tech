import { request, type Variant } from "./catalog-adapter";
import type { EcommEditableFields } from "../types/ecomm-app";
export const mamaPilotId = "PILOT-MAMA-350-SYNTHETIC";
export const mamaPilotPath = "/api/test-commercial-pilot/mama-350";
export type MamaReport = {
  available: boolean;
  test_id: string;
  authentic_ecomm_id: null;
  test_id_is_synthetic: true;
  binding_status: "PENDING";
  network_enabled: false;
  variant: Variant;
  approved_fact_count: number;
  workspace_version: number;
  initial_fields: EcommEditableFields;
  current_fields: EcommEditableFields;
  blocked_fields: string[];
  references: {
    excel: {
      file_name: string;
      sheet_name?: string;
      original_file_sha256?: string | null;
      cells?: Record<string, string>;
      external_verification?: {
        scope: "EXTERNAL_TO_CODEX";
        verified_in_codex: false;
        status: string;
      };
      row: number;
      source: string;
      name: string;
      brand: string;
      declared_ean: string;
      ean_checksum_valid: boolean;
      file_sku: string;
      declared_presentation: string;
      declared_width: string;
      logistic_weight: string;
    };
    manufacturer_candidate: {
      manufacturer: string;
      url: string;
      catalog_item_reported: string;
      source: string;
    };
    third_party_candidate?: {
      classification: "NON_OFFICIAL";
      site_name: string;
      url: string;
      reported_ean: string;
      reported_entries: string[];
      source: string;
      reported_claim: string;
    };
    missing_evidence: string[];
  };
};
export async function loadMama(
  signal?: AbortSignal,
  csrf?: string,
): Promise<MamaReport> {
  const r = await request(
    mamaPilotPath + (csrf ? "/prepare" : ""),
    csrf
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: "{}",
        }
      : { signal },
  );
  const data = (await r.json()) as MamaReport;
  if (
    data.test_id !== mamaPilotId ||
    data.network_enabled !== false ||
    (data.available &&
      (data.authentic_ecomm_id !== null ||
        data.test_id_is_synthetic !== true ||
        data.variant.id !== mamaPilotId ||
        data.variant.gtin !== null))
  )
    throw new Error(
      "El piloto no acredita su identidad de pruebas; no se vinculó a Ecomm-App.",
    );
  return data;
}
