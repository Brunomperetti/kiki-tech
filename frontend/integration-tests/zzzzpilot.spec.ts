import { expect, test, type Page } from "@playwright/test";
import type { Dossier } from "../src/integration/research-adapter";
const id = "900006",
  root = `/api/test-research/${id}`;
const text = `Nombre: Lentejas sintéticas
Marca: Marca sintética KIKI
Fabricante: Fabricante de prueba
Presentación: 1 kg
Tipo de venta: Unidad
Ingredientes: Lentejas
Contenido neto: 1 kg
Conservación: Conservar en lugar fresco y seco
`;
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
  return r.json() as Promise<Dossier>;
}
async function open(page: Page) {
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator(`[data-ecomm-id="${id}"]`)).toBeVisible();
  let data = (await (await page.request.get(root)).json()) as Dossier;
  for (const f of data.facts.filter((f) => f.state === "APPROVED")) {
    const fresh = data.facts.find((v) => v.id === f.id)!;
    data = await post(page, `${root}/facts/${f.id}/review`, {
      expected_version: data.version,
      expected_fact_version: fresh.version,
      decision: "REJECTED",
      reason:
        "Preparación de un recorrido independiente con documentación sintética.",
    });
  }
  await page
    .locator(`[data-ecomm-id="${id}"]`)
    .getByRole("button", { name: "Ver ficha", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Investigar producto", exact: true })
    .click();
  await expect(
    page.getByLabel("Preparación del piloto documental"),
  ).toContainText("Dominios autorizados: 0");
}
test("piloto sin productos ni dominios autorizados, conector bloqueado y candidatos solamente simulados", async ({
  page,
}, info) => {
  await open(page);
  const panel = page.getByLabel("Preparación del piloto documental");
  await expect(panel).toContainText("Productos auténticos autorizados: 0");
  await expect(
    panel.getByRole("button", {
      name: "Obtener documento desde una fuente oficial",
      exact: false,
    }),
  ).toBeDisabled();
  await expect(panel).toContainText("El catálogo actual es sintético");
  const status = await (
    await page.request.get("/api/test-discovery/pilot-status")
  ).json();
  expect(status.network_enabled).toBe(false);
  expect(status.openai_enabled).toBe(false);
  expect(status.authorized_domains).toEqual([]);
  const response = await page.request.post("/api/test-discovery/enable", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: { network_enabled: true, domain: "fabricante-no-autorizado.invalid" },
  });
  expect(response.status()).toBe(403);
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/piloto-preparacion-${info.project.name}.png`,
  });
  expect(new URL(page.url()).pathname).toBe("/");
});
test("archivo suministrado sintético conserva procedencia, original y citas en el contrato de IA sin llamadas", async ({
  page,
}, info) => {
  await open(page);
  await page
    .getByText("Incorporar archivo local o referencia oficial", { exact: true })
    .click();
  await page
    .getByLabel(
      "Fabricante declarado por quien suministra el documento (opcional)",
      { exact: true },
    )
    .fill("Fabricante declarado del fixture");
  await page
    .getByLabel("Fecha de consulta informada por el usuario (opcional)", {
      exact: true,
    })
    .fill("2026-01-01");
  await page.getByLabel("Archivo documental", { exact: true }).setInputFiles({
    name: "documento-sintetico-piloto.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(text),
  });
  await page
    .getByLabel("Cómo obtuve la documentación", { exact: true })
    .fill(
      "Documento SINTÉTICO de ensayo. No fue obtenido de un fabricante auténtico ni de Internet.",
    );
  await page
    .getByLabel("URL de referencia (sin acceder)", { exact: true })
    .fill("https://fabricante-prueba.invalid/documento");
  await page
    .getByLabel("Declaro que la fuente es oficial; todavía no está verificada")
    .check();
  await page
    .getByLabel(
      "Autorizo expresamente el procesamiento local de este documento o referencia",
    )
    .check();
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/test-documents/${id}/import`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Incorporar documentación", exact: true })
    .click();
  const data = (await (await pending).json()) as Dossier;
  const key = data.incorporated_document_id!;
  const provenance = page.getByLabel("Procedencia del documento local");
  await expect(provenance).toContainText(
    "Fabricante declarado: Fabricante declarado del fixture",
  );
  await expect(provenance).toContainText(
    "Fabricante extraído: Fabricante de prueba",
  );
  await expect(provenance).toContainText(
    "Dominio de referencia: fabricante-prueba.invalid",
  );
  await expect(provenance).toContainText(
    "Fecha de consulta declarada: 01/01/2026",
  );
  await expect(provenance).toContainText("Pendiente de revisión");
  await provenance
    .getByRole("button", { name: "Comprobar original conservado", exact: true })
    .click();
  await expect(provenance.getByRole("status")).toContainText(
    "recuperado desde PostgreSQL",
  );
  await provenance.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/piloto-documento-${info.project.name}.png`,
  });
  await page
    .getByLabel("Motivo de revisión de procedencia", { exact: true })
    .fill(
      "Revisión manual del fixture sintético; no se certifica la autenticidad de una fuente real.",
    );
  page.once("dialog", (d) => d.accept());
  await page
    .getByRole("button", {
      name: "Registrar revisión de procedencia",
      exact: true,
    })
    .click();
  await expect(provenance).toContainText("Revisada por una persona");
  await page
    .getByRole("button", { name: "Extraer hechos del documento", exact: true })
    .click();
  const fact = page.locator(
    `.r-fact[data-document="${key}"][data-field="ingredients"]`,
  );
  await fact
    .getByRole("textbox")
    .fill(
      "Contrasté exactamente Ingredientes: Lentejas contra el documento sintético.",
    );
  page.once("dialog", (d) => d.accept());
  await fact
    .getByRole("button", { name: "Aprobar hecho", exact: true })
    .click();
  await expect(fact.locator(".r-state")).toHaveText("Aprobada");
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await page
    .getByText("Preparación avanzada para IA real · Desactivada", {
      exact: true,
    })
    .click();
  await page
    .getByRole("button", {
      name: "Ver contrato de hechos aprobados",
      exact: true,
    })
    .click();
  const contract = page.getByLabel("Contrato de generación respaldada");
  await expect(contract).toContainText("1 hecho aprobado");
  await expect(contract).toContainText("Llamadas externas: 0");
  await expect(contract).toContainText("Ingredientes: Lentejas");
  await contract.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `artifacts/piloto-contrato-ia-${info.project.name}.png`,
  });
  await page.reload();
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await page
    .getByLabel("Documento disponible", { exact: true })
    .selectOption(key);
  await expect(
    page.getByLabel("Procedencia del documento local"),
  ).toContainText("Fabricante declarado del fixture");
  expect(new URL(page.url()).pathname).toBe("/");
});
test("una respuesta que pretende activar Internet se rechaza en el dashboard", async ({
  page,
}) => {
  await open(page);
  await page.getByRole("tab", { name: "Ficha", exact: true }).click();
  await page.route("**/api/test-discovery/pilot-status", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: {
        ...(await response.json()),
        network_enabled: true,
        release_locked: false,
        openai_enabled: true,
        authorized_domains: ["production.invalid"],
        authorized_products: ["real"],
      },
    });
  });
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  const panel = page.getByLabel("Preparación del piloto documental");
  await expect(panel.getByRole("alert")).toContainText(
    "Estado de aislamiento incompatible",
  );
  await expect(panel.getByRole("button")).toBeDisabled();
});
