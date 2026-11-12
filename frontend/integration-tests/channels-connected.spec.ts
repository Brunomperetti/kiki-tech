import { test, expect, type Page } from "@playwright/test";
import type { ChannelReport } from "../src/integration/channel-adapter";
test.skip(
  process.env.KIKI_CHANNEL_SCENARIO !== "synthetic-captures",
  "Escenario explícito: integration/run.py browser-test --channels",
);
test.setTimeout(90000);
const root = (id: string) => `/api/ecomm-app/workspace/${id}/channels`;
const calls = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page, context }) => {
  const paths: string[] = [];
  calls.set(page, paths);
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "https://127.0.0.1:8443")
      throw new Error("Solicitud fuera del backend sintético");
    paths.push(route.request().method() + " " + url.pathname);
    return route.continue();
  });
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
});
test.afterEach(async ({ page }) => {
  expect(
    calls
      .get(page)!
      .filter((p) => /oauth|sync|refresh|publish|publicar/.test(p)),
  ).toEqual([]);
});
async function open(page: Page, id = "900003") {
  await page
    .locator(`[data-ecomm-id="${id}"]`)
    .getByRole("button", { name: "Ver ficha", exact: true })
    .click();
  await expect(
    page.getByLabel("Marca comercial", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Canales", exact: true }).click();
  await expect(page.getByLabel("Canales por variante API")).toBeVisible();
  await expect(page.locator('[data-channel-panel="ml"]')).toBeVisible();
}
async function read(page: Page, id = "900003"): Promise<ChannelReport> {
  const r = await page.request.get(root(id));
  expect(r.status()).toBe(200);
  return r.json();
}
const row = (page: Page, id = "MLA900000003") =>
  page.locator(`[data-channel-panel="ml"] [data-channel-row="${id}"]`);
const metrics = (page: Page) =>
  page.getByLabel("Cobertura por canal", { exact: true });
async function fill(page: Page, ident = "MLA900000003", qty = "1") {
  const card = row(page, ident);
  await card
    .getByText("Revisar identidad y registrar decisión interna", {
      exact: true,
    })
    .click();
  for (const check of await card.getByRole("checkbox").all())
    await check.check();
  await card.getByRole("spinbutton").fill(qty);
  await card
    .getByRole("textbox")
    .fill(
      "Contrasté nombre, marca, presentación, cantidad y códigos de esta variante sintética.",
    );
}
test("candidato y decisión Excel no confirman; revisión API confirma sólo la captura ML y actualiza filtros", async ({
  page,
}, info) => {
  const initial = await read(page);
  expect(initial.ml.confirmed_listing).toBe(false);
  await open(page);
  await expect(page.locator('[data-channel-panel="ml"]')).toContainText(
    /Coincidencia candidata|Vinculación pendiente/,
  );
  await expect(page.locator('[data-channel-panel="ml"]')).toContainText(
    "decisiones históricas no se aplicaron",
  );
  await fill(page);
  page.once("dialog", (d) => d.accept());
  await row(page)
    .getByRole("button", { name: "Validar vínculo interno", exact: true })
    .click();
  await expect(page.locator('[data-channel-panel="ml"]')).toContainText(
    "Publicación confirmada en captura",
  );
  await expect(
    metrics(page)
      .getByRole("button", { name: /Variantes con ML confirmado/ })
      .locator("strong"),
  ).toHaveText("1");
  await expect(page.locator('[data-channel-panel="tn"]')).toContainText(
    "Información desactualizada",
  );
  await expect(page.locator('[data-channel-panel="tn"]')).toContainText(
    "no demuestra que siga publicado actualmente",
  );
  await row(page)
    .getByText("Revisar identidad y registrar decisión interna", {
      exact: true,
    })
    .click();
  await page
    .locator('[data-channel-panel="ml"]')
    .evaluate((el) => el.scrollIntoView({ block: "start" }));
  await expect(
    page.locator('[data-channel-panel="ml"] > strong'),
  ).toBeVisible();
  await page.screenshot({
    path: `artifacts/canales-2p-${info.project.name}.png`,
  });
  await page.reload();
  await expect(page.locator('[data-channel-panel="ml"]')).toContainText(
    "Publicación confirmada en captura",
  );
  await row(page)
    .getByText(/Historial de vinculación/)
    .click();
  await expect(row(page)).toContainText("Cantidad declarada por operador: 1");
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await metrics(page)
    .getByRole("button", { name: /Variantes con ML confirmado/ })
    .click();
  await expect(page.locator("tbody tr[data-ecomm-id]")).toHaveCount(1);
  await expect(page).toHaveURL(/filter=ml_confirmed/);
  await page.reload();
  await expect(page.locator('[data-ecomm-id="900003"]')).toBeVisible();
  await page.getByRole("button", { name: /Variantes Ecomm-App/ }).click();
  await expect(page.locator("tbody tr[data-ecomm-id]")).toHaveCount(6);
  await page.screenshot({
    path: `artifacts/dashboard-canales-2p-${info.project.name}.png`,
    fullPage: true,
  });
});
test("pack x2 y x6 siguen separados; mismo EAN no transfiere publicación y barcode/GTIN bloquean", async ({
  page,
}, info) => {
  await open(page, "900001");
  const a = await read(page, "900001");
  const b = await read(page, "900002");
  expect(a.ml.confirmed_listing).toBe(false);
  expect(b.ml.confirmed_listing).toBe(false);
  const wrong = row(page, "MLA900000002");
  await expect(wrong).toContainText(
    "Pack sin composición/cantidad coincidente",
  );
  await wrong
    .getByText("Revisar identidad y registrar decisión interna", {
      exact: true,
    })
    .click();
  await expect(
    wrong.getByRole("button", { name: "Validar vínculo interno", exact: true }),
  ).toBeDisabled();
  await wrong.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/packs-canales-2p-${info.project.name}.png`,
  });
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await open(page, "900004");
  expect((await read(page, "900004")).ml.confirmed_listing).toBe(false);
  await expect(page.locator('[data-channel-panel="ml"]')).toContainText(
    "Coincidencia candidata",
  );
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await open(page, "900006");
  await expect(page.locator('[data-channel-panel="ml"]')).toContainText(
    "Conflicto de identidad",
  );
  await expect(page.getByLabel("Canales por variante API")).toContainText(
    "BARCODE_GTIN_CONFLICT",
  );
});
test("sin evidencia no significa no publicado; conserva búsqueda, selección, cinco pestañas y URL", async ({
  page,
}) => {
  await page
    .getByText("Más indicadores y alcance de capturas", { exact: true })
    .click();
  await metrics(page)
    .getByRole("button", { name: /Candidatos pendientes/ })
    .click();
  await expect(page).toHaveURL(/filter=channel_candidates/);
  await page.getByLabel("Buscar productos", { exact: true }).fill("900004");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(page.locator("tbody tr[data-ecomm-id]")).toHaveCount(1);
  await open(page, "900004");
  for (const name of ["Ficha", "Evidencias", "IA", "Historial", "Canales"]) {
    await page.getByRole("tab", { name, exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
  }
  await expect(page).toHaveURL(/product=900004/);
  await expect(page).toHaveURL(/q=900004/);
  await expect(page).toHaveURL(/tab=Canales/);
  await page.reload();
  await expect(page.locator('[data-channel-panel="ml"]')).toContainText(
    "Coincidencia candidata",
  );
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await page.getByRole("button", { name: /Variantes Ecomm-App/ }).click();
  await open(page, "900005");
  await expect(page.locator('[data-channel-panel="ml"]')).toContainText(
    "Sin evidencia suficiente",
  );
  await expect(page.locator('[data-channel-panel="ml"]')).toContainText(
    "no significa que el producto no esté publicado",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("revocación conserva historial y retira confirmación sin cambiar la ficha comercial", async ({
  page,
}) => {
  const before = await (
    await page.request.get("/api/ecomm-app/workspace/900003")
  ).json();
  await open(page);
  const card = row(page);
  await fill(page);
  page.once("dialog", (d) => d.accept());
  await card
    .getByRole("button", { name: "Revocar vínculo interno", exact: true })
    .click();
  await expect(page.locator('[data-channel-panel="ml"]')).not.toContainText(
    "Publicación confirmada en captura",
  );
  await expect(
    metrics(page)
      .getByRole("button", { name: /Variantes con ML confirmado/ })
      .locator("strong"),
  ).toHaveText("0");
  const after = await (
    await page.request.get("/api/ecomm-app/workspace/900003")
  ).json();
  expect(after.fields).toEqual(before.fields);
  expect(after.version).toBe(before.version);
  const data = await read(page);
  expect(data.ml.confirmed_listing).toBe(false);
  expect(data.ml.candidates[0].history.at(-1)?.decision).toBe("REVOKED");
});
