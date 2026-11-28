import { test, expect, type Page } from "@playwright/test";

// Actual private HTTPS → FastAPI → PostgreSQL. No fulfilled API responses.
// The fixture originals/approvals are explicitly synthetic; field decisions
// below are real browser clicks and persist through the existing editor.
test.skip(process.env.KIKI_STAGE4_SCENARIO !== "synthetic-commercial", "Requiere --stage4 aislado; nunca producción");
test.setTimeout(180000);
test.use({ actionTimeout: 20000 });
const ids = Array.from({ length: 20 }, (_, index) => String(9104001 + index));
const root = "/api/ecomm-app/workspace";
const url = (id: string) => `${root}/${id}`;
async function get(page: Page, path: string) {
  const r = await page.request.get(path, { headers: { "X-Kiki-UI": "v2" } });
  expect(r.status(), await r.text()).toBe(200);
  return r.json();
}
async function post(page: Page, path: string, data: unknown) {
  const auth = await get(page, "/api/auth/me");
  const r = await page.request.post(path, { data, headers: { "X-CSRF-Token": auth.csrf_token, "X-Kiki-UI": "v2" } });
  expect(r.status(), await r.text()).toBe(200);
  return r.json();
}
async function generate(page: Page, selected: string[]) {
  for (const id of selected) {
    const current = await get(page, url(id));
    await post(page, url(id) + "/proposals/generate", { expected_version: current.version });
  }
}
async function select(page: Page, selected: string[]) {
  if (selected.length === 20) {
    await page.locator("#integration-search").fill("Semillas sintéticas E4");
    await page.getByRole("button", { name: "Buscar", exact: true }).click();
    await page.getByLabel("Variantes por página", { exact: true }).selectOption("25");
    await expect(page.locator("[data-ecomm-id]")).toHaveCount(20);
    await page.getByRole("button", { name: "Seleccionar esta página", exact: true }).click();
  } else {
    for (const id of selected) {
      await page.locator("#integration-search").fill(id);
      await page.getByRole("button", { name: "Buscar", exact: true }).click();
      await page.locator(`[data-ecomm-id="${id}"]`).getByRole("checkbox").check();
    }
  }
  await expect(page.getByTestId("selected-count")).toHaveText(`${selected.length} variantes seleccionadas`);
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
}
async function compare(page: Page, selected: string[]) {
  const panel = page.getByLabel("Revisión comercial por lotes", { exact: true });
  await panel.locator("summary").first().click();
  const pending = page.waitForResponse(r => r.url().endsWith("/commercial-review/preview") && r.request().method() === "POST");
  await panel.getByRole("button", { name: `Comparar propuestas de ${selected.length} variantes`, exact: true }).click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(200);
  const preview = await response.json();
  expect(preview.total).toBe(selected.length);
  expect(preview.internal_only).toBe(true);
  expect(preview.external_writes_enabled).toBe(false);
  expect(preview.items.map((r: { ecomm_id: string }) => r.ecomm_id).sort()).toEqual([...selected].sort());
  for (const id of selected) {
    const row = panel.getByTestId(`commercial-review-${id}`);
    await row.locator("summary").first().click();
    await row.getByLabel(`Decisión title ${id}`, { exact: true }).selectOption("ACCEPTED");
  }
  await panel.getByRole("checkbox", { name: "Revisé los valores y sus citas. Confirmo estas decisiones y el guardado exclusivo como borrador interno.", exact: true }).check();
  return { panel, preview };
}
test.beforeEach(async ({ page, context }) => {
  await context.route("**/*", route => {
    const target = new URL(route.request().url());
    if (target.origin !== "https://127.0.0.1:8443") throw new Error("Salida fuera del entorno aislado");
    if (/\/sync$|\/generate-ai$|\/auth-url$|\/manual\/start$|\/import-csv$/.test(target.pathname)) throw new Error("Operación productiva prohibida");
    return route.continue();
  });
  await page.goto("/v2/");
  await page.getByLabel("Usuario", { exact: true }).fill("operador-prueba");
  await page.getByLabel("Contraseña", { exact: true }).fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("30");
});

test("20 variantes: revisión humana → borradores versionados sin transferir hechos ni sobrescribir campos", async ({ page }, info) => {
  const before = new Map<string, any>(), evidence = new Map<string, any>();
  for (const id of ids) {
    before.set(id, await get(page, url(id)));
    evidence.set(id, await get(page, url(id) + "/evidence"));
  }
  await generate(page, ids);
  await select(page, ids);
  const { panel, preview } = await compare(page, ids);
  const pending = page.waitForResponse(r => r.url().endsWith("/commercial-review/apply") && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Guardar selección revisada como borrador", exact: true }).click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(200);
  const result = await response.json();
  expect(result.total).toBe(20);
  expect(result.items.every((r: { state: string }) => r.state === "SAVED_DRAFT")).toBe(true);
  await expect(panel.getByRole("status")).toContainText("20 variantes revisadas");
  await page.evaluate(() => window.scrollTo(0, 0));
  await panel.getByRole("status").scrollIntoViewIfNeeded();
  await page.screenshot({ path: `artifacts/integral-commercial-review-${info.project.name}.png`, fullPage: false });
  for (const id of ids) {
    const after = await get(page, url(id));
    const proposal = preview.items.find((r: { ecomm_id: string }) => r.ecomm_id === id);
    expect(after.fields.title).toEqual(proposal.fields.title.value);
    expect(after.status).toBe("DRAFT");
    for (const key of Object.keys(before.get(id).fields).filter(k => k !== "title")) expect(after.fields[key]).toEqual(before.get(id).fields[key]);
    expect(after.version).toBeGreaterThanOrEqual(before.get(id).version);
    expect((await get(page, url(id) + "/evidence")).facts).toEqual(evidence.get(id).facts);
    expect(after.history.length).toBeGreaterThanOrEqual(before.get(id).history.length);
  }
});

test("una edición concurrente devuelve 409 y no modifica ninguna otra variante seleccionada", async ({ page }) => {
  const selected = ids.slice(0, 2);
  await generate(page, selected);
  await select(page, selected);
  const { panel } = await compare(page, selected);
  const first = await get(page, url(selected[0])), second = await get(page, url(selected[1]));
  await post(page, url(selected[0]), { expected_version: first.version, status: "DRAFT", fields: { ...first.fields, note: first.fields.note + " · intervención concurrente de prueba" } });
  const pending = page.waitForResponse(r => r.url().endsWith("/commercial-review/apply") && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Guardar selección revisada como borrador", exact: true }).click();
  expect((await pending).status()).toBe(409);
  const firstAfter = await get(page, url(selected[0])), secondAfter = await get(page, url(selected[1]));
  expect(firstAfter.version).toBe(first.version + 1);
  expect(firstAfter.fields.title).toEqual(first.fields.title);
  expect(firstAfter.fields.note).toContain("intervención concurrente");
  expect(secondAfter.version).toBe(second.version);
  expect(secondAfter.fields).toEqual(second.fields);
});

test("caso incompleto conserva DRAFT v6 y cinco pestañas; pack y GTIN compartidos no heredan decisiones", async ({ page }) => {
  const incomplete = await get(page, url("7518949"));
  expect(incomplete.version).toBe(6);
  expect(incomplete.status).toBe("DRAFT");
  const evidence = await get(page, url("7518949") + "/evidence");
  expect(evidence.facts.filter((f: { state: string }) => f.state === "APPROVED")).toHaveLength(3);
  const permission = await get(page, url("7518949") + "/media-review");
  expect(permission.entries).toHaveLength(1);
  expect(permission.entries[0].stage4_ready).toBe(false);
  expect(permission.entries[0].state).toBe("NO_PERMISSION");
  await page.locator("#integration-search").fill("7518949");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await page.locator('[data-ecomm-id="7518949"]').getByRole("button", { name: "Ver ficha", exact: true }).click();
  for (const tab of ["Ficha", "Evidencias", "IA", "Canales", "Historial"]) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(page.getByRole("tab", { name: tab, exact: true })).toHaveAttribute("aria-selected", "true");
  }
  for (const id of ["9104091", "9104092", "9104093"]) {
    const variant = await get(page, url(id));
    expect(variant.ecomm_id).toBe(id);
    expect(variant.status).toBe("DRAFT");
    expect(variant.fields.title).toBe("");
  }
  const after = await get(page, url("7518949"));
  expect(after.version).toBe(6);
  expect(after.fields).toEqual(incomplete.fields);
});

test("imagen y video: permisos humanos con cita exacta, revocación y cero descarga remota", async ({ page }) => {
  const id = "9104001";
  await page.locator("#integration-search").fill(id);
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await page.locator(`[data-ecomm-id="${id}"]`).getByRole("button", { name: "Ver ficha", exact: true }).click();
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  const panel = page.getByRole("region", { name: "Revisión de imágenes y videos", exact: true });
  await expect(panel.getByRole("button", { name: "Actualizar registro multimedia", exact: true })).toBeEnabled();
  for (const index of [0, 1]) {
    const registry = await get(page, url(id) + "/media-review");
    const entry = registry.entries[index];
    const document = registry.documents.find((doc: { source_url: string }) => doc.source_url === entry.source_url);
    const citation = document.sections.find((part: { text: string }) => part.text.includes(entry.url));
    expect(citation).toBeTruthy();
    await panel.getByRole("combobox", { name: "Recurso multimedia a revisar", exact: true }).selectOption(String(index));
    const details = panel.locator("details").filter({ has: page.locator("summary", { hasText: /^Revisar permiso de este recurso$/ }) });
    if ((await details.getAttribute("open")) === null) await details.locator("summary").click();
    await panel.getByRole("combobox", { name: "Documento del permiso", exact: true }).selectOption(document.id);
    await panel.getByRole("combobox", { name: "Ubicación de la cita del permiso", exact: true }).selectOption(citation.location);
    await panel.getByLabel("Vencimiento del permiso (opcional)", { exact: true }).fill("2030-12-31T00:00");
    await panel.getByLabel("Justificación de la decisión multimedia", { exact: true }).fill("Revisión humana explícita del original sintético y del recurso exacto de esta variante para ensayo aislado.");
    await panel.getByRole("checkbox", { name: "Revisé la identidad y el permiso citado para este recurso", exact: true }).check();
    const pending = page.waitForResponse(r => r.url().endsWith("/media-rights") && r.request().method() === "POST");
    await panel.getByRole("button", { name: "Aprobar permiso de este recurso", exact: true }).click();
    const response = await pending;
    expect(response.status()).toBe(200);
    await expect(panel.getByRole("region", { name: "Estado del recurso multimedia", exact: true }).getByRole("status")).toContainText("Permiso vigente");
    expect((await get(page, url(id) + "/media-review")).entries[index].stage4_ready).toBe(true);
  }
  // Revoking the selected video must preserve the independent image grant.
  await panel.getByLabel("Justificación de la decisión multimedia", { exact: true }).fill("Revocación humana de prueba del video, conservando el permiso independiente de la imagen.");
  const pending = page.waitForResponse(r => r.url().endsWith("/media-rights") && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Revocar permiso de este recurso", exact: true }).click();
  expect((await pending).status()).toBe(200);
  const final = await get(page, url(id) + "/media-review");
  expect(final.remote_resources_loaded).toBe(0);
  expect(final.entries[0].state).toBe("APPROVED_CURRENT");
  expect(final.entries[1].state).toBe("REVOKED");
  expect(final.entries[1].stage4_ready).toBe(false);
});

test("clasificación: vocabulario versionado y 20 decisiones humanas sin escribir fichas ni canales", async ({ page }) => {
  const versions = new Map<string, number>();
  for (const id of ids) versions.set(id, (await get(page, url(id))).version);
  await select(page, ids);
  const panel = page.getByRole("region", { name: "Clasificación por lotes", exact: true });
  await panel.getByText("Vocabulario interno y equivalencias por canal", { exact: true }).click();
  await panel.getByRole("button", { name: "Recuperar vocabulario", exact: true }).click();
  let catalog = await get(page, root + "/taxonomy/catalog");
  if (!catalog.entries.length) {
    await panel.getByRole("button", { name: "Agregar categoría y subcategoría", exact: true }).click();
    await panel.getByLabel("Categoría 1", { exact: true }).fill("Dietética sintética");
    await panel.getByLabel("Subcategoría 1", { exact: true }).fill("Semillas de ensayo");
    await panel.getByLabel("Nombre de la nueva revisión", { exact: true }).fill("Vocabulario ficticio de aceptación offline");
    await panel.getByLabel("Motivo del cambio de vocabulario", { exact: true }).fill("Definición humana de pares internos exclusivamente sintéticos para aceptación; no representa una categoría oficial de canal.");
    await panel.getByRole("checkbox", { name: "Revisé los pares internos y las equivalencias declaradas.", exact: true }).check();
    const pending = page.waitForResponse(r => r.url().endsWith("/taxonomy/catalog") && r.request().method() === "POST");
    await panel.getByRole("button", { name: "Guardar nueva versión del vocabulario", exact: true }).click();
    const response = await pending;
    expect(response.status(), await response.text()).toBe(200);
    catalog = await get(page, root + "/taxonomy/catalog");
  }
  const pair = catalog.entries.find((entry: { category: string; subcategory: string; state: string }) => entry.category === "Dietética sintética" && entry.subcategory === "Semillas de ensayo" && entry.state === "ACTIVE");
  expect(pair).toBeTruthy();
  await panel.getByRole("button", { name: "Revisar clasificación de 20 variantes", exact: true }).click();
  for (const id of ids) {
    const row = panel.locator(`[data-taxonomy-ecomm="${id}"]`);
    await row.locator("summary").first().click();
    await row.getByRole("combobox", { name: "Decisión", exact: true }).selectOption("APPROVED");
    await row.getByRole("combobox", { name: "Par interno KIKI", exact: true }).selectOption(pair.id);
    await row.getByRole("checkbox", { name: "Revisé esta variante, su presentación y sus citas.", exact: true }).check();
  }
  await panel.getByLabel("Motivo de las decisiones seleccionadas", { exact: true }).fill("Revisé manualmente las presentaciones y citas sintéticas de las veinte variantes; no se aprueban equivalencias oficiales externas.");
  await panel.getByRole("checkbox", { name: /^Confirmo las 20 decisiones/ }).check();
  const pending = page.waitForResponse(r => r.url().endsWith("/taxonomy/review-batch") && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Guardar revisiones seleccionadas", exact: true }).click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(200);
  await expect(panel).toContainText("20 decisiones guardadas en el historial");
  for (const id of ids) expect((await get(page, url(id))).version).toBe(versions.get(id));
});
