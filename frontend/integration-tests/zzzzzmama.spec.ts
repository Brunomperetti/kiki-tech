import { test, expect, type Page } from "@playwright/test";
import {
  mamaPilotId as id,
  mamaPilotPath as api,
} from "../src/integration/mama-pilot";
const workspace = `/api/ecomm-app/workspace/${id}`;
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
    calls.get(page)?.some((url) => url.includes(`/test-discovery/${id}/start`)),
  ).toBe(false);
});
async function open(page: Page, filtered = false) {
  await page.goto(filtered ? "/?q=Almendras" : "/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Abrir expediente MAMA de pruebas",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("dialog", { name: `Ficha ${id}`, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Marca comercial", { exact: true }),
  ).toBeVisible();
}
test("referencias separadas, identidad sintética y catálogo intacto con URL y búsqueda conservadas", async ({
  page,
}, info) => {
  await open(page, true);
  const panel = page.getByLabel("Expediente comercial MAMA 350 g");
  await expect(panel).toContainText("Ecomm ID auténtico: pendiente");
  await expect(panel).toContainText("Sin vinculación por SKU o EAN");
  await expect(panel).toContainText("fila 37");
  await expect(panel).toContainText("Sheet1");
  await expect(panel).toContainText("Verificación externa al entorno de Codex");
  await expect(panel).toContainText("No calculado por Codex");
  for (const cell of ["B37", "Y37", "Q37", "R37", "L37", "U37", "W37", "X37"])
    await expect(panel).toContainText(cell);
  await expect(panel).toContainText(
    "Evidencia secundaria no oficial · Barcode-List",
  );
  await expect(panel).toContainText("MAMA RICE NOODLE 350G 10MM");
  await expect(panel).toContainText(
    "No acredita composición, origen oficial del EAN ni Ecomm ID auténtico",
  );
  await expect(panel).toContainText("8851876201433");
  await expect(panel).toContainText(
    "Correspondencia oficial con esta variante: pendiente",
  );
  await expect(panel).toContainText("0,4 kg. No es contenido neto verificado");
  await expect(panel).toContainText("Mama Rice Noodles 350g (10 Mm.)");
  await expect(panel).toContainText("0 hechos aprobados");
  await expect(page.locator(`[data-ecomm-id="${id}"]`)).toHaveCount(0);
  const report = await (await page.request.get(api)).json();
  expect(report.references.excel.original_file_sha256).toBe(
    "03c6b219335ee1dad31f8bc2c1cbd51d12f416fbe25bd9a26ece8350c30c414f",
  );
  expect(report.references.excel.external_verification.scope).toBe(
    "EXTERNAL_TO_CODEX",
  );
  expect(report.references.excel.external_verification.verified_in_codex).toBe(
    false,
  );
  expect(report.references.third_party_candidate.classification).toBe(
    "NON_OFFICIAL",
  );
  expect(report.proposed_fields_preview).toEqual({});
  expect(report.blocked_fields).toHaveLength(9);
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/mama-inicial-${info.project.name}.png`,
  });
  expect(new URL(page.url()).searchParams.get("product")).toBe(id);
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Buscar productos", exact: true }),
  ).toHaveValue("Almendras");
  expect(new URL(page.url()).searchParams.get("q")).toBe("Almendras");
});
test("referencia sin descarga no permite extracción ni propuesta y solicita evidencia precisa", async ({
  page,
}, info) => {
  await open(page);
  await page
    .getByRole("button", { name: "Investigar producto", exact: true })
    .click();
  await expect(
    page.getByLabel("Expediente comercial MAMA 350 g"),
  ).toContainText("Propuesta comercial bloqueada");
  const source = page.getByLabel("Procedencia del documento local");
  await expect(source).toContainText(
    "Sólo referencia: sin descarga ni extracción",
  );
  await expect(source).toContainText("No consultada por el navegador");
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
    path: `artifacts/mama-evidencia-${info.project.name}.png`,
  });
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/test-proposals/${id}/generate`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generar propuesta de prueba", exact: true })
    .click();
  expect((await pending).status()).toBe(409);
  const error = page.getByRole("alert");
  await expect(error).toContainText("10 mm");
  await expect(error).toContainText("350 g");
  await expect(error).toContainText("Excel informado no bastan");
  const report = await (await page.request.get(api)).json();
  expect(report.approved_fact_count).toBe(0);
  expect(report.proposed_fields_preview).toEqual({});
  await error.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/mama-bloqueo-${info.project.name}.png`,
  });
});
test("guarda y recupera sólo una nota de seguimiento con comparación e historial sin completar contenido no respaldado", async ({
  page,
}, info) => {
  await open(page);
  const note = `Pendiente documento auténtico con EAN, ancho 10 mm y contenido neto 350 g. Vinculación real Ecomm-App pendiente. Recorrido ${info.project.name}.`;
  await page
    .getByLabel("Observaciones y pendientes", { exact: true })
    .fill(note);
  const pending = page.waitForResponse(
    (r) => r.url().endsWith(workspace) && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  expect((await pending).status()).toBe(200);
  await page.reload();
  await expect(
    page.getByLabel("Observaciones y pendientes", { exact: true }),
  ).toHaveValue(note);
  const report = await (await page.request.get(api)).json();
  expect(report.initial_fields.note).toBe("");
  expect(report.current_fields.note).toBe(note);
  for (const key of report.blocked_fields)
    expect(report.current_fields[key]).toBe("");
  await page
    .getByText("Comparación inicial / guardado local", { exact: true })
    .click();
  await expect(
    page.getByLabel("Expediente comercial MAMA 350 g"),
  ).toContainText(`Guardado: ${note}`);
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(note);
  const ws = await (await page.request.get(workspace)).json();
  expect(ws.history.length).toBeGreaterThan(0);
  expect(ws.source.authentic_ecomm_id).toBeNull();
});
