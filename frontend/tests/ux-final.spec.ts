import { test, expect } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  await page.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (u.origin !== "http://127.0.0.1:4173" || u.pathname.startsWith("/api/"))
      throw new Error("La demo intentó conectarse a un servicio");
    return route.continue();
  });
  await page.goto("/");
});
test("jerarquía compacta: cinco vistas, dos preparados y secundarios sin repeticiones", async ({
  page,
}, info) => {
  const views = page.getByRole("navigation", { name: "Vistas comerciales" });
  const preparation = page.getByRole("region", {
    name: "Preparación por canal",
  });
  await expect(views.getByRole("button")).toHaveCount(5);
  await expect(preparation.getByRole("button")).toHaveCount(2);
  for (const channel of ["ml", "tn"]) {
    const metric = page.locator(`[data-metric="${channel}-ready"]`);
    await expect(metric).toHaveCount(1);
    await expect(metric).toBeVisible();
    await expect(metric.locator("strong")).toHaveText("1");
    await expect(metric).toContainText("preparación interna");
  }
  const secondary = page.getByRole("region", {
    name: "Cobertura comercial por canal",
  });
  await expect(secondary).toBeHidden();
  await page.getByText("Más indicadores comerciales", { exact: true }).click();
  await expect(secondary.getByRole("button")).toHaveCount(3);
  await expect(
    secondary.locator(
      '[data-metric="all"], [data-metric$="ready"], [data-metric$="unconfirmed"]',
    ),
  ).toHaveCount(0);
  await page.getByText("Más indicadores comerciales", { exact: true }).click();
  await expect(secondary).toBeHidden();
  await expect(page.locator('[data-metric="all"]')).toHaveCount(1);
  const tableY = await page
    .locator(".d-table")
    .evaluate((el) => el.getBoundingClientRect().top + scrollY);
  expect(tableY).toBeLessThan(info.project.name === "mobile" ? 1600 : 900);
  await page.screenshot({
    path: `artifacts/ux-final-dashboard-${info.project.name}.png`,
    fullPage: info.project.name === "mobile",
    scale: "css",
  });
  await expect(
    page.getByRole("region", { name: "Centro de operaciones", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Más acciones del catálogo", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Centro de operaciones", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Propuestas IA", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Propuestas IA", exact: true }),
  ).toContainText("locales");
});
test("preparación por canal filtra la tabla, conserva URL y no publica", async ({
  page,
}) => {
  for (const channel of ["ml", "tn"]) {
    await page.locator(`[data-metric="${channel}-ready"]`).click();
    await expect(page.locator(".d-table tbody tr")).toHaveCount(1);
    await expect(
      page.locator(`.d-table tbody tr [data-channel="${channel}"]`),
    ).toContainText("Listo para publicar");
    await expect(page).toHaveURL(new RegExp(channel + "State=ready"));
    await page.reload();
    await expect(
      page.locator(`[data-metric="${channel}-ready"]`),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".d-table tbody tr")).toHaveCount(1);
    await page.getByTestId("total").click();
    await expect(page.locator(".d-table tbody tr")).toHaveCount(8);
  }
});
test("IA destaca disponibilidad real y abre evidencias sin ejecutar investigación web", async ({
  page,
}, info) => {
  await page
    .getByRole("button", { name: "Abrir DEMO-1001", exact: true })
    .click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByRole("tab")).toHaveCount(5);
  const ai = panel.getByRole("tab", { name: "IA", exact: true });
  await expect(ai).toHaveClass(/k-ai-tab/);
  await ai.click();
  await expect(
    panel.getByRole("region", { name: "Disponibilidad de investigación e IA" }),
  ).toContainText("desactivados");
  await expect(panel).toContainText("plantilla local");
  await panel.screenshot({
    path: `artifacts/ux-final-ai-${info.project.name}.png`,
    scale: "css",
  });
  await panel
    .getByRole("button", {
      name: "Investigar y completar ficha con IA",
      exact: true,
    })
    .click();
  await expect(
    panel.getByRole("tab", { name: "Evidencias", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(panel).toContainText("datos sintéticos");
  await panel.getByRole("tab", { name: "IA", exact: true }).click();
  await expect(
    panel.getByRole("button", {
      name: "Generar propuesta simulada",
      exact: true,
    }),
  ).toBeEnabled();
});
