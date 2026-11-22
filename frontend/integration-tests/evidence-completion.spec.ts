import { test, expect, type Page } from "@playwright/test";

// Production entry against a disposable local server only. Media DTOs below
// are deliberately fabricated transport fixtures, never manufacturer licences.
test.skip(
  process.env.KIKI_PRODUCTION_COMPAT !== "isolated-only",
  "Requiere servidor /v2/ aislado y datos sintéticos",
);
const id = "900006",
  root = `/api/ecomm-app/workspace/${id}`;
const source = "https://fabricante-prueba.invalid/permiso-sintetico";
const media = [
  {
    kind: "IMAGE",
    url: "https://fabricante-prueba.invalid/imagen.png",
    source_url: source,
    alt: "Imagen sintética no descargada",
  },
  {
    kind: "VIDEO",
    url: "https://fabricante-prueba.invalid/video.mp4",
    source_url: source,
    alt: "Video sintético no descargado",
  },
];
const requests = new WeakMap<Page, Array<{ method: string; path: string }>>();
test.beforeEach(async ({ page }) => {
  const calls: Array<{ method: string; path: string }> = [];
  requests.set(page, calls);
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "https://127.0.0.1:8443")
      throw new Error("Recurso externo prohibido");
    return route.continue();
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    calls.push({ method: request.method(), path: url.pathname });
    expect(url.origin).toBe("https://127.0.0.1:8443");
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
    requests
      .get(page)!
      .filter((r) => r.method !== "GET" && r.path !== "/api/auth/login"),
  ).toEqual([]);
});
async function open(page: Page, tab: string) {
  await page
    .locator(`[data-ecomm-id="${id}"]`)
    .getByRole("button", { name: "Ver ficha", exact: true })
    .click();
  await page.getByRole("tab", { name: tab, exact: true }).click();
}
test("los 18 campos tienen estado recuperable sin certificar contenido previo", async ({
  page,
}) => {
  await open(page, "IA");
  const coverage = page.getByLabel("Cobertura de los campos comerciales", {
    exact: true,
  });
  await expect(coverage).toBeVisible();
  await coverage.locator("summary").click();
  await expect(coverage.locator("dt")).toHaveCount(18);
  await expect(coverage).toContainText("no aprobación de producto");
  await expect(coverage).toContainText("Imágenes y videos");
  await expect(coverage).toContainText("Palabras clave SEO");
  await page.reload();
  await expect(
    page.getByLabel("Cobertura de los campos comerciales").locator("dt"),
  ).toHaveCount(18);
});
test("imagen y video distinguen permiso vigente, vencido y revocado sin descargar recursos", async ({
  page,
}) => {
  let revoked = false;
  await page.route(`**${root}`, async (route) => {
    const response = await route.fetch();
    const dto = await response.json();
    await route.fulfill({
      response,
      json: { ...dto, fields: { ...dto.fields, media } },
    });
  });
  await page.route(`**${root}/evidence`, async (route) => {
    const response = await route.fetch();
    const dto = await response.json();
    const quote = `Permiso sintético de uso comercial: ${media[0].url}`;
    const documentId = "local-" + "a".repeat(32);
    await route.fulfill({
      response,
      json: {
        ...dto,
        facts: [],
        assisted: null,
        documents: [
          {
            id: documentId,
            version: 1,
            hash: "a".repeat(64),
            versions: [1],
            issues: [],
            history: [],
            body: {
              id: documentId,
              version: 1,
              synthetic: false,
              associated_ecomm_id: id,
              title: "Permiso SINTÉTICO para prueba de interfaz",
              kind: "Prueba local",
              origin_kind: "FILE",
              provenance: "local://sha256/" + "a".repeat(64),
              original: {
                sha256: "a".repeat(64),
                size: 120,
                content_type: "text/plain",
              },
              source: {
                review_state: "REVIEWED",
                reference_url: source,
                review_reason: "Fixture sintético, no licencia real",
                reviewer: "Operador de prueba",
              },
              sections: { "texto/linea/1": quote },
              claims: [],
              identity: dto.identity,
              identity_evidence: {},
              parser_blockers: [],
              parser_warnings: [],
              parse_status: "TEXT_EXTRACTED",
            },
          },
        ],
        media_rights: media.map((resource) => ({
          ...resource,
          ecomm_id: id,
          state: revoked
            ? "REVOKED"
            : resource.kind === "IMAGE"
              ? "APPROVED_CURRENT"
              : "STALE",
          current: !revoked && resource.kind === "IMAGE",
          document_id: documentId,
          document_version: 1,
          document_hash: "a".repeat(64),
          reviewer: "Operador de prueba",
          licence_basis: "OWNER_AUTHORIZATION",
          location: "texto/linea/1",
          quote,
        })),
      },
    });
  });
  await open(page, "Evidencias");
  const status = page.getByLabel("Estado efectivo del permiso multimedia", {
    exact: true,
  });
  await expect(status).toContainText("Permiso documentado vigente");
  await page
    .getByLabel("Imagen o video para revisar derechos")
    .selectOption(media[1].url);
  await expect(status).toContainText("Permiso sin vigencia");
  revoked = true;
  await page.getByRole("tab", { name: "Ficha", exact: true }).click();
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await expect(status).toContainText("Permiso revocado");
  expect(requests.get(page)!.some((r) => /\.(png|mp4)$/.test(r.path))).toBe(
    false,
  );
});
