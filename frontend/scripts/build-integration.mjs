import { build } from "vite";
import { fileURLToPath } from "node:url";

// There is no upstream selector. Never load .env or the demo/Render Vite config.
if (
  process.argv.length !== 2 ||
  Object.keys(process.env).some((key) => key.toUpperCase().startsWith("VITE_"))
) {
  throw new Error(
    "Configuración ambigua: integración no acepta argumentos ni variables VITE_.",
  );
}
await build({
  root: fileURLToPath(new URL("../", import.meta.url)),
  configFile: false,
  envFile: false,
  define: { __KIKI_INTEGRATION__: "true" },
  build: {
    outDir: ".integration-dist",
    emptyOutDir: true,
    rollupOptions: {
      input: fileURLToPath(new URL("../integration.html", import.meta.url)),
    },
  },
});
