import { test, expect, type Page } from "@playwright/test";

const outbound = new WeakMap<Page, string[]>();
test.afterEach(async ({ page }) => {
  expect(outbound.get(page)).toEqual([]);
});
test.beforeEach(async ({ page }) => {
  // Abort unexpected destinations before DNS/network, and fail if any are attempted.
  const external: string[] = [];
  outbound.set(page, external);
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "http://127.0.0.1:4173") {
      external.push(url.origin);
      return route.abort();
    }
    return route.continue();
  });
  await page.addInitScript(() => {
    (window as unknown as { __nativeFetch: typeof fetch }).__nativeFetch =
      window.fetch.bind(window);
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tu catálogo, en un solo lugar." }),
  ).toBeVisible();
});

test("busca por nombre, SKU, marca e identidad; variantes con SKU repetido son distintas", async ({
  page,
}) => {
  const search = page.getByRole("textbox", { name: "Buscar productos" });
  for (const [term, count] of [
    ["Auriculares", 1],
    ["BOT-750", 2],
    ["Casa Sur", 2],
    ["DEMO-1006", 1],
  ] as const) {
    await search.fill(term);
    await expect(page.locator(".d-table tbody tr")).toHaveCount(count);
    await expect(page).toHaveURL(
      new RegExp(`q=${encodeURIComponent(term).replace(/%20/g, "\\+")}`),
    );
  }
  await page.getByRole("button", { name: "Abrir DEMO-1006" }).click();
  await expect(page.getByRole("dialog")).toContainText("coral");
  await expect(page).toHaveURL(/product=DEMO-1006/);
});

test("combina filtros, restaura URL y muestra vacío recuperable", async ({
  page,
}) => {
  await page.getByLabel("Estado", { exact: true }).selectOption("Preparada");
  await page.getByLabel("Marca", { exact: true }).selectOption("Nexo");
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
  await page.reload();
  await expect(page.getByLabel("Marca", { exact: true })).toHaveValue("Nexo");
  await page.getByLabel("Canal verificado").selectOption("tn");
  await expect(
    page.getByRole("heading", { name: "No encontramos productos" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Ver todo el catálogo" }).click();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(8);
  await page.getByRole("button", { name: /Conflictos 2 Necesitan/ }).click();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(2);
  await page.goBack();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(8);
});

test("ficha, pestañas, URL compartible, historial de navegación y foco", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Abrir DEMO-1001" }).click();
  const panel = page.getByRole("dialog");
  await expect(panel).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Cerrar ficha" }),
  ).toBeFocused();
  for (const tab of ["Evidencias", "IA", "Canales", "Historial", "Ficha"]) {
    await panel.getByRole("tab", { name: tab, exact: true }).click();
    await expect(
      panel.getByRole("tab", { name: tab, exact: true }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(page).toHaveURL(new RegExp(`tab=${tab}`));
  }
  await page.reload();
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("DEMO-1001");
  await panel.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await expect(panel).toContainText("Publicación no confirmada.");
  await page.goBack();
  await expect(
    panel.getByRole("tab", { name: "Ficha", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Escape");
  await expect(panel).not.toBeVisible();
  await expect(page).not.toHaveURL(/product=/);
});

test("requiere confirmación y bloquea preparación con conflictos", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Abrir DEMO-1006" }).click();
  const panel = page.getByRole("dialog");
  await expect(
    panel.getByRole("button", { name: "Preparar ficha", exact: true }),
  ).toBeDisabled();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Abrir DEMO-1001" }).click();
  await panel
    .getByRole("button", { name: "Preparar ficha", exact: true })
    .click();
  await expect(panel.getByRole("alert")).toContainText("DEMO-1001");
  await panel.getByRole("button", { name: "Cancelar", exact: true }).click();
  await expect(
    panel.getByRole("button", { name: "Preparar ficha", exact: true }),
  ).toBeEnabled();
  await panel
    .getByRole("button", { name: "Preparar ficha", exact: true })
    .click();
  await panel.getByRole("button", { name: "Confirmar decisión" }).click();
  await expect(
    panel.getByRole("button", { name: "Ficha preparada", exact: true }),
  ).toBeDisabled();
  await panel.getByRole("tab", { name: "Canales", exact: true }).click();
  await expect(panel).toContainText("Publicación no confirmada.");
  await page.keyboard.press("Escape");
  await expect(
    page.locator(".d-table tbody tr").filter({ hasText: "DEMO-1006" }),
  ).toContainText("Conflicto");
});

test("no conexiones productivas: CSP, transportes, env heredado y backend bloqueados", async ({
  page,
  request,
}) => {
  const network: string[] = [];
  page.on("request", (r) => {
    if (["fetch", "xhr", "websocket", "eventsource"].includes(r.resourceType()))
      network.push(r.url());
  });
  const result = await page.evaluate(async () => {
    const attempts: string[] = [];
    for (const url of [
      "/api/dashboard",
      "https://production.invalid/api",
      "https://kiki-tech-api.onrender.com/health",
    ]) {
      try {
        await fetch(url);
        attempts.push("allowed");
      } catch {
        attempts.push("blocked");
      }
    }
    try {
      new XMLHttpRequest().open("GET", "https://production.invalid");
      attempts.push("allowed");
    } catch {
      attempts.push("blocked");
    }
    try {
      new WebSocket("wss://production.invalid");
      attempts.push("allowed");
    } catch {
      attempts.push("blocked");
    }
    try {
      new EventSource("https://production.invalid");
      attempts.push("allowed");
    } catch {
      attempts.push("blocked");
    }
    attempts.push(
      navigator.sendBeacon("https://production.invalid")
        ? "allowed"
        : "blocked",
    );
    // A new iframe would bypass JS replacements; the document CSP must block it.
    return {
      attempts,
      csp: document
        .querySelector('meta[http-equiv="Content-Security-Policy"]')
        ?.getAttribute("content"),
    };
  });
  expect(result.attempts).toEqual(Array(7).fill("blocked"));
  const nativeBlocked = await page.evaluate(async () => {
    try {
      await (
        window as unknown as { __nativeFetch: typeof fetch }
      ).__nativeFetch("/api/dashboard");
      return false;
    } catch {
      return true;
    }
  });
  expect(nativeBlocked).toBe(true);
  expect(result.csp).toContain("connect-src 'none'");
  expect(result.csp).toContain("form-action 'none'");
  expect(result.csp).toContain("frame-src 'none'");
  expect(network).toEqual([]);
  for (const endpoint of ["/api/dashboard", "/api/auth/login", "/health"]) {
    const response = await request.get(endpoint);
    expect(response.status()).toBe(403);
    expect(response.headers()["content-security-policy"]).toContain(
      "connect-src 'none'",
    );
  }
});

test("todas las rutas anteriores conservadas sin requests de API", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const apiRequests: string[] = [];
  page.on("request", (r) => {
    if (["fetch", "xhr"].includes(r.resourceType())) apiRequests.push(r.url());
  });
  const paths = [
    "/pilot",
    "/workspace",
    "/queue",
    "/propuestas-ia",
    "/cases",
    "/channels",
    "/products",
    "/work",
    "/work/details",
    "/readiness",
    "/enrichment",
    "/external-research",
    "/prepublication",
    "/images",
    "/metadata",
    "/review",
    "/duplicate-review",
    "/tiendanube",
    "/imports",
    "/guia",
    "/dashboard-classic",
  ];
  for (const path of paths) {
    await page.goto(path);
    await expect(
      page.getByText(/La herramienta original se conserva/),
    ).toBeVisible();
  }
  expect(apiRequests).toEqual([]);
  expect(errors).toEqual([]);
  await page.getByRole("link", { name: "Volver al dashboard" }).click();
  await expect(
    page.getByRole("heading", { name: "Tu catálogo, en un solo lugar." }),
  ).toBeVisible();
});

test("responsive y capturas de dashboard y ficha", async ({
  page,
}, testInfo) => {
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({
    path: `artifacts/dashboard-${testInfo.project.name}.png`,
    fullPage: true,
    scale: "css",
  });
  await page.getByRole("button", { name: "Abrir DEMO-1002" }).click();
  await page.getByRole("tab", { name: "Evidencias", exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({
    path: `artifacts/ficha-${testInfo.project.name}.png`,
    fullPage: true,
    scale: "css",
  });
});

test("tablet sin desborde", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 1180 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await page.getByRole("button", { name: "Abrir DEMO-1003" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
});
