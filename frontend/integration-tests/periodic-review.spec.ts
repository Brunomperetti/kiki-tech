import { test, expect, type Page } from "@playwright/test";

const production = process.env.KIKI_PRODUCTION_COMPAT === "isolated-only";
const stage4 = process.env.KIKI_STAGE4_SCENARIO === "synthetic-commercial";
test.skip(
  !production && !stage4,
  "Sólo PostgreSQL descartable y usuarios sintéticos explícitos",
);
test.setTimeout(120000);
const base = "/api/ecomm-app/workspace/reports/periodic";
const calls = new WeakMap<Page, string[]>();
type Policy = {
  version: number;
  settings: {
    enabled: boolean;
    interval_days: number;
    evidence_max_age_days: number;
    soon_days: number;
  };
  background_worker_enabled: false;
};

test.beforeEach(async ({ page, context }) => {
  const paths: string[] = [];
  calls.set(page, paths);
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "https://127.0.0.1:8443")
      throw new Error("Conexión fuera del entorno aislado prohibida");
    paths.push(route.request().method() + " " + url.pathname);
    return route.continue();
  });
  await page.goto(production ? "/v2/" : "/");
  await page
    .getByLabel(production ? "Usuario" : "Usuario de prueba", { exact: true })
    .fill("operador-prueba");
  await page
    .getByLabel(production ? "Contraseña" : "Contraseña de prueba", {
      exact: true,
    })
    .fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator("[data-ecomm-id]").first()).toBeVisible();
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  await page
    .getByText("Revisión periódica y pendientes", { exact: true })
    .click();
});
test.afterEach(async ({ page }) => {
  expect(
    calls
      .get(page)!
      .filter((path) =>
        /oauth|\/sync$|\/manual\/start$|\/auth-url$|\/generate$|\/generate-ai$|\/sources\/fetch/.test(
          path,
        ),
      ),
  ).toEqual([]);
});

async function api(page: Page, path: string, body?: unknown) {
  return page.evaluate(
    async ({ path, body, production }) => {
      const headers: Record<string, string> = production
        ? { "X-Kiki-UI": "v2" }
        : {};
      if (body !== undefined) {
        const session = await (await fetch("/api/auth/me", { headers })).json();
        headers["X-CSRF-Token"] = session.csrf_token;
        headers["Content-Type"] = "application/json";
      }
      const response = await fetch(path, {
        method: body === undefined ? "GET" : "POST",
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      return { status: response.status, data: await response.json() };
    },
    { path, body, production },
  );
}

test("pendientes reales del archivo, paginación y apertura de la variante sin simular consultas externas", async ({
  page,
}, info) => {
  const panel = page.getByLabel("Revisión periódica del catálogo", {
    exact: true,
  });
  const response = page.waitForResponse(
    (r) => new URL(r.url()).pathname === base + "/tasks",
  );
  await panel
    .getByRole("button", {
      name: "Consultar pendientes de revisión",
      exact: true,
    })
    .click();
  const result = await response;
  expect(result.status()).toBe(200);
  const data = await result.json();
  expect(data.execution).toBe("ON_REQUEST_REVIEW_TASKS_NO_BACKGROUND_WORKER");
  expect(data.source_changes_scope).toBe(
    "ARCHIVED_DOCUMENT_VERSIONS_NOT_LIVE_WEB",
  );
  expect(data).toMatchObject({
    commercial_changes: 0,
    facts_approved: 0,
    external_writes_enabled: false,
  });
  expect(data.total_tasks).toBeGreaterThan(0);
  const tasks = panel.getByRole("region", {
    name: "Pendientes de revisión del catálogo",
    exact: true,
  });
  await expect(tasks).toContainText(
    `${data.total_tasks} variantes con tareas entre ${data.total_variants} variantes Ecomm-App`,
  );
  await expect(panel).toContainText("no se comprueban sitios web");
  expect(data.items.length).toBeLessThanOrEqual(20);
  if (data.total_tasks > 20) {
    await tasks
      .getByRole("button", { name: "Pendientes siguientes", exact: true })
      .click();
    await expect(tasks).toContainText("Página 2 de");
    await tasks
      .getByRole("button", { name: "Pendientes anteriores", exact: true })
      .click();
    await expect(tasks).toContainText("Página 1 de");
  }
  await page.screenshot({
    path: `artifacts/periodic-review-${info.project.name}.png`,
    fullPage: false,
  });
  const first = data.items[0];
  await tasks
    .locator(`[data-periodic-ecomm="${first.ecomm_id}"]`)
    .getByRole("button", { name: "Revisar variante", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`product=${first.ecomm_id}(?:&|$)`));
});

test("programación con confirmación explícita y conflicto 409 conserva los cambios locales", async ({
  page,
}) => {
  const panel = page.getByLabel("Revisión periódica del catálogo", {
    exact: true,
  });
  const originalResult = await api(page, base + "/policy");
  expect(originalResult.status).toBe(200);
  const original = originalResult.data as Policy;
  let modified = false;
  try {
    await panel
      .getByRole("button", { name: "Recuperar programación", exact: true })
      .click();
    const interval = panel.getByLabel("Revisión general cada cuántos días", {
      exact: true,
    });
    const nextInterval = original.settings.interval_days === 30 ? 29 : 30;
    await expect(interval).toHaveValue(String(original.settings.interval_days));
    await interval.fill(String(nextInterval));
    await panel
      .getByLabel("Motivo de la programación", { exact: true })
      .fill(
        "Revisión de programación sintética con preservación de historial.",
      );
    await expect(
      panel.getByRole("button", {
        name: "Guardar programación de revisión",
        exact: true,
      }),
    ).toBeDisabled();
    const concurrent = await api(page, base + "/policy", {
      expected_version: original.version,
      settings: original.settings,
      reason: "Operador concurrente de pruebas revisó la programación interna.",
      confirm: true,
    });
    expect(concurrent.status).toBe(200);
    modified = true;
    await panel
      .getByLabel("Confirmo este cambio de programación interna.", {
        exact: true,
      })
      .check();
    const savedResponse = page.waitForResponse(
      (r) =>
        new URL(r.url()).pathname === base + "/policy" &&
        r.request().method() === "POST",
    );
    await panel
      .getByRole("button", {
        name: "Guardar programación de revisión",
        exact: true,
      })
      .click();
    expect((await savedResponse).status()).toBe(409);
    await expect(panel.getByRole("alert")).toContainText("Otro operador");
    await expect(interval).toHaveValue(String(nextInterval));
    await expect(panel).toContainText(
      "Hay cambios de programación sin guardar",
    );
    page.once("dialog", (dialog) => dialog.accept());
    await panel
      .getByRole("button", { name: "Recuperar programación", exact: true })
      .click();
    await expect(interval).toHaveValue(String(original.settings.interval_days));
    await interval.fill(String(nextInterval));
    await panel
      .getByLabel("Confirmo este cambio de programación interna.", {
        exact: true,
      })
      .check();
    await panel
      .getByRole("button", {
        name: "Guardar programación de revisión",
        exact: true,
      })
      .click();
    await expect(panel.getByRole("status")).toContainText(
      "Programación guardada",
    );
    const updated = await api(page, base + "/policy");
    expect(updated.data.settings.interval_days).toBe(nextInterval);
    expect(updated.data.background_worker_enabled).toBe(false);
    expect(updated.data.editorial_signoff_max_days).toBe(30);
  } finally {
    if (modified) {
      const current = await api(page, base + "/policy");
      const restored = await api(page, base + "/policy", {
        expected_version: current.data.version,
        settings: original.settings,
        reason:
          "Restauración de la programación inicial tras pruebas sintéticas.",
        confirm: true,
      });
      expect(restored.status).toBe(200);
    }
  }
});
