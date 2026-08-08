"""Leitura tolerante de números digitados por gente.

Um lugar só para transformar o que o usuário digitou em número, usado pela
janela, pelo painel de exportação e pela linha de comando. Estava espalhado em
quatro `float(x.replace(",", "."))` que divergiam entre si e deixavam passar
coisas que não são medida nenhuma.

Duas regras que valem explicação:

- **Com os dois separadores presentes, o último é o decimal.** "1.234,56" é
  brasileiro e "1,234.56" é americano; nos dois casos o que vem depois do
  último separador é a parte fracionária. Com um separador só, ele é o decimal
  — "1.234" são mil duzentos e trinta e quatro décimos, não mil duzentos e
  trinta e quatro. Quem escreve em português usa vírgula para decimal, então
  essa leitura é a que menos surpreende.
- **`nan` e `inf` são recusados.** O `float()` os aceita de bom grado, e
  `float("nan") <= 0` é falso — então uma escala "nan" atravessa até a
  validação de positividade do núcleo e vira um DXF de coordenadas corrompidas
  sem um aviso sequer.
"""

from __future__ import annotations

import math
import re

# Espaços que vêm colados ao número quando se copia de planilha ou de página web
_ESPACOS = dict.fromkeys(map(ord, " \t\n\r\xa0   "), None)

_UNIDADES = ("mm", "cm", "m", "km", "pt", "in", "\"", "'")


def _limpar(texto: str, o_que: str) -> str:
    """Tira espaços e reclama do que estiver claramente fora do lugar."""
    limpo = str(texto).translate(_ESPACOS)
    if not limpo:
        raise ValueError(f"Digite {o_que}.")

    sem_unidade = limpo.rstrip("\"'")
    for unidade in _UNIDADES:
        if sem_unidade.lower().endswith(unidade) and sem_unidade[:-len(unidade)]:
            raise ValueError(
                f"Não escreva a unidade junto com o número: apague o "
                f"{limpo[len(sem_unidade) - len(unidade):]!r} e escolha a "
                f"unidade na lista ao lado.")
    return limpo


def _e_milhar(inteiro: str, sep: str) -> bool:
    """O separador só é de milhar se agrupar de três em três.

    Sem esta conferência, "3,5,5" — que não é número nenhum — passaria como
    355: bastaria contar as vírgulas e apagá-las.
    """
    return re.fullmatch(rf"[+-]?\d{{1,3}}(\{sep}\d{{3}})+", inteiro) is not None


def _normalizar_separadores(limpo: str) -> str:
    """Deixa um único separador decimal, em ponto, e sem os de milhar.

    Devolve o texto intacto quando os separadores não formam nada plausível —
    aí o teste final de formato, em `ler_numero`, é que recusa.
    """
    ultimo_ponto = limpo.rfind(".")
    ultima_virgula = limpo.rfind(",")

    if ultimo_ponto >= 0 and ultima_virgula >= 0:
        # Os dois aparecem: o último é o decimal, o outro só pode ser milhar.
        corte = max(ultimo_ponto, ultima_virgula)
        milhar = "," if ultima_virgula < ultimo_ponto else "."
        inteiro, decimal = limpo[:corte], limpo[corte + 1:]
        if not _e_milhar(inteiro, milhar):
            return limpo
        return f"{inteiro.replace(milhar, '')}.{decimal}"

    for sep in (",", "."):
        if limpo.count(sep) > 1:
            return limpo.replace(sep, "") if _e_milhar(limpo, sep) else limpo

    return limpo.replace(",", ".")


def ler_numero(texto: str, o_que: str = "um número") -> float:
    """Converte o texto digitado em `float`, ou levanta `ValueError`.

    `o_que` nomeia o campo na mensagem de erro — "a medida real", "a escala" —
    para o aviso não aparecer solto na tela.
    """
    limpo = _limpar(texto, o_que)
    candidato = _normalizar_separadores(limpo)

    # O float() aceita "nan", "inf" e "infinity"; aqui só entra dígito.
    if not re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", candidato):
        raise ValueError(f"Não entendi {o_que}: {texto.strip()!r}. "
                         f"Use só números, com vírgula ou ponto (ex.: 3,50).")

    valor = float(candidato)
    if not math.isfinite(valor):
        raise ValueError(f"{o_que.capitalize()} ficou grande demais para virar "
                         f"número: {texto.strip()!r}.")
    return valor


def ler_inteiro(texto: str, o_que: str = "um número inteiro") -> int:
    """Como `ler_numero`, mas recusa fração — para página, contagem e afins."""
    limpo = _limpar(texto, o_que)
    candidato = limpo
    for sep in (",", "."):
        if sep in limpo:
            # "1.234" pode ser milhar; "2,5" é fração, e fração aqui é erro.
            if not _e_milhar(limpo, sep):
                raise ValueError(f"{o_que.capitalize()} tem de ser inteiro, "
                                 f"sem fração: {texto.strip()!r}.")
            candidato = limpo.replace(sep, "")
    if not re.fullmatch(r"[+-]?\d+", candidato):
        raise ValueError(f"Não entendi {o_que}: {texto.strip()!r}. "
                         f"Use um número inteiro (ex.: 2).")
    return int(candidato)
