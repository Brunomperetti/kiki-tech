import { test, expect, type Page, type Route } from "@playwright/test";
test.skip(
  process.env.KIKI_AUTONOMOUS_SCENARIO !== "5000-synthetic",
  "Escenario 2R explícito con 5000 variantes sintéticas.",
);
test.setTimeout(180000);
const calls = new WeakMap<Page, string[]>();
const root = "/api/ecomm-app/editorial-batches";
test.beforeEach(async ({ page, context }) => {
  const paths: string[] = [];
  calls.set(page, paths);
  await context.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (u.origin !== "https://127.0.0.1:8443")
      throw new Error("Conexión fuera del entorno aislado");
    paths.push(route.request().method() + " " + u.pathname);
    return route.continue();
  });
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("5000");
});
test.afterEach(async ({ page }) => {
  expect(
    calls
      .get(page)!
      .filter((p) =>
        /\/step$|oauth|sync|refresh|publish|publicar|openai/.test(p),
      ),
  ).toEqual([]);
});
const modal = (page: Page) =>
  page.getByRole("dialog", { name: "Lotes editoriales", exact: true });
const detail = (page: Page) =>
  page.getByRole("region", { name: "Detalle del lote", exact: true });
async function operations(page: Page, operation = "REVIEW_TASKS") {
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  await modal(page)
    .getByRole("combobox", { name: "Operación del lote" })
    .selectOption(operation);
}
async function ready(page: Page) {
  await expect(
    modal(page).getByRole("button", {
      name: "Confirmar e iniciar lote",
      exact: true,
    }),
  ).toBeEnabled({ timeout: 90000 });
  return (await detail(page).getAttribute("data-batch-id"))!;
}
async function cancel(page: Page) {
  page.once("dialog", (d) => d.accept());
  await modal(page)
    .getByRole("button", { name: "Cancelar lote", exact: true })
    .click();
  await expect(detail(page)).toHaveAttribute("data-batch-state", "CANCELLED", {
    timeout: 30000,
  });
}

test("tabla accesible, indicadores completos sin duplicación y cinco pestañas conservadas", async ({
  page,
}, info) => {
  const secondary = page.locator(".i-secondary");
  await expect(secondary).not.toHaveAttribute("open", "");
  await expect(
    page.locator(".k-preparation .c-metrics [data-metric]"),
  ).toHaveCount(2);
  for (const id of [
    "all",
    "identity",
    "ml_confirmed",
    "tn_verified",
    "untouched",
    "draft",
    "ready",
    "ready_for_channels",
    "pack",
    "channel_candidates",
    "channel_conflicts",
    "channel_no_evidence",
    "channel_stale",
  ])
    await expect(page.locator(`[data-metric="${id}"]`)).toHaveCount(1);
  const tops = await page
    .locator(".k-preparation .c-metrics [data-metric]")
    .evaluateAll((cards) =>
      cards.map((card) => card.getBoundingClientRect().top),
    );
  if (info.project.name === "desktop") expect(new Set(tops).size).toBe(1);
  else {
    expect(tops[0]).toBe(tops[1]);
  }
  const y = await page
    .locator(".i-table")
    .evaluate((el) => el.getBoundingClientRect().top + scrollY);
  expect(y).toBeLessThan(info.project.name === "mobile" ? 1600 : 900);
  await expect(
    page.getByLabel("Buscar productos", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Operaciones", exact: true }),
  ).toBeInViewport();
  await page.screenshot({
    path: `artifacts/operations-2r-dashboard-${info.project.name}.png`,
    fullPage: false,
  });
  await page.getByText("Más indicadores comerciales", { exact: true }).click();
  await expect(page.locator('[data-metric="pack"]')).toBeVisible();
  await page.getByText("Más indicadores comerciales", { exact: true }).click();
  await page
    .locator('[data-ecomm-id="900001"]')
    .getByRole("button", { name: "Ver ficha", exact: true })
    .click();
  for (const tab of ["Ficha", "Evidencias", "IA", "Canales", "Historial"])
    await expect(
      page.getByRole("tab", { name: tab, exact: true }),
    ).toBeVisible();
});

test("selección de 5000, previsualización recuperable y cancelación sin autorización de operaciones", async ({
  page,
}, info) => {
  await operations(page);
  const started = Date.now();
  await modal(page)
    .getByRole("button", {
      name: "Previsualizar 5000 resultados filtrados",
      exact: true,
    })
    .click();
  await expect(detail(page)).toBeVisible();
  expect(Date.now() - started).toBeLessThan(15000);
  const id = await ready(page);
  await expect(detail(page)).toContainText("5000 variantes exactas");
  const data = await (await page.request.get(root + "/" + id)).json();
  expect(data.total).toBe(5000);
  expect(data.authorized_by).toBeNull();
  expect(data.progress.prepared).toBe(5000);
  expect(data.progress.processed).toBe(0);
  await modal(page).screenshot({
    path: `artifacts/operations-2r-preview-${info.project.name}.png`,
  });
  await cancel(page);
  const end = await (await page.request.get(root + "/" + id)).json();
  expect(end.counts.CANCELLED).toBe(5000);
});

test("el backend continúa con el proceso navegador cerrado y recupera progreso al reabrir", async ({
  page,
  context,
  browser,
  playwright,
}, info) => {
  const paths = calls.get(page)!;
  const state = await context.storageState();
  const use = info.project.use;
  const options = {
    baseURL: "https://127.0.0.1:8443",
    storageState: state,
    viewport: use.viewport,
    deviceScaleFactor: use.deviceScaleFactor,
    isMobile: use.isMobile,
    hasTouch: use.hasTouch,
    userAgent: use.userAgent,
  };
  const owned = await browser.browserType().launch(use.launchOptions);
  const ownedContext = await owned.newContext(options);
  const restrict = async (route: Route) => {
    const u = new URL(route.request().url());
    if (u.origin !== "https://127.0.0.1:8443")
      throw new Error("Salida del navegador no autorizada");
    paths.push(route.request().method() + " " + u.pathname);
    return route.continue();
  };
  await ownedContext.route("**/*", restrict);
  const monitoring = await playwright.request.newContext({
    baseURL: options.baseURL,
    storageState: state,
  });
  let reopenedContext:
    | Awaited<ReturnType<typeof browser.newContext>>
    | undefined;
  await page.close();
  try {
    page = await ownedContext.newPage();
    await page.goto("/");
    await expect(page.getByTestId("total").locator("strong")).toHaveText(
      "5000",
    );
    await page
      .getByLabel("Buscar productos", { exact: true })
      .fill("BATCH-SYNTHETIC-2");
    await page.getByRole("button", { name: "Buscar", exact: true }).click();
    await expect(page).toHaveURL(/q=BATCH-SYNTHETIC-2/);
    await operations(page);
    await modal(page)
      .getByRole("button", {
        name: "Previsualizar 1111 resultados filtrados",
        exact: true,
      })
      .click();
    const id = await ready(page);
    const started = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/${id}/start`) && r.request().method() === "POST",
    );
    await modal(page)
      .getByRole("button", { name: "Confirmar e iniciar lote", exact: true })
      .click();
    expect((await started).status()).toBe(200);
    const before = await (await monitoring.get(root + "/" + id)).json();
    expect(before.progress.processed).toBeLessThan(before.total);
    const url = page.url();
    await owned.close();
    expect(owned.isConnected()).toBe(false);
    await expect
      .poll(
        async () => {
          const value = await (await monitoring.get(root + "/" + id)).json();
          return value.progress.processed;
        },
        { timeout: 60000 },
      )
      .toBeGreaterThan(before.progress.processed);
    reopenedContext = await browser.newContext(options);
    await reopenedContext.route("**/*", restrict);
    const reopened = await reopenedContext.newPage();
    await reopened.goto(url);
    await expect(reopened.getByTestId("total").locator("strong")).toHaveText(
      "5000",
    );
    await reopened.getByRole("button", { name: /Ver lotes/ }).click();
    await reopened.getByText(/Lotes guardados/).click();
    await reopened
      .getByRole("button", { name: /1111 variantes/ })
      .first()
      .click();
    await expect(detail(reopened)).toHaveAttribute("data-batch-id", id);
    const recovered = await (await monitoring.get(root + "/" + id)).json();
    expect(recovered.progress.processed).toBeGreaterThan(
      before.progress.processed,
    );
    await modal(reopened).screenshot({
      path: `artifacts/operations-2r-progress-${info.project.name}.png`,
    });
    if (
      await modal(reopened)
        .getByRole("button", { name: "Cancelar lote", exact: true })
        .isVisible()
    )
      await cancel(reopened);
    await reopened
      .getByRole("button", { name: "Cerrar lotes", exact: true })
      .click();
    await expect(
      reopened.getByRole("combobox", { name: "Filtrar catálogo" }),
    ).toBeVisible();
  } finally {
    await owned.close();
    await reopenedContext?.close();
    await monitoring.dispose();
  }
});

test("completado con bloqueos abre propuesta exacta y conserva aprobación humana por campo", async ({
  page,
}, info) => {
  await page
    .getByRole("checkbox", { name: "Seleccionar 900001", exact: true })
    .check();
  await page
    .getByRole("checkbox", { name: "Seleccionar 900002", exact: true })
    .check();
  await operations(page, "GENERATE_PROPOSALS");
  await modal(page)
    .getByRole("button", { name: "Previsualizar selección", exact: true })
    .click();
  const id = await ready(page);
  await modal(page)
    .getByRole("button", { name: "Confirmar e iniciar lote", exact: true })
    .click();
  await expect(detail(page)).toHaveAttribute(
    "data-batch-state",
    "COMPLETED_WITH_BLOCKS",
    { timeout: 30000 },
  );
  const result = await (await page.request.get(root + "/" + id)).json();
  expect(result.progress.completed).toBe(1);
  expect(result.progress.blocked).toBe(1);
  expect(result.progress.processed).toBe(2);
  await page
    .locator('[data-batch-ecomm="900001"]')
    .getByRole("button", { name: /Revisar propuesta/ })
    .click();
  await expect(page).toHaveURL(/product=900001.*proposal=/);
  const proposal = page.getByRole("region", {
    name: "Propuestas comerciales documentadas",
  });
  const field = proposal.locator("[data-proposal-field]").first();
  await field.getByText(/Respaldo de este campo/).click();
  await expect(field.locator("blockquote").first()).toBeVisible();
  await field.getByRole("combobox").selectOption("ACCEPTED");
  await proposal
    .getByRole("button", { name: "Registrar revisión individual", exact: true })
    .click();
  await expect(proposal).toContainText("Revisión registrada en PostgreSQL");
  page.once("dialog", (d) => d.accept());
  await proposal
    .getByRole("button", { name: "Guardar selección en ficha", exact: true })
    .click();
  await expect(proposal).toContainText("Selección guardada en PostgreSQL");
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Propuestas comerciales documentadas" }),
  ).toContainText("Selección ya guardada");
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await page.getByRole("dialog").screenshot({
    path: `artifacts/operations-2r-editor-${info.project.name}.png`,
  });
});
