import { test, expect, type Page } from "@playwright/test";

test.skip(
  process.env.KIKI_PRODUCTION_COMPAT !== "isolated-only",
  "Sólo backend descartable y transporte local explícitamente sintético",
);
test.setTimeout(120000);
const id = "900006";
const path = `/api/ecomm-app/workspace/${id}/taxonomy-review`;
const source = {
  category: "Categoría sintética",
  subcategory: "Subcategoría sintética",
};
const calls = new WeakMap<Page, string[]>();

test.beforeEach(async ({ page }) => {
  const paths: string[] = [];
  calls.set(page, paths);
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "https://127.0.0.1:8443")
      throw new Error("Red externa prohibida");
    paths.push(route.request().method() + " " + url.pathname);
    return route.continue();
  });
  await page.goto("/v2/");
  await page.getByLabel("Usuario", { exact: true }).fill("operador-prueba");
  await page
    .getByLabel("Contraseña", { exact: true })
    .fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator(`[data-ecomm-id="${id}"]`)).toBeVisible();
});
test.afterEach(async ({ page }) => {
  expect(
    calls
      .get(page)!
      .filter((p) => /oauth|sync|refresh|publish|openai|manual\/start/.test(p)),
  ).toEqual([]);
});

async function openPlan(page: Page, conflict = false) {
  let approved = false;
  let submission: Record<string, unknown> | undefined;
  const state = () => ({
    ecomm_id: id,
    channel: "KIKI",
    state: approved ? "APPROVED" : "NONE",
    mapping_version: approved ? 1 : 0,
    expected_version: approved ? 1 : 0,
    expected_workspace_version: 0,
    evidence_fingerprint: "a".repeat(64),
    can_approve: true,
    source_pair: source,
    record: approved
      ? {
          decision: "APPROVED",
          taxonomy_revision: "vocabulario-sintético-v1",
          target_pair: source,
          reviewer: "Operador de prueba · sesión sintética",
        }
      : null,
    external_writes_enabled: false,
    official_external_category_verified: false,
  });
  await page.route(
    "**/api/ecomm-app/workspace/commercial-plan/preview",
    (route) =>
      route.fulfill({
        json: {
          mode: "READ_ONLY_COMMERCIAL_EVIDENCE_PLAN",
          total: 1,
          counts: { GENERATE: 1 },
          taxonomy_counts: {},
          reviewed_internal_pairs: 0,
          taxonomy_reference: "KIKI_EDITORIAL_READY_FOR_CHANNELS_ONLY",
          external_writes_enabled: false,
          provider_calls: 0,
          ai_requests: 0,
          facts_approved: 0,
          automatic_publications: 0,
          items: [
            {
              ecomm_id: id,
              name: "Producto sintético para revisión",
              next_task: "GENERATE",
              approved_facts: 4,
              fields_supported: ["title"],
              fields_needing_support: ["media"],
              human_review_required: true,
              commercial_fiche_saved: false,
              reasons: [],
              review_due: false,
              taxonomy_alignment: {
                state: approved ? "REVIEWED_INTERNAL_MAPPING" : "NEEDS_MAPPING",
                source_approved: source,
                source_evidence_ids: ["fact-cat", "fact-sub"],
                existing_editorial: {
                  category: "",
                  subcategory: "",
                  status: "DRAFT",
                },
                exact_internal_reference: null,
                reference_fiches: 0,
                operator_review_required: true,
                mapping_saved: false,
                external_category_ids: null,
                reviewed_mapping: state(),
              },
              seo_fields: {
                seo_title: "EVIDENCE_BACKED",
                seo_description: "EVIDENCE_BACKED",
                seo_keywords: "REVIEW_TAXONOMY",
              },
            },
          ],
        },
      }),
  );
  await page.route(`**${path}*`, async (route) => {
    if (route.request().method() === "POST") {
      submission = route.request().postDataJSON();
      expect(route.request().headers()["x-csrf-token"]).toBeTruthy();
      expect(submission).toMatchObject({
        expected_version: 0,
        expected_workspace_version: 0,
        expected_fingerprint: "a".repeat(64),
        channel: "KIKI",
        confirm: true,
        decision: "APPROVED",
      });
      if (conflict)
        return route.fulfill({
          status: 409,
          json: {
            detail:
              "La investigación cambió en otra sesión. Recuperá la versión nueva.",
          },
        });
      approved = true;
    }
    return route.fulfill({ json: state() });
  });
  await page.locator(`[data-ecomm-id="${id}"]`).getByRole("checkbox").check();
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  const plan = page.getByRole("region", {
    name: "Plan de fichas comerciales verificadas",
  });
  await plan
    .getByRole("button", { name: "Analizar 1 variantes", exact: true })
    .click();
  const form = page.getByLabel(`Clasificación versionada ${id}`, {
    exact: true,
  });
  await form
    .getByText("Revisar y guardar clasificación versionada", { exact: true })
    .click();
  await form
    .getByRole("button", {
      name: "Recuperar clasificación y evidencias",
      exact: true,
    })
    .click();
  await expect(form).toContainText(
    "Fuente aprobada: Categoría sintética / Subcategoría sintética",
  );
  return { form, submission: () => submission };
}

test("clasificación humana versionada preserva fuente y exige confirmación; recuperación en el mismo dashboard", async ({
  page,
}, info) => {
  const { form, submission } = await openPlan(page);
  await form
    .getByLabel("Versión del vocabulario revisado")
    .fill("vocabulario-sintético-v1");
  await form
    .getByLabel("Motivo y comprobación")
    .fill("Contrasté la clasificación y las citas del original sintético.");
  await expect(
    form.getByRole("button", { name: "Guardar revisión humana", exact: true }),
  ).toBeDisabled();
  expect(submission()).toBeUndefined();
  await form.getByRole("checkbox").check();
  await form
    .getByRole("button", { name: "Guardar revisión humana", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Resultado del plan comercial" }),
  ).toContainText("Equivalencia interna revisada por una persona y versionada");
  expect(submission()).toMatchObject({
    target_category: source.category,
    target_subcategory: source.subcategory,
  });
  await page
    .getByLabel(`Clasificación versionada ${id}`, { exact: true })
    .getByText("Revisar y guardar clasificación versionada", { exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Recuperar clasificación y evidencias",
      exact: true,
    })
    .click();
  await expect(
    page.getByLabel(`Clasificación versionada ${id}`, { exact: true }),
  ).toContainText("Revisión vigente");
  await page.screenshot({
    path: `artifacts/taxonomy-review-${info.project.name}.png`,
    fullPage: false,
  });
});

test("conflicto 409 conserva la edición local y no asigna clasificación", async ({
  page,
}) => {
  const { form } = await openPlan(page, true);
  await form
    .getByLabel("Versión del vocabulario revisado")
    .fill("vocabulario-sintético-v1");
  await form
    .getByLabel("Categoría comercial", { exact: true })
    .fill("Clasificación local sin guardar");
  await form
    .getByLabel("Motivo y comprobación")
    .fill("Contrasté la clasificación y las citas del original sintético.");
  await form.getByRole("checkbox").check();
  await form
    .getByRole("button", { name: "Guardar revisión humana", exact: true })
    .click();
  await expect(form.getByRole("alert")).toContainText("otra sesión");
  await expect(
    form.getByLabel("Categoría comercial", { exact: true }),
  ).toHaveValue("Clasificación local sin guardar");
  await expect(form).toContainText("Sin revisión guardada");
});
