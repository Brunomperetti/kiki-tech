import { legacyDocumental } from "./legacy-documental";
import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import type { Dossier } from "../src/integration/research-adapter";
import type { Proposal } from "../src/integration/proposal-adapter";
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
test.afterEach(async ({ page }) => expect(outside.get(page)).toEqual([]));
async function csrf(api: APIRequestContext) {
  return (await (await api.get("/api/auth/me")).json()).csrf_token as string;
}
async function read(api: APIRequestContext, id = "900001"): Promise<Dossier> {
  return (await api.get(`/api/test-research/${id}`)).json();
}
async function post(api: APIRequestContext, path: string, data: unknown) {
  const response = await api.post(path, {
    headers: { "X-CSRF-Token": await csrf(api) },
    data,
  });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}
async function extract(
  api: APIRequestContext,
  name: string,
  id = "900001",
  approve = true,
  omit: string[] = [],
) {
  let dossier = await read(api, id);
  const doc = dossier.documents.find((d) => d.id === name)!;
  dossier = await post(api, `/api/test-research/${id}/extract`, {
    expected_version: dossier.version,
    document_id: name,
    document_version: doc.version,
  });
  if (approve)
    for (const item of dossier.facts.filter(
      (f) => f.document_id === name && !omit.includes(f.field),
    )) {
      const current = dossier.facts.find((f) => f.id === item.id)!;
      dossier = await post(
        api,
        `/api/test-research/${id}/facts/${item.id}/review`,
        {
          expected_version: dossier.version,
          expected_fact_version: current.version,
          decision: "APPROVED",
          reason:
            "Revisión explícita de documentación sintética para la propuesta.",
        },
      );
    }
  return dossier;
}
async function open(page: Page, id = "900001", omit: string[] = []) {
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator(`[data-ecomm-id="${id}"]`)).toBeVisible();
  // Explicit decisions and commercial saves through public test APIs; no DB reset/mock persistence.
  let dossier = await read(page.request, id);
  for (const f of dossier.facts) {
    const current = dossier.facts.find((x) => x.id === f.id)!;
    dossier = await post(
      page.request,
      `/api/test-research/${id}/facts/${f.id}/review`,
      {
        expected_version: dossier.version,
        expected_fact_version: current.version,
        decision: "REJECTED",
        reason:
          "Inicio de un recorrido de prueba independiente con decisiones trazables.",
      },
    );
  }
  const record = await (await page.request.get(workspacePath(id))).json();
  await post(page.request, workspacePath(id), {
    expected_version: record.version,
    status: "DRAFT",
    fields: {
      ...record.fields,
      title: "Título previo de prueba para comparar",
      description: "Descripción anterior sintética para comparar.",
      brand: "Marca sintética KIKI",
      manufacturer: "Fabricante de prueba",
      presentation: id === "900001" ? "250 g" : "1 kg",
      proposed_gtin: "",
      note: "Preparación explícita de caso de generación sintética.",
    },
  });
  if (id === "900001") {
    await extract(page.request, "alm-clasificacion");
    await extract(page.request, "alm-tecnica", id, true, omit);
  } else await extract(page.request, "alm-pack-1kg", id);
  await page
    .locator(`[data-ecomm-id="${id}"]`)
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await expect(
    page.getByLabel("Marca comercial", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Generar propuesta de prueba",
      exact: true,
    }),
  ).toBeEnabled();
}
async function generate(page: Page) {
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/generate") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generar propuesta de prueba", exact: true })
    .click();
  expect((await response).status()).toBe(200);
  await expect(
    page.getByText("Propuesta de prueba generada.", { exact: false }),
  ).toBeVisible();
}
async function review(page: Page, keys = ["title"]) {
  for (const key of keys)
    await page
      .getByLabel(`Decisión ${key}`, { exact: true })
      .selectOption("ACCEPTED");
  await page
    .getByRole("button", { name: "Registrar revisión individual", exact: true })
    .click();
  await expect(
    page.getByText("Revisión registrada en PostgreSQL.", { exact: false }),
  ).toBeVisible();
}
const card = (page: Page, key: string) =>
  page.locator(`[data-proposal-field="${key}"]`);

test("propuesta completa, edición respaldada, revisión individual y guardado real con recarga e historial", async ({
  page,
}, info) => {
  test.setTimeout(60000);
  await open(page);
  const before = await (await page.request.get(workspacePath("900001"))).json();
  await generate(page);
  expect(
    (await (await page.request.get(workspacePath("900001"))).json()).version,
  ).toBe(before.version);
  await card(page, "title")
    .getByText("Respaldo de este campo", { exact: false })
    .click();
  await card(page, "title")
    .getByText("Valor actual al generar", { exact: true })
    .click();
  await expect(card(page, "title")).toContainText(before.fields.title);
  await expect(card(page, "title")).toContainText("APPROVED");
  await card(page, "title").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/propuesta-comparacion-${info.project.name}.png`,
  });
  await page
    .getByLabel("Propuesta description", { exact: true })
    .fill("Ingredientes: Almendras.\nAlmendras sintéticas · 250 g.");
  await page
    .getByLabel("Decisión category", { exact: true })
    .selectOption("REJECTED");
  await expect(page.locator(".d-drawer-status")).toContainText(
    "Cambios sin guardar",
  );
  await review(page, ["title", "description"]);
  expect(
    (await (await page.request.get(workspacePath("900001"))).json()).version,
  ).toBe(before.version);
  page.once("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Guardar selección en ficha", exact: true })
    .click();
  await expect(
    page.getByText("Selección guardada en PostgreSQL de pruebas", {
      exact: false,
    }),
  ).toBeVisible();
  const saved = await (await page.request.get(workspacePath("900001"))).json();
  expect(saved.version).toBe(before.version + 1);
  expect(saved.fields.description).toBe(
    "Ingredientes: Almendras.\nAlmendras sintéticas · 250 g.",
  );
  expect(saved.fields.category).toBe(before.fields.category);
  expect(saved.fields.media).toEqual(before.fields.media);
  await page.getByRole("tab", { name: "Ficha", exact: true }).click();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "Almendras sintéticas · 250 g",
  );
  await page.reload();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "Almendras sintéticas · 250 g",
  );
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toContainText(
    `Versión ${saved.version}`,
  );
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await expect(
    page.getByText("Selección ya guardada.", { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByText("Historial de la propuesta", { exact: true }).click();
  await expect(page.getByRole("tabpanel")).toContainText(
    "APPLIED_VIA_WORKSPACE",
  );
  await page
    .getByText("Historial de la propuesta", { exact: true })
    .scrollIntoViewIfNeeded();
  expect(
    await page
      .getByRole("tabpanel")
      .evaluate((el) => el.scrollWidth - el.clientWidth),
  ).toBeLessThanOrEqual(1);
  await page.screenshot({
    path: `artifacts/propuesta-guardada-${info.project.name}.png`,
  });
});

test("ingredientes no aprobados se omiten; una afirmación inventada bloquea la revisión", async ({
  page,
}, info) => {
  await open(page, "900001", ["ingredients"]);
  await generate(page);
  await expect(
    page.getByLabel("Propuesta description", { exact: true }),
  ).not.toHaveValue(/Ingredientes:/);
  await expect(page.getByRole("tabpanel")).toContainText(
    "Ingredientes: afirmación bloqueada",
  );
  const before = await (await page.request.get(workspacePath("900001"))).json();
  await page
    .getByLabel("Propuesta description", { exact: true })
    .fill("Sin gluten. Producto orgánico.");
  await page
    .getByLabel("Decisión description", { exact: true })
    .selectOption("ACCEPTED");
  await page
    .getByRole("button", { name: "Registrar revisión individual", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("Texto sin respaldo");
  await expect(
    page.getByLabel("Propuesta description", { exact: true }),
  ).toHaveValue("Sin gluten. Producto orgánico.");
  expect(
    (await (await page.request.get(workspacePath("900001"))).json()).version,
  ).toBe(before.version);
  await page.getByRole("alert").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/propuesta-bloqueada-${info.project.name}.png`,
  });
});

test("una fuente nueva contradictoria invalida la propuesta y excluye esa afirmación", async ({
  page,
}) => {
  await open(page);
  await generate(page);
  await review(page);
  let dossier = await read(page.request);
  const doc = dossier.documents.find(
    (d) => d.id === "alm-nutricion-conflicto",
  )!;
  const old = dossier.facts.find((f) => f.document_id === doc.id);
  if (old)
    await post(
      page.request,
      `/api/test-research/documents/${doc.id}/revision`,
      { expected_version: doc.version, new_version: doc.version + 1 },
    );
  await extract(page.request, doc.id, "900001", false);
  await page
    .getByRole("button", { name: "Recuperar propuesta guardada", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Las evidencias o la identidad cambiaron",
  );
  await expect(
    page.getByRole("button", {
      name: "Guardar selección en ficha",
      exact: true,
    }),
  ).toBeDisabled();
  await generate(page);
  await expect(
    page.getByLabel("Propuesta description", { exact: true }),
  ).not.toHaveValue(/Energía:/);
  await expect(page.getByRole("tabpanel")).toContainText(
    "Energía: afirmación bloqueada",
  );
});

test("revocar evidencia entre revisión y guardado provoca 409 sin cambiar la ficha", async ({
  page,
}) => {
  await open(page);
  await generate(page);
  await review(page);
  const before = await (await page.request.get(workspacePath("900001"))).json();
  const dossier = await read(page.request),
    f = dossier.facts.find(
      (f) => f.field === "ingredients" && f.state === "APPROVED",
    )!;
  await post(page.request, `/api/test-research/900001/facts/${f.id}/review`, {
    expected_version: dossier.version,
    expected_fact_version: f.version,
    decision: "REVOKED",
    reason: "Revocación sintética posterior a la revisión comercial.",
  });
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith(workspacePath("900001")) &&
      r.request().method() === "POST",
  );
  page.once("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Guardar selección en ficha", exact: true })
    .click();
  expect((await response).status()).toBe(409);
  await expect(page.getByRole("alert")).toContainText("Aplicación bloqueada");
  expect(
    (await (await page.request.get(workspacePath("900001"))).json()).version,
  ).toBe(before.version);
});

test("otra sesión guarda primero; el contrato versionado conserva 409 y no pisa cambios", async ({
  page,
  playwright,
}) => {
  await open(page);
  await generate(page);
  await review(page);
  const other = await playwright.request.newContext({
    baseURL: "https://127.0.0.1:8443",
  });
  try {
    const auth = await (
      await other.post("/api/auth/login", {
        data: {
          username: "operador-prueba",
          password: "solo-datos-sinteticos",
        },
      })
    ).json();
    const current = await (await other.get(workspacePath("900001"))).json();
    const response = await other.post(workspacePath("900001"), {
      headers: { "X-CSRF-Token": auth.csrf_token },
      data: {
        expected_version: current.version,
        status: "DRAFT",
        fields: {
          ...current.fields,
          note: "Ganó la segunda sesión sin sobrescritura.",
        },
      },
    });
    expect(response.status()).toBe(200);
    const application = page.waitForResponse(
      (r) =>
        r.url().endsWith(workspacePath("900001")) &&
        r.request().method() === "POST",
    );
    page.once("dialog", (d) => d.accept());
    await page
      .getByRole("button", { name: "Guardar selección en ficha", exact: true })
      .click();
    expect((await application).status()).toBe(409);
    await expect(
      page
        .getByRole("alert")
        .filter({ hasText: "La ficha cambió desde la generación" })
        .first(),
    ).toBeVisible();
    expect(
      (await (await page.request.get(workspacePath("900001"))).json()).fields
        .note,
    ).toBe("Ganó la segunda sesión sin sobrescritura.");
  } finally {
    await other.dispose();
  }
});

test("SKU compartido no reutiliza hechos de 250 g para la presentación 1 kg", async ({
  page,
}) => {
  await open(page, "900002");
  await generate(page);
  await expect(page.locator('[data-proposal-field="title"]')).toHaveCount(0);
  const proposal = (await (
    await page.request.get("/api/test-proposals/900002")
  ).json()) as Proposal;
  expect(
    proposal.evidence.every(
      (f) => f.ecomm_id === "900002" && f.presentation === "1 kg",
    ),
  ).toBe(true);
  expect(proposal.fields.attributes?.value).toEqual([
    { name: "Contenido neto", value: "1000 g" },
  ]);
  expect(proposal.missing).toContain(
    "Títulos: falta nombre o presentación con respaldo aprobado.",
  );
});

test.beforeEach(async ({ page }) => {
  await legacyDocumental(page);
});
