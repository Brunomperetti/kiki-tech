import { test, expect, type Page } from "@playwright/test";

test.skip(process.env.KIKI_PRODUCTION_COMPAT !== "isolated-only", "Transporte documental sintético sin proveedores");
test.setTimeout(60000);
const endpoint = "/api/ecomm-app/workspace/sources/intake-jobs";
const jobId = "00000000-0000-4000-8000-000000000088";
const states = ["PENDING", "RUNNING", "IMPORTED", "ALREADY_PRESENT", "BLOCKED", "CANCELLED"];
type Item = { ecomm_id: string; url: string; state: string; attempts: number; document_id: string | null; error: string | null; next_action: string; recoverable: boolean; retry_available: boolean };
function syntheticJob(items?: Item[], revision = 2) {
  const selected = items || ["900001", "900002"].map(ecomm_id => ({ ecomm_id, url: `https://fabricante-prueba.invalid/${ecomm_id}`, state: "PENDING", attempts: 0, document_id: null, error: null, next_action: "INCORPORATE", recoverable: false, retry_available: false }));
  const counts = Object.fromEntries(states.map(state => [state, selected.filter(item => item.state === state).length]));
  return {
    mode: "MANUAL_RESUMABLE_SOURCE_INTAKE", id: jobId, revision,
    state: counts.BLOCKED ? "NEEDS_REVIEW" : counts.PENDING ? "PENDING" : "COMPLETED",
    total: selected.length, counts,
    coverage: { total_variants: selected.length, documents_recorded: counts.IMPORTED + counts.ALREADY_PRESENT, without_recorded_document: counts.PENDING + counts.RUNNING + counts.BLOCKED, cancelled: counts.CANCELLED, completed_steps: counts.IMPORTED + counts.ALREADY_PRESENT + counts.CANCELLED, facts_approved_by_operation: 0, commercial_fields_saved: 0 },
    items: selected, recoverable_items: 0, max_attempts: 3, selection_mode: "EXACT_OPERATOR_URL", sitemap_url: "", source_host: "fabricante-prueba.invalid", external_writes_enabled: false, manual_steps_only: true, claims_approved: 0, ai_requests: 0,
  };
}

async function open(page: Page) {
  await page.goto("/v2/");
  await page.getByLabel("Usuario", { exact: true }).fill("operador-prueba");
  await page.getByLabel("Contraseña", { exact: true }).fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
}

for (const scenario of ["complete", "blocked", "conflict", "network", "pause", "close", "off"] as const) {
  test(`lote autorizado secuencial: ${scenario}`, async ({ page }) => {
    let job = syntheticJob();
    const stepBodies: { expected_revision: number; confirm: boolean }[] = [];
    const reads: string[] = [];
    let confirmations = 0;
    let release: (() => void) | undefined;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/*", route => {
      if (new URL(route.request().url()).origin !== "https://127.0.0.1:8443")
        throw new Error("Conexión a proveedores prohibida en este test");
      return route.continue();
    });
    await page.route("**/api/ui/v2", async route => {
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...await response.json(),
        document_intake_state: true, document_resumable_intake: scenario !== "off",
        document_exact_url_manifest: false, document_batch_source_import: false,
        document_sitemap_discovery: false,
      } });
    });
    await page.route("**/api/ecomm-app/workspace/sources/intake-jobs**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (route.request().method() === "GET") {
        reads.push(path);
        if (path === endpoint) return route.fulfill({ json: { mode: job.mode, items: [job], external_writes_enabled: false } });
        if (path === `${endpoint}/${jobId}`) return route.fulfill({ json: job });
      }
      if (route.request().method() === "POST" && path === `${endpoint}/${jobId}/step`) {
        stepBodies.push(route.request().postDataJSON());
        expect(route.request().headers()["x-csrf-token"]).toBeTruthy();
        expect(stepBodies.at(-1)).toEqual({ expected_revision: job.revision, confirm: true });
        if (scenario === "conflict")
          return route.fulfill({ status: 409, json: { detail: "Conflicto sintético de otra sesión" } });
        if (scenario === "network") return route.abort("failed");
        if (["pause", "close"].includes(scenario) && stepBodies.length === 1) await gate;
        const selected = job.items.find(item => item.state === "PENDING");
        if (!selected) throw new Error("No se puede repetir una incorporación finalizada");
        job = syntheticJob(job.items.map(item => item !== selected ? item : {
          ...item, state: scenario === "blocked" && stepBodies.length === 1 ? "BLOCKED" : "IMPORTED",
          attempts: item.attempts + 1, document_id: `local-synthetic-${item.ecomm_id}`, next_action: "REVIEW_EVIDENCE",
        }), job.revision + 2);
        return route.fulfill({ json: job });
      }
      throw new Error(`No se autorizan reintentos ni otras operaciones: ${path}`);
    });
    page.on("dialog", async dialog => {
      confirmations++;
      expect(dialog.message()).toContain("fuentes PENDIENTES de fabricante-prueba.invalid");
      expect(dialog.message()).toContain("sin reintentos automáticos");
      await dialog.accept();
    });
    await open(page);
    const panel = page.getByRole("region", { name: "Fuentes de fabricantes · cola reanudable", exact: true });
    const process = panel.getByRole("button", { name: "Procesar lote autorizado", exact: true });
    await expect(panel).toContainText("Dominio revisado: fabricante-prueba.invalid");
    if (scenario === "off") {
      await expect(process).toBeDisabled();
      expect(stepBodies).toEqual([]);
      expect(confirmations).toBe(0);
      return;
    }
    await process.click();
    if (["pause", "close"].includes(scenario)) {
      await expect.poll(() => stepBodies.length).toBe(1);
      if (scenario === "pause") {
        await panel.getByRole("button", { name: "Pausar después del paso actual", exact: true }).click();
        release!();
        await expect(panel).toContainText("Lote pausado tras 1 pasos");
      } else {
        await page.getByRole("button", { name: "Cerrar lotes", exact: true }).click();
        release!();
        await expect.poll(() => job.counts.IMPORTED).toBe(1);
        await page.getByRole("button", { name: "Operaciones", exact: true }).click();
        await expect(panel).toContainText("1 de 2 incorporadas");
      }
      expect(stepBodies).toHaveLength(1);
      await process.click();
      await expect(panel).toContainText("2 de 2 incorporadas");
      expect(confirmations).toBe(2);
      // Each resume performed a fresh detail read and used the committed CAS.
      expect(reads.filter(path => path === `${endpoint}/${jobId}`).length).toBe(2);
      expect(stepBodies.map(body => body.expected_revision)).toEqual([2, 4]);
    } else if (["conflict", "network"].includes(scenario)) {
      await expect(panel.getByRole("alert")).toBeVisible();
      await expect(process).toBeEnabled();
      expect(stepBodies).toHaveLength(1);
      expect(confirmations).toBe(1);
      expect(job.counts.IMPORTED).toBe(0);
    } else {
      await expect(panel).toContainText(scenario === "blocked" ? "1 de 2 incorporadas" : "2 de 2 incorporadas");
      await expect(process).toBeDisabled();
      expect(stepBodies).toHaveLength(2);
      expect(confirmations).toBe(1);
      expect(job.counts.BLOCKED).toBe(scenario === "blocked" ? 1 : 0);
      expect(stepBodies.map(body => body.expected_revision)).toEqual([2, 4]);
    }
  });
}
