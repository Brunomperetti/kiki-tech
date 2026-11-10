import { CatalogError, request } from "./catalog-adapter";
export type AssistedCandidate = {
  id: string;
  source_id: string;
  title: string;
  kind: string;
  url: string;
  priority: number;
  declared_official: boolean;
  simulated: true;
  version: number;
  decision: string;
  document_id: string | null;
  identity_state: string;
  provenance_state: string;
  comparisons: Record<
    string,
    {
      expected: string | boolean | null;
      found: string | boolean | null;
      status: string;
    }
  >;
  history: {
    at: string;
    actor: string;
    decision: string;
    reason?: string;
    version: number;
    document_id?: string;
  }[];
};
export type AssistedRun = {
  run_id: string;
  ecomm_id: string;
  state: string;
  current: boolean;
  created_at: string;
  actor: string;
  simulated_only: true;
  network_enabled: false;
  stale_reason?: string;
  candidates: AssistedCandidate[];
  query_context: {
    query: Record<string, string | boolean | null>;
    provenance: Record<string, string>;
    workspace_version: number;
    missing: string[];
    hash: string;
  };
  search_trace: Record<string, unknown>;
};
export type ResearchFact = {
  id: string;
  ecomm_id: string;
  field: string;
  commercial_field: string;
  label: string;
  value: string;
  unit: string | null;
  presentation: string;
  location: string;
  quote: string;
  document_id: string;
  document_version: number;
  document_hash: string;
  consulted_at: string;
  state: "PENDING" | "APPROVED" | "REJECTED" | "REVOKED" | "STALE";
  version: number;
  reviewer: string | null;
  reviewed_at: string | null;
  provenance: string;
  blockers: string[];
  verified: boolean;
  history: {
    at: string;
    actor: string;
    action: string;
    reason: string;
    version: number;
    before: Record<string, unknown>;
    after: Record<string, unknown>;
  }[];
};
export type ResearchDocument = {
  id: string;
  version: number;
  hash: string;
  versions: number[];
  issues: string[];
  body: {
    title: string;
    kind: string;
    synthetic: boolean;
    origin_kind?: "FILE" | "URL";
    retrieval?: {
      simulated: true;
      network_enabled: false;
      requested_url: string;
      final_url: string;
      acquired_at: string;
      sha256: string;
      hops: unknown[];
    };
    associated_ecomm_id?: string;
    parse_status?: string;
    parser_warnings?: string[];
    original?: {
      filename: string | null;
      content_type: string | null;
      size: number;
      sha256: string;
    };
    source?: {
      declared_manufacturer?: string | null;
      declared_consulted_at?: string | null;
      declared_official: boolean;
      note: string;
      reference_url: string;
      registered_at: string;
      registered_by: string;
      review_state: string;
      reviewer: string | null;
      reviewed_at: string | null;
      review_reason: string | null;
    };
    provenance: string;
    identity: Record<string, string>;
    sections: Record<string, string>;
    identity_evidence?: Record<
      string,
      { value: string; location: string; quote: string }
    >;
  };
  history: {
    at: string;
    actor: string;
    version: number;
    action?: string;
    body: ResearchDocument["body"];
  }[];
};
export type Dossier = {
  assisted?: AssistedRun | null;
  ecomm_id: string;
  version: number;
  identity: Record<string, string | null> & {
    provenance: Record<string, string>;
  };
  facts: ResearchFact[];
  missing: string[];
  documents: ResearchDocument[];
  history: {
    at: string;
    actor: string;
    version: number;
    action: string;
    detail: unknown;
  }[];
  synthetic_only: boolean;
  isolated_only: true;
  incorporated_document_id?: string;
  commercial_fields_applied: false;
  external_writes_enabled: false;
};
export const researchPath = (id: string) => `/api/test-research/${id}`;
export const evidenceLabels = {
  PENDING: "Pendiente de revisión",
  APPROVED: "Aprobada",
  REJECTED: "Rechazada",
  REVOKED: "Verificación revocada",
  STALE: "Verificación invalidada",
};
function adapt(value: unknown, id: string): Dossier {
  const data = value as Dossier;
  if (
    !data ||
    data.ecomm_id !== id ||
    data.isolated_only !== true ||
    data.commercial_fields_applied !== false ||
    data.external_writes_enabled !== false ||
    !Number.isSafeInteger(data.version) ||
    !Array.isArray(data.facts) ||
    !Array.isArray(data.documents) ||
    !Array.isArray(data.history) ||
    !Array.isArray(data.missing) ||
    (data.assisted &&
      (data.assisted.ecomm_id !== id ||
        data.assisted.simulated_only !== true ||
        data.assisted.network_enabled !== false ||
        !Array.isArray(data.assisted.candidates) ||
        data.assisted.candidates.some(
          (c) => c.simulated !== true || !/^[a-f0-9]{24}$/.test(c.id),
        ))) ||
    data.facts.some(
      (f) =>
        f.ecomm_id !== id ||
        !/^[a-f0-9]{24}$/.test(f.id) ||
        !Number.isSafeInteger(f.version) ||
        typeof f.verified !== "boolean" ||
        !Object.keys(evidenceLabels).includes(f.state) ||
        !Array.isArray(f.blockers),
    ) ||
    data.documents.some(
      (d) =>
        !(
          d.body.synthetic === true &&
          d.body.provenance.startsWith("fixture://")
        ) &&
        !(
          d.body.synthetic === false &&
          d.body.associated_ecomm_id === id &&
          /^local-[a-f0-9]{32}$/.test(d.id) &&
          d.body.provenance.startsWith("local://sha256/") &&
          !!d.body.original &&
          !!d.body.source
        ),
    )
  )
    throw new CatalogError(
      0,
      "La respuesta de investigación no acredita el contrato sintético. No se sustituyeron evidencias.",
    );
  return data;
}
export async function loadResearch(id: string, signal?: AbortSignal) {
  return adapt(await (await request(researchPath(id), { signal })).json(), id);
}
export async function changeResearch(
  id: string,
  path: string,
  body: unknown,
  csrf: string,
) {
  return adapt(
    await (
      await request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify(body),
      })
    ).json(),
    id,
  );
}
