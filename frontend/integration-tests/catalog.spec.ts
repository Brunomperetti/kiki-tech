import { test, expect, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import {
  adaptCatalog,
  catalogPath,
  queuePath,
} from "../src/integration/catalog-adapter";

const rows = (page: Page) => page.locator("tbody tr");
const sourceHeaders = {
  "Content-Type": "application/json",
  "X-Kiki-Environment": "local-synthetic",
};
const external = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page, context }) => {
  const requests: string[] = [];
  external.set(page, requests);
  await context.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== "https://127.0.0.1:8443") {
      requests.push(route.request().url());
      return route.abort();
    }
    return route.continue();
  });
});
test.afterEach(async ({ page }) => {
  expect(external.get(page)).toEqual([]);
});
async function login(page: Page, path = "/") {
  await page.goto(path);
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Tu catálogo, en un solo lugar." }),
  ).toBeVisible();
  await expect(rows(page)).toHaveCount(6);
}
async function payload(page: Page) {
  const result = await page.request.get(catalogPath + "?q=&page=1&limit=6");
  expect(result.status()).toBe(200);
  return result.json();
}
async function mockCatalog(page: Page, body: unknown, status = 200) {
  // A local catalog double must agree with the separately authenticated queue.
  // Runtime code never invents queue rows or uses this test-only mapping.
  const catalog = body as {
    items?: Record<string, unknown>[];
    total_matches?: number;
    total_variants_in_capture?: number;
    capture_last_at?: string | null;
  };
  if (status === 200 && Array.isArray(catalog.items)) {
    const response = await page.request.get(
      `${queuePath}?sort=capture&limit=6`,
    );
    const queue = await response.json();
    const rows = queue.items;
    queue.total = catalog.total_matches;
    queue.source_snapshot_at = catalog.capture_last_at;
    queue.summary = Object.fromEntries(
      Object.entries(queue.summary).map(([key, value]) => [
        key,
        key === "total"
          ? catalog.total_variants_in_capture
          : Math.min(Number(value), catalog.total_variants_in_capture ?? 0),
      ]),
    );
    queue.items = catalog.items.map((source) => ({
      ...(rows.find(
        (x: { ecomm_id: unknown }) => x.ecomm_id === source.ecomm_id,
      ) || rows[0]),
      source,
      ecomm_id: source.ecomm_id,
      sku: source.sku ?? "",
      product_name: source.product_name ?? "",
    }));
    await page.route(`**${queuePath}?*`, (route) =>
      route.fulfill({
        status: 200,
        headers: sourceHeaders,
        body: JSON.stringify(queue),
      }),
    );
  }
  await page.route(`**${catalogPath}?*`, (route) =>
    route.fulfill({
      status,
      headers: sourceHeaders,
      body: JSON.stringify(body),
    }),
  );
  await page
    .getByRole("button", { name: "Volver a consultar", exact: true })
    .click();
}

test("seis variantes persistidas, indicadores del backend y capturas", async ({
  page,
}, info) => {
  await login(page);
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
  await expect(page.getByTestId("shown").locator("strong")).toHaveText("6");
  await expect(page.getByTestId("capture")).toContainText("Completa");
  expect(
    await rows(page).evaluateAll((items) =>
      items.map((row) => row.getAttribute("data-ecomm-id")),
    ),
  ).toEqual(["900001", "900002", "900003", "900004", "900005", "900006"]);
  await expect(
    page.getByLabel("Indicadores sin fuente integrada"),
  ).toContainText("Sin datos disponibles");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `artifacts/integracion-${info.project.name}.png`,
    fullPage: true,
  });
  await rows(page).first().getByRole("button", { name: "Ver ficha" }).click();
  await expect(
    page.getByRole("dialog", { name: "Ficha 900001" }),
  ).toBeVisible();
  await page.screenshot({
    path: `artifacts/integracion-ficha-${info.project.name}.png`,
  });
});

test("búsqueda y paginación conservan total global, URL y contexto de ficha", async ({
  page,
}) => {
  await login(page);
  await page.getByLabel("Variantes por página").selectOption("3");
  await expect(rows(page)).toHaveCount(3);
  await page.getByRole("button", { name: "Siguiente", exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(rows(page).first()).toHaveAttribute("data-ecomm-id", "900004");
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
  await rows(page).first().getByRole("button", { name: "Ver ficha" }).click();
  await expect(page).toHaveURL(/product=900004/);
  await page.getByRole("button", { name: "Cerrar ficha" }).click();
  await expect(page).toHaveURL(/page=2/);
  await page
    .getByRole("textbox", { name: "Buscar productos" })
    .fill("DEMO-ALM");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(rows(page)).toHaveCount(2);
  await expect(page).toHaveURL(/q=DEMO-ALM/);
  await page.goBack();
  await expect(rows(page).first()).toHaveAttribute("data-ecomm-id", "900004");
  await expect(
    page.getByRole("textbox", { name: "Buscar productos" }),
  ).toHaveValue("");
});

test("un SKU duplicado conserva dos Ecomm IDs y dos presentaciones", async ({
  page,
}) => {
  await login(page);
  await page
    .getByRole("textbox", { name: "Buscar productos" })
    .fill("DEMO-ALM");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(rows(page)).toHaveCount(2);
  for (const [id, presentation] of [
    ["900001", "250 g"],
    ["900002", "1 kg"],
  ]) {
    await page
      .locator(`[data-ecomm-id="${id}"]`)
      .getByRole("button", { name: "Ver ficha" })
      .click();
    await expect(page.getByRole("dialog")).toContainText(presentation);
    await expect(page.getByRole("dialog")).toContainText(`Ecomm ID: ${id}`);
    await page.keyboard.press("Escape");
  }
  await expect(
    page.getByRole("textbox", { name: "Buscar productos" }),
  ).toHaveValue("DEMO-ALM");
});

test("búsqueda sin resultados usa la respuesta real y mantiene la captura global", async ({
  page,
}) => {
  await login(page);
  await page
    .getByRole("textbox", { name: "Buscar productos" })
    .fill("SYNTHETIC-NOT-FOUND");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sin resultados" }),
  ).toBeVisible();
  await expect(rows(page)).toHaveCount(0);
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
});

test("catálogo completo vacío se representa con un doble local explícito", async ({
  page,
}) => {
  await login(page);
  const body = await payload(page);
  body.items = [];
  body.total_matches = 0;
  body.total_variants_in_capture = 0;
  body.quality.variants = 0;
  await mockCatalog(page, body);
  await expect(
    page.getByRole("heading", { name: "Catálogo vacío" }),
  ).toBeVisible();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("0");
  await expect(rows(page)).toHaveCount(0);
});

test("datos opcionales ausentes y stock cero no generan marca, EAN o imágenes", async ({
  page,
}) => {
  await login(page);
  const body = await payload(page);
  body.capture_first_at = null;
  body.capture_last_at = null;
  for (const item of body.items) {
    item.stock_at_capture = null;
    item.gtin = null;
    item.sku = null;
    item.captured_at = null;
    item.variant_description = null;
  }
  body.items[0].stock_at_capture = 0;
  await mockCatalog(page, body);
  await expect(
    rows(page).first().locator('td[data-label="Stock de captura"]'),
  ).toContainText("0");
  await rows(page).first().getByRole("button", { name: "Ver ficha" }).click();
  await expect(page.getByRole("dialog")).toContainText("Sin datos disponibles");
  await expect(page.locator("img, video, iframe")).toHaveCount(0);
});

for (const [status, message] of [
  [403, "No tenés permiso"],
  [409, "Captura incompleta"],
  [500, "no pudo responder"],
] as const) {
  test(`error ${status}: sin productos ni indicadores de fallback`, async ({
    page,
  }) => {
    await login(page);
    await mockCatalog(page, { detail: "synthetic-error" }, status);
    await expect(page.getByRole("alert")).toContainText(message);
    await expect(rows(page)).toHaveCount(0);
    await expect(page.getByTestId("total").locator("strong")).toHaveText("—");
    await expect(
      page.getByRole("button", { name: "Reintentar", exact: true }),
    ).toBeVisible();
  });
}

test("401 y sesión perdida regresan al login conservando filtros", async ({
  page,
  context,
}) => {
  await login(page);
  await page.getByRole("textbox", { name: "Buscar productos" }).fill("Avena");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(rows(page)).toHaveCount(1);
  await context.clearCookies();
  await page
    .getByRole("button", { name: "Volver a consultar", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("La sesión venció");
  await expect(page).toHaveURL(/q=Avena/);
  await expect(rows(page)).toHaveCount(0);
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(rows(page)).toHaveCount(1);
});

test("un corte de conexión no carga fixtures y permite reintentar", async ({
  page,
}) => {
  await login(page);
  const abort = (route: Route) => route.abort();
  await page.route(`**${catalogPath}?*`, abort);
  await page
    .getByRole("button", { name: "Volver a consultar", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "No pudimos comunicarnos",
  );
  await expect(rows(page)).toHaveCount(0);
  await page.unroute(`**${catalogPath}?*`, abort);
  await page.getByRole("button", { name: "Reintentar", exact: true }).click();
  await expect(rows(page)).toHaveCount(6);
});

test("identidad y metadatos ambiguos se rechazan sin fallback", async ({
  page,
}) => {
  await login(page);
  const original = await payload(page);
  for (const change of [
    (body: typeof original) => {
      body.items[1].ecomm_id = body.items[0].ecomm_id;
    },
    (body: typeof original) => {
      body.total_variants_in_capture = 3;
    },
    (body: typeof original) => {
      body.source = "HISTORICAL_XLSX";
    },
    (body: typeof original) => {
      body.quality.duplicate_variant_ids = 1;
    },
  ]) {
    const body = structuredClone(original);
    change(body);
    expect(() => adaptCatalog(body, "", 1, 6)).toThrow(
      "incompatible o ambigua",
    );
  }
  original.items[1].ecomm_id = original.items[0].ecomm_id;
  await mockCatalog(page, original);
  await expect(page.getByRole("alert")).toContainText("incompatible o ambigua");
  await expect(rows(page)).toHaveCount(0);
});

test("operaciones comerciales bloqueadas tanto en UI como en gateway", async ({
  page,
}) => {
  await login(page);
  await rows(page).first().getByRole("button", { name: "Ver ficha" }).click();
  for (const tab of ["Ficha", "Evidencias", "IA", "Canales", "Historial"]) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    for (const name of [
      "Generar con IA",
      "Aprobar cambios",
      "Preparar por canal",
    ])
      await expect(
        page.getByRole("button", { name, exact: true }),
      ).toBeDisabled();
  }
  for (const path of [
    "/api/ecomm-app/workspace/900001/confirm-review",
    "/api/ecomm-app/stage/manual/start",
    "/api/mercadolibre/sync",
    "/api/tiendanube/import-csv",
    "/api/ecomm-app/workspace/ai/900001/suggest",
  ]) {
    expect((await page.request.post(path)).status()).toBe(403);
  }
});

test("proveedores, imágenes, video y redirecciones externas están bloqueados", async ({
  page,
}) => {
  await login(page);
  const blocked = await page.evaluate(async () => {
    const results = [];
    for (const url of [
      "https://admin.ecomm-app.com",
      "https://api.mercadolibre.com",
      "https://api.tiendanube.com",
      "https://api.openai.com",
      "https://kiki-tech-api.onrender.com",
    ]) {
      try {
        await fetch(url);
        results.push(false);
      } catch {
        results.push(true);
      }
    }
    const image = document.createElement("img");
    image.src = "https://admin.ecomm-app.com/forbidden.png";
    document.body.append(image);
    const video = document.createElement("video");
    video.src = "https://api.tiendanube.com/forbidden.mp4";
    video.preload = "auto";
    document.body.append(video);
    return results;
  });
  expect(blocked).toEqual([true, true, true, true, true]);
  await page.route(`**${catalogPath}?*`, (route) =>
    route.fulfill({
      status: 307,
      headers: { Location: "https://kiki-tech-api.onrender.com/forbidden" },
    }),
  );
  await page
    .getByRole("button", { name: "Volver a consultar", exact: true })
    .click();
  await expect(page.getByRole("alert")).toBeVisible();
});

for (const replacement of [
  "",
  '<meta name="kiki-environment" content="local-synthetic" /><meta name="kiki-environment" content="local-synthetic" />',
]) {
  test(`configuración ${replacement ? "ambigua" : "incompleta"} no consulta backend ni entra en demo`, async ({
    page,
  }) => {
    let apiRequests = 0;
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.startsWith("/api/")) apiRequests++;
    });
    const html = readFileSync(
      ".integration-dist/integration.html",
      "utf8",
    ).replace(
      '<meta name="kiki-environment" content="local-synthetic" />',
      replacement,
    );
    await page.route("https://127.0.0.1:8443/", (route) =>
      route.fulfill({ contentType: "text/html", body: html }),
    );
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Integración bloqueada" }),
    ).toBeVisible();
    expect(apiRequests).toBe(0);
    await expect(rows(page)).toHaveCount(0);
  });
}

test("URL inválida conserva error explícito y no consulta catálogo", async ({
  page,
}) => {
  await login(page);
  let calls = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === catalogPath) calls++;
  });
  await page.goto("/?page=0&limit=6");
  await expect(
    page.getByRole("heading", { name: "Filtros de URL inválidos" }),
  ).toBeVisible();
  expect(calls).toBe(0);
  await expect(rows(page)).toHaveCount(0);
});
