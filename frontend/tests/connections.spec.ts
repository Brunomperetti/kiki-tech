import { test, expect } from "@playwright/test";
test("centro de conexiones público: tres fuentes sintéticas, sin API ni acciones engañosas", async ({
  page,
}, info) => {
  const calls: string[] = [];
  await page.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (
      u.origin !== "http://127.0.0.1:4173" ||
      u.pathname.startsWith("/api/")
    ) {
      calls.push(u.origin + u.pathname);
      return route.abort();
    }
    return route.continue();
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Centro de conexiones", exact: true })
    .click();
  const settings = page.getByRole("dialog", {
    name: "Configuración del catálogo",
  });
  const center = settings.getByRole("region", { name: "Centro de conexiones" });
  await expect(center.getByRole("article")).toHaveCount(3);
  await expect(center).toContainText("Ejemplos sintéticos de la demo pública");
  await expect(
    center.getByRole("button", { name: "Actualizar catálogo ahora" }),
  ).toBeDisabled();
  await expect(
    center.getByRole("button", {
      name: "Actualizar publicaciones",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    center.getByRole("button", { name: "Conectar Mercado Libre", exact: true }),
  ).toBeDisabled();
  await expect(
    center.getByLabel("Importar / Actualizar CSV de Tiendanube", {
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    center
      .getByRole("article", { name: "Conexión Ecomm-App" })
      .locator("dd")
      .nth(1),
  ).toHaveText("8");
  await settings.screenshot({
    path: `artifacts/conexiones-demo-${info.project.name}.png`,
    scale: "css",
  });
  await settings
    .getByRole("button", { name: "Cerrar configuración", exact: true })
    .click();
  await expect(page.locator(".d-table tbody tr")).toHaveCount(8);
  expect(calls).toEqual([]);
});
