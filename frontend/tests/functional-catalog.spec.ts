import { test, expect } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (
      url.origin !== "http://127.0.0.1:4173" ||
      url.pathname.startsWith("/api/")
    )
      throw new Error("Demo intentó acceder a servicios");
    return route.continue();
  });
  await page.goto("/");
});
test("cinco vistas locales, registros sin vincular y calidad sin backend", async ({
  page,
}, info) => {
  const nav = page.getByRole("navigation", { name: "Vistas comerciales" });
  await expect(nav.getByRole("button")).toHaveCount(5);
  await expect(page.locator(".d-table tbody tr")).toHaveCount(8);
  await expect(
    page.getByRole("region", { name: "Cobertura comercial por canal" }),
  ).toBeHidden();
  await page.screenshot({
    path: `artifacts/functional-demo-dashboard-${info.project.name}.png`,
    fullPage: false,
  });
  await nav
    .getByRole("button", { name: /^Publicaciones Mercado Libre/ })
    .click();
  await page
    .getByRole("textbox", { name: "Buscar productos" })
    .fill("DEMO-ML-SIN-VINCULO");
  const orphan = page
    .locator("[data-channel-record]")
    .filter({ hasText: "DEMO-ML-SIN-VINCULO" });
  await expect(orphan).toContainText("Sin Ecomm ID validado");
  await expect(orphan.getByRole("button")).toHaveCount(0);
  await nav.getByRole("button", { name: /^Registros Tiendanube/ }).click();
  await expect(
    page.getByRole("region", { name: "Registros Tiendanube" }),
  ).not.toContainText("Publicación confirmada en captura");
  await nav.getByRole("button", { name: /^Catálogo Ecomm-App/ }).click();
  await page
    .getByText("Calidad del catálogo · demostración", { exact: true })
    .click();
  const quality = page.getByRole("group", {
    name: "Calidad de la demostración",
  });
  await expect(
    quality.getByRole("button", { name: /^EAN repetido/ }).locator("strong"),
  ).toHaveText("2");
  await quality.getByRole("button", { name: /^EAN repetido/ }).click();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
  await expect(page).toHaveURL(/quality=ean_repeated/);
  await page.reload();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
});
test("el formulario original de 18 campos conserva cambios en la sesión y muestra su alcance", async ({
  page,
}, info) => {
  await page
    .getByRole("button", { name: "Abrir DEMO-1001", exact: true })
    .click();
  const panel = page.getByRole("dialog");
  await panel
    .getByText("Editor comercial completo · 18 campos compartidos", {
      exact: true,
    })
    .click();
  await expect(panel).toContainText("en memoria");
  await expect(panel.locator(".o-comparison tbody tr")).toHaveCount(0);
  await expect(
    panel.getByLabel("Detalles, uso y aclaraciones", { exact: true }),
  ).toHaveValue("Ingredientes, origen y alérgenos pendientes de verificación.");
  await panel
    .getByLabel("Descripción corta", { exact: true })
    .fill("Descripción sintética revisada en el formulario compartido");
  await panel
    .getByRole("link", { name: "Fotos y videos", exact: true })
    .click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(
    panel.getByLabel("Descripción corta", { exact: true }),
  ).toHaveValue("Descripción sintética revisada en el formulario compartido");
  await panel
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(panel.locator(".o-comparison tbody tr")).toHaveCount(0);
  await page.screenshot({
    path: `artifacts/functional-demo-editor-${info.project.name}.png`,
    fullPage: false,
  });
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await page
    .getByRole("button", { name: "Abrir DEMO-1001", exact: true })
    .click();
  await panel
    .getByText("Editor comercial completo · 18 campos compartidos", {
      exact: true,
    })
    .click();
  await expect(
    panel.getByLabel("Descripción corta", { exact: true }),
  ).toHaveValue("Descripción sintética revisada en el formulario compartido");
  await panel.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(panel).toContainText("Borrador guardado");
});
