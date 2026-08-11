import { defineConfig } from "@playwright/test";

// O Python que sobe a API. O padrão continua sendo o `.venv` do projeto, que é
// como se roda nesta máquina; quem não tem esse caminho — o runner Linux da
// integração contínua, por exemplo — exporta `PDFTODXF_PYTHON` apontando para
// o seu interpretador.
//
// **Barra invertida no Windows, e isso não é gosto:** o Playwright entrega este
// comando ao `cmd.exe`, que corta `.venv/Scripts/python.exe` no primeiro `/` e
// responde "'.venv' não é reconhecido". Com `\` funciona. O erro só não
// aparecia antes porque `reuseExistingServer` encontrava um uvicorn já de pé.
const python = process.env.PDFTODXF_PYTHON
  || (process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  // O PDF de teste é gerado a cada execução, não versionado: `*.pdf` está no
  // .gitignore para que planta de cliente nunca vá ao GitHub, e abrir exceção
  // com `git add -f` enfraqueceria justamente a regra que protege os arquivos
  // do usuário.
  globalSetup: "./e2e/preparar.ts",
  // Sem repetição automática: um teste que só passa na segunda tentativa está
  // escondendo um defeito. A etapa 2 já mostrou o preço disso.
  retries: 0,
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:5173", trace: "retain-on-failure" },
  webServer: [
    {
      // O caminho é relativo ao `cwd` abaixo, que já é a raiz do repositório.
      command: `${python} -m uvicorn web.api.main:app --port 8000`,
      cwd: "../..",
      // `/openapi.json`, e não `/docs`: a API sobe com `docs_url=None` de
      // propósito, então `/docs` devolve 404 para sempre e a espera nunca
      // terminaria. Foi medido, não suposto.
      url: "http://127.0.0.1:8000/openapi.json",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 5173 --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
