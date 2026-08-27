"""Pode? — a cota por janela deslizante.

Um registro por consumo, com a hora. A cota disponível é o limite menos o que
foi consumido na janela: **não existe virada em horário fixo**, e por isso não
existe a meia-noite em que todo mundo volta a enviar de uma vez.

Reservar e confirmar são coisas separadas porque PDF sem vetores e worker morto
por recurso não podem consumir cota. A transição é de mão única e idempotente:
a primeira página que dá certo confirma a reserva do documento inteiro, e o que
falhar depois não desfaz.

**A soltura é do documento, não da página.** Quem chama `soltar` só chama
quando **todas** as páginas terminaram e **nenhuma** ficou pronta — nesse ponto
o PDF de origem já foi apagado, e não há mais página que possa dar certo.
Soltar por página deixava furar o teto: converter primeiro a página escaneada
devolvia a vaga, o envio seguinte entrava, e a página com vetores promovia
depois uma reserva já solta.

Soltar **não apaga**: marca `'solto'`. A linha fica, invisível para a contagem,
como rastro do que passou por ali — e é o que faz `cobrar` sobre a mesma
referência cobrar de verdade, em vez de esbarrar na guarda de repetição.
`confirmar` **não** promove linha solta: soltar já devolveu a vaga, e uma
tentativa nova reserva de novo. Promover as duas levas cobraria duas vagas por
uma entrega só — e, como a referência de download não carrega identidade
dentro, cobraria de quem falhou o DXF que outro recebeu.

Reserva nunca confirmada **continua contando** até sair da janela. Quem envia e
fecha a aba consumiu banda e disco; não há varredura de reserva órfã, porque a
janela deslizante já é o prazo.
"""

from __future__ import annotations

import os
import time

from . import db, limits

PADROES = {
    "arquivos": 5,
    "downloads": 15,
    "mb": 10,
    "arquivos_logado": 15,
    "downloads_logado": 45,
    "mb_logado": 100,
    "janela_h": 2,
}

TIPOS = ("arquivo", "download")

# O valor de janela que já foi avisado, não um "já avisei": trocar a chave em
# tempo de execução tem de rearmar o aviso, senão o valor novo passa calado.
_avisou_janela: int | None = None


class SemVaga(Exception):
    """Não cabe nesta janela. `libera_em` é quando a próxima vaga abre."""

    def __init__(self, tipo: str, libera_em: float | None):
        super().__init__(tipo, libera_em)
        self.tipo = tipo
        self.libera_em = libera_em


def _chave(nome: str) -> int:
    """O valor de `PDFTODXF_COTA_<NOME>`, ou o padrão. `0` é sem limite."""
    cru = os.environ.get(f"PDFTODXF_COTA_{nome.upper()}")
    if cru is None or cru.strip() == "":
        return PADROES[nome]
    try:
        valor = int(cru)
    except ValueError:
        # Chave escrita errada cai no padrão, que é seguro — e não em
        # "sem limite", que seria o modo de falhar caro.
        return PADROES[nome]
    if valor < 0:
        # `-1` é a convenção de "sem limite" de outros sistemas, então é o lixo
        # mais provável de aparecer aqui. Grampear em `0` abriria a cota
        # inteira em silêncio; negativo cai no padrão como qualquer outro lixo.
        return PADROES[nome]
    return valor


def janela_s() -> int:
    global _avisou_janela
    horas = _chave("janela_h")
    if horas == 0:
        # Única chave em que `0` não é "sem limite": janela sem limite seria
        # janela infinita, que nunca esquece um consumo — mais apertado, não
        # mais folgado. Quem escreveu `0` queria o contrário, então: padrão.
        horas = PADROES["janela_h"]
    segundos = horas * 60 * 60
    if segundos <= db.PRAZO_DO_CONSUMO_S:
        # Voltou para dentro do prazo da limpeza: esquece o aviso, para que um
        # valor alto colocado outra vez mais tarde volte a avisar.
        _avisou_janela = None
    elif _avisou_janela != horas:
        # A limpeza apaga consumo de mais de 24 h, então a janela é truncada
        # ali de qualquer jeito. Avisa uma vez por valor, não a cada pedido.
        _avisou_janela = horas
        print(f"PDFTODXF_COTA_JANELA_H={horas}: a limpeza apaga consumo com "
              f"mais de {db.PRAZO_DO_CONSUMO_S // 3600} h, entao a janela "
              f"efetiva continua sendo de {db.PRAZO_DO_CONSUMO_S // 3600} h.")
    return segundos


def _bytes_do_plano(mb: int) -> int:
    """Os MB do plano em bytes, nunca acima do teto técnico do servidor.

    `0` é "sem limite" em toda chave de cota, e aqui não pode ser diferente:
    "sem teto de plano" é o teto técnico, e não teto zero. Fazendo o `min` cru,
    `PDFTODXF_COTA_MB=0` recusava **todo** envio com "O arquivo passa de 0 MB.".

    O teto técnico manda nos dois sentidos: a chave é do plano, o teto é do
    servidor, e deixar a chave passar por cima abriria um caminho de derrubar o
    site por configuração.
    """
    if mb == 0:
        return limits.TETO_PDF_BYTES
    return min(mb * 1024 * 1024, limits.TETO_PDF_BYTES)


def limites(ident) -> dict:
    """Os tetos do plano de quem está pedindo.

    Conta sem o endereço confirmado tem cota de visitante — é o que faz a
    confirmação valer alguma coisa.
    """
    if ident.tipo == "logado" and ident.confirmado:
        return {
            "arquivos": _chave("arquivos_logado"),
            "downloads": _chave("downloads_logado"),
            "bytes": _bytes_do_plano(_chave("mb_logado")),
        }
    return {
        "arquivos": _chave("arquivos"),
        "downloads": _chave("downloads"),
        "bytes": _bytes_do_plano(_chave("mb")),
    }


def _teto(ident, tipo: str, balde) -> int:
    base = limites(ident)["arquivos" if tipo == "arquivo" else "downloads"]
    return 0 if base == 0 else base * balde.folga


def _contar(con, balde: str, tipo: str, desde: float) -> int:
    # `estado <> 'solto'`: linha solta não ocupa vaga — ela já foi devolvida, e
    # nada mais a promove. Fica no banco como rastro da tentativa.
    linha = con.execute(
        "SELECT count(*) AS n FROM consumo "
        "WHERE balde = ? AND tipo = ? AND quando > ? AND estado <> 'solto'",
        (balde, tipo, desde)).fetchone()
    return int(linha["n"])


def _libera_em(con, balde: str, tipo: str, desde: float) -> float | None:
    """Quando abre a próxima vaga: a linha mais antiga da janela + a janela."""
    linha = con.execute(
        "SELECT min(quando) AS q FROM consumo "
        "WHERE balde = ? AND tipo = ? AND quando > ? AND estado <> 'solto'",
        (balde, tipo, desde)).fetchone()
    return None if linha["q"] is None else float(linha["q"]) + janela_s()


def _consumir(ident, tipo: str, referencia: str, estado: str,
              agora: float | None) -> None:
    if tipo not in TIPOS:
        # Um typo do chamador (`"arquivos"`) pegaria o teto errado e ainda
        # abriria um namespace de balde vazio: passe livre silencioso.
        raise ValueError(f"tipo desconhecido: {tipo!r}")
    agora = time.time() if agora is None else agora
    desde = agora - janela_s()
    con = db.conexao()

    # `BEGIN IMMEDIATE`: contar e inserir têm de ser um passo só. Sem isso dois
    # envios simultâneos do mesmo visitante contam 4 cada um e gravam os dois,
    # e a sexta vaga aparece do nada.
    con.execute("BEGIN IMMEDIATE")
    try:
        # A guarda de repetição é pelo **balde identificador** — o primeiro da
        # tupla, que `identidade.resolver` garante ser o `cookie:` do
        # visitante e do logado **sem confirmar**, e o `usuario:` só do
        # logado **confirmado**. Ela responde "esta identidade já pagou por
        # esta referência?": se já pagou, repetir não custa de novo (clique
        # duplicado e reenvio saem de graça); se não pagou, paga em **todos**
        # os baldes dela.
        #
        # Perguntar balde a balde seria pior de duas formas. Quem recebesse o
        # link de um trabalho alheio baixaria de graça a combinação que outro
        # pagou — `job_id` é um uuid e as rotas de job não são presas à
        # identidade. E, pior, o balde do IP nunca passaria de uma linha por
        # referência: o teto folgado do IP existe justamente para contar a
        # repetição de quem limpa o cookie, e ele não conta nada se cada
        # referência só pode aparecer ali uma vez.
        #
        # `estado <> 'solto'`: só linha que ocupa vaga vale como já paga. Uma
        # referência solta e cobrada de novo tem de cobrar de verdade.
        identificador = ident.baldes[0].chave if ident.baldes else None
        if identificador is not None and con.execute(
                "SELECT 1 FROM consumo WHERE referencia = ? AND tipo = ? "
                "AND balde = ? AND estado <> 'solto' LIMIT 1",
                (referencia, tipo, identificador)).fetchone() is not None:
            con.execute("COMMIT")
            return

        # Varre **todos** os baldes antes de decidir: só há vaga quando todos
        # têm vaga, então quem manda no `libera_em` é o que libera por último.
        # Sair no primeiro cheio mandaria o usuário voltar cedo demais, para
        # levar a mesma recusa.
        libera: float | None = None
        cheio = False
        for balde in ident.baldes:
            teto = _teto(ident, tipo, balde)
            if teto == 0:
                continue
            if _contar(con, balde.chave, tipo, desde) >= teto:
                cheio = True
                quando = _libera_em(con, balde.chave, tipo, desde)
                if quando is not None and (libera is None or quando > libera):
                    libera = quando
        if cheio:
            con.execute("ROLLBACK")
            # Qual balde estourou não sai daqui: dizer isso conta a quem
            # tenta burlar exatamente o que ele precisa saber.
            raise SemVaga(tipo, libera)

        con.executemany(
            "INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
            "VALUES (?, ?, ?, ?, ?)",
            [(b.chave, tipo, estado, agora, referencia) for b in ident.baldes])
        con.execute("COMMIT")
    except SemVaga:
        raise
    except Exception:
        con.execute("ROLLBACK")
        raise


def reservar(ident, tipo: str, referencia: str, agora=None) -> None:
    """Guarda a vaga. Levanta `SemVaga` se não couber."""
    _consumir(ident, tipo, referencia, "reservado", agora)


def cobrar(ident, tipo: str, referencia: str, agora=None) -> None:
    """Consome de vez, sem passar por reserva. Levanta `SemVaga` se não couber."""
    _consumir(ident, tipo, referencia, "confirmado", agora)


def confirmar(referencia: str) -> None:
    """Promove as reservas daquela referência. Uma vez confirmado, nada solta.

    **Só `'reservado'` sobe.** Linha solta fica solta: soltar já devolveu a
    vaga, e a tentativa seguinte grava reserva nova. Promover a solta junto
    cobraria as duas levas por uma entrega só — refazer uma exportação que
    estourou queimava duas vagas — e, pior, a referência de download é
    `job_id:chave`, sem identidade dentro: a confirmação de um visitante
    promoveria a linha solta de outro, que pagaria por um DXF que não recebeu.
    """
    con = db.conexao()
    con.execute("UPDATE consumo SET estado = 'confirmado' "
                "WHERE referencia = ? AND estado = 'reservado'",
                (referencia,))
    con.commit()


def soltar(referencia: str) -> None:
    """Devolve as vagas ainda reservadas. Não mexe no que já foi confirmado.

    Marca, não apaga: a linha fica como rastro daquela tentativa, e é ela que
    faz `cobrar` sobre a mesma referência cobrar de verdade em vez de a guarda
    de repetição achar que já foi paga.
    """
    con = db.conexao()
    con.execute("UPDATE consumo SET estado = 'solto' "
                "WHERE referencia = ? AND estado = 'reservado'", (referencia,))
    con.commit()


def restante(ident, tipo: str, agora=None) -> tuple[int | None, float | None]:
    """`(quantas vagas restam, quando libera a próxima)`.

    `(None, None)` quando o tipo está sem limite — e não um número grande, que
    a tela mostraria como se fosse cota. O balde mais apertado é o que manda,
    porque é ele que vai recusar; e entre os cheios manda o que libera por
    último, porque só há vaga quando todos tiverem vaga.
    """
    if tipo not in TIPOS:
        raise ValueError(f"tipo desconhecido: {tipo!r}")
    agora = time.time() if agora is None else agora
    desde = agora - janela_s()
    con = db.conexao()

    sobra: int | None = None
    libera: float | None = None
    for balde in ident.baldes:
        teto = _teto(ident, tipo, balde)
        if teto == 0:
            continue
        livre = max(0, teto - _contar(con, balde.chave, tipo, desde))
        sobra = livre if sobra is None else min(sobra, livre)
        if livre == 0:
            quando = _libera_em(con, balde.chave, tipo, desde)
            if quando is not None and (libera is None or quando > libera):
                libera = quando
    return sobra, libera
