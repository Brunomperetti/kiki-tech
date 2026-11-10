import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import {
  researchPath,
  type Dossier,
} from "../src/integration/research-adapter";
import { workspacePath } from "../src/integration/workspace-adapter";

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
test.afterEach(async ({ page }) => {
  expect(outside.get(page)).toEqual([]);
});
const fact = (page: Page, doc: string, field: string) =>
  page.locator(`.r-fact[data-document="${doc}"][data-field="${field}"]`);
async function read(api: APIRequestContext, id = "900001"): Promise<Dossier> {
  const response = await api.get(researchPath(id));
  expect(response.status()).toBe(200);
  return response.json();
}
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
  // Each project starts from explicit rejected decisions, not a hidden data reset.
  const csrf = (await (await page.request.get("/api/auth/me")).json())
    .csrf_token;
  let data = await read(page.request, id);
  for (const item of data.facts) {
    const current = data.facts.find((f) => f.id === item.id)!;
    const response = await page.request.post(
      `${researchPath(id)}/facts/${item.id}/review`,
      {
        headers: { "X-CSRF-Token": csrf },
        data: {
          expected_version: data.version,
          expected_fact_version: current.version,
          decision: "REJECTED",
          reason: "Inicio explícito de un recorrido sintético independiente.",
        },
      },
    );
    expect(response.status()).toBe(200);
    data = await response.json();
  }
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await expect(
    page.getByLabel("Documento sintético", { exact: true }),
  ).toBeVisible();
}
async function extract(page: Page, document = "alm-tecnica") {
  await page
    .getByLabel("Documento sintético", { exact: true })
    .selectOption(document);
  const pending = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith("/extract") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Extraer hechos del documento", exact: true })
    .click();
  expect((await pending).status()).toBe(200);
  await expect(
    page.locator(`.r-fact[data-document="${document}"]`).first(),
  ).toBeVisible();
}
async function decide(page: Page, doc: string, field: string, button: string) {
  const card = fact(page, doc, field);
  await card
    .getByRole("textbox")
    .fill("Contrasté el fragmento y la variante de prueba de forma explícita.");
  page.once("dialog", (dialog) => dialog.accept());
  await card.getByRole("button", { name: button, exact: true }).click();
}

test("documento, hecho aprobado, historial, recarga y consulta desde ficha sin reemplazar campos", async ({
  page,
}, info) => {
  await open(page);
  const before = await (await page.request.get(workspacePath("900001"))).json();
  await extract(page);
  await page
    .getByText("Ver documento y ubicaciones verificables", { exact: true })
    .click();
  await expect(page.getByLabel("Vista del documento")).toContainText(
    "DOCUMENTO SINTÉTICO DE PRUEBA",
  );
  await page.getByLabel("Vista del documento").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/investigacion-documento-${info.project.name}.png`,
  });
  await decide(page, "alm-tecnica", "ingredients", "Aprobar hecho");
  await expect(
    fact(page, "alm-tecnica", "ingredients").locator(".r-state"),
  ).toHaveText("Aprobada");
  await fact(page, "alm-tecnica", "ingredients").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/investigacion-hecho-${info.project.name}.png`,
  });
  const after = await (await page.request.get(workspacePath("900001"))).json();
  expect(after.fields).toEqual(before.fields);
  expect(after.version).toBe(before.version);
  await page.reload();
  await expect(
    fact(page, "alm-tecnica", "ingredients").locator(".r-state"),
  ).toHaveText("Aprobada");
  const data = await read(page.request);
  expect(
    data.facts.find(
      (f) => f.field === "ingredients" && f.document_id === "alm-tecnica",
    )?.reviewer,
  ).toContain("sesión de prueba");
  await fact(page, "alm-tecnica", "ingredients")
    .locator("summary")
    .first()
    .click();
  await expect(fact(page, "alm-tecnica", "ingredients")).toContainText(
    "APPROVED",
  );
  await page.getByRole("tab", { name: "Ficha", exact: true }).click();
  await expect(
    page.getByLabel("Respaldo documental de la ficha"),
  ).toContainText("Ingredientes: Almendras");
  await expect(page.getByLabel("Marca comercial", { exact: true })).toHaveValue(
    before.fields.brand,
  );
});

test("EAN/presentación incompatibles y falta de fragmento o unidad impiden aprobación", async ({
  page,
}, info) => {
  await open(page);
  for (const [doc, field, message] of [
    ["alm-ean-incompatible", "allergens", "EAN"],
    ["alm-pack-1kg", "net_weight", "Presentación"],
    ["alm-incompleta", "nutrition.energy", "unidad"],
    ["alm-incompleta", "commercial_claim", "fragmento"],
  ]) {
    await extract(page, doc);
    const card = fact(page, doc, field);
    await card
      .getByRole("textbox")
      .fill("Revisión de una evidencia insuficiente o incompatible de prueba.");
    await expect(card.getByLabel("Bloqueos de evidencia")).toContainText(
      message,
    );
    await expect(
      card.getByRole("button", { name: "Aprobar hecho", exact: true }),
    ).toBeDisabled();
    await expect(card.locator(".r-state")).not.toHaveText("Aprobada");
  }
  await fact(
    page,
    "alm-incompleta",
    "commercial_claim",
  ).scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/investigacion-insuficiente-${info.project.name}.png`,
  });
});

test("una contradicción invalida aprobación previa y exige rechazo y nueva revisión", async ({
  page,
}, info) => {
  await open(page);
  await extract(page);
  await decide(page, "alm-tecnica", "nutrition.energy", "Aprobar hecho");
  await expect(
    fact(page, "alm-tecnica", "nutrition.energy").locator(".r-state"),
  ).toHaveText("Aprobada");
  await extract(page, "alm-nutricion-conflicto");
  if (
    (await read(page.request)).facts.find(
      (f) => f.document_id === "alm-nutricion-conflicto",
    )?.state === "REJECTED"
  ) {
    // Reimporting unchanged rejected evidence must not silently reopen its decision.
    page.once("dialog", (dialog) => dialog.accept());
    await page
      .getByRole("button", {
        name: "Simular nueva versión del documento",
        exact: true,
      })
      .click();
    await expect(
      fact(page, "alm-nutricion-conflicto", "nutrition.energy").locator(
        ".r-state",
      ),
    ).toHaveText("Verificación invalidada");
    await extract(page, "alm-nutricion-conflicto");
  }
  await expect(
    fact(page, "alm-tecnica", "nutrition.energy").locator(".r-state"),
  ).toHaveText("Verificación invalidada");
  await expect(
    fact(page, "alm-nutricion-conflicto", "nutrition.energy").getByLabel(
      "Bloqueos de evidencia",
    ),
  ).toContainText("contradictorio");
  await fact(
    page,
    "alm-nutricion-conflicto",
    "nutrition.energy",
  ).scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/investigacion-contradiccion-${info.project.name}.png`,
  });
  await decide(
    page,
    "alm-nutricion-conflicto",
    "nutrition.energy",
    "Rechazar hecho",
  );
  await expect(
    fact(page, "alm-nutricion-conflicto", "nutrition.energy").locator(
      ".r-state",
    ),
  ).toHaveText("Rechazada");
  await extract(page);
  await expect(
    fact(page, "alm-tecnica", "nutrition.energy").locator(".r-state"),
  ).toHaveText("Pendiente de revisión");
  await decide(page, "alm-tecnica", "nutrition.energy", "Aprobar hecho");
  await expect(
    fact(page, "alm-tecnica", "nutrition.energy").locator(".r-state"),
  ).toHaveText("Aprobada");
});

test("revocación y nueva versión documental persisten sin restaurar verificaciones automáticamente", async ({
  page,
}, info) => {
  await open(page);
  await extract(page);
  await decide(page, "alm-tecnica", "ingredients", "Aprobar hecho");
  await expect(
    fact(page, "alm-tecnica", "ingredients").locator(".r-state"),
  ).toHaveText("Aprobada");
  await decide(page, "alm-tecnica", "ingredients", "Revocar verificación");
  await expect(
    fact(page, "alm-tecnica", "ingredients").locator(".r-state"),
  ).toHaveText("Verificación revocada");
  await decide(page, "alm-tecnica", "ingredients", "Aprobar hecho");
  await expect(
    fact(page, "alm-tecnica", "ingredients").locator(".r-state"),
  ).toHaveText("Aprobada");
  const old = await read(page.request);
  const doc = old.documents.find((d) => d.id === "alm-tecnica")!;
  expect(doc.versions).toContain(doc.version + 1);
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", {
      name: "Simular nueva versión del documento",
      exact: true,
    })
    .click();
  await expect(
    fact(page, "alm-tecnica", "ingredients").locator(".r-state"),
  ).toHaveText("Verificación invalidada");
  await page.reload();
  await expect(
    fact(page, "alm-tecnica", "ingredients").locator(".r-state"),
  ).toHaveText("Verificación invalidada");
  await fact(page, "alm-tecnica", "ingredients")
    .locator("summary")
    .first()
    .click();
  await expect(fact(page, "alm-tecnica", "ingredients")).toContainText(
    "Sistema",
  );
  await page.screenshot({
    path: `artifacts/investigacion-revocacion-${info.project.name}.png`,
  });
  await extract(page);
  await expect(
    fact(page, "alm-tecnica", "ingredients").locator(".r-state"),
  ).toHaveText("Pendiente de revisión");
});

test("el mismo SKU mantiene hechos separados por Ecomm ID y presentación", async ({
  page,
}) => {
  await open(page, "900002");
  await extract(page, "alm-pack-1kg");
  await decide(page, "alm-pack-1kg", "net_weight", "Aprobar hecho");
  await expect(
    fact(page, "alm-pack-1kg", "net_weight").locator(".r-state"),
  ).toHaveText("Aprobada");
  const first = await read(page.request),
    second = await read(page.request, "900002");
  expect(first.identity.sku).toBe(second.identity.sku);
  expect(first.facts.every((f) => f.ecomm_id === "900001")).toBe(true);
  expect(second.facts.every((f) => f.ecomm_id === "900002")).toBe(true);
  expect(second.facts.find((f) => f.field === "net_weight")?.presentation).toBe(
    "1 kg",
  );
});

test("409 de una decisión en otra sesión conserva el motivo y no reintenta aprobación", async ({
  page,
  request,
}) => {
  await open(page);
  await extract(page);
  const otherLogin = await request.post("/api/auth/login", {
    data: { username: "operador-prueba", password: "solo-datos-sinteticos" },
  });
  const csrf = (await otherLogin.json()).csrf_token;
  const current = await read(page.request);
  const target = current.facts.find(
    (f) => f.field === "ingredients" && f.document_id === "alm-tecnica",
  )!;
  let attempts = 0;
  await page.route(
    `**${researchPath("900001")}/facts/${target.id}/review`,
    async (route) => {
      attempts++;
      const body = route.request().postDataJSON();
      const won = await request.post(
        `${researchPath("900001")}/facts/${target.id}/review`,
        {
          headers: { "X-CSRF-Token": csrf },
          data: {
            ...body,
            decision: "REJECTED",
            reason: "Otra sesión revisó primero este hecho sintético.",
          },
        },
      );
      expect(won.status()).toBe(200);
      await route.continue();
    },
    { times: 1 },
  );
  await decide(page, "alm-tecnica", "ingredients", "Aprobar hecho");
  await expect(page.getByRole("alert")).toContainText("otra sesión");
  expect(attempts).toBe(1);
  await expect(
    fact(page, "alm-tecnica", "ingredients").locator(".r-state"),
  ).toHaveText("Rechazada");
  await expect(
    fact(page, "alm-tecnica", "ingredients").getByRole("textbox"),
  ).toHaveValue(
    "Contrasté el fragmento y la variante de prueba de forma explícita.",
  );
});
