import { test, expect, type Page } from "@playwright/test";
const outbound = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const requests: string[] = [];
  outbound.set(page, requests);
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== "http://127.0.0.1:4173") {
      requests.push(route.request().url());
      return route.abort();
    }
    return route.continue();
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tu catálogo, en un solo lugar." }),
  ).toBeVisible();
});
test.afterEach(async ({ page }) => {
  expect(outbound.get(page)).toEqual([]);
});
const open = async (page: Page, id = "DEMO-1001") => {
  await page.getByRole("button", { name: `Abrir ${id}`, exact: true }).click();
  return page.getByRole("dialog");
};
async function tool(page: Page, name: string) {
  await page.getByRole("button", { name, exact: true }).click();
  return page.getByRole("region", { name, exact: true });
}
async function select(work: ReturnType<Page["getByRole"]>, id: string) {
  await work
    .getByRole("checkbox")
    .filter({ hasNotText: "Comparé" })
    .first()
    .waitFor();
  await work
    .locator("label")
    .filter({ hasText: id })
    .getByRole("checkbox")
    .check();
}

test("edita ficha, guarda borrador, consulta versión y conserva búsqueda y filtros", async ({
  page,
}, info) => {
  await page.getByRole("textbox", { name: "Buscar productos" }).fill("BOT-750");
  await page.getByLabel("Marca", { exact: true }).selectOption("Monte");
  const panel = await open(page);
  await panel
    .getByLabel("Nombre", { exact: true })
    .fill("Botella de excursión demo");
  await panel
    .getByLabel("Descripción", { exact: true })
    .fill("Descripción revisada por el operador de muestra.");
  await panel
    .getByLabel("Imagen de muestra")
    .selectOption("Vista lateral de muestra");
  await expect(panel.getByText("Tenés cambios sin guardar.")).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Preparar ficha", exact: true }),
  ).toBeDisabled();
  await panel.getByRole("tab", { name: "Historial", exact: true }).click();
  const alert = page.getByRole("alertdialog");
  await expect(alert).toBeVisible();
  await alert.getByRole("button", { name: "Seguir editando" }).click();
  await expect(panel.getByLabel("Nombre", { exact: true })).toHaveValue(
    "Botella de excursión demo",
  );
  await page.screenshot({
    path: `artifacts/edicion-${info.project.name}.png`,
    scale: "css",
  });
  await panel.getByRole("button", { name: "Guardar borrador" }).click();
  await expect(panel.getByRole("status")).toContainText("Borrador guardado");
  await panel.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(panel).toContainText("Operador demo");
  await panel
    .getByRole("button", { name: "Consultar versión 1", exact: true })
    .click();
  await expect(
    panel.getByRole("region", { name: "Versión anterior" }),
  ).toContainText("Botella térmica · 750 ml");
  await expect(
    panel.getByRole("heading", { name: "Botella de excursión demo" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cerrar ficha" }).click();
  await expect(page).toHaveURL(/q=BOT-750/);
  await expect(page).toHaveURL(/brand=Monte/);
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
  await expect(
    page.locator(".d-table tbody tr").filter({ hasText: "DEMO-1006" }),
  ).toContainText("coral");
});

test("aviso de cambios sin guardar protege Escape, pestañas, atrás y descarte", async ({
  page,
}) => {
  const panel = await open(page);
  await panel.getByLabel("Nombre", { exact: true }).fill("Edición no guardada");
  await page.keyboard.press("Escape");
  const alert = page.getByRole("alertdialog");
  await expect(alert).toBeVisible();
  await alert.getByRole("button", { name: "Seguir editando" }).click();
  await expect(panel.getByLabel("Nombre", { exact: true })).toHaveValue(
    "Edición no guardada",
  );
  await page.goBack();
  await expect(alert).toBeVisible();
  await alert.getByRole("button", { name: "Seguir editando" }).click();
  await expect(panel.getByLabel("Nombre", { exact: true })).toHaveValue(
    "Edición no guardada",
  );
  await panel.getByRole("tab", { name: "IA", exact: true }).click();
  await alert.getByRole("button", { name: "Descartar y continuar" }).click();
  await expect(
    panel.getByRole("tab", { name: "IA", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await panel.getByRole("tab", { name: "Ficha", exact: true }).click();
  await expect(panel.getByLabel("Nombre", { exact: true })).toHaveValue(
    "Botella térmica · 750 ml",
  );
});

test("genera, edita, acepta y descarta IA simulada con confirmación e historial", async ({
  page,
}, info) => {
  const panel = await open(page);
  await panel.getByRole("tab", { name: "IA", exact: true }).click();
  await panel
    .getByRole("button", { name: "Generar propuesta simulada" })
    .click();
  await expect(panel).toContainText("plantilla local KIKI demo");
  await panel
    .getByLabel("Propuesta editable")
    .fill("Descripción editorial aceptada en demostración.");
  await page.screenshot({
    path: `artifacts/ia-${info.project.name}.png`,
    scale: "css",
  });
  await panel.getByRole("button", { name: "Aceptar propuesta" }).click();
  await panel.getByRole("button", { name: "Confirmar decisión" }).click();
  await expect(panel.getByRole("status")).toContainText(
    "Propuesta IA aceptada",
  );
  await panel.getByRole("tab", { name: "Ficha", exact: true }).click();
  await expect(panel.getByLabel("Descripción", { exact: true })).toHaveValue(
    "Descripción editorial aceptada en demostración.",
  );
  await panel.getByRole("tab", { name: "IA", exact: true }).click();
  await panel
    .getByRole("button", { name: "Generar propuesta simulada" })
    .click();
  await panel.getByRole("button", { name: "Descartar propuesta" }).click();
  await expect(panel).toContainText("Estado: Descartada");
  await panel.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(panel).toContainText("Propuesta IA descartada");
});

test("resuelve conflicto fundamentado, prepara canal sin confirmar publicación", async ({
  page,
}, info) => {
  const panel = await open(page, "DEMO-1006");
  await panel.getByRole("tab", { name: "Canales", exact: true }).click();
  await expect(
    panel.getByRole("button", { name: "Preparar para ML" }),
  ).toBeDisabled();
  await panel.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await expect(
    panel.getByRole("button", { name: "Aceptar candidato" }),
  ).toBeDisabled();
  await panel
    .getByLabel("Fundamento de la decisión")
    .fill("Comparé color coral, presentación de 750 ml y Ecomm ID DEMO-1006.");
  await expect(
    panel.getByRole("button", { name: "Aceptar candidato" }),
  ).toBeDisabled();
  await panel.getByRole("checkbox").check();
  await panel.getByRole("button", { name: "Aceptar candidato" }).click();
  await page.screenshot({
    path: `artifacts/evidencias-${info.project.name}.png`,
    scale: "css",
  });
  await panel.getByRole("button", { name: "Confirmar decisión" }).click();
  await expect(panel).toContainText("Aceptada");
  await panel.getByRole("tab", { name: "Canales", exact: true }).click();
  await expect(panel).toContainText("Publicación no confirmada.");
  await panel.getByRole("button", { name: "Preparar para ML" }).click();
  await panel.getByRole("button", { name: "Confirmar decisión" }).click();
  await expect(panel).toContainText("Preparada internamente");
  await expect(panel).toContainText("Publicación no confirmada.");
  await page.screenshot({
    path: `artifacts/canales-${info.project.name}.png`,
    scale: "css",
  });
  await panel.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(panel).toContainText("Evidencia aceptada");
  await page.screenshot({
    path: `artifacts/historial-${info.project.name}.png`,
    scale: "css",
  });
});

test("lotes omiten conflictos, muestran resultados y preservan contexto", async ({
  page,
}, info) => {
  await page.getByRole("textbox", { name: "Buscar productos" }).fill("BOT-750");
  const work = await tool(page, "Preparación por lotes");
  await work
    .getByRole("button", { name: "Seleccionar las 8 variantes de muestra" })
    .click();
  await work.getByRole("button", { name: "Revisar selección (8)" }).click();
  await expect(work).toContainText("Se omitirá: Conflicto de identidad");
  await page.screenshot({
    path: `artifacts/lotes-${info.project.name}.png`,
    fullPage: true,
    scale: "css",
  });
  await work
    .getByRole("button", { name: "Confirmar trabajo simulado" })
    .click();
  await expect(work.getByRole("status")).toContainText(
    "6 variantes preparadas internamente; 2 omitidas",
  );
  await expect(page).toHaveURL(/q=BOT-750/);
  await expect(page).toHaveURL(/tool=/);
  await work.getByRole("button", { name: "Ver trabajos y resultados" }).click();
  const jobs = page.getByRole("region", {
    name: "Trabajos y resultados",
    exact: true,
  });
  await jobs.getByRole("button", { name: "Ver resultado DEMO-JOB-1" }).click();
  await expect(jobs.getByRole("status")).toContainText("DEMO-1006");
  await jobs.getByRole("button", { name: "Cerrar herramienta" }).click();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
});

test("herramientas de actualización, familias, conciliación, evidencias, IA y diagnóstico completan flujo", async ({
  page,
}) => {
  for (const name of [
    "Actualización de catálogo",
    "Familias SKU y duplicados",
    "Conciliación de canales",
    "Evidencias y conflictos",
    "Propuestas IA",
    "Diagnóstico operativo",
  ]) {
    const work = await tool(page, name);
    await select(work, "DEMO-1006");
    await work.getByRole("button", { name: "Revisar selección (1)" }).click();
    if (
      [
        "Familias SKU y duplicados",
        "Conciliación de canales",
        "Evidencias y conflictos",
      ].includes(name)
    ) {
      await expect(
        work.getByRole("button", { name: "Confirmar trabajo simulado" }),
      ).toBeDisabled();
      await work.getByRole("checkbox").check();
      await work
        .getByLabel("Fundamento de la revisión")
        .fill(
          "Identidad coral y Ecomm ID revisados individualmente en fixture.",
        );
    }
    await work
      .getByRole("button", { name: "Confirmar trabajo simulado" })
      .click();
    await expect(work.getByRole("status")).toContainText("Trabajo completado");
    await expect(page).toHaveURL(/^http:\/\/127.0.0.1:4173\/\?/);
  }
  const work = await tool(page, "Trabajos y resultados");
  await expect(work.getByText(/Completado \(demo\)/)).toHaveCount(6);
  await work.getByRole("button", { name: "Ver resultado DEMO-JOB-6" }).click();
  await expect(work.getByRole("status")).toContainText(
    "Diagnóstico de 1 variantes",
  );
});

test("filtros por conflicto y siguiente acción, conteos separados y prioridad", async ({
  page,
}) => {
  await expect(
    page.getByRole("region", { name: "Progreso del catálogo" }),
  ).toContainText("7 productos base · 8 variantes");
  await expect(page.locator(".d-table tbody tr").first()).toContainText(
    "Conflicto",
  );
  await page.getByLabel("Conflicto", { exact: true }).selectOption("yes");
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
  await page
    .getByLabel("Siguiente acción", { exact: true })
    .selectOption("Resolver conflicto");
  await page.reload();
  await expect(page.getByLabel("Conflicto", { exact: true })).toHaveValue(
    "yes",
  );
  await expect(
    page.getByLabel("Siguiente acción", { exact: true }),
  ).toHaveValue("Resolver conflicto");
  await page
    .locator(".d-table tbody tr")
    .first()
    .getByRole("button", { name: "Resolver tarea" })
    .click();
  await expect(
    page.getByRole("tab", { name: "Evidencias", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
});
