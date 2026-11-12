declare const __KIKI_PRODUCTION__: boolean;
export const production =
  typeof __KIKI_PRODUCTION__ !== "undefined" && __KIKI_PRODUCTION__ === true;
export type Capabilities = {
  contract: "kiki-same-origin-v2-1";
  synthetic: boolean;
  enabled: boolean;
  writes: boolean;
  connections: boolean;
  documents: boolean;
  document_upload: boolean;
  channels: boolean;
  batches: boolean;
  executor: boolean;
  openai_configured: boolean;
  openai_generation: boolean;
  evidence_openai_generation: false;
  external_research: false;
  legacy_path: "/dashboard-classic";
  missing_schema: { core: string[]; documents: string[]; batches: string[] };
};
export let capabilities: Capabilities | undefined;
export function configureRuntime(value?: unknown) {
  if (value === undefined) {
    capabilities = undefined;
    return;
  }
  const c = value as Capabilities;
  if (
    !c ||
    c.contract !== "kiki-same-origin-v2-1" ||
    c.enabled !== true ||
    c.legacy_path !== "/dashboard-classic" ||
    c.external_research !== false ||
    c.evidence_openai_generation !== false ||
    [
      c.synthetic,
      c.writes,
      c.connections,
      c.documents,
      c.document_upload,
      c.channels,
      c.batches,
      c.executor,
      c.openai_configured,
      c.openai_generation,
    ].some((v) => typeof v !== "boolean") ||
    !c.missing_schema ||
    !Array.isArray(c.missing_schema.core) ||
    c.missing_schema.core.length !== 0 ||
    !Array.isArray(c.missing_schema.documents) ||
    !Array.isArray(c.missing_schema.batches)
  )
    throw new Error(
      "Configuración 2.0 incompatible; no se cargaron datos alternativos.",
    );
  capabilities = c;
}
export const canWrite = () => !production || capabilities?.writes === true;
export const availableFeature = (
  feature: "documents" | "channels" | "batches",
) => !production || capabilities?.[feature] === true;
export const environmentText = (isolated: string, connected: string) =>
  production ? connected : isolated;
