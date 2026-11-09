import { test, expect, type Page } from "@playwright/test";
const attempts = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const external: string[] = [];
  attempts.set(page, external);
  await page.route("**/*", (r) => {
    if (new URL(r.request().url()).origin !== "http://127.0.0.1:4173") {
      external.push(r.request().url());
      return r.abort();
    }
    return r.continue();
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tu catálogo, en un solo lugar." }),
  ).toBeVisible();
});
test.afterEach(async ({ page }) => expect(attempts.get(page)).toEqual([]));
const row = (page: Page, id: string) =>
  page.locator(".d-table tbody tr").filter({ hasText: id });
test("navegación simple y ocho indicadores comerciales en la misma pantalla", async ({
  page,
}, info) => {
  const nav = page.getByRole("navigation", {
    name: "Navegación del prototipo",
  });
  await expect(nav.getByRole("button")).toHaveCount(3);
  await expect(
    nav.getByRole("button", { name: "Mi catálogo", exact: true }),
  ).toBeVisible();
  await expect(nav.getByRole("link")).toHaveCount(0);
  const metrics = page.getByRole("region", {
    name: "Cobertura comercial por canal",
  });
  await expect(metrics.getByRole("button")).toHaveCount(8);
  await page
    .getByRole("button", { name: "Ver todo el catálogo", exact: true })
    .click();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(8);
  await page.screenshot({
    path: `artifacts/simple-dashboard-${info.project.name}.png`,
    fullPage: true,
    scale: "css",
  });
});
test("editorial y canales separados; preparar no publica ni confirma candidatos", async ({
  page,
}) => {
  const lamp = row(page, "DEMO-1005");
  await expect(lamp).toContainText("Ficha aprobada");
  await expect(lamp).toContainText("Publicado");
  await expect(lamp).toContainText("Sin publicación confirmada");
  await expect(lamp).not.toContainText("Sin publicar");
  const speaker = row(page, "DEMO-1008");
  await expect(speaker).toContainText("Publicado");
  await expect(speaker).toContainText("Listo para publicar");
  await expect(row(page, "DEMO-1002")).not.toContainText("Publicado");
  await page.getByRole("button", { name: "Abrir DEMO-1005" }).click();
  const panel = page.getByRole("dialog");
  await panel.getByRole("tab", { name: "Canales", exact: true }).click();
  await expect(panel).toContainText("Ficha editorial: Ficha aprobada");
  await expect(panel).toContainText("Publicación no confirmada.");
  await panel.getByRole("button", { name: "Preparar para TN" }).click();
  await panel.getByRole("button", { name: "Confirmar decisión" }).click();
  await expect(panel).toContainText("Listo para publicar");
  await expect(panel).toContainText("sujeta a revisar vigencia");
  await page.keyboard.press("Escape");
  await expect(lamp).toContainText("Listo para publicar");
  await expect(lamp).toContainText("Publicado");
  await page
    .getByRole("region", { name: "Cobertura comercial por canal" })
    .getByRole("button", { name: /^Listos para Tiendanube 2 / })
    .click();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
});
test("historial y configuración dentro del catálogo sin perder búsqueda", async ({
  page,
}, info) => {
  await page.getByRole("textbox", { name: "Buscar productos" }).fill("ALM-NAT");
  await page
    .getByRole("button", { name: "Configuración", exact: true })
    .click();
  const settings = page.getByRole("dialog", {
    name: "Configuración del catálogo",
  });
  await expect(settings).toBeVisible();
  await settings.getByLabel("Mostrar precios en la tabla").uncheck();
  await settings.getByLabel("Mostrar filtros y detalles avanzados").check();
  await page.screenshot({
    path: `artifacts/configuracion-${info.project.name}.png`,
    scale: "css",
  });
  await page.keyboard.press("Escape");
  await expect(settings).not.toBeVisible();
  await expect(page.locator(".d-table thead")).toContainText("Disponibilidad");
  await expect(page.getByLabel("Conflicto", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/q=ALM-NAT/);
  await page.getByRole("button", { name: "Historial", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Trabajos y resultados", exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/q=ALM-NAT/);
  await page
    .getByRole("button", { name: "Volver a búsqueda y productos ↑" })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Buscar productos" }),
  ).toBeFocused();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
  await expect(page).toHaveURL(/^http:\/\/127.0.0.1:4173\/\?/);
});

test("editar invalida preparación y muestra bloqueo sin borrar publicación confirmada", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Abrir DEMO-1008" }).click();
  const panel = page.getByRole("dialog");
  await panel.getByLabel("Imagen de muestra").selectOption("");
  await panel.getByRole("button", { name: "Guardar borrador" }).click();
  await panel.getByRole("tab", { name: "Canales", exact: true }).click();
  await expect(
    panel.getByRole("button", { name: "Preparar para TN" }),
  ).toBeDisabled();
  await expect(panel).toContainText("Publicado");
  await page.keyboard.press("Escape");
  await expect(row(page, "DEMO-1008")).toContainText("Datos incompletos");
  await expect(row(page, "DEMO-1008")).toContainText("Publicado");
  await expect(row(page, "DEMO-1008")).not.toContainText("Listo para publicar");
  const metrics = page.getByRole("region", {
    name: "Cobertura comercial por canal",
  });
  await expect(
    metrics.getByRole("button", { name: /^Necesitan revisión 4 / }),
  ).toBeVisible();
  await expect(
    metrics.getByRole("button", { name: /^Listos para Tiendanube 0 / }),
  ).toBeVisible();
  await expect(
    metrics.getByRole("button", { name: /^Mercado Libre · confirmadas 4 / }),
  ).toBeVisible();
});
