import { test, expect, type Page } from "@playwright/test";
import type { Dossier } from "../src/integration/research-adapter";
test.skip(
  process.env.KIKI_PRODUCTION_COMPAT !== "isolated-only",
  "Sólo compatibilidad explícita sin proveedores",
);
test.setTimeout(120000);
const root = "/api/ecomm-app/workspace/900006";
const paths = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const calls: string[] = [];
  paths.set(page, calls);
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    if (u.origin !== "https://127.0.0.1:8443")
      throw new Error("Conexión externa prohibida");
    calls.push(u.pathname);
    return r.continue();
  });
  await page.goto("/v2/");
  await page.getByLabel("Usuario", { exact: true }).fill("operador-prueba");
  await page
    .getByLabel("Contraseña", { exact: true })
    .fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator('[data-ecomm-id="900006"]')).toBeVisible();
  await expect(page.getByText(/VALIDACIÓN AISLADA/)).toBeVisible();
});
test.afterEach(async ({ page }) => {
  expect(
    paths
      .get(page)!
      .filter((p) =>
        /^\/api\/test-|\/suggest$|\/sync$|\/manual\/start$|\/auth-url$/.test(p),
      ),
  ).toEqual([]);
});
async function post(page: Page, path: string, data: unknown) {
  const csrf = (await (await page.request.get("/api/auth/me")).json())
    .csrf_token;
  const r = await page.request.post(path, {
    headers: { "X-Kiki-UI": "v2", "X-CSRF-Token": csrf },
    data,
  });
  expect(r.status(), await r.text()).toBe(200);
  return r.json();
}
async function open(page: Page, tab = "Ficha") {
  await page
    .locator('[data-ecomm-id="900006"]')
    .getByRole("button", { name: "Ver ficha", exact: true })
    .click();
  await expect(
    page.getByLabel("Título completo", { exact: true }),
  ).toBeVisible();
  if (tab !== "Ficha")
    await page.getByRole("tab", { name: tab, exact: true }).click();
}
test("cinco vistas, calidad, URL, conexiones sin sincronizaciones", async ({
  page,
}, info) => {
  for (const view of [
    "Publicaciones Mercado Libre",
    "Registros Tiendanube",
    "Sin confirmación en ML",
    "Sin confirmación en TN",
    "Catálogo Ecomm-App",
  ]) {
    await page
      .getByRole("button", { name: new RegExp(view) })
      .first()
      .click();
    await expect(page.locator(".d-catalog")).toBeVisible();
  }
  await page.getByText("Calidad del catálogo", { exact: true }).click();
  await page
    .getByRole("button", { name: /EAN no informado en Ecomm-App/ })
    .click();
  await expect(page).toHaveURL(/filter=ean_missing/);
  await page.reload();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(6);
  await page.getByText("Calidad del catálogo", { exact: true }).click();
  await page
    .getByRole("button", { name: /SKU repetido · no confirma duplicados/ })
    .click();
  await expect(page).toHaveURL(/filter=sku_repeated/);
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(2);
  await page
    .getByRole("button", { name: /EAN repetido · revisar presentaciones/ })
    .click();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(0);
  await page
    .getByRole("button", { name: /EAN no informado en Ecomm-App/ })
    .click();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(6);
  await page
    .getByRole("button", { name: "Centro de conexiones", exact: true })
    .click();
  const center = page.getByRole("region", { name: "Centro de conexiones" });
  await expect(center.getByRole("article")).toHaveCount(3);
  await expect(
    center.getByRole("button", {
      name: "Actualizar catálogo ahora",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(center).toContainText(
    "Actualizaciones bloqueadas por configuración",
  );
  await page
    .getByRole("dialog")
    .screenshot({ path: `artifacts/v2-conexiones-${info.project.name}.png` });
});
test("editor original 18 campos, guardado, recuperación, cinco pestañas e historial", async ({
  page,
}, info) => {
  await open(page);
  const title = "Edición sintética V2 " + info.project.name;
  await page.getByLabel("Título completo", { exact: true }).fill(title);
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(page.getByText(/Guardado en KIKI PostgreSQL/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    title,
  );
  const record = await (await page.request.get(root)).json();
  expect(Object.keys(record.fields)).toHaveLength(18);
  for (const tab of ["Evidencias", "IA", "Canales", "Historial", "Ficha"]) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(
      page.getByRole("tab", { name: tab, exact: true }),
    ).toHaveAttribute("aria-selected", "true");
  }
  await page
    .getByRole("dialog")
    .screenshot({ path: `artifacts/v2-editor-${info.project.name}.png` });
});
test("documento local → hechos revisados → propuesta respaldada → editor versionado", async ({
  page,
}) => {
  // Fixtures are explicitly authored, never presented as manufacturer documentation.
  const before = await (await page.request.get(root)).json();
  await post(page, root, {
    expected_version: before.version,
    status: "DRAFT",
    fields: {
      ...before.fields,
      brand: "",
      manufacturer: "",
      presentation: "",
      title: "Inicio V2",
      description: "Descripción preservada",
    },
  });
  let dossier: Dossier = await (
    await page.request.get(root + "/evidence")
  ).json();
  for (const original of dossier.facts.filter((f) => f.state !== "REJECTED")) {
    const f = dossier.facts.find((f) => f.id === original.id)!;
    dossier = await post(page, root + `/evidence/facts/${f.id}/review`, {
      expected_version: dossier.version,
      expected_fact_version: f.version,
      decision: "REJECTED",
      reason:
        "Separación explícita de hechos anteriores en prueba de compatibilidad.",
    });
  }
  await open(page, "Evidencias");
  await page
    .getByText("Incorporar archivo local o referencia oficial", { exact: true })
    .click();
  await page.getByLabel("Archivo documental", { exact: true }).setInputFiles({
    name: "compatibilidad-v2.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Nombre: Lentejas sintéticas\nMarca: Marca sintética KIKI\nFabricante: Fabricante de prueba\nPresentación: 1 kg\nTipo de venta: Unidad\nIngredientes: Lentejas\nContenido neto: 1000 g\nCategoría: Dietética\nSubcategoría: Legumbres\n",
    ),
  });
  await page
    .getByLabel("Cómo obtuve la documentación", { exact: true })
    .fill(
      "Archivo inventado expresamente para esta validación aislada, no documento auténtico.",
    );
  await page
    .getByLabel(
      "Autorizo expresamente el procesamiento local de este documento o referencia",
      { exact: true },
    )
    .check();
  await page
    .getByRole("button", { name: "Incorporar documentación", exact: true })
    .click();
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Pendiente de revisión");
  await page
    .getByLabel("Motivo de revisión de procedencia", { exact: true })
    .fill(
      "Revisión humana de prueba; no acredita fabricante ni catálogo real.",
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
  dossier = await (await page.request.get(root + "/evidence")).json();
  const doc = dossier.documents.find(
    (d) =>
      d.body.title === "compatibilidad-v2.txt" &&
      d.body.source?.review_state === "REVIEWED",
  )!;
  for (const fact of dossier.facts.filter((f) => f.document_id === doc.id)) {
    const card = page.locator(
      `.r-fact[data-document="${doc.id}"][data-field="${fact.field}"]`,
    );
    await card
      .getByRole("textbox")
      .fill(
        "Contraste humano explícito de prueba; identidad y fragmento comprobados para esta variante.",
      );
    page.once("dialog", (d) => d.accept());
    await card
      .getByRole("button", { name: "Aprobar hecho", exact: true })
      .click();
    await expect(card.locator(".r-state")).toHaveText("Aprobada");
  }
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByRole("button", { name: "Generar propuesta respaldada", exact: true })
    .click();
  await expect(page.getByLabel("Propuesta title", { exact: true })).toHaveValue(
    "Lentejas sintéticas · 1 kg",
  );
  await page
    .getByLabel("Decisión title", { exact: true })
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
  await expect(page.getByText(/Selección ya guardada/)).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "Ficha", exact: true }).click();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "Lentejas sintéticas · 1 kg",
  );
  expect((await (await page.request.get(root)).json()).fields.description).toBe(
    "Descripción preservada",
  );
});
test("configuración de sólo lectura y funciones sin migración no simulan disponibilidad", async ({
  page,
}) => {
  await page.route("**/api/ui/v2", async (r) => {
    const response = await r.fetch();
    const data = await response.json();
    await r.fulfill({
      response,
      json: {
        ...data,
        writes: false,
        documents: false,
        batches: false,
        channels: false,
      },
    });
  });
  await page.reload();
  await open(page);
  await expect(
    page.getByLabel("Título completo", { exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Guardar borrador", exact: true }),
  ).toBeDisabled();
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await expect(
    page.getByText(/Documentos pendientes de habilitación/),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Canales", exact: true }).click();
  await expect(
    page.getByText(/Revisión de canales deshabilitada/),
  ).toBeVisible();
});
test("error de catálogo no usa fallback y permite regresar a la interfaz anterior", async ({
  page,
}) => {
  await page.route("**/api/ecomm-app/stage/catalog?*", (r) =>
    r.fulfill({
      status: 503,
      headers: { "X-Kiki-UI-Contract": "kiki-same-origin-v2-1" },
      json: { detail: "Captura no disponible" },
    }),
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "No se pudo cargar el catálogo" }),
  ).toBeVisible();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(0);
  await page
    .getByRole("link", { name: "Volver a la interfaz anterior", exact: true })
    .click();
  await expect(page).toHaveURL(/dashboard-classic/);
  await expect(
    page.getByText("Ecomm API: copia completa", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("KIKI Tech 2.0 no disponible", { exact: true }),
  ).toHaveCount(0);
});

test("OpenAI existente: transporte simulado, versión visible y bloqueo por edición pendiente", async ({
  page,
}) => {
  await page.route("**/api/ui/v2", async (r) => {
    const response = await r.fetch();
    const data = await response.json();
    await r.fulfill({
      response,
      json: { ...data, openai_configured: true, openai_generation: true },
    });
  });
  // UI contract only. The real backend still denies consumption and the POST is never forwarded.
  let sent: unknown;
  const capture = await (await page.request.get(root)).json();
  await page.route(
    "**/api/ecomm-app/workspace/ai/900006/suggest",
    async (r) => {
      sent = r.request().postDataJSON();
      await r.fulfill({
        status: 200,
        headers: { "X-Kiki-UI-Contract": "kiki-same-origin-v2-1" },
        json: { ecomm_id: "900006", saved_to_product_fields: false },
      });
    },
  );
  await page.reload();
  await open(page, "IA");
  await page
    .getByText("Servicios IA existentes y límites", { exact: true })
    .click();
  const generate = page.getByRole("button", {
    name: "Generar título y descripción con OpenAI existente",
    exact: true,
  });
  await expect(generate).toBeEnabled();
  page.once("dialog", (d) => d.accept());
  await generate.click();
  await expect.poll(() => sent).toEqual({ expected_version: capture.version });
  const after = await (await page.request.get(root)).json();
  expect(after.version).toBe(capture.version);
  expect(after.fields).toEqual(capture.fields);
  await page.getByRole("tab", { name: "Ficha", exact: true }).click();
  await page
    .getByLabel("Título completo", { exact: true })
    .fill("Cambios sin guardar para comprobar bloqueo IA");
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByText("Servicios IA existentes y límites", { exact: true })
    .click();
  await expect(generate).toBeDisabled();
});

test("raíz original, sesión compartida y reversión de v2 sin bloquear la aplicación anterior", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveURL(/dashboard-classic/);
  await expect(
    page.getByText("Ecomm API: copia completa", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Abrir KIKI Tech 2.0", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Iniciar sesión", { exact: true })).toHaveCount(
    0,
  );
  await page.route("**/api/ui/v2", (r) =>
    r.fulfill({
      status: 404,
      headers: { "X-Kiki-UI-Contract": "kiki-same-origin-v2-1" },
      json: { detail: "KIKI Tech 2.0 deshabilitado" },
    }),
  );
  await page
    .getByRole("link", { name: "Abrir KIKI Tech 2.0", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "KIKI Tech 2.0 no disponible",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(0);
  await page
    .getByRole("link", { name: "Volver a la interfaz anterior", exact: true })
    .click();
  await expect(page).toHaveURL(/dashboard-classic/);
  await expect(
    page.getByText("Ecomm API: copia completa", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Abrir KIKI Tech 2.0", exact: true }),
  ).toBeVisible();
});

test("lote desde v2: seis Ecomm ID exactos, previsualización, confirmación y tareas sin cambios comerciales", async ({
  page,
}) => {
  const before = await (
    await page.request.get("/api/ecomm-app/workspace/900001")
  ).json();
  await page
    .getByRole("button", { name: "Seleccionar esta página", exact: true })
    .click();
  await expect(page.getByTestId("selected-count")).toHaveText(
    "6 variantes seleccionadas",
  );
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  await page
    .getByLabel("Operación del lote", { exact: true })
    .selectOption("REVIEW_TASKS");
  await page
    .getByRole("button", { name: "Previsualizar selección", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Revisá antes de iniciar", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("batch-progress")).toContainText(
    "Pendiente: 6",
  );
  await page
    .getByRole("button", { name: "Confirmar e iniciar lote", exact: true })
    .click();
  await expect(page.getByTestId("batch-progress")).toContainText(
    "Completado: 6",
  );
  const after = await (
    await page.request.get("/api/ecomm-app/workspace/900001")
  ).json();
  expect(after.fields).toEqual(before.fields);
  expect(after.version).toBe(before.version);
  const jobs = await (
    await page.request.get("/api/ecomm-app/editorial-batches?page=1&limit=10")
  ).json();
  const job = jobs.items.find(
    (j: { operation: string }) => j.operation === "REVIEW_TASKS",
  );
  expect(job).toBeTruthy();
  const detail = await (
    await page.request.get(
      `/api/ecomm-app/editorial-batches/${job.id}?page=1&limit=25`,
    )
  ).json();
  expect(
    detail.items.map((i: { ecomm_id: string }) => i.ecomm_id).sort(),
  ).toEqual(["900001", "900002", "900003", "900004", "900005", "900006"]);
});
