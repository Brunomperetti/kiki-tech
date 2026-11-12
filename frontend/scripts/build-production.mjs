import { build } from "vite";
import { fileURLToPath } from "node:url";
import { rename, readFile } from "node:fs/promises";
if (
  process.argv.length !== 2 ||
  Object.keys(process.env).some((k) => k.toUpperCase().startsWith("VITE_"))
)
  throw new Error(
    "Configuración ambigua: producción requiere el mismo origen, sin variables VITE_.",
  );
const root = fileURLToPath(new URL("../", import.meta.url));
await build({
  root,
  configFile: false,
  envFile: false,
  base: "/",
  define: { __KIKI_PRODUCTION__: "true" },
  build: {
    outDir: ".production-dist",
    emptyOutDir: true,
    rollupOptions: { input: root + "production.html" },
  },
  plugins: [
    {
      name: "no-demo-in-production",
      generateBundle(_options, bundle) {
        for (const output of Object.values(bundle))
          if (output.type === "chunk")
            for (const id of Object.keys(output.modules))
              if (
                /\/prototype\/(?:fixtures|commercial-demo|operations-model|Dashboard|DemoConnections)\./.test(
                  id,
                )
              )
                throw new Error(
                  "Se intentó incluir un controlador o datos de demostración: " +
                    id,
                );
      },
    },
  ],
});
await rename(
  root + ".production-dist/production.html",
  root + ".production-dist/index.html",
);
const html = await readFile(root + ".production-dist/index.html", "utf8");
if (!html.includes("connect-src 'self'"))
  throw new Error("CSP productiva ausente");
