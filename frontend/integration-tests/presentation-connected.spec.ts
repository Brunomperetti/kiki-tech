import { test, expect, type Page } from "@playwright/test";
import type { Dossier } from "../src/integration/research-adapter";
import {
  hileretUnitId,
  hileretPackId,
  hileretOriginalSha,
} from "../src/integration/hileret-pilot";
test.skip(
  process.env.KIKI_PRESENTATION_SCENARIO !== "local-synthetic",
  "Escenario explícito de presentación, sin proveedores.",
);
test.setTimeout(180000);
const root = "/api/ecomm-app/workspace/900003";
const reason =
  "RECORRIDO AUTOMATIZADO DE PRUEBA para la presentación; datos sintéticos, no aprobación efectiva del cliente.";
const calls = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page, context }) => {
  const paths: string[] = [];
  calls.set(page, paths);
  await context.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (u.origin !== "https://127.0.0.1:8443")
      throw new Error("Conexión externa prohibida");
    paths.push(route.request().method() + " " + u.pathname);
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
      .filter((p) =>
        /\/suggest$|oauth|sync|refresh|publish|openai|\/step$/.test(p),
      ),
  ).toEqual([]);
});
async function open(page: Page) {
  await page.getByLabel("Buscar productos", { exact: true }).fill("DEMO-CHIA");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(1);
  await page
    .locator('[data-ecomm-id="900003"]')
    .getByRole("button", { name: "Ver ficha", exact: true })
    .click();
}

test("presentación integral: evidencia → comparación → revisión → persistencia → canales → lote", async ({
  page,
}, info) => {
  const initial = await (await page.request.get(root)).json();
  if (initial.fields.title) {
    const session = await (await page.request.get("/api/auth/me")).json();
    const reset = await page.request.post(root, {
      headers: { "X-CSRF-Token": session.csrf_token },
      data: {
        expected_version: initial.version,
        status: "DRAFT",
        fields: {
          ...initial.fields,
          title: "Ficha inicial sintética del recorrido de prueba",
        },
      },
    });
    expect(reset.status()).toBe(200);
  }
  await page.screenshot({
    path: `artifacts/presentacion-guillermo-dashboard-${info.project.name}.png`,
    fullPage: false,
  });
  await open(page);
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  const source = page.getByLabel("Procedencia del documento local");
  await expect(source).toContainText("inventado");
  await page
    .getByLabel("Motivo de revisión de procedencia", { exact: true })
    .fill(reason);
  page.once("dialog", (d) => d.accept());
  await page
    .getByRole("button", {
      name: "Registrar revisión de procedencia",
      exact: true,
    })
    .click();
  await expect(source).toContainText("Revisada por una persona");
  await page
    .getByRole("button", { name: "Extraer hechos del documento", exact: true })
    .click();
  const evidence: Dossier = await (
    await page.request.get(root + "/evidence")
  ).json();
  const doc = evidence.documents.find(
    (d) => d.body.title === "presentacion-chia-exclusivamente-sintetica.txt",
  )!;
  expect(doc).toBeTruthy();
  const facts = evidence.facts.filter(
    (f) => f.document_id === doc.id && f.document_version === doc.version,
  );
  expect(facts.length).toBeGreaterThan(6);
  for (const f of facts) {
    const card = page
      .locator(".r-fact")
      .filter({ has: page.getByLabel(`Motivo ${f.id}`, { exact: true }) });
    await card.getByRole("textbox").fill(reason);
    page.once("dialog", (d) => d.accept());
    await card
      .getByRole("button", { name: "Aprobar hecho", exact: true })
      .click();
    await expect(card.locator(".r-state")).toHaveText("Aprobada");
  }
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByText("Preparación avanzada para IA real · Desactivada", {
      exact: true,
    })
    .click();
  await page
    .getByRole("button", {
      name: "Consultar servicio OpenAI existente (sin generar)",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("region", { name: "Servicio OpenAI existente" }),
  ).toContainText("Desactivado");
  await page
    .getByRole("button", {
      name: "Ver contrato de hechos aprobados",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("region", { name: "Contrato de generación respaldada" }),
  ).toContainText("Llamadas externas: 0");
  await page
    .getByText("Preparación avanzada para IA real · Desactivada", {
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Generar propuesta de prueba", exact: true })
    .click();
  const panel = page.getByRole("region", {
    name: "Propuestas comerciales documentadas",
  });
  await expect(
    panel.locator('[data-proposal-field="seo_title"]'),
  ).toBeVisible();
  for (const key of [
    "title",
    "description",
    "details",
    "seo_title",
    "seo_description",
  ]) {
    const field = panel.locator(`[data-proposal-field="${key}"]`);
    await expect(field).toBeVisible();
    await field
      .getByRole("combobox")
      .selectOption(key === "seo_description" ? "REJECTED" : "ACCEPTED");
  }
  await panel
    .locator('[data-proposal-field="title"]')
    .getByText(/Respaldo de este campo/)
    .click();
  await expect(
    panel.locator('[data-proposal-field="title"] blockquote').first(),
  ).toBeVisible();
  await panel
    .getByRole("button", { name: "Registrar revisión individual", exact: true })
    .click();
  await expect(panel).toContainText("Revisión registrada en PostgreSQL");
  await page.getByRole("dialog").screenshot({
    path: `artifacts/presentacion-guillermo-propuesta-${info.project.name}.png`,
  });
  const before = await (await page.request.get(root)).json();
  page.once("dialog", (d) => d.accept());
  await panel
    .getByRole("button", { name: "Guardar selección en ficha", exact: true })
    .click();
  await expect(panel).toContainText("Selección guardada en PostgreSQL");
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Propuestas comerciales documentadas" }),
  ).toContainText("Selección ya guardada");
  const after = await (await page.request.get(root)).json();
  expect(after.version).toBeGreaterThan(before.version);
  expect(after.fields.title).toContain("chía");
  expect(after.fields.seo_description).toBe(before.fields.seo_description);
  await page.getByRole("tab", { name: "Canales", exact: true }).click();
  await expect(page.getByLabel("Canales por variante API")).toContainText(
    /candidata|pendiente/i,
  );
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(/Versión|versión/);
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await page
    .getByRole("checkbox", { name: "Seleccionar 900003", exact: true })
    .check();
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Operación del lote" })
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
    "Completado: 1",
  );
  await page.getByRole("dialog").screenshot({
    path: `artifacts/presentacion-guillermo-lote-${info.project.name}.png`,
  });
});

test("Hileret auténtico disponible, sin aprobaciones ni identidad real; OpenAI ajeno y POST bloqueados", async ({
  page,
}, info) => {
  const r = await (
    await page.request.get("/api/test-commercial-pilot/hileret-200")
  ).json();
  const unit = r.cases.find(
    (c: { test_id: string }) => c.test_id === hileretUnitId,
  );
  const pack = r.cases.find(
    (c: { test_id: string }) => c.test_id === hileretPackId,
  );
  expect(unit.original_pdf_available).toBe(true);
  expect(unit.approved_fact_count).toBe(0);
  expect(pack.approved_fact_count).toBe(0);
  expect(unit.authentic_ecomm_id).toBeNull();
  expect(pack.authentic_ecomm_id).toBeNull();
  expect(
    unit.documents.some(
      (d: { original: { sha256: string } | null }) =>
        d.original?.sha256 === hileretOriginalSha,
    ),
  ).toBe(true);
  await page
    .getByRole("button", {
      name: "Abrir Hileret unidad de pruebas",
      exact: true,
    })
    .click();
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await page
    .getByLabel("Documento disponible", { exact: true })
    .selectOption({ label: "Folleto Ventas Hileret 17x25_400s.pdf · v1" });
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText(hileretOriginalSha);
  await expect(page.locator('.r-fact[data-field="ean"]').last()).toContainText(
    "7794940000796",
  );
  await expect(
    page.locator('.r-fact[data-field="logistic_dun"]').last(),
  ).toContainText("97794940000799");
  await page.getByRole("dialog").screenshot({
    path: `artifacts/presentacion-guillermo-hileret-${info.project.name}.png`,
  });
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await open(page);
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByText("Preparación avanzada para IA real · Desactivada", {
      exact: true,
    })
    .click();
  await page.route("**/workspace/ai/900003/latest", (route) =>
    route.fulfill({
      headers: { "X-Kiki-Environment": "local-synthetic" },
      json: {
        available: true,
        enabled: false,
        remaining_today: 10,
        draft: { ecomm_id: "900004" },
      },
    }),
  );
  await page
    .getByRole("button", {
      name: "Consultar servicio OpenAI existente (sin generar)",
      exact: true,
    })
    .click();
  await expect(page.getByRole("alert")).toContainText("otra identidad");
  expect(
    (
      await page.request.post("/api/ecomm-app/workspace/ai/900003/suggest", {
        data: { expected_version: 0 },
      })
    ).status(),
  ).toBe(403);
});
