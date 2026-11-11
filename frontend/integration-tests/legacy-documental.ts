/** Regression-only transport for the previous fixture/pilot profile.
 * New acceptance tests use ordinary routes without this override.
 */
import type { Page } from "@playwright/test";
export const researchPath = (id: string) => `/api/test-research/${id}`;
export async function legacyDocumental(page: Page) {
  await page.addInitScript(() => {
    const native = window.fetch.bind(window);
    window.fetch = (input, options) => {
      if (typeof input === "string") {
        input = input.replace(
          /^\/api\/ecomm-app\/workspace\/(90000[1-6])\/(evidence|proposals|documents)(?=\/|$)/,
          (_, id: string, kind: string) =>
            `/api/test-${kind === "evidence" ? "research" : kind}/${id}`,
        );
      }
      return native(input, options);
    };
  });
}
