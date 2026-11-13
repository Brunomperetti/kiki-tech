import { defineConfig } from "vite";
// No proxy, rewrite, env-based upstream, external assets or backend in this prototype.
const policy =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; frame-src 'none'; form-action 'none'; object-src 'none'; base-uri 'self'";
export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    hmr: false,
    headers: { "Content-Security-Policy": policy },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    headers: { "Content-Security-Policy": policy },
  },
  plugins: [
    {
      name: "isolated-prototype",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (/^\/(api(?:\/|$)|health(?:\/|$))/.test(req.url || "")) {
            res.setHeader("Content-Security-Policy", policy);
            res.statusCode = 403;
            res.end("Prototype: backend disabled");
            return;
          }
          next();
        });
      },
      configurePreviewServer(server) {
        server.middlewares.use((req, res, next) => {
          if (/^\/(api(?:\/|$)|health(?:\/|$))/.test(req.url || "")) {
            res.setHeader("Content-Security-Policy", policy);
            res.statusCode = 403;
            res.end("Prototype: backend disabled");
            return;
          }
          next();
        });
      },
    },
  ],
});
