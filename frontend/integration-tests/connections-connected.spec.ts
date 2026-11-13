import { test, expect, type Page } from "@playwright/test";
import type { ConnectionStatus } from "../src/integration/connections";
test.skip(
  process.env.KIKI_CONNECTION_SCENARIO !== "offline-fixtures",
  "Escenario explícito de conexiones sin red.",
);
test.setTimeout(90000);
const center = (page: Page) =>
  page.getByRole("region", { name: "Centro de conexiones", exact: true });
const card = (page: Page, name: string) =>
  center(page).getByRole("article", { name, exact: true });
async function original(page: Page): Promise<ConnectionStatus> {
  const r = await page.request.get("/api/connections/status");
  expect(r.status()).toBe(200);
  return r.json();
}
async function open(page: Page) {
  await page
    .getByRole("button", { name: "Centro de conexiones", exact: true })
    .click();
  await expect(center(page)).toBeVisible();
  await expect(card(page, "Conexión Ecomm-App")).toContainText(
    "Lectura API configurada",
  );
}
test.beforeEach(async ({ page, context }) => {
  await context.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (u.origin !== "https://127.0.0.1:8443")
      throw new Error("Salida externa prohibida");
    if (
      route.request().method() === "POST" &&
      ![
        "/api/auth/login",
        "/api/auth/logout",
        "/api/ecomm-app/stage/manual/start",
        "/api/mercadolibre/sync",
        "/api/mercadolibre/auth-url",
        "/api/tiendanube/import-csv",
        "/api/ecomm-app/workspace/900003",
      ].includes(u.pathname)
    )
      throw new Error("Operación no autorizada");
    return route.continue();
  });
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
});

test("tres conexiones registradas, cuenta existente sin pedir OAuth y capturas por grano", async ({
  page,
}, info) => {
  const data = await original(page);
  await open(page);
  await expect(center(page).getByRole("article")).toHaveCount(3);
  const e = card(page, "Conexión Ecomm-App");
  await expect(e).toContainText("Variantes de la captura");
  await expect(e.locator("dd").nth(1)).toHaveText("6");
  const ml = card(page, "Conexión Mercado Libre");
  await expect(ml).toContainText("SYNTHETIC-ML-ACCOUNT");
  await expect(ml).toContainText("Cuenta vinculada");
  await expect(
    ml.getByRole("button", { name: "Conectar Mercado Libre", exact: true }),
  ).toHaveCount(0);
  await expect(ml.locator("dd").nth(3)).toHaveText(
    data.ml.publication_count === null
      ? "—"
      : String(data.ml.publication_count),
  );
  await expect(card(page, "Importación Tiendanube")).toContainText(
    "No es una conexión API activa",
  );
  await e.getByText("Actualizaciones programadas", { exact: true }).click();
  await expect(e).toContainText("08:25 y 16:25, hora argentina");
  await expect(e.getByRole("list")).toContainText("16:25");
  await expect(e).toContainText("no garantizan ejecución puntual");
  await page.getByRole("dialog").evaluate((element) => {
    element.scrollTop = 0;
  });
  await page.getByRole("dialog").screenshot({
    path: `artifacts/conexiones-${info.project.name}.png`,
    scale: "css",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("actualización manual existente en segundo plano conserva edición, búsqueda y tabla hasta refrescar", async ({
  page,
}, info) => {
  const root = "/api/ecomm-app/workspace/900003";
  const before = await (await page.request.get(root)).json();
  const csrf = (await (await page.request.get("/api/auth/me")).json())
    .csrf_token;
  const fields = {
    ...before.fields,
    title: `Título interno sintético ${info.project.name} que la captura no reemplaza`,
  };
  expect(
    (
      await page.request.post(root, {
        headers: { "X-CSRF-Token": csrf },
        data: { fields, status: "DRAFT", expected_version: before.version },
      })
    ).status(),
  ).toBe(200);
  await open(page);
  page.once("dialog", (dialog) => dialog.accept());
  await center(page)
    .getByRole("button", { name: "Actualizar catálogo ahora", exact: true })
    .click();
  await expect(center(page)).toContainText(
    "Actualización iniciada en segundo plano",
  );
  await page
    .getByRole("button", { name: "Cerrar configuración", exact: true })
    .click();
  await page.getByLabel("Buscar productos", { exact: true }).fill("DEMO-CHIA");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(1);
  await expect(page.locator(".n-shortcut")).toContainText(
    "Nueva copia disponible",
    { timeout: 20000 },
  );
  await open(page);
  await expect(card(page, "Conexión Ecomm-App")).toContainText(
    "Última actualización exitosa",
  );
  const saved = await (await page.request.get(root)).json();
  expect(saved.fields.title).toBe(fields.title);
  expect(saved.version).toBe(before.version + 1);
  await center(page)
    .getByRole("button", { name: "Refrescar indicadores y tabla", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Cerrar configuración", exact: true })
    .click();
  await expect(page).toHaveURL(/q=DEMO-CHIA/);
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(1);
  await expect(page.locator('[data-ecomm-id="900003"]')).toContainText(
    fields.title,
  );
});

test("programación en curso bloquea otra captura y error conserva catálogo previo sin decir publicación fallida", async ({
  page,
}) => {
  const data = await original(page);
  data.ecomm.refresh_in_progress = true;
  data.ecomm.refresh_job = {
    status: "RUNNING",
    origin: "SCHEDULED",
    started_at: new Date().toISOString(),
    pages_saved: 1,
    expected_pages: 3,
    message: "Captura programada sintética en curso",
  };
  await page.route("**/api/connections/status", (route) =>
    route.fulfill({
      json: data,
      headers: { "X-Kiki-Environment": "local-synthetic" },
    }),
  );
  await open(page);
  const e = card(page, "Conexión Ecomm-App");
  await expect(
    e.getByRole("button", { name: "Actualizar catálogo ahora" }),
  ).toBeDisabled();
  await expect(e).toContainText("Proceso programado");
  data.ecomm.refresh_in_progress = false;
  data.ecomm.refresh_job.status = "FAILED";
  data.ecomm.refresh_job.message =
    "Fallo de lectura sintético; copia anterior conservada.";
  await center(page)
    .getByRole("button", { name: "Volver a consultar estados" })
    .click();
  await expect(e).toContainText("Error de captura");
  await expect(e.locator("dd").nth(1)).toHaveText("6");
  await expect(e).not.toContainText("falló la publicación");
});

test("desconectado y token vencido son explícitos; OAuth prepara el contrato sin abrir un proveedor", async ({
  page,
}, info) => {
  const data = await original(page);
  data.ml.connected = false;
  data.ml.user_id = null;
  data.ml.token_expired = false;
  await page.route("**/api/connections/status", (route) =>
    route.fulfill({
      json: data,
      headers: { "X-Kiki-Environment": "local-synthetic" },
    }),
  );
  await open(page);
  const ml = card(page, "Conexión Mercado Libre");
  await expect(ml).toContainText("Sin cuenta conectada");
  await expect(
    ml.getByRole("button", { name: "Actualizar publicaciones", exact: true }),
  ).toBeDisabled();
  page.once("dialog", (d) => d.accept());
  await ml
    .getByRole("button", { name: "Conectar Mercado Libre", exact: true })
    .click();
  await expect(center(page)).toContainText(
    "no se abrió Mercado Libre ni se vinculó una cuenta",
  );
  await expect(page).toHaveURL("https://127.0.0.1:8443/");
  data.ml.connected = true;
  data.ml.user_id = "SYNTHETIC-ML-ACCOUNT";
  data.ml.token_expired = true;
  data.ml.token_expiration = new Date(Date.now() - 60000).toISOString();
  await center(page)
    .getByRole("button", { name: "Volver a consultar estados" })
    .click();
  await expect(ml).toContainText("Token de acceso vencido");
  await expect(
    ml.getByRole("button", { name: "Actualizar publicaciones", exact: true }),
  ).toBeEnabled();
  await ml.scrollIntoViewIfNeeded();
  await page.getByRole("dialog").screenshot({
    path: `artifacts/conexiones-autorizacion-${info.project.name}.png`,
    scale: "css",
  });
});

test("lectura ML y CSV originales, sin publicaciones y con copia anterior conservada si CSV inválido", async ({
  page,
}, info) => {
  await open(page);
  page.once("dialog", (d) => d.accept());
  await card(page, "Conexión Mercado Libre")
    .getByRole("button", { name: "Actualizar publicaciones", exact: true })
    .click();
  await expect(center(page)).toContainText("Copia interna actualizada");
  expect((await original(page)).ml.publication_count).toBe(1);
  const csv =
    "Identificador de URL;Nombre;SKU;Precio;Stock\nchia-de-prueba;Chía sintética;DEMO-CHIA;1;2\nchia-de-prueba;Chía sintética pack x6;DEMO-CHIA-PACK;6;1\n";
  page.once("dialog", (d) => d.accept());
  await center(page)
    .getByLabel("Importar / Actualizar CSV de Tiendanube", { exact: true })
    .setInputFiles({
      name: "catalogo-sintetico.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
  await expect(card(page, "Importación Tiendanube")).toContainText(
    "CSV importado en KIKI",
  );
  const before = (await original(page)).tn;
  expect([before.products, before.records]).toEqual([1, 2]);
  expect(before.current_publication_verified).toBe(false);
  await expect(
    card(page, "Importación Tiendanube").locator("dd").nth(2),
  ).toHaveText("2");
  page.once("dialog", (d) => d.accept());
  await center(page)
    .getByLabel("Importar / Actualizar CSV de Tiendanube", { exact: true })
    .setInputFiles({
      name: "invalido.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("invalid"),
    });
  await expect(center(page).getByRole("alert")).toBeVisible();
  await expect(center(page).getByRole("alert")).toBeInViewport();
  expect((await original(page)).tn).toEqual(before);
  await card(page, "Importación Tiendanube").scrollIntoViewIfNeeded();
  await page.getByRole("dialog").screenshot({
    path: `artifacts/conexiones-csv-${info.project.name}.png`,
    scale: "css",
  });
});

test("configuración ausente o respuesta incompatible no habilita operaciones ni inventa conexión", async ({
  page,
}) => {
  const data = await original(page);
  data.actions_enabled = false;
  data.ecomm.api_configured = false;
  await page.route("**/api/connections/status", (route) =>
    route.fulfill({
      json: data,
      headers: { "X-Kiki-Environment": "local-synthetic" },
    }),
  );
  await page
    .getByRole("button", { name: "Centro de conexiones", exact: true })
    .click();
  await expect(center(page)).toContainText("Sin credencial configurada");
  await expect(
    center(page).getByRole("button", { name: "Actualizar catálogo ahora" }),
  ).toBeDisabled();
  data.external_oauth_allowed = true;
  await center(page)
    .getByRole("button", { name: "Volver a consultar estados" })
    .click();
  await expect(center(page).getByRole("alert")).toContainText("incompatible");
  await expect(
    center(page).getByRole("button", {
      name: "Actualizar publicaciones",
      exact: true,
    }),
  ).toBeDisabled();
});
