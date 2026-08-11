/**
 * O que a tela diz em cada situação.
 *
 * Uma mensagem só serve se disser o que houve **e** o que fazer. "Erro ao
 * processar" não é mensagem, é desculpa.
 */
import { ErroDaApi } from "./api.js";

export type Aviso = {
  titulo: string;
  detalhe: string;
  podeTentarDeNovo: boolean;
};

const POR_CODIGO: Record<string, Aviso> = {
  sem_vetores: {
    titulo: "Esta página não tem desenho vetorial",
    detalhe: "Só funcionam PDFs gerados pelo CAD. Um PDF escaneado é uma " +
             "imagem: não há linhas para converter, só pixels.",
    podeTentarDeNovo: false,
  },
  entidades_demais: {
    titulo: "A planta é grande demais",
    detalhe: "Esta página passa do limite de elementos que o servidor " +
             "processa. Tente exportar do CAD apenas as camadas necessárias.",
    podeTentarDeNovo: false,
  },
  recurso: {
    titulo: "Não consegui processar esta planta",
    detalhe: "Ela passou do limite de memória ou de tempo do servidor.",
    podeTentarDeNovo: true,
  },
  interno: {
    titulo: "Alguma coisa deu errado aqui do meu lado",
    detalhe: "A falha foi registrada no servidor. Tente de novo em instantes.",
    podeTentarDeNovo: true,
  },
};

const NA_FILA: Aviso = {
  titulo: "Processando a planta",
  detalhe: "A extração já começou. Plantas grandes levam alguns minutos.",
  podeTentarDeNovo: false,
};

export function avisoDaSituacao(situacao: string, codigo?: string,
                                mensagem?: string): Aviso | null {
  if (situacao === "pronta") return null;
  // "extraindo" está no contrato da API e hoje nada o escreve: o processo pai
  // é o dono do estado e não sabe quando o worker pega o trabalho.
  if (situacao === "na_fila" || situacao === "extraindo") return NA_FILA;

  const conhecido = codigo ? POR_CODIGO[codigo] : undefined;
  if (conhecido) return conhecido;
  return {
    titulo: "Não consegui processar esta planta",
    detalhe: mensagem || "O servidor não explicou o motivo. Tente de novo.",
    podeTentarDeNovo: true,
  };
}

export function avisoDoErro(erro: unknown): Aviso {
  if (erro instanceof ErroDaApi) {
    if (erro.status === 404) {
      return {
        titulo: "Esta planta expirou",
        detalhe: "Os arquivos enviados são apagados depois de 4 horas. " +
                 "Envie o PDF de novo para continuar.",
        podeTentarDeNovo: false,
      };
    }
    if (erro.status === 413) {
      return {
        titulo: "O arquivo passa do tamanho permitido",
        detalhe: erro.message || "Escolha um PDF menor.",
        podeTentarDeNovo: false,
      };
    }
    if (erro.status === 409) {
      return {
        titulo: "A página ainda não está pronta",
        detalhe: "Espere a extração terminar.",
        podeTentarDeNovo: true,
      };
    }
    return {
      titulo: "O servidor recusou o pedido",
      detalhe: erro.message,
      podeTentarDeNovo: true,
    };
  }
  return {
    titulo: "Não consegui falar com o servidor",
    detalhe: "Confira a conexão e tente de novo.",
    podeTentarDeNovo: true,
  };
}
