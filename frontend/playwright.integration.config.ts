import { defineConfig, devices } from "@playwright/test";
import { createHash, X509Certificate } from "node:crypto";
import { readFileSync } from "node:fs";
// Trust only the public key of this ephemeral local certificate; no global TLS bypass.
const certificate = new X509Certificate(
  readFileSync("../.integration-runtime/api/tls-cert.pem"),
);
const pin = createHash("sha256")
  .update(certificate.publicKey.export({ type: "spki", format: "der" }))
  .digest("base64");
export default defineConfig({
  testDir: "./integration-tests",
  outputDir: "integration-test-results",
  workers: 1,
  reporter: "list",
  timeout: 30000,
  use: {
    baseURL: "https://127.0.0.1:8443",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath:
        process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
      args: [`--ignore-certificate-errors-spki-list=${pin}`],
    },
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1080 } } },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
});
