import { defineConfig } from "@playwright/test";
import integration from "./playwright.integration.config";
export default defineConfig({
  ...integration,
  testDir: "./pilot-tests",
  outputDir: "pilot-test-results",
});
