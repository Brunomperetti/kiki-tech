import { documentalPath } from "./documental-paths";
import { CatalogError, request } from "./catalog-adapter";
import type { ResearchFact } from "./research-adapter";
import { fieldKeys } from "./workspace-adapter";
import type { EcommEditableFields } from "../types/ecomm-app";

export type ProposalField = keyof EcommEditableFields;
export type FieldValue = EcommEditableFields[ProposalField];
export type Decisions = Partial<
  Record<
    ProposalField,
    { decision: "ACCEPTED" | "REJECTED"; value: FieldValue }
  >
>;
export type Proposal = {
  available: boolean;
  synthetic_only: boolean;
  isolated_only: boolean;
  internal_only?: boolean;
  external_writes_enabled: false;
  ecomm_id: string;
  draft_id: number;
  revision: number;
  workspace_version: number;
  created_at: string;
  state: string;
  source_current: boolean;
  fields: Partial<
    Record<
      ProposalField,
      { value: FieldValue; evidence_ids: string[]; clauses: string[] }
    >
  >;
  base_fields: EcommEditableFields;
  missing: string[];
  blockers: string[];
  decisions: Decisions;
  evidence: ResearchFact[];
  authorized_facts: ResearchFact[];
  history: {
    event: string;
    at: string;
    actor?: string;
    decisions?: Decisions;
    reasons?: string[];
    selected_fields?: string[];
  }[];
};
export const proposalPath = (id: string) => documentalPath(id, "proposals");
async function read(id: string, init?: RequestInit, suffix = "") {
  const data = (await (
    await request(proposalPath(id) + suffix, init)
  ).json()) as Proposal;
  if (
    !data ||
    data.ecomm_id !== id ||
    (data.internal_only !== true && data.isolated_only !== true) ||
    data.external_writes_enabled !== false ||
    typeof data.available !== "boolean" ||
    !Array.isArray(data.authorized_facts) ||
    data.authorized_facts.some(
      (f) => f.ecomm_id !== id || f.state !== "APPROVED",
    ) ||
    (data.available &&
      (!Number.isSafeInteger(data.draft_id) ||
        !Number.isSafeInteger(data.revision) ||
        !data.fields ||
        Object.keys(data.fields).some(
          (k) => !fieldKeys.includes(k as ProposalField),
        ) ||
        !Array.isArray(data.evidence) ||
        data.evidence.some(
          (f) => f.ecomm_id !== id || f.state !== "APPROVED",
        ) ||
        !Array.isArray(data.history) ||
        !Array.isArray(data.blockers)))
  )
    throw new CatalogError(
      0,
      "La propuesta no acredita el contrato sintético. No se aplicó ningún dato.",
    );
  return data;
}
export const loadProposal = (id: string, signal?: AbortSignal) =>
  read(id, { signal });
export const mutateProposal = (
  id: string,
  suffix: string,
  body: unknown,
  csrf: string,
) =>
  read(
    id,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(body),
    },
    suffix,
  );
