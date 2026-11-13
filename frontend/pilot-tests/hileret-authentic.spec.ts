import { test, expect, type Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import {
  hileretUnitId as id,
  hileretPackId as pack,
  hileretPilotPath as api,
  hileretOriginalSha,
  hileretOriginalSize,
} from "../src/integration/hileret-pilot";
import type { Dossier } from "../src/integration/research-adapter";
const research = `/api/test-research/${id}`,
  documents = `/api/test-documents/${id}`,
  workspace = `/api/ecomm-app/workspace/${id}`;
const original = readFileSync("../integration/fixtures/hileret-original.pdf");
const reason =
  "RECORRIDO AUTOMATIZADO DE PRUEBA, no aprobación efectiva del cliente: contrastados bytes, página 2 y citas del original adjunto por el usuario.";
const url =
  "https://descargas.hileret.com.ar/Hileret/Folleto%20Ventas%20Hileret%2017x25_400s.pdf";
test.setTimeout(180000);
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
async function post(page: Page, path: string, data: unknown) {
  const session = await (await page.request.get("/api/auth/me")).json();
  const response = await page.request.post(path, {
    headers: { "X-CSRF-Token": session.csrf_token },
    data,
  });
  expect(response.status(), (await response.text()).slice(0, 1500)).toBe(200);
  return response.json();
}
const dossier = async (page: Page): Promise<Dossier> =>
  (await page.request.get(research)).json();

test("original auténtico: bytes, citas, revisiones explícitas del operador de prueba, propuesta limitada, persistencia y pack bloqueado", async ({
  page,
}, info) => {
  expect(original.length).toBe(hileretOriginalSize);
  expect(createHash("sha256").update(original).digest("hex")).toBe(
    hileretOriginalSha,
  );
  await page.goto("/?q=Almendras");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Abrir Hileret unidad de pruebas",
      exact: true,
    }),
  ).toBeVisible();
  await post(page, api + "/prepare", {});
  let state = await dossier(page);
  for (const existing of state.facts.filter((f) => f.state !== "REJECTED")) {
    const fact = state.facts.find((f) => f.id === existing.id)!;
    state = await post(page, `${research}/facts/${fact.id}/review`, {
      expected_version: state.version,
      expected_fact_version: fact.version,
      decision: "REJECTED",
      reason:
        "Preparación explícita del recorrido de prueba independiente, sin borrar originales ni historial.",
    });
  }
  const prior = await (await page.request.get(workspace)).json();
  const blank = Object.fromEntries(
    Object.entries(prior.fields).map(([k, v]) => [
      k,
      Array.isArray(v) ? [] : "",
    ]),
  );
  await post(page, workspace, {
    expected_version: prior.version,
    status: "DRAFT",
    fields: { ...blank, note: reason },
  });
  const before = await (await page.request.get(workspace)).json();
  await page
    .getByRole("button", {
      name: "Abrir Hileret unidad de pruebas",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "",
  );
  await page
    .getByLabel("Expediente comercial Hileret", { exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/hileret-autentico-antes-${info.project.name}.png`,
  });
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Investigar y completar ficha con IA",
      exact: true,
    })
    .click();
  await page
    .getByText("Incorporar archivo local o referencia oficial", { exact: true })
    .click();
  await page.getByLabel("Archivo documental", { exact: true }).setInputFiles({
    name: "Folleto Ventas Hileret 17x25_400s.pdf",
    mimeType: "application/pdf",
    buffer: original,
  });
  await page
    .getByLabel("Cómo obtuve la documentación", { exact: true })
    .fill(
      "Original adjunto por el usuario, quien informa descarga del dominio oficial Hileret. Codex verifica localmente hash y página 2; sin descarga web ni fecha de consulta inferida.",
    );
  await page
    .getByLabel("URL de referencia (sin acceder)", { exact: true })
    .fill(url);
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
  let pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`${documents}/import`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Incorporar documentación", exact: true })
    .click();
  let response = await pending;
  expect(response.status(), (await response.text()).slice(0, 1000)).toBe(200);
  const imported = await response.json();
  const doc = imported.incorporated_document_id as string;
  await expect(
    page.getByLabel("Documento disponible", { exact: true }),
  ).toHaveValue(doc);
  const source = page.getByLabel("Procedencia del documento local");
  await expect(source).toContainText(hileretOriginalSha);
  await expect(source).toContainText("6232081 bytes");
  await expect(source).toContainText("Pendiente de revisión");
  await page
    .getByRole("button", { name: "Comprobar original conservado", exact: true })
    .click();
  await expect(
    page.getByText("Original v1 recuperado desde PostgreSQL", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Extraer hechos del documento", exact: true })
    .click();
  await expect(page.locator(`.r-fact[data-document="${doc}"]`)).toHaveCount(7);
  for (const button of await page
    .locator(`.r-fact[data-document="${doc}"]`)
    .getByRole("button", { name: "Aprobar hecho", exact: true })
    .all())
    await expect(button).toBeDisabled();
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
  pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`${research}/extract`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Extraer hechos del documento", exact: true })
    .click();
  expect((await pending).status()).toBe(200);
  const fields = [
    "product_name",
    "brand",
    "presentation",
    "net_weight",
    "ean",
    "logistic_units",
    "logistic_dun",
  ];
  for (const field of fields) {
    const fact = page.locator(
      `.r-fact[data-document="${doc}"][data-field="${field}"]`,
    );
    await expect(fact).toContainText("pagina/2/tabla/stevia/");
    await fact.getByRole("textbox").fill(reason);
    page.once("dialog", (d) => d.accept());
    await fact
      .getByRole("button", { name: "Aprobar hecho", exact: true })
      .click();
    await expect(fact).toContainText("Aprobada");
  }
  const approved = await dossier(page);
  expect(approved.facts.filter((f) => f.verified)).toHaveLength(7);
  const ean = page.locator(`.r-fact[data-document="${doc}"][data-field="ean"]`);
  await expect(ean).toContainText("7794940000796");
  await ean.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/hileret-autentico-evidencias-${info.project.name}.png`,
  });
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/test-proposals/${id}/generate`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generar propuesta de prueba", exact: true })
    .click();
  response = await pending;
  expect(response.status()).toBe(200);
  const proposal = await response.json();
  expect(proposal.fields.title.value).toBe("Hileret Stevia · 200 ml");
  expect(proposal.fields.description.value).toBe(
    "Hileret Stevia · 200 ml.\nContenido neto: 200 ml.",
  );
  for (const k of [
    "category",
    "subcategory",
    "manufacturer",
    "proposed_gtin",
    "media",
  ])
    expect(proposal.fields[k]).toBeUndefined();
  for (const key of Object.keys(proposal.fields))
    await page
      .getByLabel(`Decisión ${key}`, { exact: true })
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
  await page.locator('[data-proposal-field="title"]').scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/hileret-autentico-propuesta-${info.project.name}.png`,
  });
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
  await page.reload();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "Hileret Stevia · 200 ml",
  );
  await page
    .getByText("Comparación inicial / guardado local", { exact: true })
    .click();
  await expect(
    page.getByLabel("Expediente comercial Hileret", { exact: true }),
  ).toContainText("Guardado: Hileret Stevia · 200 ml");
  const saved = await (await page.request.get(workspace)).json();
  expect(saved.fields.proposed_gtin).toBe("");
  expect(saved.source.authentic_ecomm_id).toBeNull();
  expect(saved.fields.note).toBe(reason);
  expect(saved.version).toBe(before.version + 1);
  await page
    .getByLabel("Expediente comercial Hileret", { exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/hileret-autentico-guardado-${info.project.name}.png`,
  });
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toContainText(
    `Versión ${saved.version}`,
  );
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Buscar productos", exact: true }),
  ).toHaveValue("Almendras");
  const packCase = await post(page, `/api/test-documents/${pack}/import`, {
    kind: "FILE",
    expected_version: (
      await (await page.request.get(`/api/test-research/${pack}`)).json()
    ).version,
    filename: "Folleto Ventas Hileret 17x25_400s.pdf",
    content_type: "application/pdf",
    content_base64: original.toString("base64"),
    reference_url: url,
    provenance_note:
      "Control de identidad: original auténtico de unidad y caja x9, sin respaldo del pack comercial x6.",
    declared_official: true,
    authorized_local_processing: true,
  });
  const packDoc = packCase.incorporated_document_id;
  const packExtracted = await post(page, `/api/test-research/${pack}/extract`, {
    expected_version: packCase.version,
    document_id: packDoc,
    document_version: 1,
  });
  expect(
    packExtracted.facts.every(
      (f: { verified: boolean; blockers: string[] }) =>
        !f.verified && f.blockers.length > 0,
    ),
  ).toBe(true);
  await page
    .getByRole("button", {
      name: "Abrir Hileret pack x6 de pruebas",
      exact: true,
    })
    .click();
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Investigar y completar ficha con IA",
      exact: true,
    })
    .click();
  await page
    .getByLabel("Documento disponible", { exact: true })
    .selectOption(packDoc);
  await expect(page.getByLabel("Vista del documento")).toContainText(
    "incompatible",
  );
  await page.getByLabel("Vista del documento").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/hileret-autentico-pack-bloqueado-${info.project.name}.png`,
  });
  const report = await (await page.request.get(api)).json();
  expect(
    report.cases.find((c: { test_id: string }) => c.test_id === pack)
      .approved_fact_count,
  ).toBe(0);
  writeFileSync(
    `artifacts/hileret-autentico-resultado-${info.project.name}.json`,
    JSON.stringify(
      {
        scope:
          "Recorrido automatizado del operador de prueba; no aprobación efectiva del cliente",
        original_sha256: hileretOriginalSha,
        original_bytes: original.length,
        before,
        after: saved,
        approved_evidence: approved.facts.filter((f) => f.verified),
        report,
      },
      null,
      2,
    ),
  );
});
