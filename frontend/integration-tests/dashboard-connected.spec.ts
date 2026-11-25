import { test, expect, type Page } from "@playwright/test";
import { queuePath, catalogPath } from "../src/integration/catalog-adapter";

const rows = (page: Page) => page.locator("tbody tr");
test.beforeEach(async ({ context }) => {
  await context.route("**/*", (route) =>
    new URL(route.request().url()).origin === "https://127.0.0.1:8443"
      ? route.continue()
      : route.abort(),
  );
});
async function login(page: Page, path = "/") {
  await page.goto(path);
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
}

test("indicadores globales del backend filtran sin sumar tareas superpuestas", async ({
  page,
}) => {
  await login(page);
  // Totals remain authoritative in the backend, while the main dashboard
  // presents only actionable channel differences. Filters remain available.
  const response = await page.request.get(`${queuePath}?sort=capture`);
  const body = await response.json();
  for (const key of [
    "identity",
    "untouched",
    "draft",
    "ready",
    "ready_for_channels",
    "pack",
  ]) {
    expect(Number.isSafeInteger(body.summary[key])).toBe(true);
  }
  await expect(page.locator(".k-business-gap-card")).toHaveCount(4);
  await page.getByLabel("Filtrar catálogo").selectOption("identity");
  await expect(page).toHaveURL(/filter=identity/);
  await expect(rows(page)).toHaveCount(2);
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
  await page.getByLabel("Buscar productos", { exact: true }).fill("1 kg");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toHaveAttribute("data-ecomm-id", "900002");
  await page.getByRole("button", { name: "Ver ficha", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("1 kg");
  await page.getByRole("button", { name: "Cerrar ficha", exact: true }).click();
  await page
    .getByRole("button", { name: "Limpiar filtro", exact: true })
    .click();
  await expect(rows(page)).toHaveCount(3);
  await page.goBack();
  await expect(page.getByLabel("Filtrar catálogo")).toHaveValue("identity");
  await expect(rows(page)).toHaveCount(1);
});

test("guardado persistente refresca cola, marca, título e historial y conserva contexto", async ({
  page,
}, info) => {
  await login(page);
  await page
    .locator('[data-ecomm-id="900003"]')
    .getByRole("button", { name: "Ver ficha" })
    .click();
  const title = `Chía sintética 2N ${info.project.name}`;
  await page.getByLabel("Título completo", { exact: true }).fill(title);
  await page
    .getByLabel("Marca comercial", { exact: true })
    .fill("Marca sintética Chía 2N");
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Guardado en PostgreSQL de pruebas" }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("tab", { name: "Historial", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(title);
  await page.getByRole("button", { name: "Cerrar ficha" }).click();
  await page.getByLabel("Filtrar catálogo").selectOption("draft");
  await page
    .getByLabel("Buscar productos", { exact: true })
    .fill("Marca sintética Chía 2N");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toContainText(title);
  await page.reload();
  await expect(rows(page)).toHaveCount(1);
  await page.getByRole("button", { name: "Ver ficha" }).click();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    title,
  );
  await page.getByRole("button", { name: "Cerrar ficha" }).click();
  expect(page.url()).toContain("filter=draft");
  await page.getByTestId("total").click();
  await expect(rows(page)).toHaveCount(6);
  await expect(
    rows(page)
      .first()
      .locator('td[data-label="Ficha y siguiente paso"] > small'),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `artifacts/dashboard-2n-${info.project.name}.png`,
    fullPage: true,
  });
  await page
    .locator('[data-ecomm-id="900003"]')
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Ficha 900003" }),
  ).toBeVisible();
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    title,
  );
  await page.getByRole("dialog").locator(".i-source > summary").click();
  await page.screenshot({
    path: `artifacts/editor-2n-${info.project.name}.png`,
  });
});

test("enlace profundo consulta un Ecomm ID fuera de la página sin perder filtros", async ({
  page,
}) => {
  await login(page, "/?q=Lentejas&limit=3&product=900002&tab=Ficha");
  await expect(
    page.getByRole("dialog", { name: "Ficha 900002" }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("1 kg");
  await page.reload();
  await expect(
    page.getByRole("dialog", { name: "Ficha 900002" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toHaveAttribute("data-ecomm-id", "900006");
  await expect(page).toHaveURL(/q=Lentejas/);
});

test("códigos opcionales vacíos no se inventan ni se confunden con cambio de identidad", async ({
  page,
}, info) => {
  await page.route("**/api/ecomm-app/workspace/900005", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch(),
      body = await response.json();
    Object.assign(body.source, { barcode: "", gtin_raw: "", gtin: "" });
    await route.fulfill({ response, json: body });
  });
  await login(page);
  const before = await (
    await page.request.get("/api/ecomm-app/workspace/900005")
  ).json();
  await page
    .locator('[data-ecomm-id="900005"]')
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await page
    .getByLabel("Título completo", { exact: true })
    .fill(`Avena sintética códigos ausentes ${info.project.name}`);
  await expect(
    page.getByRole("button", { name: "Guardar borrador", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Guardado en PostgreSQL de pruebas" }),
  ).toBeVisible();
  await page
    .getByLabel("Observaciones y pendientes", { exact: true })
    .fill(`Segundo guardado con códigos ausentes ${info.project.name}`);
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get("/api/ecomm-app/workspace/900005")
          ).json()
        ).version,
    )
    .toBe(before.version + 2);
});

test("reemplazar una ficha completa requiere confirmación y cancelar conserva PostgreSQL", async ({
  page,
}) => {
  await login(page);
  const path = "/api/ecomm-app/workspace/900004";
  const current = await (await page.request.get(path)).json();
  const auth = await (await page.request.get("/api/auth/me")).json();
  const fields = {
    ...current.fields,
    brand: "Marca sintética 2N",
    manufacturer: "Fabricante de prueba",
    title: "Ficha completa sintética 2N",
    short_title: "Ficha sintética",
    short_description: "Descripción de prueba",
    description: "Texto sintético completo",
    details: "Detalles sintéticos",
    presentation: "1 kg",
    category: "Dietética sintética",
    subcategory: "Harinas",
    seo_title: "Título de prueba",
    seo_description: "Descripción de buscador sintética",
    seo_keywords: "sintético, prueba",
    attributes: [{ name: "Presentación", value: "1 kg" }],
    media: [
      {
        kind: "IMAGE",
        url: "https://synthetic.invalid/2n.jpg",
        alt: "Imagen de prueba",
        source_url: "",
      },
    ],
    sources: [
      {
        kind: "ETIQUETA",
        name: "Control sintético",
        url: "",
        note: "Aprobación automatizada de prueba; no es evidencia auténtica.",
        verified: true,
      },
    ],
  };
  const approved = await page.request.post(path, {
    headers: { "X-CSRF-Token": auth.csrf_token },
    data: {
      fields,
      status: "READY_FOR_CHANNELS",
      expected_version: current.version,
    },
  });
  expect(approved.status()).toBe(200);
  await page.getByRole("button", { name: "Volver a consultar" }).click();
  await page
    .locator('[data-ecomm-id="900004"]')
    .getByRole("button", { name: "Ver ficha" })
    .click();
  await page
    .getByLabel("Título completo", { exact: true })
    .fill("Edición pendiente sin confirmar");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  const unchanged = await (await page.request.get(path)).json();
  expect(unchanged.status).toBe("READY_FOR_CHANNELS");
  expect(unchanged.fields.title).toBe(fields.title);
  await expect(page.getByLabel("Título completo", { exact: true })).toHaveValue(
    "Edición pendiente sin confirmar",
  );
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Guardado en PostgreSQL de pruebas" }),
  ).toBeVisible();
});

test("sin resultados de filtro no se confunde con catálogo vacío ni se inventa cobertura", async ({
  page,
}) => {
  await login(page);
  await page.getByLabel("Filtrar catálogo").selectOption("pack");
  await expect(rows(page)).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Sin resultados" }),
  ).toBeVisible();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
  await expect(
    page.getByLabel("Alcance de la evidencia de canales"),
  ).toContainText("Sin datos disponibles");
  await page
    .getByRole("button", { name: "Limpiar filtro", exact: true })
    .click();
  await expect(rows(page)).toHaveCount(6);
});

test("fallo de cola elimina filas e indicadores sin fallback al demo", async ({
  page,
}) => {
  await login(page);
  await page.route(`**${queuePath}?*`, (route) =>
    route.fulfill({
      status: 500,
      headers: { "X-Kiki-Environment": "local-synthetic" },
      body: "{}",
    }),
  );
  await page.getByRole("button", { name: "Volver a consultar" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "No se utilizan cifras ni productos de demostración",
  );
  await expect(rows(page)).toHaveCount(0);
  await expect(page.getByTestId("total").locator("strong")).toHaveText("—");
});

test("barcode y gtin contradictorios se conservan y bloquean el editor", async ({
  page,
}) => {
  const barcode = "0000000000000",
    gtin = "1111111111111"; // Explicitly invalid, synthetic controls.
  const amend = (source: Record<string, unknown>) =>
    Object.assign(source, {
      barcode,
      gtin,
      gtin_raw: gtin,
      identity_blockers: ["BARCODE_GTIN_CONFLICT"],
    });
  await page.route(`**${catalogPath}?*`, async (route) => {
    const response = await route.fetch(),
      body = await response.json();
    for (const row of body.items) if (row.ecomm_id === "900003") amend(row);
    await route.fulfill({ response, json: body });
  });
  await page.route(`**${queuePath}?*`, async (route) => {
    const response = await route.fetch(),
      body = await response.json();
    for (const row of body.items)
      if (row.ecomm_id === "900003") amend(row.source);
    await route.fulfill({ response, json: body });
  });
  await page.route("**/api/ecomm-app/workspace/900003", async (route) => {
    const response = await route.fetch(),
      body = await response.json();
    amend(body.source);
    await route.fulfill({ response, json: body });
  });
  await login(page);
  const row = page.locator('[data-ecomm-id="900003"]');
  await expect(row).toContainText(`Barcode: ${barcode}`);
  await expect(row).toContainText(`GTIN: ${gtin}`);
  await expect(row).toContainText("Guardado bloqueado");
  await row.getByRole("button", { name: "Ver ficha" }).click();
  await expect(
    page.getByRole("button", { name: "Guardar borrador", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Título completo", { exact: true }),
  ).toBeDisabled();
});

for (const suffix of [
  "filter=unknown",
  "product=None",
  "product=null",
  "filter=all&filter=draft",
]) {
  test(`URL inválida bloquea consultas de negocio: ${suffix}`, async ({
    page,
  }) => {
    let queries = 0;
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      // The independent, read-only connection-status header is allowed;
      // invalid filters must not load catalogue/product/business data.
      if (
        path.startsWith("/api/ecomm-app/") &&
        path !== "/api/ecomm-app/stage/auto/status"
      )
        queries++;
    });
    await page.goto(`/?${suffix}`);
    await page.getByLabel("Usuario de prueba").fill("operador-prueba");
    await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
    await page.getByRole("button", { name: "Ingresar", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Filtros de URL inválidos" }),
    ).toBeVisible();
    expect(queries).toBe(0);
    await expect(rows(page)).toHaveCount(0);
  });
}

test("cuatro atajos Ver lista llevan a la lista exacta, limpian búsqueda y permiten volver", async ({
  page,
}) => {
  await login(page);
  const overview = page.getByLabel("Diferencias principales entre catálogos");
  const cards = overview.locator(".k-business-gap-card");
  await expect(cards).toHaveCount(4);
  const cases = [
    {
      idx: 0,
      path: /filter=ml_comparison_no_match/,
      selector: "#kiki-catalog-results",
      label: /Lista: Ecomm-App sin coincidencia en Mercado Libre/,
    },
    {
      idx: 1,
      path: /filter=tn_comparison_no_match/,
      selector: "#kiki-catalog-results",
      label: /Lista: Ecomm-App sin coincidencia en Tiendanube/,
    },
    {
      idx: 2,
      path: /view=ml.*linkage=no_match/,
      selector: "#kiki-channel-results",
      label: /Lista: Mercado Libre sin candidato en Ecomm-App/,
    },
    {
      idx: 3,
      path: /view=tn.*linkage=no_match/,
      selector: "#kiki-channel-results",
      label: /Lista: Tiendanube sin candidato en Ecomm-App/,
    },
  ];
  for (const current of cases) {
    // Existing search cannot silently narrow a global indicator.
    await page.getByLabel("Buscar productos", { exact: true }).fill("Lentejas");
    await page.getByRole("button", { name: "Buscar", exact: true }).click();
    await cards.nth(current.idx).click();
    await expect(page).toHaveURL(current.path);
    await expect(page).not.toHaveURL(/[?&]q=/);
    const list = page.locator(current.selector);
    await expect(list).toBeFocused();
    await expect(list).toContainText(current.label);
    await expect(cards.nth(current.idx).locator("strong")).toHaveText(
      /^[\d.]+$/,
    );
    const visibleCount = Number(
      (await cards.nth(current.idx).locator("strong").innerText()).replace(
        /\./g,
        "",
      ),
    );
    const shownCount = list.locator(".k-gap-list-banner");
    await expect(shownCount).toContainText(
      new Intl.NumberFormat("es-AR").format(visibleCount),
    );
    await list.getByRole("button", { name: "Volver a indicadores" }).click();
    await expect(overview).toBeInViewport();
  }
});


test("guía de uso accesible, plegable y buscable sin modificar el catálogo", async ({ page }) => {
  await login(page);
  const guide = page.locator("#guia-de-uso");
  const heading = guide.locator(":scope > summary");
  await expect(heading).toBeVisible();
  await expect(guide).not.toHaveAttribute("open", "");
  await heading.click();
  const search = guide.getByRole("searchbox");
  await expect(search).toBeVisible();
  await expect(guide.locator(".k-user-guide-chapter")).toHaveCount(8);
  await search.fill("taxonomia-inexistente");
  await expect(guide.getByRole("status")).toContainText("No encontramos");
  await search.fill("procesar lotes");
  await expect(guide.locator(".k-user-guide-chapter")).toHaveCount(1);
  await guide.locator(".k-user-guide-chapter > summary").click();
  await expect(guide.getByText("Pulsá Guardar manifiesto de investigación.", { exact: false })).toBeVisible();
  await heading.click();
  await expect(search).not.toBeVisible();
  await expect(page.getByLabel("Buscar productos", { exact: true })).toBeVisible();
});
