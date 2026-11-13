import { test, expect, type Page } from "@playwright/test";
import { products, type Channel } from "../src/prototype/data";
const outbound = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const external: string[] = [];
  outbound.set(page, external);
  await page.route("**/*", (r) => {
    if (new URL(r.request().url()).origin !== "http://127.0.0.1:4173") {
      external.push(r.request().url());
      return r.abort();
    }
    return r.continue();
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tu catálogo, en un solo lugar." }),
  ).toBeVisible();
  // Legacy secondary indicators remain available inside their collapsed group.
  await page.getByText("Más indicadores comerciales", { exact: true }).click();
});
test.afterEach(async ({ page }) => expect(outbound.get(page)).toEqual([]));
const record = (page: Page, id: string) =>
  page.locator(".d-table tbody tr").filter({ hasText: id });
const fixtureConfirmed = (c: Channel) =>
  products.filter(
    (p) =>
      p.evidence[c].freshness === "current" &&
      p.evidence[c].publications.some((v) => v.id && v.proof && v.capturedAt),
  );
const fixturePubs = (c: Channel) =>
  new Set(
    fixtureConfirmed(c).flatMap((p) =>
      p.evidence[c].publications.map((v) => v.id),
    ),
  ).size;
test("totales calculados separan publicaciones únicas, variantes y registros repetidos", async ({
  page,
}, info) => {
  const metrics = page.getByRole("region", {
    name: "Cobertura comercial por canal",
  });
  await expect(metrics.getByRole("button")).toHaveCount(3);
  await expect(page.locator('[data-metric="all"] strong')).toHaveText(
    String(new Set(products.map((p) => p.id)).size),
  );
  for (const c of ["ml", "tn"] as const) {
    const confirmed = fixtureConfirmed(c);
    await expect(
      metrics.locator(`[data-metric="${c}-confirmed"] strong`),
    ).toHaveText(String(fixturePubs(c)));
    await expect(
      metrics.locator(`[data-metric="${c}-confirmed"] small`),
    ).toContainText(`${confirmed.length} variantes`);
    await expect(
      page
        .getByRole("navigation", { name: "Vistas comerciales" })
        .getByRole("button", {
          name:
            c === "ml"
              ? /^Variantes sin publicación confirmada · ML/
              : /^Variantes sin publicación confirmada · TN/,
        })
        .locator("strong"),
    ).toHaveText(
      String(c === "ml" ? products.length - confirmed.length : products.length),
    );
    await metrics.locator(`[data-metric="${c}-confirmed"]`).click();
    await expect(page.locator(".d-table tbody tr")).toHaveCount(
      confirmed.length,
    );
    for (const p of confirmed) await expect(record(page, p.id)).toBeVisible();
    await page.locator('[data-metric="all"]').click();
    await page
      .getByLabel(c === "ml" ? "Estado Mercado Libre" : "Estado Tiendanube", {
        exact: true,
      })
      .selectOption("unconfirmed");
    await expect(page.locator(".d-table tbody tr")).toHaveCount(
      products.length - confirmed.length,
    );
    await page.locator('[data-metric="all"]').click();
  }
  expect(fixturePubs("ml")).toBeGreaterThan(fixtureConfirmed("ml").length);
  await page.screenshot({
    path: `artifacts/cobertura-${info.project.name}.png`,
    fullPage: true,
    scale: "css",
  });
});
test("estados distinguen evidencia, candidatos, ausencia de confirmación y vigencia", async ({
  page,
}) => {
  await expect(record(page, "DEMO-1003")).toContainText(
    "Publicado con evidencia",
  );
  await expect(record(page, "DEMO-1002")).toContainText(
    "Vinculación por revisar",
  );
  await expect(record(page, "DEMO-1002")).toContainText(
    "Sin publicación confirmada",
  );
  await expect(record(page, "DEMO-1008")).toContainText("Listo para publicar");
  await expect(record(page, "DEMO-1007")).toContainText(
    "Información desactualizada",
  );
  await expect(record(page, "DEMO-1006")).toContainText(
    "Información desconocida",
  );
  await expect(record(page, "DEMO-1007")).not.toContainText(
    "Publicado con evidencia",
  );
  await page.getByRole("button", { name: "Abrir DEMO-1007" }).click();
  const panel = page.getByRole("dialog");
  await panel.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await expect(panel).toContainText("Información desactualizada");
  await expect(panel).toContainText("01/10/2026");
  await expect(panel).toContainText("no permite concluir si está publicado");
  await page.keyboard.press("Escape");
  await page
    .getByText("Cómo interpretar los estados de canal", { exact: true })
    .click();
  await expect(page.locator(".c-legend")).toContainText(
    "No demuestra que no esté publicado",
  );
});
test("filtros combinados de ambos canales restauran URL y preservan Ecomm ID", async ({
  page,
}) => {
  await page
    .getByLabel("Estado Mercado Libre", { exact: true })
    .selectOption("unconfirmed");
  await page
    .getByLabel("Estado Tiendanube", { exact: true })
    .selectOption("confirmed");
  await expect(page.locator(".d-table tbody tr")).toHaveCount(1);
  await expect(record(page, "DEMO-1001")).toBeVisible();
  await page.getByLabel("Marca", { exact: true }).selectOption("Monte");
  await page.reload();
  await expect(
    page.getByLabel("Estado Mercado Libre", { exact: true }),
  ).toHaveValue("unconfirmed");
  await expect(
    page.getByLabel("Estado Tiendanube", { exact: true }),
  ).toHaveValue("confirmed");
  await expect(page).toHaveURL(/mlState=unconfirmed/);
  await expect(page).toHaveURL(/tnState=confirmed/);
  await page.getByRole("button", { name: "Abrir DEMO-1001" }).click();
  await page
    .getByRole("dialog")
    .getByRole("tab", { name: "Canales", exact: true })
    .click();
  await page.keyboard.press("Escape");
  await expect(record(page, "DEMO-1001")).toBeVisible();
  await page.getByText("Más indicadores comerciales", { exact: true }).click();
  await page.locator('[data-metric="all"]').click();
  await page.getByRole("textbox", { name: "Buscar productos" }).fill("ALM-NAT");
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
  await expect(record(page, "DEMO-1006")).toContainText("1 kg");
  await expect(record(page, "DEMO-1001")).toContainText("250 g");
  await page
    .getByLabel("Estado Tiendanube", { exact: true })
    .selectOption("unknown");
  await expect(page.locator(".d-table tbody tr")).toHaveCount(1);
  await expect(record(page, "DEMO-1006")).toBeVisible();
  await page.locator('[data-metric="all"]').click();
  await page
    .getByLabel("Estado Tiendanube", { exact: true })
    .selectOption("stale");
  await expect(record(page, "DEMO-1007")).toBeVisible();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(1);
  await page.goBack();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(products.length);
});
test("preparar un canal modifica listas internas y confirma cero publicaciones nuevas", async ({
  page,
}) => {
  const metrics = page.getByRole("region", {
    name: "Cobertura comercial por canal",
  });
  for (const [key, n] of [
    ["ml-ready", 1],
    ["tn-ready", 1],
    ["attention", 3],
  ] as const) {
    await expect(page.locator(`[data-metric="${key}"] strong`)).toHaveText(
      String(n),
    );
    await page.locator(`[data-metric="${key}"]`).click();
    await expect(page.locator(".d-table tbody tr")).toHaveCount(n);
    await page.locator('[data-metric="all"]').click();
  }
  const before = { ml: fixturePubs("ml"), tn: fixturePubs("tn") };
  await page.getByRole("button", { name: "Abrir DEMO-1005" }).click();
  const panel = page.getByRole("dialog");
  await panel.getByRole("tab", { name: "Canales", exact: true }).click();
  await panel.getByRole("button", { name: "Preparar para TN" }).click();
  await panel.getByRole("button", { name: "Confirmar decisión" }).click();
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-metric="tn-ready"] strong')).toHaveText("2");
  for (const c of ["ml", "tn"] as const)
    await expect(
      metrics.locator(`[data-metric="${c}-confirmed"] strong`),
    ).toHaveText(String(before[c]));
  await expect(record(page, "DEMO-1005")).toContainText(
    "Publicado con evidencia",
  );
  await expect(record(page, "DEMO-1005")).toContainText("Listo para publicar");
  await page.getByRole("button", { name: "Abrir DEMO-1002" }).click();
  await panel.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await panel
    .getByLabel("Fundamento de la decisión")
    .fill(
      "Comparé presentación de 500 g y la identidad DEMO-1002 en la muestra.",
    );
  await panel.getByRole("checkbox").check();
  await panel.getByRole("button", { name: "Aceptar candidato" }).click();
  await panel.getByRole("button", { name: "Confirmar decisión" }).click();
  await page.keyboard.press("Escape");
  await expect(record(page, "DEMO-1002")).not.toContainText(
    "Publicado con evidencia",
  );
  for (const c of ["ml", "tn"] as const)
    await expect(
      metrics.locator(`[data-metric="${c}-confirmed"] strong`),
    ).toHaveText(String(before[c]));
});
