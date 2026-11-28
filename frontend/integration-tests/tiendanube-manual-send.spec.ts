import { test, expect, type Page } from "@playwright/test";

test.skip(process.env.KIKI_TN_SUBMISSION_SCENARIO !== "offline-hidden-only", "Requiere perfil PG18 privado con Tiendanube simulado");
test.setTimeout(90000);
const base = "/api/ecomm-app/workspace/channels/tn/submissions";
async function read(page: Page, path: string) {
  const response = await page.request.get(path, { headers: { "X-Kiki-UI": "v2" } });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}
async function open(page: Page, id: string) {
  await page.goto("/v2/");
  await page.getByLabel("Usuario", { exact: true }).fill("operador-prueba");
  await page.getByLabel("Contraseña", { exact: true }).fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await page.locator("#integration-search").fill(id);
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await page.locator(`[data-ecomm-id="${id}"]`).getByRole("button", { name: "Ver ficha", exact: true }).click();
  // Use the actual editor and PostgreSQL, with optional SEO empty deliberately.
  await page.getByLabel("Título completo", { exact: true }).fill(`Semillas sintéticas E4 ${Number(id) - 9104000} 250 g`);
  await page.getByLabel("Título SEO", { exact: true }).fill("");
  const saved = page.waitForResponse(r => r.url().endsWith(`/workspace/${id}`) && r.request().method() === "POST");
  await page.getByRole("button", { name: "Guardar borrador", exact: true }).click();
  expect((await saved).status()).toBe(200);
  await page.getByRole("tab", { name: "Canales", exact: true }).click();
  await page.getByRole("button", { name: "Ver Tiendanube", exact: true }).click();
  const panel = page.getByRole("region", { name: "Envíos controlados a Tiendanube", exact: true });
  await panel.getByRole("button", { name: "Cargar producto en Tiendanube", exact: true }).click();
  await panel.getByRole("checkbox", { name: /Revisé nombre, marca/ }).check();
  const pending = page.waitForResponse(r => r.url().endsWith(base + "/preview") && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Previsualizar para Tiendanube", exact: true }).click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(200);
  const draft = await response.json();
  expect(draft.state, JSON.stringify(draft.blockers)).toBe("PREVIEW");
  expect(draft.payload_preview.published).toBe(false);
  expect(draft.payload_preview.seo_title).toBeUndefined();
  return { panel, draft };
}
test.beforeEach(async ({ context }) => {
  await context.route("**/*", route => {
    if (new URL(route.request().url()).origin !== "https://127.0.0.1:8443") throw new Error("No se permite acceso externo en aceptación");
    return route.continue();
  });
});

test("guardar, previsualizar, confirmar creación oculta y recuperar resultado sin repetir", async ({ page }, info) => {
  const id = info.project.name === "desktop" ? "9104007" : "9104008";
  const { panel, draft } = await open(page, id);
  // Rejecting the native confirmation does not issue a send request.
  page.once("dialog", dialog => dialog.dismiss());
  await panel.getByRole("button", { name: "Enviar a Tiendanube", exact: true }).click();
  expect((await read(page, `${base}/${draft.id}`)).state).toBe("PREVIEW");
  const before = await read(page, `/api/ecomm-app/workspace/${id}`);
  page.once("dialog", dialog => dialog.accept());
  const sent = page.waitForResponse(r => r.url().endsWith(`${base}/${draft.id}/send`));
  await panel.getByRole("button", { name: "Enviar a Tiendanube", exact: true }).click();
  const response = await sent;
  expect(response.status(), await response.text()).toBe(200);
  const receipt = await response.json();
  expect(receipt.state).toBe("SUCCEEDED");
  expect(receipt.target_product_id).toMatch(/^5\d+/);
  await expect(panel.getByRole("link", { name: "Revisar producto en Tiendanube" })).toHaveAttribute("href", receipt.product_admin_url);
  expect((await read(page, `/api/ecomm-app/workspace/${id}`)).history).toEqual(before.history);
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `artifacts/tiendanube-hidden-send-${info.project.name}.png`, fullPage: false });
  await page.reload();
  await page.getByRole("button", { name: "Ver Tiendanube", exact: true }).click();
  await page.getByRole("button", { name: "Cargar producto en Tiendanube", exact: true }).click();
  await expect(page.getByRole("region", { name: "Envíos controlados a Tiendanube" })).toContainText("Contenido enviado con confirmación");
});

for (const scenario of ["duplicate", "timeout"] as const) test(`${scenario}: bloqueo o resultado incierto, nunca reenvío automático`, async ({ page }, info) => {
  const id = String((scenario === "duplicate" ? 9104009 : 9104011) + (info.project.name === "mobile" ? 1 : 0));
  const { panel, draft } = await open(page, id);
  page.once("dialog", dialog => dialog.accept());
  const pending = page.waitForResponse(r => r.url().endsWith(`${base}/${draft.id}/send`));
  await panel.getByRole("button", { name: "Enviar a Tiendanube", exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const receipt = await response.json();
  expect(receipt.state).toBe(scenario === "duplicate" ? "BLOCKED" : "UNKNOWN");
  expect(receipt.target_product_id).toBeNull();
  await expect(panel.getByRole("button", { name: "Enviar a Tiendanube", exact: true })).toBeDisabled();
  await panel.getByRole("button", { name: "Consultar resultado del envío", exact: true }).click();
  expect((await read(page, `${base}/${draft.id}`)).provider_calls).toBe(receipt.provider_calls);
});
