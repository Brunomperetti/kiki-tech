import { legacyDocumental } from "./legacy-documental";
import { test, expect, type Page } from "@playwright/test";
import type {
  Dossier,
  AssistedCandidate,
} from "../src/integration/research-adapter";
const id = "900005",
  root = `/api/test-research/${id}`,
  api = `/api/test-discovery/${id}`,
  workspace = `/api/ecomm-app/workspace/${id}`;
test.setTimeout(90000);
const attempts = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page, context }) => {
  const blocked: string[] = [];
  attempts.set(page, blocked);
  await context.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== "https://127.0.0.1:8443") {
      blocked.push(route.request().url());
      return route.abort();
    }
    return route.continue();
  });
});
test.afterEach(async ({ page }) => expect(attempts.get(page)).toEqual([]));
async function csrf(page: Page) {
  return (await (await page.request.get("/api/auth/me")).json())
    .csrf_token as string;
}
async function post(page: Page, path: string, data: unknown) {
  const r = await page.request.post(path, {
    headers: { "X-CSRF-Token": await csrf(page) },
    data,
  });
  expect(r.status(), await r.text()).toBe(200);
  return r.json();
}
async function get(page: Page): Promise<Dossier> {
  return (await page.request.get(root)).json();
}
async function open(
  page: Page,
  options: { missing?: boolean; wrong?: boolean } = {},
) {
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator(`[data-ecomm-id="${id}"]`)).toBeVisible();
  let data = await get(page);
  for (const item of data.facts.filter((f) => f.state === "APPROVED")) {
    const f = data.facts.find((f) => f.id === item.id)!;
    data = await post(page, `${root}/facts/${f.id}/review`, {
      expected_version: data.version,
      expected_fact_version: f.version,
      decision: "REJECTED",
      reason:
        "Preparación explícita de un nuevo recorrido con fuentes sintéticas.",
    });
  }
  const record = await (await page.request.get(workspace)).json();
  await post(page, workspace, {
    expected_version: record.version,
    status: "DRAFT",
    fields: {
      ...record.fields,
      title: "Título anterior para comparar investigación",
      description: "Descripción anterior de prueba",
      presentation: "500 g",
      attributes: [],
      brand: options.missing ? "" : "Marca sintética KIKI",
      manufacturer: options.missing
        ? ""
        : options.wrong
          ? "Fabricante editado no verificado"
          : "Fabricante de prueba",
      proposed_gtin: options.wrong ? "2000000000046" : "",
    },
  });
  await page
    .locator(`[data-ecomm-id="${id}"]`)
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await expect(
    page.getByLabel("Marca comercial", { exact: true }),
  ).toBeVisible();
  const pending = page.waitForResponse(
    (r) => r.url().endsWith(`${api}/start`) && r.request().method() === "POST",
  );
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Investigar y completar ficha con IA",
      exact: true,
    })
    .click();
  expect((await pending).status()).toBe(200);
  await expect(
    page.getByLabel("Investigación asistida de fabricantes"),
  ).toBeVisible();
  await expect(
    page.locator('[data-source-id="avena-500-sitio"]'),
  ).toBeVisible();
}
const candidate = (page: Page, suffix: string) =>
  page.locator(`[data-source-id="avena-500-${suffix}"]`);
async function choose(page: Page, suffix: string) {
  const card = candidate(page, suffix);
  await card
    .getByRole("textbox")
    .fill(
      "Selecciono esta fuente sintética para revisar identidad y procedencia, sin aprobar datos.",
    );
  await card
    .getByRole("button", { name: "Seleccionar para revisión", exact: true })
    .click();
  await expect(card).toContainText("Seleccionada para revisión");
  return card;
}
async function acquire(page: Page, suffix: string) {
  const card = await choose(page, suffix);
  const pending = page.waitForResponse(
    (r) => r.url().endsWith("/acquire") && r.request().method() === "POST",
  );
  page.once("dialog", (d) => d.accept());
  await card
    .getByRole("button", { name: "Incorporar documento simulado", exact: true })
    .click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const value = (await response.json()) as Dossier;
  await expect(
    page.getByLabel("Documento disponible", { exact: true }),
  ).toHaveValue(value.incorporated_document_id!);
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Fuente SIMULADA");
  return value.incorporated_document_id!;
}
async function origin(page: Page, key: string) {
  await page
    .getByLabel("Documento disponible", { exact: true })
    .selectOption(key);
  await page
    .getByLabel("Motivo de revisión de procedencia", { exact: true })
    .fill(
      "Revisé la procedencia de este fixture, sin comprobar una fuente auténtica de Internet.",
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
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`${root}/extract`) && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Extraer hechos del documento", exact: true })
    .click();
  expect((await pending).status()).toBe(200);
}
async function approve(page: Page, key: string, field: string) {
  const card = page.locator(
    `.r-fact[data-document="${key}"][data-field="${field}"]`,
  );
  await card
    .getByRole("textbox")
    .fill(
      "Verifiqué el dato y su cita contra el documento sintético de esta variante.",
    );
  page.once("dialog", (d) => d.accept());
  await card
    .getByRole("button", { name: "Aprobar hecho", exact: true })
    .click();
  await expect(card.locator(".r-state")).toHaveText("Aprobada");
}

test("investigar desde ficha, candidatos simulados, ingesta, aprobación y guardado versionado sin salir del dashboard", async ({
  page,
}, info) => {
  await open(page);
  await candidate(page, "sitio")
    .getByText("Contrastar identidad y presentación", { exact: true })
    .click();
  await candidate(page, "sitio").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/investigacion-asistida-${info.project.name}.png`,
  });
  const key = await acquire(page, "tecnica");
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Pendiente de revisión");
  await origin(page, key);
  const sodium = page.locator(
    `.r-fact[data-document="${key}"][data-field="nutrition.sodium"]`,
  );
  await expect(sodium).toContainText("10 mg/100 g");
  const certificate = page.locator(
    `.r-fact[data-document="${key}"][data-field="certification"]`,
  );
  await expect(certificate.getByLabel("Bloqueos de evidencia")).toContainText(
    "sin respaldo documental específico",
  );
  for (const field of [
    "product_name",
    "presentation",
    "ingredients",
    "certification_evidence",
    "certification",
  ])
    await approve(page, key, field);
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByRole("button", { name: "Generar propuesta de prueba", exact: true })
    .click();
  await expect(
    page.getByLabel("Propuesta description", { exact: true }),
  ).toHaveValue(/Certificación declarada: Sin gluten/);
  await expect(
    page.getByLabel("Propuesta description", { exact: true }),
  ).not.toHaveValue(/Sodio:/);
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
    "Avena sintética · 500 g",
  );
  await page.reload();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "Avena sintética · 500 g",
  );
  await page
    .getByLabel("Descripción larga", { exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/investigacion-guardada-${info.project.name}.png`,
  });
});

test("sin EAN, marca o fabricante no inventa datos de la captura ni usa SKU como identidad", async ({
  page,
}) => {
  await open(page, { missing: true });
  await page
    .getByText("Datos utilizados y campos no disponibles", { exact: true })
    .click();
  const data = await get(page);
  expect(data.assisted!.query_context.query.ean).toBeNull();
  expect(data.assisted!.query_context.query.brand).toBeNull();
  expect(data.assisted!.query_context.query.manufacturer).toBeNull();
  expect(data.assisted!.query_context.provenance.brand).toContain(
    "No disponible",
  );
  await expect(candidate(page, "tecnica")).toContainText(
    "Contraste incompleto",
  );
  await expect(candidate(page, "pista")).toContainText(
    "Pista pública · No clasificada como oficial",
  );
});

test("EAN incorrecto y fabricante distinto permanecen discrepancias aunque se declare oficial", async ({
  page,
}, info) => {
  await open(page, { wrong: true });
  const card = candidate(page, "tecnica");
  await card
    .getByText("Contrastar identidad y presentación", { exact: true })
    .click();
  await expect(card).toContainText("EAN: Discrepancia");
  await expect(card).toContainText("Fabricante: Discrepancia");
  await expect(card).toContainText("Procedencia sin comprobar");
  await card.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/investigacion-discrepancias-${info.project.name}.png`,
  });
});

test("fuentes contradictorias bloquean energía e insuficiente no simula extracción exitosa", async ({
  page,
}) => {
  await open(page);
  const first = await acquire(page, "tecnica"),
    second = await acquire(page, "contradiccion");
  await origin(page, first);
  await origin(page, second);
  for (const key of [first, second]) {
    const card = page.locator(
      `.r-fact[data-document="${key}"][data-field="nutrition.energy"]`,
    );
    await expect(card.getByLabel("Bloqueos de evidencia")).toContainText(
      "contradictorio",
    );
    await expect(
      card.getByRole("button", { name: "Aprobar hecho", exact: true }),
    ).toBeDisabled();
  }
  await acquire(page, "insuficiente");
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Información insuficiente");
  await expect(
    page.getByRole("button", {
      name: "Extraer hechos del documento",
      exact: true,
    }),
  ).toBeDisabled();
});

test("otra sesión decide primero: 409, motivo conservado e historial sin sobrescritura", async ({
  page,
}) => {
  await open(page);
  const data = await get(page),
    source = data.assisted!.candidates.find(
      (c) => c.source_id === "avena-500-tecnica",
    ) as AssistedCandidate;
  await post(page, `${api}/candidates/${source.id}/decision`, {
    expected_version: data.version,
    run_id: data.assisted!.run_id,
    expected_candidate_version: source.version,
    decision: "REJECTED",
    reason: "Otra sesión rechazó primero esta fuente sintética con su motivo.",
  });
  const card = candidate(page, "tecnica"),
    reason =
      "Conservo este motivo local al detectar la decisión de otra sesión.";
  await card.getByRole("textbox").fill(reason);
  const pending = page.waitForResponse(
    (r) => r.url().endsWith("/decision") && r.request().method() === "POST",
  );
  await card
    .getByRole("button", { name: "Seleccionar para revisión", exact: true })
    .click();
  expect((await pending).status()).toBe(409);
  await expect(page.getByRole("alert")).toContainText("investigación cambió");
  await expect(card.getByRole("textbox")).toHaveValue(reason);
  await expect(card).toContainText("Rechazada");
  await card
    .getByText("Decisiones anteriores de la fuente", { exact: false })
    .click();
  await expect(card).toContainText("Otra sesión rechazó primero");
});

test.beforeEach(async ({ page }) => {
  await legacyDocumental(page);
});
