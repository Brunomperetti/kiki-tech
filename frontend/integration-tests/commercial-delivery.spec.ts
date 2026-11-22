import { test, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";

test.skip(
  process.env.KIKI_PRODUCTION_COMPAT !== "isolated-only",
  "Sólo PostgreSQL y catálogo sintéticos aislados",
);
test.setTimeout(120000);

test.beforeEach(async ({ page }) => {
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "https://127.0.0.1:8443")
      throw new Error("Proveedor externo prohibido");
    if (
      /\/sync$|\/manual\/start$|\/suggest$|\/auth-url$|\/fetch$/.test(
        url.pathname,
      )
    )
      throw new Error("Operación externa prohibida");
    return route.continue();
  });
  await page.goto("/v2/");
  await page.getByLabel("Usuario", { exact: true }).fill("operador-prueba");
  await page
    .getByLabel("Contraseña", { exact: true })
    .fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator('[data-ecomm-id="900006"]')).toBeVisible();
  await page
    .locator("summary")
    .filter({ hasText: /^Planificar lotes de investigación verificable$/ })
    .click();
});

async function openCommercial(page: Page) {
  await page.locator('[data-ecomm-id="900006"]').getByRole("checkbox").check();
  await page
    .locator("summary")
    .filter({ hasText: /^Preparar salida comercial por canal$/ })
    .click();
  return page.getByLabel("Exportación comercial por canal", { exact: true });
}

test("informe mensual se previsualiza, guarda, confirma y recupera sin aprobar fichas", async ({
  page,
}, info) => {
  const audit = page.getByLabel("Auditoría comercial integral", {
    exact: true,
  });
  await expect(
    audit.getByRole("button", {
      name: "Confirmar y exportar pendientes (CSV)",
      exact: true,
    }),
  ).toBeDisabled();
  await audit
    .getByRole("button", { name: "Auditar catálogo completo", exact: true })
    .click();
  await expect(
    audit.getByRole("region", { name: "Cobertura y excepciones" }),
  ).toBeVisible();
  await audit
    .locator("summary")
    .filter({
      hasText: /^Guardar informe y registrar revisión general mensual$/,
    })
    .click();
  const reports = audit.getByLabel("Registro de revisión general mensual", {
    exact: true,
  });
  await reports
    .getByLabel("Responsable de seguimiento")
    .fill("Operador sintético de aceptación");
  await reports
    .getByRole("button", {
      name: "Guardar informe general con pendientes",
      exact: true,
    })
    .click();
  const receipt = reports.getByRole("region", {
    name: "Constancia del informe general",
  });
  await expect(receipt).toBeVisible();
  await expect(receipt).toContainText(
    "no acredita que la captura o las fuentes sigan sin cambios",
  );
  const reason = receipt.getByLabel(
    "Resultado y excepciones de la revisión general",
  );
  if (await reason.count()) {
    await reason.fill(
      "Revisé el informe sintético completo y asigné los faltantes de fuentes sin aprobar productos individuales.",
    );
    await receipt
      .getByRole("button", {
        name: "Confirmar revisión general del informe",
        exact: true,
      })
      .click();
  }
  await expect(receipt).toContainText("Revisión general confirmada");
  await expect(reports).toContainText(
    "no cambia las fechas de revisión de cada producto",
  );
  const downloadEvent = page.waitForEvent("download");
  await receipt
    .getByRole("button", {
      name: "Descargar CSV del informe archivado",
      exact: true,
    })
    .click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe(
    "kiki-auditoria-comercial-mensual.csv",
  );
  expect((await readFile((await download.path())!)).toString("utf8")).toContain(
    "estado_revision",
  );
  await reports.screenshot({
    path: `artifacts/entrega-informe-mensual-${info.project.name}.png`,
  });
  await page.reload();
  await page
    .locator("summary")
    .filter({ hasText: /^Planificar lotes de investigación verificable$/ })
    .click();
  await page
    .getByRole("button", { name: "Auditar catálogo completo", exact: true })
    .click();
  await page
    .locator("summary")
    .filter({
      hasText: /^Guardar informe y registrar revisión general mensual$/,
    })
    .click();
  await page
    .getByRole("button", { name: "Recuperar informes anteriores", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /^Abrir informe / }).first(),
  ).toBeVisible();
});

test("paquete por canal conserva identidad y bloqueos; CSV sólo tras previsualización", async ({
  page,
}, info) => {
  const panel = await openCommercial(page);
  await expect(
    panel.getByRole("button", {
      name: "Confirmar y descargar paquete de revisión",
      exact: true,
    }),
  ).toHaveCount(0);
  await panel.getByLabel("Canal de revisión").selectOption("tn");
  await panel
    .getByRole("button", {
      name: "Previsualizar exportación comercial",
      exact: true,
    })
    .click();
  const preview = panel.getByRole("region", {
    name: "Previsualización comercial",
  });
  await expect(preview).toContainText("Ecomm ID 900006");
  await expect(preview).toContainText("no se publica nada");
  await expect(preview).toContainText("Clasificación del canal");
  await panel.screenshot({
    path: `artifacts/entrega-exportacion-canal-${info.project.name}.png`,
  });
  const downloadEvent = page.waitForEvent("download");
  await panel
    .getByRole("button", {
      name: "Confirmar y descargar paquete de revisión",
      exact: true,
    })
    .click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("kiki-comercial-tn-revision.csv");
  const body = (await readFile((await download.path())!)).toString("utf8");
  expect(body).toContain("900006");
  expect(body).toContain("formato_nativo_proveedor");
  await panel.getByLabel("Canal de revisión").selectOption("ml");
  await expect(
    panel.getByRole("button", {
      name: "Confirmar y descargar paquete de revisión",
      exact: true,
    }),
  ).toHaveCount(0);
});

test("conflicto 409 invalida previsualización y conserva selección y catálogo", async ({
  page,
}) => {
  const panel = await openCommercial(page);
  await panel
    .getByRole("button", {
      name: "Previsualizar exportación comercial",
      exact: true,
    })
    .click();
  await expect(
    panel.getByRole("region", { name: "Previsualización comercial" }),
  ).toBeVisible();
  await page.route(
    "**/api/ecomm-app/workspace/exports/commercial/download",
    (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        headers: { "X-Kiki-UI-Contract": "kiki-same-origin-v2-1" },
        body: JSON.stringify({
          detail:
            "La previsualización cambió; revisá la fuente y sus versiones.",
        }),
      }),
  );
  await panel
    .getByRole("button", {
      name: "Confirmar y descargar paquete de revisión",
      exact: true,
    })
    .click();
  await expect(panel.getByRole("alert")).toContainText(
    "previsualización cambió",
  );
  await expect(
    panel.getByRole("button", {
      name: "Confirmar y descargar paquete de revisión",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.locator('[data-ecomm-id="900006"]').getByRole("checkbox"),
  ).toBeChecked();
});
