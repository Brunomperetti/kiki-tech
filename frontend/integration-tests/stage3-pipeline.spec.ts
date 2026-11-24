import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import {
  verifiedManufacturerReport,
  type ManufacturerPipelineReport,
} from "../src/integration/ManufacturerPipelineReport";

// Real local auth/API/PostgreSQL, with only the manufacturer's HTTP transport
// replaced inside the isolated backend. No fulfilled API responses in the E2E.
test.skip(
  process.env.KIKI_STAGE3_SCENARIO !== "local-synthetic",
  "Requiere escenario documental aislado --stage3; nunca ejecutar en producción",
);
test.setTimeout(150000);
test.use({ actionTimeout: 20000 });
const endpoint = "/api/ecomm-app/workspace/sources/intake-jobs";
const sourceUrl = (id: string) =>
  `https://fabricante-stage3.invalid/producto/${id}/`;
const workspace = (id: string) => `/api/ecomm-app/workspace/${id}`;

async function json(page: Page, path: string) {
  const response = await page.request.get(path, {
    headers: { "X-Kiki-UI": "v2" },
  });
  expect(response.status(), await response.text()).toBe(200);
  expect(response.headers()["x-kiki-ui-contract"]).toBe(
    "kiki-same-origin-v2-1",
  );
  return response.json();
}
async function post(page: Page, path: string, data: unknown) {
  const csrf = (await json(page, "/api/auth/me")).csrf_token;
  const response = await page.request.post(path, {
    headers: { "X-Kiki-UI": "v2", "X-CSRF-Token": csrf },
    data,
  });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}
async function login(page: Page) {
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== "https://127.0.0.1:8443")
      throw new Error("Salida a fabricante/proveedor real prohibida");
    return route.continue();
  });
  page.on("request", (request) => {
    expect(new URL(request.url()).origin).toBe("https://127.0.0.1:8443");
    expect(new URL(request.url()).pathname).not.toMatch(
      /\/sync$|\/generate-ai$|\/auth-url$|\/manual\/start$/,
    );
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/v2/");
  await page.getByLabel("Usuario", { exact: true }).fill("operador-prueba");
  await page
    .getByLabel("Contraseña", { exact: true })
    .fill("solo-datos-sinteticos");
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.locator('[data-ecomm-id="900006"]')).toBeVisible();
}
function panel(page: Page) {
  return page.getByRole("region", {
    name: "Fuentes de fabricantes · cola reanudable",
    exact: true,
  });
}
async function create(page: Page, ids: string[]) {
  const capabilities = await json(page, "/api/ui/v2");
  expect(
    capabilities.document_exact_url_manifest,
    "El lector aislado y la capacidad de manifiestos deben estar disponibles; no se simulan flags",
  ).toBe(true);
  expect(capabilities.document_resumable_intake).toBe(true);
  const existing = new Set(
    (await json(page, endpoint)).items.map((item: { id: string }) => item.id),
  );
  for (const id of ids)
    await page.locator(`[data-ecomm-id="${id}"]`).getByRole("checkbox").check();
  await page.getByRole("button", { name: "Operaciones", exact: true }).click();
  await panel(page)
    .getByText("Preparar lote por URLs exactas (sin sitemap)", { exact: true })
    .click();
  await panel(page)
    .getByLabel("Lista de URLs exactas de un fabricante")
    .fill(
      ids
        .map(
          (id) =>
            `${id};${sourceUrl(id)};Fuente HTTP SINTÉTICA de prueba, cotejada para esta variante y presentación.`,
        )
        .join("\n"),
    );
  await panel(page)
    .getByRole("button", {
      name: "Guardar manifiesto de investigación",
      exact: true,
    })
    .click();
  let jobId = "";
  await expect
    .poll(async () => {
      const jobs = (await json(page, endpoint)).items;
      jobId =
        jobs.find((item: { id: string }) => !existing.has(item.id))?.id || "";
      return jobId;
    })
    .not.toBe("");
  await expect(
    panel(page).getByLabel("Seleccionar lote de fuentes"),
  ).toHaveValue(jobId);
  return jobId;
}
async function report(
  page: Page,
  jobId: string,
): Promise<ManufacturerPipelineReport> {
  const job = await json(page, `${endpoint}/${jobId}`);
  return verifiedManufacturerReport(
    await json(page, `${endpoint}/${jobId}/report`),
    jobId,
    job.revision,
    job.items,
  );
}

test("lote real de prueba: pausa, reinicio de navegador, reintento y citas PENDING sin alterar fichas", async ({
  page,
}, info) => {
  await login(page);
  const ids = ["900003", "900004"];
  const before = await Promise.all(ids.map((id) => json(page, workspace(id))));
  const beforeApproved = await Promise.all(
    ids.map(
      async (id) =>
        (await json(page, workspace(id) + "/evidence")).facts.filter(
          (fact: { state: string }) => fact.state === "APPROVED",
        ).length,
    ),
  );
  const jobId = await create(page, ids);
  let release: (() => void) | undefined;
  const wait = new Promise<void>((resolve) => {
    release = resolve;
  });
  let stepCalls = 0;
  // Delay one request then send it to the real API; do not mock its response.
  await page.route(`**/sources/intake-jobs/${jobId}/step`, async (route) => {
    stepCalls++;
    if (stepCalls === 1) await wait;
    return route.continue();
  });
  try {
    await panel(page)
      .getByRole("button", { name: "Procesar lote autorizado", exact: true })
      .click();
    await expect.poll(() => stepCalls).toBe(1);
    await panel(page)
      .getByRole("button", {
        name: "Pausar después del paso actual",
        exact: true,
      })
      .click();
    release!();
    await expect(panel(page)).toContainText("Lote pausado tras 1 pasos");
    expect(stepCalls).toBe(1);
    await page.reload();
    await page
      .getByRole("button", { name: "Operaciones", exact: true })
      .click();
    await panel(page)
      .getByLabel("Seleccionar lote de fuentes")
      .selectOption(jobId);
    await expect(panel(page)).toContainText("1 de 2 incorporadas");
    await panel(page)
      .getByRole("button", { name: "Procesar lote autorizado", exact: true })
      .click();
    await expect
      .poll(
        async () => (await json(page, `${endpoint}/${jobId}`)).counts.PENDING,
      )
      .toBe(0);
    const intermediate = await report(page, jobId);
    // The synthetic HTTP double returns503once. On mobile it may already have
    // been consumed by desktop, so a successful cached source is not a failure.
    if (intermediate.summary.FAILED > 0) {
      await panel(page)
        .getByRole("button", { name: "Reintentar esta fuente", exact: true })
        .click();
      await expect(
        panel(page).getByRole("button", {
          name: "Procesar lote autorizado",
          exact: true,
        }),
      ).toBeEnabled();
      await panel(page)
        .getByRole("button", { name: "Procesar lote autorizado", exact: true })
        .click();
    }
    await expect
      .poll(async () => {
        const job = await json(page, `${endpoint}/${jobId}`);
        return job.counts.IMPORTED + job.counts.ALREADY_PRESENT;
      })
      .toBe(2);
    const final = await report(page, jobId);
    expect(final.metrics.ai_requests).toBe(0);
    expect(final.metrics.publication_writes).toBe(0);
    expect(final.items.map((item) => item.ecomm_id)).toEqual(ids);
    expect(
      final.items.every((item) =>
        /^[a-f0-9]{64}$/.test(item.document_sha256 || ""),
      ),
    ).toBe(true);
    expect(
      final.items.every(
        (item) =>
          item.claims.length > 0 &&
          item.claims.every((claim) => claim.quote && claim.location),
      ),
    ).toBe(true);
    const after = await Promise.all(ids.map((id) => json(page, workspace(id))));
    for (let index = 0; index < ids.length; index++) {
      expect(after[index].fields).toEqual(before[index].fields);
      expect(after[index].version).toBe(before[index].version);
      const facts = (await json(page, workspace(ids[index]) + "/evidence"))
        .facts;
      expect(
        facts.filter((fact: { state: string }) => fact.state === "APPROVED"),
      ).toHaveLength(beforeApproved[index]);
    }
    await panel(page)
      .getByRole("button", {
        name: "Actualizar informe documental",
        exact: true,
      })
      .click();
    const result = panel(page).getByRole("region", {
      name: "Resultado documental del lote",
      exact: true,
    });
    await expect(result).toContainText("0 solicitudes OpenAI");
    const download = page.waitForEvent("download");
    await result
      .getByRole("button", {
        name: "Exportar excepciones del lote (CSV)",
        exact: true,
      })
      .click();
    const file = await download;
    expect(file.suggestedFilename()).toBe(
      "kiki-lote-documental-excepciones.csv",
    );
    expect(readFileSync((await file.path())!, "utf8")).toContain("900003");
    await result.locator('[data-pipeline-ecomm-id="900003"] > summary').click();
    await expect(
      result.locator('[data-pipeline-ecomm-id="900003"]'),
    ).toContainText(sourceUrl("900003"));
    await page.screenshot({
      path: `artifacts/etapa3-lote-documental-${info.project.name}.png`,
      fullPage: false,
    });
  } finally {
    release?.();
  }
});

test("plan determinista exige revisión humana y la exportación rechaza una huella anterior", async ({
  page,
}, info) => {
  await login(page);
  const id = "900005",
    jobId = await create(page, [id]);
  const before = await json(page, workspace(id));
  await panel(page)
    .getByRole("button", { name: "Procesar lote autorizado", exact: true })
    .click();
  await expect
    .poll(async () => {
      const job = await json(page, `${endpoint}/${jobId}`);
      return job.counts.IMPORTED + job.counts.ALREADY_PRESENT;
    })
    .toBe(1);
  const pendingReport = await report(page, jobId);
  let dossier = await json(page, workspace(id) + "/evidence");
  const doc = dossier.documents.find(
    (item: { body: { source?: { reference_url?: string } } }) =>
      item.body.source?.reference_url === sourceUrl(id),
  );
  expect(doc).toBeTruthy();
  if (doc.body.source.review_state !== "REVIEWED") {
    await post(page, `${workspace(id)}/documents/${doc.id}/provenance`, {
      expected_document_version: doc.version,
      decision: "REVIEWED",
      reason:
        "Revisión humana SINTÉTICA de un original de prueba; no certifica fabricante real.",
    });
  }
  dossier = await json(page, workspace(id) + "/evidence");
  const reviewedOriginal = dossier.documents.find(
    (item: { id: string }) => item.id === doc.id,
  );
  await post(page, `${workspace(id)}/evidence/extract`, {
    expected_version: dossier.version,
    document_id: reviewedOriginal.id,
    document_version: reviewedOriginal.version,
  });
  dossier = await json(page, workspace(id) + "/evidence");
  const identities = dossier.facts.filter(
    (fact: { field: string; document_id: string }) =>
      fact.document_id === doc.id &&
      ["product_name", "presentation"].includes(fact.field),
  );
  expect(identities.length).toBeGreaterThanOrEqual(2);
  for (const candidate of identities) {
    dossier = await json(page, workspace(id) + "/evidence");
    const fact = dossier.facts.find(
      (item: { id: string }) => item.id === candidate.id,
    );
    if (fact.state === "APPROVED" && fact.verified) continue;
    expect(fact.blockers).toEqual([]);
    await post(page, `${workspace(id)}/evidence/facts/${fact.id}/review`, {
      expected_version: dossier.version,
      expected_fact_version: fact.version,
      decision: "APPROVED",
      reason:
        "Aprobación humana explícita de cita SINTÉTICA, exclusiva de esta prueba aislada.",
    });
  }
  const beforeCompletion = await report(page, jobId);
  if (beforeCompletion.summary.READY === 0) {
    await panel(page)
      .getByRole("button", { name: "Actualizar estados", exact: true })
      .click();
    const finish = panel(page).getByRole("button", {
      name: "Completar extracción local sin descargar",
      exact: true,
    });
    await expect(finish).toBeEnabled();
    await finish.click();
    await expect(finish).toHaveCount(0);
  }
  const approvedReport = await report(page, jobId);
  expect(approvedReport.summary.READY).toBe(1);
  expect(
    approvedReport.items[0].plan.fields.title.evidence_ids.length,
  ).toBeGreaterThan(0);
  expect(
    approvedReport.items[0].plan.fields.description.citations.every(
      (citation) => citation.quote && citation.document_id,
    ),
  ).toBe(true);
  expect((await json(page, workspace(id))).fields).toEqual(before.fields);
  if (pendingReport.fingerprint !== approvedReport.fingerprint) {
    const old = new URLSearchParams({
      expected_revision: String(pendingReport.revision),
      expected_fingerprint: pendingReport.fingerprint,
    });
    expect(
      (
        await page.request.get(`${endpoint}/${jobId}/exceptions.csv?${old}`, {
          headers: { "X-Kiki-UI": "v2" },
        })
      ).status(),
    ).toBe(409);
  }
  await panel(page)
    .getByRole("button", { name: "Actualizar informe documental", exact: true })
    .click();
  await expect(
    panel(page).getByRole("region", { name: "Resultado documental del lote" }),
  ).toContainText("Propuesta respaldada disponible (READY)");
  const plan = panel(page).locator(`[data-pipeline-ecomm-id="${id}"]`);
  await plan.locator(":scope > summary").click();
  await plan
    .locator("summary")
    .filter({ hasText: "Título comercial" })
    .first()
    .click();
  await page.screenshot({
    path: `artifacts/etapa3-propuesta-respaldada-${info.project.name}.png`,
    fullPage: false,
  });
});

test("contrato del informe rechaza citas pendientes, variantes ajenas y campos no respaldados", () => {
  const citation = {
    fact_id: "fact",
    document_id: "doc",
    document_version: 1,
    quote: "Nombre de prueba",
    location: "texto/linea/1",
  };
  const fixture: ManufacturerPipelineReport = {
    mode: "SOURCE_INTAKE_PIPELINE_REPORT",
    schema_version: "kiki-documental-pipeline-v1",
    job_id: "synthetic-job",
    revision: 1,
    fingerprint: "a".repeat(64),
    total: 1,
    summary: {
      READY: 1,
      RESEARCH: 0,
      REVIEW_REQUIRED: 0,
      BLOCKED: 0,
      FAILED: 0,
    },
    metrics: {
      processed: 1,
      pending_facts: 0,
      without_source: 0,
      failed: 0,
      attempts_total: 1,
      ai_requests: 0,
      publication_writes: 0,
    },
    items: [
      {
        ecomm_id: "900005",
        sku: "SYNTHETIC",
        barcode: null,
        state: "READY",
        legacy_state: "IMPORTED",
        url: sourceUrl("900005"),
        document_id: "doc",
        document_sha256: "b".repeat(64),
        processing_status: "EXTRACTED",
        claims: [
          {
            ...citation,
            field: "product_name",
            value: "Nombre de prueba",
            unit: null,
            state: "APPROVED",
            verified: true,
          },
        ],
        plan: {
          fields: {
            title: {
              value: "Nombre de prueba",
              evidence_ids: ["fact"],
              citations: [citation],
            },
          },
          blocked_reasons: [],
        },
        blockers: [],
      },
    ],
    external_writes_enabled: false,
  };
  const members = fixture.items.map((item) => ({
    ecomm_id: item.ecomm_id,
    url: item.url,
  }));
  expect(verifiedManufacturerReport(fixture, fixture.job_id, 1, members)).toBe(
    fixture,
  );
  const pending = structuredClone(fixture);
  pending.items[0].claims[0].state = "PENDING";
  pending.items[0].claims[0].verified = false;
  expect(() =>
    verifiedManufacturerReport(pending, fixture.job_id, 1, members),
  ).toThrow();
  const otherDocument = structuredClone(fixture);
  otherDocument.items[0].plan.fields.title.citations[0].document_version = 2;
  expect(() =>
    verifiedManufacturerReport(otherDocument, fixture.job_id, 1, members),
  ).toThrow();
  const media = structuredClone(fixture);
  media.items[0].plan.fields.media = {
    value: "invented",
    evidence_ids: ["fact"],
    citations: [citation],
  };
  expect(() =>
    verifiedManufacturerReport(media, fixture.job_id, 1, members),
  ).toThrow();
  const prototypeKey = structuredClone(fixture);
  Object.defineProperty(prototypeKey.items[0].plan.fields, "constructor", {
    enumerable: true,
    value: { value: "invented", evidence_ids: ["fact"], citations: [citation] },
  });
  expect(() =>
    verifiedManufacturerReport(prototypeKey, fixture.job_id, 1, members),
  ).toThrow();
  expect(() =>
    verifiedManufacturerReport(fixture, fixture.job_id, 1, [
      { ecomm_id: "900006", url: sourceUrl("900006") },
    ]),
  ).toThrow();
});
