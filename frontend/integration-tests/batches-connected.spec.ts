import { test, expect, type Page } from "@playwright/test";
test.skip(
  process.env.KIKI_BATCH_SCENARIO !== "synthetic-approvals",
  "Escenario explícito: integration/run.py browser-test --batches",
);
test.setTimeout(120000);
const calls = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page, context }) => {
  const paths: string[] = [];
  calls.set(page, paths);
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "https://127.0.0.1:8443")
      throw new Error("Salida fuera del entorno aislado");
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
      .filter((p) => /oauth|sync|refresh|publish|publicar|openai/.test(p)),
  ).toEqual([]);
});
async function preview(page: Page) {
  await page
    .getByRole("button", { name: "Seleccionar esta página", exact: true })
    .click();
  await expect(page.getByTestId("selected-count")).toHaveText(
    "6 variantes seleccionadas",
  );
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  await page
    .getByRole("button", { name: "Previsualizar selección", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Revisá antes de iniciar", exact: true }),
  ).toBeVisible();
}

test("previsualización explícita → propuestas persistentes → revisión por campo → editor e historial", async ({
  page,
}, info) => {
  await preview(page);
  await expect(page.getByTestId("batch-progress")).toContainText(
    "Pendiente: 6",
  );
  expect(
    calls.get(page)!.filter((p) => p.endsWith("/start") || p.endsWith("/step")),
  ).toEqual([]);
  await page.screenshot({
    path: `artifacts/batches-preview-${info.project.name}.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Confirmar e iniciar lote", exact: true })
    .click();
  await expect(page.getByTestId("batch-progress")).toContainText(
    "Completado: 1",
  );
  await expect(page.getByTestId("batch-progress")).toContainText(
    "Bloqueado: 5",
  );
  await expect(
    page.getByRole("button", { name: "Recuperar estado guardado" }),
  ).toBeEnabled();
  await page.screenshot({
    path: `artifacts/batches-results-${info.project.name}.png`,
    fullPage: true,
  });
  const item = page.locator('[data-batch-ecomm="900001"]');
  await item.getByRole("button", { name: /Revisar propuesta/ }).click();
  await expect(page).toHaveURL(/product=900001.*tab=IA.*proposal=\d+/);
  const ia = page.getByRole("region", {
    name: "Propuestas comerciales documentadas",
  });
  await expect(ia.locator("[data-proposal-field]").first()).toBeVisible();
  const field = ia.locator("[data-proposal-field]").first();
  const key = (await field.getAttribute("data-proposal-field"))!;
  await field.getByText(/Respaldo de este campo/).click();
  await expect(field.locator("blockquote").first()).toBeVisible();
  await field.getByRole("combobox").selectOption("ACCEPTED");
  await ia
    .getByRole("button", { name: "Registrar revisión individual", exact: true })
    .click();
  await expect(ia).toContainText("Revisión registrada en PostgreSQL");
  await page.screenshot({
    path: `artifacts/batches-proposal-${info.project.name}.png`,
    fullPage: true,
  });
  page.once("dialog", (d) => d.accept());
  await ia
    .getByRole("button", { name: "Guardar selección en ficha", exact: true })
    .click();
  await expect(ia).toContainText("Selección guardada en PostgreSQL de pruebas");
  const saved = await (
    await page.request.get("/api/ecomm-app/workspace/900001")
  ).json();
  expect(saved.fields[key]).toBeTruthy();
  expect(saved.history.length).toBeGreaterThan(0);
  await page.reload();
  await expect(
    page.getByRole("tab", { name: "IA", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Propuestas comerciales documentadas" }),
  ).toContainText("Selección ya guardada");
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Guardar selección en ficha/ }),
  ).not.toBeVisible();
});

test("filtrar en la misma tabla y seleccionar todos los resultados sin perder Ecomm ID", async ({
  page,
}) => {
  await page
    .getByRole("combobox", { name: "Filtrar catálogo", exact: true })
    .selectOption("needs_research");
  await expect(page).toHaveURL(/filter=needs_research/);
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(5);
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Operación del lote", exact: true })
    .selectOption("REVIEW_TASKS");
  await page
    .getByRole("button", {
      name: "Previsualizar 5 resultados filtrados",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("region", { name: "Detalle del lote", exact: true }),
  ).toContainText("5 variantes exactas");
  const ids = await page
    .locator("[data-batch-ecomm]")
    .evaluateAll((rows) => rows.map((r) => r.getAttribute("data-batch-ecomm")));
  expect(ids).not.toContain("900001");
  expect(new Set(ids).size).toBe(5);
  page.once("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Cancelar lote", exact: true })
    .click();
  await expect(page.getByTestId("batch-progress")).toContainText(
    "Cancelado: 5",
  );
});

test("selección por páginas y reapertura recuperan el lote sin ejecutar pasos desde el navegador", async ({
  page,
}) => {
  await page
    .getByRole("combobox", { name: "Variantes por página" })
    .selectOption("3");
  await page
    .getByRole("button", { name: "Seleccionar esta página", exact: true })
    .click();
  await page.getByRole("button", { name: "Siguiente", exact: true }).click();
  await page
    .getByRole("button", { name: "Seleccionar esta página", exact: true })
    .click();
  await expect(page.getByTestId("selected-count")).toHaveText(
    "6 variantes seleccionadas",
  );
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Operación del lote", exact: true })
    .selectOption("REVIEW_TASKS");
  await page
    .getByRole("button", { name: "Previsualizar selección", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Confirmar e iniciar lote", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Confirmar e iniciar lote", exact: true })
    .click();
  await expect(page.getByTestId("batch-progress")).toContainText(
    "Completado: 6",
  );
  await page.reload();
  await page.getByRole("button", { name: /Ver lotes/ }).click();
  await page.getByText(/Lotes guardados/).click();
  await page
    .getByRole("button", { name: /6 variantes · Completado/ })
    .first()
    .click();
  await expect(page.getByTestId("batch-progress")).toContainText(
    "Completado: 6",
  );
  expect(calls.get(page)!.filter((p) => p.endsWith("/step"))).toEqual([]);
});

test("check individual, cinco pestañas y URL de propuesta ajena bloqueada", async ({
  page,
}) => {
  await page
    .getByRole("checkbox", { name: "Seleccionar 900002", exact: true })
    .check();
  await expect(page.getByTestId("selected-count")).toHaveText(
    "1 variantes seleccionadas",
  );
  await page
    .locator('[data-ecomm-id="900002"]')
    .getByRole("button", { name: "Ver ficha", exact: true })
    .click();
  for (const tab of ["Ficha", "Evidencias", "IA", "Canales", "Historial"])
    await expect(
      page.getByRole("tab", { name: tab, exact: true }),
    ).toBeVisible();
  await page.goto("/?product=900002&tab=IA&proposal=1");
  await expect(
    page
      .getByRole("region", { name: "Propuestas comerciales documentadas" })
      .getByRole("alert"),
  ).toContainText(/no pertenece/);
});
