import { test, expect, type Page } from "@playwright/test";
import { workspacePath } from "../src/integration/workspace-adapter";

test.beforeEach(async ({ context }) => {
  await context.route("**/*", (route) =>
    new URL(route.request().url()).origin === "https://127.0.0.1:8443"
      ? route.continue()
      : route.abort(),
  );
});
async function open(page: Page, id = "900001") {
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await page
    .locator(`[data-ecomm-id="${id}"]`)
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await expect(
    page.getByLabel("Marca comercial", { exact: true }),
  ).toBeVisible();
}
const field = (page: Page, name: string) =>
  page.getByLabel(name, { exact: true });
async function saved(page: Page) {
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Guardado en PostgreSQL de pruebas" }),
  ).toBeVisible();
}

test("editor completo: todos los campos persisten, recargan e historial conserva versiones", async ({
  page,
}, info) => {
  test.setTimeout(60000);
  await open(page);
  const name = `Almendras de prueba comercial ${info.project.name}`;
  for (const [label, value] of Object.entries({
    "Marca comercial": "Marca sintética KIKI",
    "Fabricante / responsable": "Fabricante de prueba",
    "Título completo": name,
    "Título corto": "Almendras sintéticas",
    "Presentación comercial y packs": "250 g",
    "GTIN/EAN sugerido (si existe)": "12345670",
    "Descripción corta": "Descripción corta de prueba.",
    "Descripción larga":
      "Descripción larga sintética con información comercial de prueba.",
    "Detalles, uso y aclaraciones":
      "Detalles, características y precauciones sintéticos.",
    "Categoría principal": "Dietética de prueba",
    Subcategoría: "Frutos secos",
    "Título SEO": "Almendras sintéticas 250 g",
    "Descripción para buscadores": "Metadescripción de prueba.",
    "Palabras clave / términos relevantes": "almendras, sintético",
    "Observaciones y pendientes": "Ficha exclusivamente sintética.",
  }))
    await field(page, label).fill(value);
  // Replace existing array rows through the existing editor controls, never drop hidden fields.
  for (const label of [
    /Quitar característica/,
    /Quitar recurso/,
    /Quitar fuente/,
  ]) {
    while (await page.getByRole("button", { name: label }).count())
      await page.getByRole("button", { name: label }).first().click();
  }
  await page
    .getByRole("button", { name: "+ Agregar característica", exact: true })
    .click();
  await field(page, "Atributo").fill("Contenido neto");
  await field(page, "Valor comprobado").fill("250 g");
  for (const [index, kind] of ["IMAGE", "VIDEO"].entries()) {
    await page
      .getByRole("button", { name: "+ Agregar imagen o video", exact: true })
      .click();
    await field(page, "Tipo de recurso").nth(index).selectOption(kind);
    await field(page, "URL HTTPS del archivo o video")
      .nth(index)
      .fill(`https://synthetic.invalid/${kind}.test`);
    await field(page, "Descripción / texto alternativo")
      .nth(index)
      .fill(`Recurso sintético ${kind}`);
    await field(page, "Fuente original del recurso")
      .nth(index)
      .fill("https://synthetic.invalid/product");
  }
  await page
    .getByRole("button", {
      name: "+ Registrar fuente verificable",
      exact: true,
    })
    .click();
  await field(page, "Nombre de la fuente").fill("Fabricante de prueba");
  await field(
    page,
    "Enlace HTTPS (obligatorio para fabricante/distribuidor)",
  ).fill("https://synthetic.invalid/product");
  await field(page, "Verificación, fecha o evidencia en envase").fill(
    "Evidencia sintética de la presentación exacta.",
  );
  await page.getByRole("checkbox", { name: /Verifiqué esta fuente/ }).check();
  await expect(page.locator(".i-save-bar")).toContainText(
    "Cambios sin guardar",
  );
  await expect(
    page.locator(".i-editor img,.i-editor video,.i-editor a[target]"),
  ).toHaveCount(0);
  await saved(page);
  const response = await page.request.get(workspacePath("900001"));
  const stored = await response.json();
  expect(stored.fields.title).toBe(name);
  expect(stored.fields.media).toHaveLength(2);
  expect(stored.fields.sources[0].verified).toBe(true);
  expect(stored.fields.proposed_gtin).toBe("12345670");
  for (const [id, label] of [
    ["kiki-identidad", "identidad"],
    ["kiki-contenido", "descripciones"],
    ["kiki-seo", "seo"],
    ["kiki-atributos", "atributos"],
    ["kiki-multimedia", "multimedia"],
    ["kiki-fuentes", "fuentes"],
  ]) {
    await page.locator(`#${id}`).scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `artifacts/editor-${label}-${info.project.name}.png`,
    });
  }
  await page.getByRole("button", { name: "Cerrar ficha" }).click();
  await page
    .locator('[data-ecomm-id="900001"]')
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await expect(field(page, "Título completo")).toHaveValue(name);
  await page.reload();
  await expect(field(page, "Título completo")).toHaveValue(name);
  await expect(field(page, "Fabricante / responsable")).toHaveValue(
    "Fabricante de prueba",
  );
  await expect(field(page, "URL HTTPS del archivo o video")).toHaveCount(2);
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Historial persistido en KIKI" }),
  ).toBeVisible();
  await expect(page.getByRole("tabpanel")).toContainText(
    `Versión actual guardada: ${stored.version}`,
  );
  await page.getByRole("tabpanel").locator("summary").first().click();
  await expect(page.getByRole("tabpanel")).toContainText(name);
  await page.screenshot({
    path: `artifacts/editor-historial-${info.project.name}.png`,
  });
});

test("protege cambios sin guardar al cerrar, cambiar variante y usar atrás", async ({
  page,
}, info) => {
  await open(page, "900002");
  await field(page, "Título completo").fill(
    `Pendiente de revisión ${info.project.name}`,
  );
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Cerrar ficha" }).click();
  await expect(
    page.getByRole("dialog", { name: "Ficha 900002" }),
  ).toBeVisible();
  await expect(field(page, "Título completo")).toHaveValue(
    `Pendiente de revisión ${info.project.name}`,
  );
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await page.getByRole("tab", { name: "Ficha", exact: true }).click();
  await expect(field(page, "Título completo")).toHaveValue(
    `Pendiente de revisión ${info.project.name}`,
  );
  await page.goBack();
  await expect(
    page.getByRole("tab", { name: "Evidencias", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.goBack();
  await expect(
    page.getByRole("tab", { name: "Ficha", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.goBack();
  await expect(page).toHaveURL(/product=900002/);
  await expect(
    page.getByRole("dialog", { name: "Ficha 900002" }),
  ).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Cerrar ficha" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("validaciones y completitud se mantienen en backend; estados son internos", async ({
  page,
}, info) => {
  await open(page, "900003");
  await field(page, "Marca comercial").fill(
    `Marca de prueba ${info.project.name}`,
  );
  await field(page, "GTIN/EAN sugerido (si existe)").fill("123");
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("verificador válido");
  await expect(field(page, "GTIN/EAN sugerido (si existe)")).toHaveValue("123");
  await field(page, "GTIN/EAN sugerido (si existe)").fill("");
  await field(page, "Estado editorial").selectOption("READY_FOR_CHANNELS");
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Guardar estado editorial", exact: true })
    .click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(field(page, "Estado editorial")).toHaveValue(
    "READY_FOR_CHANNELS",
  );
  await saved(page);
  const stored = await (await page.request.get(workspacePath("900003"))).json();
  expect(stored.status).toBe("DRAFT");
  expect(stored.external_writes_enabled).toBe(false);
});

test("dos sesiones simultáneas: una guarda, otra compara y decide sin sobrescritura", async ({
  page,
  browser,
}, info) => {
  const context = await browser.newContext({
    baseURL: "https://127.0.0.1:8443",
    viewport:
      info.project.name === "mobile"
        ? { width: 390, height: 844 }
        : { width: 1440, height: 1080 },
  });
  const second = await context.newPage();
  await context.route("**/*", (route) =>
    new URL(route.request().url()).origin === "https://127.0.0.1:8443"
      ? route.continue()
      : route.abort(),
  );
  try {
    await open(page, "900004");
    await open(second, "900004");
    const firstText = `Operador A ${info.project.name}`,
      secondText = `Operador B ${info.project.name}`;
    await field(page, "Título completo").fill(firstText);
    await field(second, "Título completo").fill(secondText);
    let count = 0;
    let release!: () => void;
    const barrier = new Promise<void>((resolve) => {
      release = resolve;
    });
    for (const target of [page, second])
      await target.route(`**${workspacePath("900004")}`, async (route) => {
        if (route.request().method() === "POST") {
          count++;
          if (count === 2) release();
          if (count <= 2) await barrier;
        }
        await route.continue();
      });
    const statuses: number[] = [];
    for (const target of [page, second])
      target.on("response", (response) => {
        if (
          response.url().endsWith(workspacePath("900004")) &&
          response.request().method() === "POST"
        )
          statuses.push(response.status());
      });
    await Promise.all([
      page
        .getByRole("button", { name: "Guardar borrador", exact: true })
        .click(),
      second
        .getByRole("button", { name: "Guardar borrador", exact: true })
        .click(),
    ]);
    await expect.poll(() => statuses.sort()).toEqual([200, 409]);
    const stored = await (
      await page.request.get(workspacePath("900004"))
    ).json();
    const losing = stored.fields.title === firstText ? second : page;
    const localText =
      stored.fields.title === firstText ? secondText : firstText;
    await expect(losing.getByLabel("Comparar versiones")).toBeVisible();
    await expect(field(losing, "Título completo")).toHaveValue(localText);
    await expect(
      losing.getByRole("button", { name: "Guardar borrador", exact: true }),
    ).toBeDisabled();
    await losing.screenshot({
      path: `artifacts/editor-conflicto-${info.project.name}.png`,
    });
    losing.once("dialog", (dialog) => dialog.accept());
    await losing
      .getByRole("button", {
        name: "Conservar mi edición para revisar",
        exact: true,
      })
      .click();
    expect(
      (await (await page.request.get(workspacePath("900004"))).json()).version,
    ).toBe(stored.version);
    await saved(losing);
    const final = await (
      await page.request.get(workspacePath("900004"))
    ).json();
    expect(final.version).toBe(stored.version + 1);
    expect(final.fields.title).toBe(localText);
  } finally {
    await context.close();
  }
});

test("identidad incompatible bloquea el botón y no emite POST", async ({
  page,
}) => {
  await open(page, "900005");
  await page.getByRole("button", { name: "Cerrar ficha" }).click();
  const original = await (
    await page.request.get(workspacePath("900005"))
  ).json();
  original.source_sku_changed = true;
  let writes = 0;
  await page.route(`**${workspacePath("900005")}`, (route) => {
    if (route.request().method() === "POST") {
      writes++;
      return route.abort();
    }
    return route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "X-Kiki-Environment": "local-synthetic",
      },
      body: JSON.stringify(original),
    });
  });
  await page
    .locator('[data-ecomm-id="900005"]')
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await expect(page.getByRole("alert")).toContainText("identidad");
  await expect(
    page.getByRole("button", { name: "Guardar borrador", exact: true }),
  ).toBeDisabled();
  expect(writes).toBe(0);
});

test("sesión vencida conserva edición, reautentica y requiere guardar explícitamente", async ({
  page,
  context,
}, info) => {
  await open(page, "900005");
  const value = `Sesión recuperada ${info.project.name}`;
  await field(page, "Título completo").fill(value);
  await context.clearCookies();
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(
    page.getByRole("form", { name: "Restablecer sesión" }),
  ).toBeVisible();
  await expect(field(page, "Título completo")).toHaveValue(value);
  await page
    .getByLabel("Contraseña de prueba", { exact: true })
    .fill("solo-datos-sinteticos");
  await page
    .getByRole("button", { name: "Restablecer sesión", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Sesión restablecida" }),
  ).toBeVisible();
  await expect(field(page, "Título completo")).toHaveValue(value);
  await saved(page);
});
