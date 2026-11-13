import { test, expect, type Page } from "@playwright/test";
import type { Dossier } from "../src/integration/research-adapter";
const id = "900006",
  root = `/api/ecomm-app/workspace/${id}`;
const source = `Nombre: Lentejas sintéticas
Marca: Marca sintética KIKI
Fabricante: Fabricante de prueba
Presentación: 1 kg
Tipo de venta: Unidad
Ingredientes: Lentejas
Contenido neto: 1000 g
Categoría: Dietética
Subcategoría: Legumbres
`;
test.setTimeout(120000);
const calls = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page, context }) => {
  const paths: string[] = [];
  calls.set(page, paths);
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "https://127.0.0.1:8443")
      throw new Error(`Salida no autorizada: ${url.origin}`);
    paths.push(url.pathname);
    return route.continue();
  });
});
test.afterEach(async ({ page }) => {
  expect(
    calls
      .get(page)!
      .filter((p) =>
        /^\/api\/test-(research|proposals|documents)\/90000/.test(p),
      ),
  ).toEqual([]);
});
async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator(`[data-ecomm-id="${id}"]`)).toBeVisible();
}
async function post(page: Page, path: string, data: unknown) {
  const csrf = (await (await page.request.get("/api/auth/me")).json())
    .csrf_token;
  const response = await page.request.post(path, {
    headers: { "X-CSRF-Token": csrf },
    data,
  });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}
async function read(page: Page): Promise<Dossier> {
  return (await page.request.get(root + "/evidence")).json();
}
async function open(page: Page, product = id, expectDocuments = true) {
  await page
    .locator(`[data-ecomm-id="${product}"]`)
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await expect(
    page.getByLabel("Marca comercial", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  if (expectDocuments)
    await expect(
      page.getByLabel("Documento disponible", { exact: true }),
    ).toBeVisible();
}
test("catálogo → documento → revisión → propuesta por campo → editor → historial persistido", async ({
  page,
}, info) => {
  await login(page);
  let dossier = await read(page);
  for (const original of dossier.facts.filter((f) => f.state !== "REJECTED")) {
    const f = dossier.facts.find((f) => f.id === original.id)!;
    dossier = await post(page, root + `/evidence/facts/${f.id}/review`, {
      expected_version: dossier.version,
      expected_fact_version: f.version,
      decision: "REJECTED",
      reason: "Preparación explícita del recorrido de aceptación sintético 2O.",
    });
  }
  const before = await (await page.request.get(root)).json();
  await post(page, root, {
    expected_version: before.version,
    status: "DRAFT",
    fields: {
      ...before.fields,
      brand: "",
      manufacturer: "",
      presentation: "",
      title: "Ficha inicial sintética 2O",
      description: "Descripción inicial conservada",
    },
  });
  await open(page);
  await page
    .getByText("Incorporar archivo local o referencia oficial", { exact: true })
    .click();
  await page.getByLabel("Archivo documental", { exact: true }).setInputFiles({
    name: "lentejas-2o.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(source),
  });
  await page
    .getByLabel("Cómo obtuve la documentación", { exact: true })
    .fill(
      "Documento inventado para esta aceptación aislada, sin procedencia de fabricante real.",
    );
  await page
    .getByLabel(
      "Autorizo expresamente el procesamiento local de este documento o referencia",
      { exact: true },
    )
    .check();
  const imported = page.waitForResponse(
    (r) =>
      r.url().endsWith(root + "/documents/import") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Incorporar documentación", exact: true })
    .click();
  expect((await imported).status()).toBe(200);
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Pendiente de revisión");
  await page
    .getByLabel("Motivo de revisión de procedencia", { exact: true })
    .fill(
      "Revisé origen y contenido del documento de prueba, sin certificar oficialidad.",
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
  await page
    .getByRole("button", { name: "Extraer hechos del documento", exact: true })
    .click();
  await expect(
    page.locator('.r-fact[data-field="ingredients"] .r-state').last(),
  ).toHaveText("Pendiente de revisión");
  dossier = await read(page);
  const doc = dossier.documents.find(
    (d) =>
      d.body.title === "lentejas-2o.txt" &&
      d.body.source?.review_state === "REVIEWED",
  )!;
  for (const fact of dossier.facts.filter((f) => f.document_id === doc.id)) {
    const card = page.locator(
      `.r-fact[data-document="${doc.id}"][data-field="${fact.field}"]`,
    );
    await card
      .getByRole("textbox")
      .fill(
        "Verifiqué el fragmento y la variante sintética de 1 kg de forma explícita.",
      );
    page.once("dialog", (d) => d.accept());
    await card
      .getByRole("button", { name: "Aprobar hecho", exact: true })
      .click();
    await expect(card.locator(".r-state")).toHaveText("Aprobada");
  }
  const first = page.locator(`.r-fact[data-document="${doc.id}"]`).first();
  await first.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/evidencias-2o-${info.project.name}.png`,
  });
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByRole("button", { name: "Generar propuesta de prueba", exact: true })
    .click();
  await expect(page.getByLabel("Propuesta title", { exact: true })).toHaveValue(
    "Lentejas sintéticas · 1 kg",
  );
  const title = page.locator('[data-proposal-field="title"]');
  await title.getByText("Valor actual al generar", { exact: true }).click();
  await expect(title).toContainText("Ficha inicial sintética 2O");
  await title.getByText(/Respaldo de este campo/).click();
  await expect(title).toContainText("Nombre: Lentejas sintéticas");
  await title.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/propuesta-2o-${info.project.name}.png`,
  });
  // Supported edit: reorder whole documented title clauses; no new assertions.
  await page
    .getByLabel("Propuesta title", { exact: true })
    .fill("1 kg · Lentejas sintéticas");
  await page
    .getByLabel("Decisión title", { exact: true })
    .selectOption("ACCEPTED");
  await page
    .getByLabel("Decisión description", { exact: true })
    .selectOption("REJECTED");
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
  await expect(page.getByText(/Selección ya guardada/)).toBeVisible();
  await page.getByRole("tab", { name: "Ficha", exact: true }).click();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "1 kg · Lentejas sintéticas",
  );
  await page.reload();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "1 kg · Lentejas sintéticas",
  );
  const saved = await (await page.request.get(root)).json();
  expect(saved.fields.description).toBe("Descripción inicial conservada");
  expect(saved.fields.media).toEqual(before.fields.media);
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Historial persistido en KIKI" }),
  ).toBeVisible();
  const last = page
    .locator(".i-message")
    .filter({ hasText: `Versión ${saved.version}` })
    .first();
  await last.locator("summary").click();
  await expect(last).toContainText("1 kg · Lentejas sintéticas");
  await last.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/historial-2o-${info.project.name}.png`,
  });
});
test("revocar procedencia invalida la evidencia y una propuesta sin transferirla a otra variante", async ({
  page,
}) => {
  await login(page);
  const dossier = await read(page);
  const doc = dossier.documents.find(
    (d) =>
      d.body.title === "lentejas-2o.txt" &&
      d.body.source?.review_state === "REVIEWED",
  )!;
  expect(doc).toBeTruthy();
  const current = await (await page.request.get(root)).json();
  const proposal = await post(page, root + "/proposals/generate", {
    expected_version: current.version,
  });
  await post(page, root + `/documents/${doc.id}/provenance`, {
    expected_document_version: doc.version,
    decision: "REVOKED",
    reason:
      "Retiro explícito del respaldo de prueba para validar revocaciones.",
  });
  await open(page);
  expect((await read(page)).facts.some((f) => f.verified)).toBe(false);
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Guardar selección en ficha",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: /Las evidencias o la identidad cambiaron/ }),
  ).toBeVisible();
  const csrf = (await (await page.request.get("/api/auth/me")).json())
    .csrf_token;
  const cross = await page.request.post("/api/ecomm-app/workspace/900002", {
    headers: {
      "X-CSRF-Token": csrf,
      "X-Kiki-Proposal-Id": String(proposal.draft_id),
      "X-Kiki-Proposal-Revision": String(proposal.revision),
    },
    data: {
      expected_version: 0,
      status: "DRAFT",
      fields: proposal.base_fields,
    },
  });
  expect(cross.status()).toBe(409);
});
test("sin evidencias explica el bloqueo y no inventa una propuesta", async ({
  page,
}) => {
  await login(page);
  await open(page, "900005");
  await expect(
    page.getByText(
      "No se extrajeron hechos. Ningún dato se completará por suposición.",
    ),
  ).toBeVisible();
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByRole("button", { name: "Generar propuesta de prueba", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Faltan hechos documentales aprobados vigentes",
  );
  await expect(page.getByLabel("Propuesta title", { exact: true })).toHaveCount(
    0,
  );
});
test("rechaza respuesta documental de otra identidad sin permitir revisión", async ({
  page,
}) => {
  await login(page);
  await page.route(`**${root}/evidence`, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.ecomm_id = "900002";
    await route.fulfill({ response, json: data });
  });
  await open(page, id, false);
  await expect(page.getByRole("alert")).toContainText(
    "La respuesta de investigación no acredita",
  );
  await expect(
    page.getByRole("button", { name: "Aprobar hecho", exact: true }),
  ).toHaveCount(0);
});
