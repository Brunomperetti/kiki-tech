import { test, expect, type Page } from "@playwright/test";
test.skip(
  process.env.KIKI_PRESENTATION_SCENARIO !== "local-synthetic",
  "Escenario aislado de presentación",
);
const nav = (page: Page) =>
  page.getByRole("navigation", { name: "Vistas comerciales" });
test.beforeEach(async ({ page, context }) => {
  await context.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== "https://127.0.0.1:8443")
      throw new Error("Destino externo prohibido");
    if (
      /\/suggest$|oauth|sync|refresh|publish|openai/.test(
        new URL(route.request().url()).pathname,
      )
    )
      throw new Error("Proveedor prohibido");
    return route.continue();
  });
  await page.goto("/");
  await page.getByLabel("Usuario de prueba").fill("operador-prueba");
  await page.getByLabel("Contraseña de prueba").fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
});
test("cinco vistas: registros huérfanos, CSV sin vigencia y maestro sin identidades inventadas", async ({
  page,
}, info) => {
  await expect(nav(page).getByRole("button")).toHaveCount(5);
  await page.screenshot({
    path: `artifacts/functional-catalog-dashboard-${info.project.name}.png`,
    fullPage: false,
  });
  await page.getByLabel("Variantes por página").selectOption("6");
  await nav(page)
    .getByRole("button", { name: /^Publicaciones Mercado Libre/ })
    .click();
  const records = page.getByRole("region", { name: "Registros Mercado Libre" });
  await expect(records.locator("[data-channel-record]")).toHaveCount(6);
  const orphan = records.locator("tr").filter({ hasText: "MLA999000001" });
  await expect(orphan).toContainText("Sin Ecomm ID validado");
  await expect(orphan.getByRole("button")).toHaveCount(0);
  await records.getByLabel("Vinculación del canal").selectOption("unlinked");
  await expect(page).toHaveURL(/linkage=unlinked/);
  await page.screenshot({
    path: `artifacts/functional-catalog-ml-${info.project.name}.png`,
    fullPage: false,
  });
  await nav(page)
    .getByRole("button", { name: /^Registros Tiendanube/ })
    .click();
  const tn = page.getByRole("region", { name: "Registros Tiendanube" });
  await expect(tn.locator("[data-channel-record]")).toHaveCount(5);
  await expect(tn).toContainText("registro-tn-sin-vinculo");
  await expect(tn).toContainText("Información desactualizada");
  await expect(tn).not.toContainText("Publicación confirmada en captura");
  for (const label of [
    /^Variantes sin publicación confirmada · ML/,
    /^Variantes sin publicación confirmada · TN/,
  ]) {
    await nav(page).getByRole("button", { name: label }).click();
    await expect(page.locator("[data-ecomm-id]")).toHaveCount(6);
    await expect(page.locator(".i-pagination")).toContainText(
      "6 variantes en la captura",
    );
  }
});
test("calidad calculada, intersección, búsqueda y URL recuperable sin mezclar variantes", async ({
  page,
}, info) => {
  await page.getByText("Calidad del catálogo", { exact: true }).click();
  const quality = page.getByRole("group", { name: "Indicadores de calidad" });
  const metric = quality.getByRole("button", { name: /^EAN repetido/ });
  await expect(metric.locator("strong")).toHaveText("2");
  await metric.click();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(2);
  await expect(page.locator('[data-ecomm-id="900003"]')).toContainText("250 g");
  await expect(page.locator('[data-ecomm-id="900004"]')).toBeVisible();
  await page
    .getByLabel("Combinar filtro de catálogo")
    .selectOption("images_missing");
  await expect(page).toHaveURL(/ean_repeated%2Bimages_missing/);
  await page.reload();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(2);
  await page.getByLabel("Buscar productos", { exact: true }).fill("900004");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(1);
  await expect(page.locator('[data-ecomm-id="900004"]')).toContainText("1 kg");
  await page.screenshot({
    path: `artifacts/functional-catalog-quality-${info.project.name}.png`,
    fullPage: false,
  });
  await page.goBack();
  await expect(page.locator("[data-ecomm-id]")).toHaveCount(2);
});
test("configuración, exportación e historial reutilizan contratos existentes", async ({
  page,
}, info) => {
  await page
    .getByRole("button", { name: "Configuración", exact: true })
    .click();
  const settings = page.getByRole("dialog", {
    name: "Configuración del catálogo",
  });
  await expect(settings).toContainText(
    "OpenAI real e investigación externa desactivados",
  );
  await settings.getByLabel("Mostrar filtros y detalles avanzados").check();
  const download = page.waitForEvent("download");
  await settings
    .getByRole("link", { name: "Descargar fichas guardadas · JSON" })
    .click();
  expect((await download).suggestedFilename()).toMatch(/\.json$/);
  await settings.getByRole("button", { name: "Volver a Mi catálogo" }).click();
  await expect(
    page.getByRole("group", { name: "Indicadores de calidad" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Historial", exact: true }).click();
  const history = page.getByRole("dialog", {
    name: "Historial de fichas guardadas",
  });
  await expect(history).toBeVisible();
  await expect(history).toContainText("El mismo editor y sus versiones");
  await history.getByRole("button", { name: "Volver a Mi catálogo" }).click();
  await page
    .locator('[data-ecomm-id="900003"]')
    .getByRole("button", { name: "Ver ficha", exact: true })
    .click();
  await page.getByRole("tab", { name: "IA", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Investigar y completar ficha con IA",
      exact: true,
    }),
  ).toHaveText("Investigar y completar ficha con IA");
  await expect(page.getByRole("tab")).toHaveCount(5);
  await page.getByRole("dialog").screenshot({
    path: `artifacts/functional-catalog-editor-${info.project.name}.png`,
  });
});
test("rechaza una respuesta de canal que pretende confirmar un CSV", async ({
  page,
}) => {
  await page.route("**/workspace/channels/listings?*", async (route) => {
    const u = new URL(route.request().url());
    const original = await route.fetch();
    const data = await original.json();
    if (u.searchParams.get("channel") === "tn" && data.items.length) {
      data.items[0].confirmed_listing = true;
      data.items[0].evidence_state = "CONFIRMED_CAPTURE";
    }
    await route.fulfill({ response: original, json: data });
  });
  await nav(page)
    .getByRole("button", { name: /^Registros Tiendanube/ })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Registros de canal incompatibles",
  );
  await expect(page.locator("[data-channel-record]")).toHaveCount(0);
});

test("preparación calculada por canal, CTA IA y publicación confirmada se mantienen separados", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  const root = "/api/ecomm-app/workspace/900003";
  const csrf = (await (await page.request.get("/api/auth/me")).json())
    .csrf_token;
  const headers = { "X-CSRF-Token": csrf };
  const before = await (await page.request.get(root)).json();
  let linked = false;
  try {
    const fields = {
      ...before.fields,
      brand: "Marca sintética KIKI",
      title: "Semillas de chía sintéticas 250 g",
      short_title: "Chía sintética",
      short_description: "Ficha de prueba, no comercial.",
      description:
        "Semillas de chía sintéticas 250 g. Información exclusivamente de prueba.",
      presentation: "250 g",
      category: "Dietética",
      subcategory: "Semillas",
      seo_title: "Chía de prueba 250 g",
      seo_description: "Texto sintético de presentación.",
      seo_keywords: "demostración, chía",
      attributes: [{ name: "Presentación de prueba", value: "250 g" }],
      media: [
        {
          kind: "IMAGE",
          url: "https://synthetic.invalid/imagen.jpg",
          alt: "No se descarga",
          source_url: "",
        },
      ],
      sources: [
        {
          kind: "ETIQUETA",
          name: "Fuente sintética",
          url: "",
          note: "Verificación automatizada del fixture, no aprobación del cliente.",
          verified: true,
        },
      ],
    };
    const saved = await page.request.post(root, {
      headers,
      data: {
        expected_version: before.version,
        status: "READY_FOR_CHANNELS",
        fields,
      },
    });
    expect(saved.status()).toBe(200);
    await page.reload();
    for (const channel of ["ml", "tn"])
      await expect(
        page.locator(`[data-metric="${channel}-ready"] strong`),
      ).toHaveText("1");
    const r = await (await page.request.get(root + "/channels")).json();
    const c = r.ml.candidates.find(
      (c: { id: string }) => c.id === "MLA900000003",
    );
    expect(c.can_review).toBe(true);
    const result = await page.request.post(root + "/channels/review", {
      headers,
      data: {
        channel: "ml",
        listing_id: c.id,
        expected_fingerprint: c.token,
        expected_revision: c.revision,
        decision: "APPROVED",
        checks: [
          "name",
          "brand",
          "presentation",
          "quantity",
          "sale_type",
          "codes",
        ],
        quantity_commercial: 1,
        reason:
          "Validación automatizada de identidad y cantidad sintéticas para comprobar sólo la interfaz.",
      },
    });
    expect(result.status()).toBe(200);
    linked = true;
    await page.reload();
    await expect(page.locator('[data-metric="ml-ready"] strong')).toHaveText(
      "0",
    );
    await expect(page.locator('[data-metric="tn-ready"] strong')).toHaveText(
      "1",
    );
    await page.locator('[data-metric="tn-ready"]').click();
    await expect(page).toHaveURL(/filter=ready_for_channels%2Btn_unconfirmed/);
    await expect(page.locator("[data-ecomm-id]")).toHaveCount(1);
    await expect(page.locator('[data-ecomm-id="900003"]')).toBeVisible();
    await expect(page.locator('[data-metric="tn-ready"]')).toContainText(
      "no publica",
    );
    await page.getByTestId("total").click();
    await expect(page.getByTestId("total").locator("strong")).toHaveText("6");
    await expect(page.locator("[data-ecomm-id]")).toHaveCount(6);
    await expect(page.locator('[data-metric="tn-ready"] strong')).toHaveText(
      "1",
    );
    const coverage = await page
      .getByRole("region", { name: "Preparación por canal" })
      .evaluate((element) => {
        const cards = Array.from(element.querySelectorAll("button"));
        return (
          cards.reduce(
            (sum, card) => sum + card.getBoundingClientRect().width,
            0,
          ) / element.getBoundingClientRect().width
        );
      });
    expect(coverage).toBeGreaterThan(0.9);
    await page.screenshot({
      path: `artifacts/ux-final-connected-dashboard-${info.project.name}.png`,
      fullPage: info.project.name === "mobile",
      scale: "css",
    });
    await page
      .locator('[data-ecomm-id="900001"]')
      .getByRole("button", { name: "Revisar identidad", exact: true })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Ficha 900001" }),
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Evidencias", exact: true }),
    ).toHaveAttribute("aria-selected", "true");
    await page
      .getByRole("button", { name: "Cerrar ficha", exact: true })
      .click();
    await page
      .locator('[data-ecomm-id="900003"]')
      .getByRole("button", { name: "Ver ficha", exact: true })
      .click();
    await page.getByRole("tab", { name: "IA", exact: true }).click();
    await expect(
      page.getByRole("region", {
        name: "Disponibilidad de investigación e IA",
      }),
    ).toContainText("bloqueados");
    await expect(
      page.getByRole("button", {
        name: "Investigar y completar ficha con IA",
        exact: true,
      }),
    ).toBeVisible();
    await page.getByRole("dialog").screenshot({
      path: `artifacts/ux-final-connected-ai-${info.project.name}.png`,
      scale: "css",
    });
  } finally {
    if (linked) {
      const r = await (await page.request.get(root + "/channels")).json();
      const c = r.ml.candidates.find(
        (c: { id: string }) => c.id === "MLA900000003",
      );
      const revoked = await page.request.post(root + "/channels/review", {
        headers,
        data: {
          channel: "ml",
          listing_id: c.id,
          expected_fingerprint: c.token,
          expected_revision: c.revision,
          decision: "REVOKED",
          checks: [
            "name",
            "brand",
            "presentation",
            "quantity",
            "sale_type",
            "codes",
          ],
          quantity_commercial: 1,
          reason:
            "Fin del recorrido automatizado: retiro explícitamente la vinculación sintética de prueba.",
        },
      });
      expect(revoked.status()).toBe(200);
    }
    const current = await (await page.request.get(root)).json();
    const restored = await page.request.post(root, {
      headers,
      data: {
        expected_version: current.version,
        status: before.status === "NOT_STARTED" ? "DRAFT" : before.status,
        fields: before.fields,
      },
    });
    expect(restored.status()).toBe(200);
  }
});
