// De "vitest/config", não de "vite": o `defineConfig` do Vite puro não conhece
// o bloco `test` e o TypeScript recusa o arquivo.
import { defineConfig } from "vitest/config";

export default defineConfig({
  server: {
    // O frontend e a API vivem em portas diferentes em desenvolvimento. Sem
    // este proxy, todo pedido a /api viraria requisição de outra origem e
    // esbarraria em CORS — que não queremos afrouxar no servidor só por causa
    // do ambiente de trabalho.
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "node", include: ["testes/**/*.test.ts"] },
});
