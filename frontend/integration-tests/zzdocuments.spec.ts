import { legacyDocumental } from "./legacy-documental";
import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { Dossier } from "../src/integration/research-adapter";
const id = "900003",
  research = `/api/test-research/${id}`,
  documents = `/api/test-documents/${id}`,
  workspace = `/api/ecomm-app/workspace/${id}`;
const text = readFileSync(
  "integration-fixtures/chia-local-sintetica.txt",
  "utf8",
);
test.setTimeout(90000);
const outside = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page, context }) => {
  const attempts: string[] = [];
  outside.set(page, attempts);
  await context.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== "https://127.0.0.1:8443") {
      attempts.push(route.request().url());
      return route.abort();
    }
    return route.continue();
  });
});
test.afterEach(async ({ page }) => expect(outside.get(page)).toEqual([]));
async function csrf(page: Page) {
  return (await (await page.request.get("/api/auth/me")).json())
    .csrf_token as string;
}
async function post(page: Page, path: string, data: unknown) {
  const response = await page.request.post(path, {
    headers: { "X-CSRF-Token": await csrf(page) },
    data,
  });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}
async function dossier(page: Page): Promise<Dossier> {
  return (await page.request.get(research)).json();
}
async function open(page: Page, reset = true) {
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator(`[data-ecomm-id="${id}"]`)).toBeVisible();
  if (reset) {
    let data = await dossier(page);
    for (const original of data.facts.filter((f) => f.state !== "REJECTED")) {
      const f = data.facts.find((f) => f.id === original.id)!;
      data = await post(page, `${research}/facts/${f.id}/review`, {
        expected_version: data.version,
        expected_fact_version: f.version,
        decision: "REJECTED",
        reason:
          "Preparación explícita de un caso documental sintético independiente.",
      });
    }
    const current = await (await page.request.get(workspace)).json();
    await post(page, workspace, {
      expected_version: current.version,
      status: "DRAFT",
      fields: {
        ...current.fields,
        brand: "Marca sintética KIKI",
        manufacturer: "Fabricante de prueba",
        presentation: "250 g",
        proposed_gtin: "12345670",
        title: "Título anterior de prueba documental",
        description: "Descripción anterior de prueba documental",
      },
    });
  }
  await page
    .locator(`[data-ecomm-id="${id}"]`)
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await expect(
    page.getByLabel("Marca comercial", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await expect(
    page.getByLabel("Documento disponible", { exact: true }),
  ).toBeVisible();
}
async function form(page: Page) {
  const summary = page.getByText(
    "Incorporar archivo local o referencia oficial",
    { exact: true },
  );
  if (
    !(await summary.evaluate(
      (el) => (el.parentElement as HTMLDetailsElement).open,
    ))
  )
    await summary.click();
  await page
    .getByLabel("Cómo obtuve la documentación", { exact: true })
    .fill(
      "Archivo sintético redactado para esta prueba; no corresponde a documentación real de fabricante.",
    );
  await page
    .getByLabel(
      "Declaro que la fuente es oficial; todavía no está verificada",
      { exact: true },
    )
    .check();
  await page
    .getByLabel(
      "Autorizo expresamente el procesamiento local de este documento o referencia",
      { exact: true },
    )
    .check();
}
async function upload(
  page: Page,
  name: string,
  buffer: Buffer,
  mimeType: string,
) {
  await form(page);
  await page
    .getByLabel("Origen a incorporar", { exact: true })
    .selectOption("FILE");
  await page
    .getByLabel("Archivo documental", { exact: true })
    .setInputFiles({ name, mimeType, buffer });
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`${documents}/import`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Incorporar documentación", exact: true })
    .click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const data = (await response.json()) as Dossier;
  await expect(
    page.getByLabel("Documento disponible", { exact: true }),
  ).toHaveValue(data.incorporated_document_id!);
  return data.incorporated_document_id!;
}
async function reviewSource(page: Page) {
  await page
    .getByLabel("Motivo de revisión de procedencia", { exact: true })
    .fill(
      "Contrasté manualmente origen y versión del archivo sintético autorizado.",
    );
  page.once("dialog", (d) => d.accept());
  await page
    .getByRole("button", {
      name: "Registrar revisión de procedencia",
      exact: true,
    })
    .click();
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Revisada por una persona");
}
async function extract(page: Page) {
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`${research}/extract`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Extraer hechos del documento", exact: true })
    .click();
  expect((await pending).status()).toBe(200);
}

test("PDF local, original, procedencia independiente, evidencia aprobada, propuesta y guardado persistente", async ({
  page,
}, info) => {
  await open(page);
  const doc = await upload(
    page,
    `tecnica-${info.project.name}.pdf`,
    readFileSync("integration-fixtures/chia-local-sintetica.pdf"),
    "application/pdf",
  );
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Pendiente de revisión");
  const originalPath = `**${documents}/${doc}/original/1`;
  await page.route(originalPath, async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.content_base64 = Buffer.from("bytes alterados de prueba").toString(
      "base64",
    );
    await route.fulfill({ response, json: body });
  });
  await page
    .getByRole("button", { name: "Comprobar original conservado", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "El original recuperado no coincide",
  );
  await page.unroute(originalPath);
  await page
    .getByRole("button", { name: "Comprobar original conservado", exact: true })
    .click();
  await expect(
    page.getByText("Original v1 recuperado desde PostgreSQL", { exact: false }),
  ).toBeVisible();
  await reviewSource(page);
  await page
    .getByText("Ver documento y ubicaciones verificables", { exact: true })
    .click();
  await expect(page.getByLabel("Vista del documento")).toContainText(
    "pagina/1/linea/",
  );
  await page.getByLabel("Vista del documento").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/documento-local-${info.project.name}.png`,
  });
  await extract(page);
  for (const field of ["product_name", "presentation", "ingredients"]) {
    const card = page.locator(
      `.r-fact[data-document="${doc}"][data-field="${field}"]`,
    );
    await card
      .getByRole("textbox")
      .fill(
        "Contrasté el fragmento y la identidad del producto sintético de prueba.",
      );
    page.once("dialog", (d) => d.accept());
    await card
      .getByRole("button", { name: "Aprobar hecho", exact: true })
      .click();
    await expect(card.locator(".r-state")).toHaveText("Aprobada");
  }
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByRole("button", { name: "Generar propuesta de prueba", exact: true })
    .click();
  await expect(
    page.getByLabel("Propuesta description", { exact: true }),
  ).toHaveValue(/Ingredientes: Semillas de chía/);
  for (const field of ["title", "description"])
    await page
      .getByLabel(`Decisión ${field}`, { exact: true })
      .selectOption("ACCEPTED");
  await page
    .getByRole("button", { name: "Registrar revisión individual", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Guardar selección en ficha",
      exact: true,
    }),
  ).toBeEnabled();
  page.once("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Guardar selección en ficha", exact: true })
    .click();
  await expect(
    page.getByText("Selección guardada en PostgreSQL de pruebas", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Ficha", exact: true }).click();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "Semillas de chía sintéticas · 250 g",
  );
  await page.reload();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "Semillas de chía sintéticas · 250 g",
  );
  await page
    .getByLabel("Descripción larga", { exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/documento-propuesta-${info.project.name}.png`,
  });
});

test("EAN y presentación incompatibles bloquean aprobación aunque la procedencia esté revisada", async ({
  page,
}, info) => {
  await open(page);
  for (const [kind, raw] of [
    ["ean", text.replace("12345670", "12345685")],
    ["pack", text.replace("250 g", "1 kg").replace("Unidad", "Pack")],
  ]) {
    const doc = await upload(
      page,
      `incompatible-${kind}-${info.project.name}.txt`,
      Buffer.from(raw),
      "text/plain",
    );
    await reviewSource(page);
    await extract(page);
    const card = page.locator(`.r-fact[data-document="${doc}"]`).first();
    await expect(card.getByLabel("Bloqueos de evidencia")).toContainText(
      kind === "ean" ? "EAN incompatible" : "Presentación incompatible",
    );
    await card
      .getByRole("textbox")
      .fill("La discrepancia no se puede superar por una coincidencia de SKU.");
    await expect(
      card.getByRole("button", { name: "Aprobar hecho", exact: true }),
    ).toBeDisabled();
  }
});

test("PDF sin texto requiere procesamiento; URL declarada oficial nunca se descarga", async ({
  page,
}, info) => {
  await open(page);
  await upload(
    page,
    `sin-texto-${info.project.name}.pdf`,
    readFileSync("integration-fixtures/etiqueta-sin-texto.pdf"),
    "application/pdf",
  );
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Requiere OCR");
  await expect(
    page.getByRole("button", {
      name: "Extraer hechos del documento",
      exact: true,
    }),
  ).toBeDisabled();
  await page
    .getByLabel("Procedencia del documento local")
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/documento-sin-texto-${info.project.name}.png`,
  });
  await form(page);
  await page
    .getByLabel("Origen a incorporar", { exact: true })
    .selectOption("URL");
  await page
    .getByLabel("URL de referencia (sin acceder)", { exact: true })
    .fill("https://api.mercadolibre.com/no-consultar");
  await page
    .getByRole("button", { name: "Incorporar documentación", exact: true })
    .click();
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Sólo referencia: sin descarga ni extracción");
  await expect(
    page.getByRole("button", {
      name: "Extraer hechos del documento",
      exact: true,
    }),
  ).toBeDisabled();
});

test("reemplazo conserva original y vuelve obsoleta una propuesta; versión vieja de procedencia recibe 409", async ({
  page,
}, info) => {
  await open(page, false);
  let data = await dossier(page);
  let doc = data.documents.find(
    (d) => d.body.title === `tecnica-${info.project.name}.pdf`,
  )!;
  // Explicitly approve the three source-backed facts again for this independent scenario.
  for (const field of ["product_name", "presentation", "ingredients"]) {
    const f = data.facts.find(
      (f) => f.document_id === doc.id && f.field === field,
    )!;
    data = await post(page, `${research}/facts/${f.id}/review`, {
      expected_version: data.version,
      expected_fact_version: f.version,
      decision: "APPROVED",
      reason:
        "Revisión explícita anterior al reemplazo de documento de prueba.",
    });
  }
  const current = await (await page.request.get(workspace)).json();
  const proposal = await post(page, `/api/test-proposals/${id}/generate`, {
    expected_version: current.version,
  });
  await page
    .getByRole("button", {
      name: "Actualizar evidencias guardadas",
      exact: true,
    })
    .click();
  await expect(
    page.getByText(`Versión de investigación: ${data.version}`, {
      exact: false,
    }),
  ).toBeVisible();
  await page
    .getByLabel("Documento disponible", { exact: true })
    .selectOption(doc.id);
  await form(page);
  await page
    .getByLabel(
      "Reemplazar el documento local seleccionado y conservar su historial",
      { exact: true },
    )
    .check();
  const originalVersion = doc.version;
  await upload(
    page,
    `revision-${info.project.name}.txt`,
    Buffer.from(text.replace("600 kcal/100 g", "620 kcal/100 g")),
    "text/plain",
  );
  data = await dossier(page);
  doc = data.documents.find((d) => d.id === doc.id)!;
  expect(doc.version).toBe(originalVersion + 1);
  expect(
    data.facts
      .filter((f) => f.document_id === doc.id)
      .every((f) => f.state === "STALE"),
  ).toBe(true);
  const stored = await (
    await page.request.get(`${documents}/${doc.id}/original/1`)
  ).json();
  expect(Buffer.from(stored.content_base64, "base64")).toEqual(
    readFileSync("integration-fixtures/chia-local-sintetica.pdf"),
  );
  const latest = await (
    await page.request.get(`/api/test-proposals/${id}`)
  ).json();
  expect(latest.draft_id).toBe(proposal.draft_id);
  expect(latest.state).toBe("STALE");
  const response = await page.request.post(
    `${documents}/${doc.id}/provenance`,
    {
      headers: { "X-CSRF-Token": await csrf(page) },
      data: {
        expected_document_version: originalVersion,
        decision: "REVIEWED",
        reason:
          "Una sesión con una base antigua no puede sobrescribir la revisión.",
      },
    },
  );
  expect(response.status()).toBe(409);
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Pendiente de revisión");
});

test.beforeEach(async ({ page }) => {
  await legacyDocumental(page);
});
