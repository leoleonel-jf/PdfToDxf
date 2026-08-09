import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

/**
 * Gera o PDF sintético antes da suíte.
 *
 * Ele não é versionado: `*.pdf` está no .gitignore para impedir que planta de
 * cliente vá parar no GitHub, e forçar exceção para este arquivo enfraqueceria
 * a regra inteira. Gerar custa milissegundos.
 */
export default function preparar(): void {
  const raiz = fileURLToPath(new URL("../../..", import.meta.url));
  execFileSync(".venv/Scripts/python.exe",
               ["tests/gerar_pdf_de_teste.py", "tests/fixtures/planta_de_teste.pdf"],
               { cwd: raiz, stdio: "inherit" });
}
