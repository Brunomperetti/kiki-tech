import { test, expect } from "@playwright/test";

// UI transport responses below are explicitly synthetic. Genuine local
// persistence/auth/CSRF and CAS are exercised by test_documental_intake_recovery.
test.skip(
  process.env.KIKI_PRODUCTION_COMPAT !== "isolated-only",
  "Sólo navegador privado de compatibilidad con backend descartable",
);

const endpoint = "/api/ecomm-app/workspace/sources/intake-jobs";
const contractHeaders = {
  "Content-Type": "application/json",
  "X-Kiki-UI-Contract": "kiki-same-origin-v2-1",
};
const id = "00000000-0000-4000-8000-000000000099";
function report(recoverable: boolean) {
  return {
    mode: "MANUAL_RESUMABLE_SOURCE_INTAKE",
    id,
    revision: 2,
    state: "RUNNING",
    total: 2,
    counts: { PENDING: 1, RUNNING: 1, IMPORTED: 0, ALREADY_PRESENT: 0, BLOCKED: 0, CANCELLED: 0 },
    coverage: { total_variants: 2, documents_recorded: 0, without_recorded_document: 2, cancelled: 0, completed_steps: 0, facts_approved_by_operation: 0, commercial_fields_saved: 0 },
    recoverable_items: recoverable ? 1 : 0,
    max_attempts: 3,
    selection_mode: "EXACT_OPERATOR_URL",
    sitemap_url: "",
    source_host: "fabricante-prueba.invalid",
    external_writes_enabled: false,
    manual_steps_only: true,
    claims_approved: 0,
    ai_requests: 0,
    items: [
      { ecomm_id: "900001", url: "https://fabricante-prueba.invalid/almendras", state: "RUNNING", attempts: 1, document_id: null, error: null as string | null, next_action: "WAIT", claim_until: "2026-11-01T12:00:00Z", recoverable, retry_available: false },
      { ecomm_id: "900002", url: "https://fabricante-prueba.invalid/avena", state: "PENDING", attempts: 0, document_id: null, error: null as string | null, next_action: "INCORPORATE", recoverable: false, retry_available: false },
    ],
  };
}

for (const recoverable of [true, false]) {
  test(`recuperación local con descargas apagadas, plazo ${recoverable ? "vencido" : "activo"}`, async ({ page }, info) => {
    let job = report(recoverable);
    const posts: string[] = [];
    await page.route("**/*", route => {
      if (new URL(route.request().url()).origin !== "https://127.0.0.1:8443")
        throw new Error("Prueba sin conexiones externas");
      if (route.request().method() !== "GET") posts.push(new URL(route.request().url()).pathname);
      return route.continue();
    });
    await page.route("**/api/ui/v2", async route => {
      const response = await route.fetch();
      const config = await response.json();
      await route.fulfill({ response, json: {
        ...config, document_intake_state: true, document_resumable_intake: false,
        document_exact_url_manifest: false, document_batch_source_import: false,
        document_sitemap_discovery: false,
      } });
    });
    await page.route("**/api/ecomm-app/workspace/sources/intake-jobs**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (route.request().method() === "GET" && path === endpoint)
        return route.fulfill({ headers: contractHeaders, json: { mode: job.mode, items: [job], external_writes_enabled: false } });
      if (route.request().method() === "POST" && path === `${endpoint}/${id}/recover`) {
        posts.push(path);
        expect(route.request().headers()["x-csrf-token"]).toBeTruthy();
        expect(route.request().postDataJSON()).toEqual({ expected_revision: 2, confirm: true });
        job = { ...job, revision: 3, state: "NEEDS_REVIEW", recoverable_items: 0,
          counts: { ...job.counts, RUNNING: 0, BLOCKED: 1 },
          items: job.items.map((item, index) => index ? item : {
            ...item, state: "BLOCKED", recoverable: false, claim_until: undefined,
            next_action: "RETRY", retry_available: true, error: "Paso interrumpido; revisar antes de reintentar.",
          }),
        };
        return route.fulfill({ headers: contractHeaders, json: job });
      }
      throw new Error(`Operación de proveedor o reintento inesperado: ${path}`);
    });
    await page.goto("/v2/");
    await page.getByLabel("Usuario", { exact: true }).fill("operador-prueba");
    await page.getByLabel("Contraseña", { exact: true }).fill("solo-datos-sinteticos");
    await page.getByRole("button", { name: "Ingresar", exact: true }).click();
    await page.getByRole("button", { name: "Operaciones", exact: true }).click();
    const panel = page.getByRole("region", { name: "Fuentes de fabricantes · cola reanudable", exact: true });
    await expect(panel).toContainText("Descargas deshabilitadas");
    await expect(panel).toContainText("Cobertura documental: 0 de 2");
    await expect(panel.getByRole("button", { name: "Procesar siguiente fuente", exact: true })).toBeDisabled();
    const recover = panel.getByRole("button", { name: "Recuperar pasos vencidos sin descargar", exact: true });
    if (recoverable) {
      await expect(recover).toBeEnabled();
      page.once("dialog", dialog => dialog.accept());
      await recover.click();
      await expect(panel).toContainText("NEEDS_REVIEW");
      await expect(recover).toBeDisabled();
      await expect(panel).toContainText("intentos 0");
      await expect(panel.getByRole("button", { name: "Reintentar esta fuente", exact: true })).toBeDisabled();
      expect(posts.filter(path => path.startsWith(endpoint))).toEqual([`${endpoint}/${id}/recover`]);
      await page.screenshot({ path: `artifacts/documental-recuperacion-${info.project.name}.png`, fullPage: false });
    } else {
      await expect(recover).toBeDisabled();
      await expect(panel).toContainText("no se interrumpe un paso activo");
      expect(posts.filter(path => path.startsWith(endpoint))).toEqual([]);
    }
  });
}
