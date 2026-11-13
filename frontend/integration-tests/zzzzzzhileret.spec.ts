import { test, expect, type Page } from "@playwright/test";
import {
  hileretUnitId as unit,
  hileretPackId as pack,
  hileretPilotPath as api,
} from "../src/integration/hileret-pilot";

test.setTimeout(90000);
const external = new WeakMap<Page, string[]>(),
  calls = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page, context }) => {
  const blocked: string[] = [],
    requested: string[] = [];
  external.set(page, blocked);
  calls.set(page, requested);
  await context.route("**/*", (route) => {
    const url = route.request().url();
    requested.push(url);
    if (new URL(url).origin !== "https://127.0.0.1:8443") {
      blocked.push(url);
      return route.abort();
    }
    return route.continue();
  });
});
test.afterEach(async ({ page }) => {
  expect(external.get(page)).toEqual([]);
  expect(
    calls.get(page)?.some((url) => /test-discovery\/PILOT-HILERET/.test(url)),
  ).toBe(false);
});

async function login(page: Page, q = "") {
  await page.goto(q ? `/?q=${q}` : "/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
}
async function open(page: Page, kind: "unidad" | "pack x6" = "unidad") {
  await page
    .getByRole("button", {
      name: `Abrir Hileret ${kind} de pruebas`,
      exact: true,
    })
    .click();
  const id = kind === "unidad" ? unit : pack;
  await expect(
    page.getByRole("dialog", { name: `Ficha ${id}`, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Marca comercial", { exact: true }),
  ).toBeVisible();
  return page.getByLabel("Expediente comercial Hileret", { exact: true });
}

test("unidad y pack x6 separados, caja x9 logística y original pendiente sin modificar catálogo ni contexto", async ({
  page,
}, info) => {
  await login(page, "Almendras");
  let panel = await open(page);
  await expect(panel).toContainText("Unidad 200 ml");
  await expect(panel).toContainText("fila 28");
  await expect(panel).toContainText("EAN declarado: 7794940000796");
  await expect(panel).toContainText("DUN logístico 97794940000799");
  await expect(panel).toContainText("Caja logística x9");
  await expect(panel).toContainText("no es el pack x6");
  await expect(panel).toContainText("Bloqueado: PDF original no disponible");
  await expect(panel).toContainText(
    "Sin descarga, SHA-256 de archivo, extracción ni citas procesadas",
  );
  await expect(panel).toContainText("0 hechos aprobados");
  await expect(panel).toContainText("Ecomm ID auténtico: pendiente");
  const report = await (await page.request.get(api)).json();
  expect(report.cases.map((c: { test_id: string }) => c.test_id)).toEqual([
    unit,
    pack,
  ]);
  for (const c of report.cases) {
    expect(c.authentic_ecomm_id).toBeNull();
    expect(c.proposed_fields_preview).toEqual({});
    expect(c.original_pdf_available).toBe(false);
    expect(c.documents[0].original).toBeNull();
    expect(c.references.brochure.document_sha256_at_registration).toBeNull();
  }
  await expect(page.locator(`[data-ecomm-id="${unit}"]`)).toHaveCount(0);
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/hileret-unidad-${info.project.name}.png`,
  });
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  panel = await open(page, "pack x6");
  await expect(panel).toContainText("Pack comercial x6 de 200 ml");
  await expect(panel).toContainText("fila 27");
  expect(new URL(page.url()).searchParams.get("product")).toBe(pack);
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/hileret-pack6-${info.project.name}.png`,
  });
  await page.reload();
  await expect(
    page.getByRole("dialog", { name: `Ficha ${pack}`, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Buscar productos", exact: true }),
  ).toHaveValue("Almendras");
  expect(new URL(page.url()).searchParams.get("q")).toBe("Almendras");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("URL sin bytes bloquea extracción y propuesta, mantiene incorporación manual y no activa recolector", async ({
  page,
}, info) => {
  await login(page);
  await open(page);
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Investigar y completar ficha con IA",
      exact: true,
    })
    .click();
  const source = page.getByLabel("Procedencia del documento local");
  await expect(source).toContainText(
    "Sólo referencia: sin descarga ni extracción",
  );
  await expect(source).toContainText("No consultada por el navegador");
  await expect(source).toContainText("SHA-256 de la URL (no del PDF)");
  await expect(
    page.getByRole("button", {
      name: "Extraer hechos del documento",
      exact: true,
    }),
  ).toBeDisabled();
  await page
    .getByText("Incorporar archivo local o referencia oficial", { exact: true })
    .click();
  await expect(
    page.getByLabel("Archivo documental", { exact: true }),
  ).toHaveAttribute("accept", ".pdf,.txt,.html,.json");
  await source.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/hileret-documento-pendiente-${info.project.name}.png`,
  });
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/test-proposals/${unit}/generate`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generar propuesta de prueba", exact: true })
    .click();
  expect((await pending).status()).toBe(409);
  await expect(page.getByRole("alert")).toContainText("falta PDF original");
  await expect(page.getByRole("alert")).toContainText("pack x6 y caja x9");
  const report = await (await page.request.get(api)).json();
  expect(
    report.cases.every(
      (c: { approved_fact_count: number }) => c.approved_fact_count === 0,
    ),
  ).toBe(true);
});

test("seguimiento persiste y se recupera con historial y comparación sin copiar al pack ni completar ficha sin respaldo", async ({
  page,
}, info) => {
  await login(page);
  await open(page);
  const packBefore = await (
    await page.request.get(`/api/ecomm-app/workspace/${pack}`)
  ).json();
  const note = `Seguimiento ${info.project.name}: falta PDF original, Ecomm ID y respaldo específico del pack. Sin composición aprobada.`;
  await page
    .getByLabel("Observaciones y pendientes", { exact: true })
    .fill(note);
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/ecomm-app/workspace/${unit}`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  expect((await pending).status()).toBe(200);
  await page.reload();
  await expect(
    page.getByLabel("Observaciones y pendientes", { exact: true }),
  ).toHaveValue(note);
  await page
    .getByText("Comparación inicial / guardado local", { exact: true })
    .click();
  await expect(
    page.getByLabel("Expediente comercial Hileret", { exact: true }),
  ).toContainText(`Guardado: ${note}`);
  const report = await (await page.request.get(api)).json();
  const c = report.cases.find(
    (entry: { test_id: string }) => entry.test_id === unit,
  );
  expect(c.initial_fields.note).toBe("");
  expect(c.current_fields.note).toBe(note);
  for (const key of c.blocked_fields) expect(c.current_fields[key]).toBe("");
  expect(
    await (await page.request.get(`/api/ecomm-app/workspace/${pack}`)).json(),
  ).toEqual(packBefore);
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(note);
});
