import { test, expect, type Page } from "@playwright/test";

// Same-origin production bundle → authenticated FastAPI → disposable PG18.
// No mocked API responses, real provider traffic, tokens or OAuth refresh.
test.skip(process.env.KIKI_STAGE4_SCENARIO !== "synthetic-commercial", "Sólo perfil PG18 sintético --stage4; nunca producción");
test.setTimeout(90000);
test.use({ actionTimeout: 20000 });
const id = "9104001";
const workspace = `/api/ecomm-app/workspace/${id}`;
const endpoint = "/api/ecomm-app/workspace/channels/ml/validations";
async function read(page: Page, path: string) {
  const response = await page.request.get(path, { headers: { "X-Kiki-UI": "v2" } });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

test("Mercado Libre: validación oficial OFF, faltantes explícitos y cero consultas al proveedor", async ({ page, context }) => {
  const requests: string[] = [];
  await context.route("**/*", route => {
    const target = new URL(route.request().url());
    if (target.origin !== "https://127.0.0.1:8443") throw new Error("Proveedor externo prohibido en aceptación aislada");
    if (/\/sync$|\/generate-ai$|\/auth-url$|\/manual\/start$|\/lookup$|\/import-csv$/.test(target.pathname)) throw new Error("Consulta o escritura externa no autorizada");
    requests.push(route.request().method() + " " + target.pathname);
    return route.continue();
  });
  await page.goto("/v2/");
  await page.getByRole("textbox", { name: "Usuario", exact: true }).fill("operador-prueba");
  await page.getByLabel("Contraseña", { exact: true }).fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator("[data-ecomm-id]").first()).toBeVisible();
  const before = await read(page, workspace);
  const factsBefore = await read(page, workspace + "/evidence");
  await page.locator("#integration-search").fill(id);
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await page.locator(`[data-ecomm-id="${id}"]`).getByRole("button", { name: "Ver ficha", exact: true }).click();
  await page.getByRole("tab", { name: "Canales", exact: true }).click();
  await page.getByRole("button", { name: "Ver Mercado Libre", exact: true }).click();
  const panel = page.getByRole("region", { name: "Validación oficial controlada Mercado Libre", exact: true });
  await panel.getByRole("button", { name: "Preparar validación oficial de Mercado Libre", exact: true }).click();
  await expect(panel).toContainText("Validación oficial deshabilitada. Podés revisar los faltantes sin consultar al proveedor.");
  for (const name of ["ID del vendedor autorizado", "ID oficial de categoría", "Precio real (sólo para validar)", "Moneda", "Cantidad real (sólo para validar)", "Condición oficial", "Modalidad de venta", "Modalidad de publicación oficial"]) {
    await expect(panel.getByRole("textbox", { name, exact: true })).toHaveValue("");
  }
  await panel.getByRole("textbox", { name: "Revisión y procedencia de estos parámetros", exact: true }).fill("Ensayo aislado con parámetros ausentes deliberadamente; no autoriza consultas externas ni permite inventar datos.");
  const pending = page.waitForResponse(response => response.url().endsWith(endpoint + "/preview") && response.request().method() === "POST");
  await panel.getByRole("button", { name: "Previsualizar validación sin consultas externas", exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const preview = await response.json();
  expect(preview.ecomm_id).toBe(id);
  expect(preview.state).toBe("BLOCKED");
  expect(preview.provider_calls).toBe(0);
  expect(preview.publication_created).toBe(false);
  expect(preview.external_writes_enabled).toBe(false);
  expect(preview.official_payload_validated).toBe(false);
  expect(preview.preview_fingerprint).toMatch(/^[a-f0-9]{64}$/);
  for (const field of ["category_id", "price", "currency_id", "available_quantity", "condition", "buying_mode", "listing_type_id"]) expect(preview.payload_preview[field]).toBeNull();
  expect(preview.payload_preview.attributes).toEqual([]);
  expect(preview.blockers.join(" ")).toContain("Falta el vendedor auténtico autorizado");
  expect(preview.blockers.join(" ")).toContain("Falta precio real suministrado para validar; no se inventa");
  await expect(panel.getByRole("button", { name: "Confirmar consulta a /items/validate · No publica", exact: true })).toBeDisabled();
  await expect(panel).toContainText("Requiere revisión");

  const auth = await read(page, "/api/auth/me");
  const execution = { expected_revision: preview.revision, expected_preview_fingerprint: preview.preview_fingerprint, confirm: true };
  const noCsrf = await page.request.post(`${endpoint}/${preview.id}/validate`, { headers: { "X-Kiki-UI": "v2" }, data: execution });
  expect(noCsrf.status()).toBe(403);
  const denied = await page.request.post(`${endpoint}/${preview.id}/validate`, { headers: { "X-Kiki-UI": "v2", "X-CSRF-Token": auth.csrf_token }, data: execution });
  expect(denied.status(), await denied.text()).toBe(403);
  expect((await denied.json()).detail).toContain("deshabilitada");
  const registry = await read(page, endpoint + "?ecomm_id=" + id);
  expect(registry.official_validation_enabled).toBe(false);
  const stored = registry.items.find((item: { id: number }) => item.id === preview.id);
  expect(stored.state).toBe("BLOCKED");
  expect(stored.revision).toBe(preview.revision);
  expect(stored.provider_calls).toBe(0);
  expect(stored.history).toEqual(preview.history);
  const after = await read(page, workspace);
  expect(after.version).toBe(before.version);
  expect(after.fields).toEqual(before.fields);
  expect(after.history).toEqual(before.history);
  expect((await read(page, workspace + "/evidence")).facts).toEqual(factsBefore.facts);
  expect(requests.some(path => path.includes("/items/validate"))).toBe(false);
});
