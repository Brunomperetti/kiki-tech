import { test, expect, type Page } from "@playwright/test";

test.skip(process.env.KIKI_STAGE4_SCENARIO !== "synthetic-commercial", "Requiere automatización offline en PostgreSQL descartable");
test.setTimeout(180000);
test.use({ actionTimeout: 20000 });
const endpoint = "/api/ecomm-app/workspace/research/automation";
const workspace = (id: string) => `/api/ecomm-app/workspace/${id}`;
async function read(page: Page, path: string) {
  const response = await page.request.get(path, { headers: { "X-Kiki-UI": "v2" } });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}
async function search(page: Page, text: string) {
  await page.locator("#integration-search").fill(text);
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
}
async function operate(page: Page, count: number) {
  await expect(page.getByTestId("selected-count")).toHaveText(`${count} variantes seleccionadas`);
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  const panel = page.getByLabel("Investigar y completar productos", { exact: true });
  await panel.locator("summary").first().click();
  await panel.getByRole("button", { name: "Comprobar disponibilidad y recuperar lotes", exact: true }).click();
  await expect(panel).toContainText("configurado");
  await panel.getByRole("checkbox", { name: `Autorizo investigar estas ${count} variantes con los proveedores y límites configurados. Revisaré las excepciones y los campos antes de guardarlos.`, exact: true }).check();
  const pending = page.waitForResponse(response => response.url().endsWith(endpoint) && response.request().method() === "POST");
  await panel.getByRole("button", { name: `Investigar y completar ${count} productos`, exact: true }).click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(200);
  const job = await response.json();
  return { panel, job };
}
test.beforeEach(async ({ page, context }) => {
  await context.route("**/*", route => {
    const target = new URL(route.request().url());
    if (target.origin !== "https://127.0.0.1:8443") throw new Error("No se permite transporte externo en aceptación");
    if (/\/generate-ai$|\/sync$|\/auth-url$|\/manual\/start$|\/import-csv$/.test(target.pathname)) throw new Error("Escritura o proveedor real no autorizado");
    return route.continue();
  });
  await page.goto("/v2/");
  await page.getByLabel("Usuario", { exact: true }).fill("operador-prueba");
  await page.getByLabel("Contraseña", { exact: true }).fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("30");
});

test("investigar desde catálogo: original y citas PENDING, sin aprobación ni escritura editorial", async ({ page }, info) => {
  const id = "900003";
  const before = await read(page, workspace(id));
  await search(page, id);
  await page.locator(`[data-ecomm-id="${id}"]`).getByRole("checkbox").check();
  const { panel, job } = await operate(page, 1);
  await expect.poll(async () => (await read(page, `${endpoint}/${job.id}`)).items[0].state, { timeout: 90000 }).not.toMatch(/^(PENDING|RUNNING)$/);
  const terminal = await read(page, `${endpoint}/${job.id}`);
  expect(terminal.items[0].state, JSON.stringify(terminal.items[0].error)).toMatch(/IMPORTED|ALREADY_PRESENT/);
  await expect(panel.getByRole("region", { name: "Resultado de investigación", exact: true })).toContainText("1 / 1 pasos resueltos");
  const result = await read(page, `${endpoint}/${job.id}`);
  expect(result.automatic_fact_approvals).toBe(0);
  expect(result.commercial_fields_saved).toBe(0);
  expect(result.external_writes_enabled).toBe(false);
  expect(result.paid_ai_enabled).toBe(false);
  expect(result.search_requests).toBeLessThanOrEqual(1);
  expect(result.items[0].automation.official_verified).toBe(false);
  const evidence = await read(page, workspace(id) + "/evidence");
  expect(evidence.documents.length).toBeGreaterThan(0);
  expect(evidence.facts.length).toBeGreaterThan(0);
  expect(evidence.facts.every((fact: { state: string; document_id: string; quote: string; location: string }) => fact.state === "PENDING" && fact.document_id && fact.quote && fact.location)).toBe(true);
  const after = await read(page, workspace(id));
  expect(after.version).toBe(before.version);
  expect(after.fields).toEqual(before.fields);
  await page.screenshot({ path: `artifacts/integral-documentary-research-${info.project.name}.png`, fullPage: true });
  await panel.getByRole("button", { name: "Revisar evidencia y propuesta", exact: true }).click();
  await expect(page.getByRole("tab", { name: "IA", exact: true })).toBeVisible();
});

test("20 fuentes archivadas: reutilización sin búsquedas, límites persistentes y recuperación sin duplicar originales", async ({ page }) => {
  const ids = Array.from({ length: 20 }, (_, index) => String(9104001 + index));
  const originals = new Map<string, string[]>();
  const versions = new Map<string, number>();
  for (const id of ids) {
    const evidence = await read(page, workspace(id) + "/evidence");
    originals.set(id, evidence.documents.map((doc: { id: string }) => doc.id).sort());
    versions.set(id, (await read(page, workspace(id))).version);
  }
  await search(page, "Semillas sintéticas E4");
  await page.getByLabel("Variantes por página", { exact: true }).selectOption("25");
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(20);
  await page.getByRole("button", { name: "Seleccionar esta página", exact: true }).click();
  const { panel, job } = await operate(page, 20);
  await expect.poll(async () => (await read(page, `${endpoint}/${job.id}`)).items.filter((row: { state: string }) => ["PENDING", "RUNNING"].includes(row.state)).length, { timeout: 120000 }).toBe(0);
  const result = await read(page, `${endpoint}/${job.id}`);
  expect(result.total).toBe(20);
  expect(result.search_requests).toBe(0);
  expect(result.automatic_fact_approvals).toBe(0);
  expect(result.commercial_fields_saved).toBe(0);
  expect(result.items.every((row: { state: string }) => ["IMPORTED", "ALREADY_PRESENT"].includes(row.state))).toBe(true);
  await expect(panel.getByRole("button", { name: "Recuperar interrupciones", exact: true })).toBeEnabled();
  const pending = page.waitForResponse(response => response.url().endsWith(`/${job.id}/recover`) && response.request().method() === "POST");
  await panel.getByRole("button", { name: "Recuperar interrupciones", exact: true }).click();
  const recovery = await pending;
  // A completed job has no expired lease: recovery must reject replay.
  expect(recovery.status(), await recovery.text()).toBe(409);
  for (const id of ids) {
    const evidence = await read(page, workspace(id) + "/evidence");
    expect(evidence.documents.map((doc: { id: string }) => doc.id).sort()).toEqual(originals.get(id));
    expect((await read(page, workspace(id))).version).toBe(versions.get(id));
  }
});
