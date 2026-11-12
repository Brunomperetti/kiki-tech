import { test, expect, type Page } from "@playwright/test";
test.skip(
  process.env.KIKI_PRESENTATION_SCENARIO !== "local-synthetic",
  "Escenario aislado de presentación",
);
const nav = (page: Page) =>
  page.getByRole("navigation", { name: "Vistas comerciales" });
test.beforeEach(async ({ page, context }) => {
  await context.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== "https://127.0.0.1:8443")
      throw new Error("Destino externo prohibido");
    if (
      /\/suggest$|oauth|sync|refresh|publish|openai/.test(
        new URL(route.request().url()).pathname,
      )
    )
      throw new Error("Proveedor prohibido");
    return route.continue();
  });
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
});
test("cinco vistas: registros huérfanos, CSV sin vigencia y maestro sin identidades inventadas", async ({
  page,
}, info) => {
  await expect(nav(page).getByRole("button")).toHaveCount(5);
  await page.screenshot({
    path: `artifacts/functional-catalog-dashboard-${info.project.name}.png`,
    fullPage: false,
  });
  await page.getByLabel("Variantes por página").selectOption("6");
  await nav(page)
    .getByRole("button", { name: /^Publicaciones Mercado Libre/ })
    .click();
  const records = page.getByRole("region", { name: "Registros Mercado Libre" });
  await expect(records.locator("[data-channel-record]")).toHaveCount(6);
  const orphan = records.locator("tr").filter({ hasText: "MLA999000001" });
  await expect(orphan).toContainText("Sin Ecomm ID validado");
  await expect(orphan.getByRole("button")).toHaveCount(0);
  await records.getByLabel("Vinculación del canal").selectOption("unlinked");
  await expect(page).toHaveURL(/linkage=unlinked/);
  await page.screenshot({
    path: `artifacts/functional-catalog-ml-${info.project.name}.png`,
    fullPage: false,
  });
  await nav(page)
    .getByRole("button", { name: /^Registros Tiendanube/ })
    .click();
  const tn = page.getByRole("region", { name: "Registros Tiendanube" });
  await expect(tn.locator("[data-channel-record]")).toHaveCount(5);
  await expect(tn).toContainText("registro-tn-sin-vinculo");
  await expect(tn).toContainText("Información desactualizada");
  await expect(tn).not.toContainText("Publicación confirmada en captura");
  for (const label of [/^Sin confirmación en ML/, /^Sin confirmación en TN/]) {
    await nav(page).getByRole("button", { name: label }).click();
    await expect(page.locator("[data-ecomm-id]")).toHaveCount(6);
    await expect(page.locator(".i-pagination")).toContainText(
      "6 variantes en la captura",
    );
  }
});
test("calidad calculada, intersección, búsqueda y URL recuperable sin mezclar variantes", async ({
  page,
}, info) => {
  await page
    .getByText("Más indicadores y alcance de capturas", { exact: true })
    .click();
  const quality = page.getByRole("group", { name: "Indicadores de calidad" });
  const metric = quality.getByRole("button", { name: /^EAN repetido/ });
  await expect(metric.locator("strong")).toHaveText("2");
  await metric.click();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(2);
  await expect(page.locator('[data-ecomm-id="900003"]')).toContainText("250 g");
  await expect(page.locator('[data-ecomm-id="900004"]')).toBeVisible();
  await page
    .getByLabel("Combinar filtro de catálogo")
    .selectOption("images_missing");
  await expect(page).toHaveURL(/ean_repeated%2Bimages_missing/);
  await page.reload();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(2);
  await page.getByLabel("Buscar productos", { exact: true }).fill("900004");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(1);
  await expect(page.locator('[data-ecomm-id="900004"]')).toContainText("1 kg");
  await page.screenshot({
    path: `artifacts/functional-catalog-quality-${info.project.name}.png`,
    fullPage: false,
  });
  await page.goBack();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(2);
});
test("configuración, exportación e historial reutilizan contratos existentes", async ({
  page,
}, info) => {
  await page
    .getByRole("button", { name: "Configuración", exact: true })
    .click();
  const settings = page.getByRole("dialog", {
    name: "Configuración del catálogo",
  });
  await expect(settings).toContainText(
    "OpenAI real e investigación externa desactivados",
  );
  await settings.getByLabel("Mostrar filtros y detalles avanzados").check();
  const download = page.waitForEvent("download");
  await settings
    .getByRole("link", { name: "Descargar fichas guardadas · JSON" })
    .click();
  expect((await download).suggestedFilename()).toMatch(/\.json$/);
  await settings.getByRole("button", { name: "Volver a Mi catálogo" }).click();
  await expect(
    page.getByRole("group", { name: "Indicadores de calidad" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Historial", exact: true }).click();
  const history = page.getByRole("dialog", {
    name: "Historial de fichas guardadas",
  });
  await expect(history).toBeVisible();
  await expect(history).toContainText("El mismo editor y sus versiones");
  await history.getByRole("button", { name: "Volver a Mi catálogo" }).click();
  await page
    .locator('[data-ecomm-id="900003"]')
    .getByRole("button", { name: "Ver ficha", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Investigar producto", exact: true }),
  ).toHaveText("Investigar y completar ficha con IA");
  await expect(page.getByRole("tab")).toHaveCount(5);
  await page
    .getByRole("dialog")
    .screenshot({
      path: `artifacts/functional-catalog-editor-${info.project.name}.png`,
    });
});
test("rechaza una respuesta de canal que pretende confirmar un CSV", async ({
  page,
}) => {
  await page.route("**/workspace/channels/listings?*", async (route) => {
    const u = new URL(route.request().url());
    const original = await route.fetch();
    const data = await original.json();
    if (u.searchParams.get("channel") === "tn" && data.items.length) {
      data.items[0].confirmed_listing = true;
      data.items[0].evidence_state = "CONFIRMED_CAPTURE";
    }
    await route.fulfill({ response: original, json: data });
  });
  await nav(page)
    .getByRole("button", { name: /^Registros Tiendanube/ })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Registros de canal incompatibles",
  );
  await expect(page.locator("[data-channel-record]")).toHaveCount(0);
});
