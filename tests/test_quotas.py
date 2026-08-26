"""A cota: janela deslizante, reserva, confirmação e as chaves de configuração."""

import contextlib
import io
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from web.api import db, identidade, limits, quotas

AGORA = 1_755_000_000.0


def visitante(cookie: str, ip: str = "198.51.100.1") -> identidade.Identidade:
    return identidade.Identidade(
        tipo="visitante", usuario_id=None, confirmado=False,
        baldes=(identidade.Balde(db.marca(f"cookie:{cookie}"), 1),
                identidade.Balde(db.marca(f"ip:{ip}"), 4)),
        cookie_novo=None)


def logado(uid: int, confirmado: bool = True) -> identidade.Identidade:
    return identidade.Identidade(
        tipo="logado", usuario_id=uid, confirmado=confirmado,
        baldes=(identidade.Balde(db.marca(f"usuario:{uid}"), 1),),
        cookie_novo=None)


def limpar_tudo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def estados(referencia: str | None = None) -> dict:
    """Quantas linhas há em cada estado — o que o banco de fato guardou."""
    con = db.conexao()
    if referencia is None:
        linhas = con.execute(
            "SELECT estado, count(*) AS n FROM consumo GROUP BY estado")
    else:
        linhas = con.execute(
            "SELECT estado, count(*) AS n FROM consumo "
            "WHERE referencia = ? GROUP BY estado", (referencia,))
    return {l["estado"]: int(l["n"]) for l in linhas}


def test_visitante_envia_cinco_e_para_no_sexto():
    limpar_tudo()
    quem = visitante("c1")
    for i in range(5):
        quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
    try:
        quotas.reservar(quem, "arquivo", "job5", AGORA)
        raise AssertionError("o sexto tinha que ser recusado")
    except quotas.SemVaga as e:
        assert e.tipo == "arquivo"
        assert e.libera_em and e.libera_em > AGORA
    print("OK: visitante envia 5 arquivos e é barrado no sexto")


def test_limpar_o_cookie_nao_devolve_cota():
    """O balde do IP continua contando, e é ele que tapa o furo do cookie."""
    limpar_tudo()
    for i in range(5):
        quotas.reservar(visitante("c1"), "arquivo", f"job{i}", AGORA)
    # Cookie novo, mesmo IP: cabe, porque o IP tem folga de 4x (teto 20).
    quotas.reservar(visitante("c2"), "arquivo", "job5", AGORA)

    for i in range(6, 20):
        quotas.reservar(visitante(f"c{i}"), "arquivo", f"job{i}", AGORA)
    try:
        quotas.reservar(visitante("c-final"), "arquivo", "job20", AGORA)
        raise AssertionError("o vigésimo primeiro tinha que ser recusado")
    except quotas.SemVaga:
        pass
    print("OK: limpar o cookie não devolve cota; o IP barra no 21º")


def test_a_janela_desliza():
    limpar_tudo()
    quem = visitante("c1")
    velho = AGORA - quotas.janela_s() - 1
    for i in range(5):
        quotas.reservar(quem, "arquivo", f"job{i}", velho)
    quotas.reservar(quem, "arquivo", "novo", AGORA)
    restam, _ = quotas.restante(quem, "arquivo", AGORA)
    assert restam == 4, restam
    print("OK: a janela desliza — consumo de 2 h e 1 s atrás não conta")


def test_confirmar_e_soltar_sao_de_mao_unica():
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "arquivo", "jobA", AGORA)

    # Página ruim antes de qualquer boa: solta — e soltar de novo não muda nada.
    quotas.soltar("jobA")
    quotas.soltar("jobA")
    assert estados("jobA") == {"solto": 2}, estados("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 5

    # Boa e depois ruim: a ruim não desfaz.
    quotas.reservar(quem, "arquivo", "jobB", AGORA)
    quotas.confirmar("jobB")
    quotas.soltar("jobB")
    assert estados("jobB") == {"confirmado": 2}, "confirmado não solta"
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4

    # Confirmar de novo não duplica linha nem move o que já estava confirmado:
    # a contagem por estado é o que revela isso — o saldo sozinho não revelaria.
    quotas.confirmar("jobB")
    assert estados() == {"solto": 2, "confirmado": 2}, estados()
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4
    print("OK: confirmar e soltar são de mão única e idempotentes")


def test_confirmar_nao_promove_o_que_foi_solto():
    """Soltar devolveu a vaga; confirmar depois não pode cobrá-la de volta.

    Quem chama `soltar` só chama no fim do documento, com **nenhuma** página
    pronta e o PDF de origem já apagado: não existe confirmação para vir depois
    dela. Promover a linha solta cobraria duas levas por uma entrega só, porque
    a tentativa seguinte grava reservas novas — a guarda de repetição ignora
    `solto`.
    """
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "arquivo", "jobA", AGORA)
    quotas.soltar("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 5, "solto não ocupa vaga"

    quotas.confirmar("jobA")
    assert estados("jobA") == {"solto": 2}, estados("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 5, "solto continua solto"
    print("OK: confirmar não promove linha solta")


def test_refazer_a_exportacao_que_falhou_cobra_uma_vaga_so():
    """O caminho do `export`: reservar, soltar na falha, reservar e confirmar.

    Medido antes da correção, forçando exceção em `exportacao.gerar`: as duas
    levas viravam `confirmado` e a mesma entrega queimava duas vagas.
    """
    limpar_tudo()
    quem = visitante("c1")
    ref = "jobA:chave1"

    # Primeira tentativa: `exportacao.gerar` estoura, e o `export` solta.
    quotas.reservar(quem, "download", ref, AGORA)
    quotas.soltar(ref)
    assert estados(ref) == {"solto": 2}, estados(ref)
    assert quotas.restante(quem, "download", AGORA)[0] == 15, "a falha não cobra"

    # Segunda tentativa: a guarda de repetição ignora `solto`, então reserva de
    # novo — e só essa leva pode ser promovida.
    quotas.reservar(quem, "download", ref, AGORA)
    quotas.confirmar(ref)
    assert estados(ref) == {"solto": 2, "confirmado": 2}, estados(ref)
    assert quotas.restante(quem, "download", AGORA)[0] == 14, \
        "um DXF entregue, uma vaga queimada"
    print("OK: refazer a exportação que falhou cobra uma vaga só")


def test_a_falha_de_um_visitante_nao_e_cobrada_pela_confirmacao_de_outro():
    """A referência de download é `job_id:chave`: não tem identidade dentro.

    O visitante A estoura e solta; B gera a mesma combinação depois e confirma.
    O `UPDATE` de `confirmar` casa por `referencia`, não por balde — se ele
    promovesse linha solta, A pagaria por um DXF que só B recebeu.
    """
    limpar_tudo()
    a = visitante("c-a", ip="198.51.100.7")
    b = visitante("c-b", ip="203.0.113.7")
    ref = "jobX:chave1"

    quotas.reservar(a, "download", ref, AGORA)
    quotas.soltar(ref)
    assert quotas.restante(a, "download", AGORA)[0] == 15, "a falha de A não cobra"

    quotas.reservar(b, "download", ref, AGORA)
    quotas.confirmar(ref)

    assert estados(ref) == {"solto": 2, "confirmado": 2}, estados(ref)
    assert quotas.restante(b, "download", AGORA)[0] == 14, "B paga o que levou"
    assert quotas.restante(a, "download", AGORA)[0] == 15, \
        "A não pode pagar pelo DXF de B"
    print("OK: a falha de um visitante não é cobrada pela confirmação de outro")


def test_boa_antes_da_ruim_a_ruim_nao_desfaz():
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "arquivo", "jobB", AGORA)
    quotas.confirmar("jobB")
    quotas.soltar("jobB")
    assert estados("jobB") == {"confirmado": 2}, estados("jobB")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4
    print("OK: boa antes da ruim — a ruim não desfaz o que foi confirmado")


def test_reserva_nunca_confirmada_continua_contando():
    limpar_tudo()
    quem = visitante("c1")
    for i in range(5):
        quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
    assert estados() == {"reservado": 10}, estados()
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 0
    try:
        quotas.reservar(quem, "arquivo", "job5", AGORA)
        raise AssertionError("reserva não confirmada tinha que continuar contando")
    except quotas.SemVaga:
        pass
    print("OK: reserva nunca confirmada continua ocupando a vaga")


def test_a_mesma_referencia_nao_cobra_duas_vezes():
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "download", "jobA:chave1", AGORA)
    quotas.reservar(quem, "download", "jobA:chave1", AGORA)
    restam, _ = quotas.restante(quem, "download", AGORA)
    assert restam == 14, restam

    # Outra identidade com a mesma referência **paga**: `job_id` é um uuid e a
    # rota não é presa à identidade, então quem recebe o link de um trabalho
    # alheio não herda a combinação que o dono pagou.
    outro = visitante("c2", ip="203.0.113.9")
    quotas.reservar(outro, "download", "jobA:chave1", AGORA)
    assert quotas.restante(outro, "download", AGORA)[0] == 14, "identidade nova paga"
    assert quotas.restante(quem, "download", AGORA)[0] == 14, "o dono não paga de novo"
    print("OK: a mesma referência não cobra duas vezes, mas outra identidade paga")


def linhas_do_balde(balde: str) -> int:
    con = db.conexao()
    linha = con.execute("SELECT count(*) AS n FROM consumo WHERE balde = ?",
                        (balde,)).fetchone()
    return int(linha["n"])


def test_cookie_novo_no_mesmo_ip_paga_no_balde_do_ip():
    """A idempotência é da identidade, não do balde: o IP conta a repetição.

    Se a guarda perguntasse balde a balde, o balde do IP nunca passaria de uma
    linha por referência — e o teto folgado do IP, que é o antídoto contra
    limpar o cookie e repetir, não teria o que contar.
    """
    limpar_tudo()
    um = visitante("c1")
    dois = visitante("c2")            # cookie diferente, **mesmo IP**
    balde_ip = um.baldes[1].chave
    assert balde_ip == dois.baldes[1].chave, "o teste precisa do mesmo IP"

    quotas.reservar(um, "arquivo", "jobA", AGORA)
    quotas.reservar(um, "arquivo", "jobA", AGORA)      # repetir não cobra
    assert linhas_do_balde(balde_ip) == 1, linhas_do_balde(balde_ip)

    quotas.reservar(dois, "arquivo", "jobA", AGORA)    # outra identidade paga
    assert linhas_do_balde(balde_ip) == 2, linhas_do_balde(balde_ip)
    assert quotas.restante(um, "arquivo", AGORA)[0] == 4
    assert quotas.restante(dois, "arquivo", AGORA)[0] == 4
    print("OK: cookie novo no mesmo IP paga no balde do IP; repetir não paga")


def test_muitos_visitantes_no_mesmo_ip_esbarram_no_teto_do_ip():
    """Vinte cookies diferentes na **mesma referência** enchem o balde do IP."""
    limpar_tudo()
    for i in range(20):
        quotas.reservar(visitante(f"c{i}"), "arquivo", "jobA", AGORA)
    balde_ip = visitante("c0").baldes[1].chave
    assert linhas_do_balde(balde_ip) == 20, linhas_do_balde(balde_ip)
    try:
        quotas.reservar(visitante("c-final"), "arquivo", "jobA", AGORA)
        raise AssertionError("o vigésimo primeiro cookie tinha que ser recusado")
    except quotas.SemVaga as e:
        assert e.tipo == "arquivo"
        assert e.libera_em and e.libera_em > AGORA
    print("OK: N visitantes no mesmo IP esbarram no teto do balde do IP")


def test_cobrar_depois_de_soltar_cobra_de_verdade():
    """Linha solta não ocupa vaga, então também não vale como já paga."""
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "arquivo", "jobA", AGORA)
    quotas.soltar("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 5, "solto não ocupa vaga"

    quotas.cobrar(quem, "arquivo", "jobA", AGORA)
    assert estados("jobA") == {"solto": 2, "confirmado": 2}, estados("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4, "cobrar tem que cobrar"

    # E `reservar` sobre a mesma referência também reserva de verdade: é o que
    # faz a tentativa seguinte de uma exportação que falhou pagar a sua vaga —
    # uma, porque a leva solta fica onde está.
    limpar_tudo()
    quotas.reservar(quem, "arquivo", "jobB", AGORA)
    quotas.soltar("jobB")
    quotas.reservar(quem, "arquivo", "jobB", AGORA)
    assert estados("jobB") == {"solto": 2, "reservado": 2}, estados("jobB")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4
    print("OK: cobrar e reservar depois de soltar cobram de verdade")


def test_libera_em_ignora_a_linha_solta_mais_antiga():
    """A solta não conta na contagem **nem** na hora anunciada.

    Sem o `estado <> 'solto'` de `_libera_em`, uma linha solta mais antiga
    puxaria o `min(quando)` para trás e a tela anunciaria uma vaga cedo demais.
    """
    limpar_tudo()
    quem = logado(7)
    balde = quem.baldes[0].chave
    con = db.conexao()
    con.executemany(
        "INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
        "VALUES (?, ?, ?, ?, ?)",
        # A solta é uma hora mais velha que as que de fato ocupam vaga.
        [(balde, "arquivo", "solto", AGORA - 3600, "velho-solto")]
        + [(balde, "arquivo", "confirmado", AGORA, f"job{i}") for i in range(15)])
    con.commit()

    esperado = AGORA + quotas.janela_s()
    assert quotas.restante(quem, "arquivo", AGORA) == (0, esperado), \
        quotas.restante(quem, "arquivo", AGORA)
    try:
        quotas.reservar(quem, "arquivo", "novo", AGORA)
        raise AssertionError("com o balde cheio tinha que recusar")
    except quotas.SemVaga as e:
        assert e.libera_em == esperado, (e.libera_em, esperado)
    print("OK: libera_em ignora a linha solta mais antiga")


def test_libera_em_e_o_maior_entre_os_baldes_cheios():
    """Só há vaga quando todos os baldes tiverem vaga: manda o que libera por último."""
    limpar_tudo()
    quem = visitante("c1")
    cookie, ip = quem.baldes
    con = db.conexao()
    # Cookie cheio desde AGORA (teto 5), IP cheio desde AGORA+3600 (teto 20):
    # o cookie libera em AGORA+7200, o IP em AGORA+10800.
    con.executemany(
        "INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
        "VALUES (?, ?, ?, ?, ?)",
        [(cookie.chave, "arquivo", "confirmado", AGORA, f"c{i}")
         for i in range(5)]
        + [(ip.chave, "arquivo", "confirmado", AGORA + 3600, f"i{i}")
           for i in range(20)])
    con.commit()

    agora = AGORA + 3600
    esperado = AGORA + 3600 + quotas.janela_s()
    assert quotas.restante(quem, "arquivo", agora) == (0, esperado), \
        quotas.restante(quem, "arquivo", agora)
    try:
        quotas.reservar(quem, "arquivo", "novo", agora)
        raise AssertionError("com os dois baldes cheios tinha que recusar")
    except quotas.SemVaga as e:
        assert e.libera_em == esperado, (e.libera_em, esperado)

    # E no instante anunciado a vaga existe de verdade.
    quotas.reservar(quem, "arquivo", "novo", esperado)
    print("OK: libera_em é o maior entre os baldes cheios, e nele a vaga existe")


def test_dezesseis_ao_mesmo_tempo_passam_exatamente_cinco():
    """Contar e inserir são um passo só — sem `BEGIN IMMEDIATE` isso quebra."""
    limpar_tudo()
    quem = visitante("c-corrida")
    n = 16
    portao = threading.Barrier(n)
    passou, recusado, erros = [], [], []

    def tentar(i):
        portao.wait()
        try:
            quotas.reservar(quem, "arquivo", f"corrida{i}", AGORA)
            passou.append(i)
        except quotas.SemVaga:
            recusado.append(i)
        except Exception as e:  # noqa: BLE001 — qualquer erro é falha do teste
            erros.append(repr(e))
        finally:
            db.fechar()

    fios = [threading.Thread(target=tentar, args=(i,)) for i in range(n)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()

    assert not erros, erros
    assert len(passou) == 5, (len(passou), len(recusado))
    assert len(recusado) == n - 5, len(recusado)
    linhas = db.conexao().execute("SELECT count(*) AS n FROM consumo").fetchone()
    assert int(linhas["n"]) == 5 * len(quem.baldes), int(linhas["n"])
    print(f"OK: {n} pedidos ao mesmo tempo e exatamente 5 passam")


def test_downloads_do_visitante_param_no_decimo_sexto():
    limpar_tudo()
    quem = visitante("c1")
    for i in range(15):
        quotas.cobrar(quem, "download", f"jobA:{i}", AGORA)
    try:
        quotas.cobrar(quem, "download", "jobA:16", AGORA)
        raise AssertionError("o décimo sexto tinha que ser recusado")
    except quotas.SemVaga as e:
        assert e.tipo == "download"
    print("OK: visitante baixa 15 combinações inéditas e para na décima sexta")


def test_logado_tem_o_triplo():
    limpar_tudo()
    quem = logado(1)
    assert quotas.limites(quem)["arquivos"] == 15
    assert quotas.limites(quem)["downloads"] == 45
    for i in range(15):
        quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
    try:
        quotas.reservar(quem, "arquivo", "job15", AGORA)
        raise AssertionError("o décimo sexto tinha que ser recusado")
    except quotas.SemVaga:
        pass
    print("OK: logado tem o triplo da cota do visitante")


def test_chave_em_zero_nao_limita_e_ausente_cai_no_padrao():
    limpar_tudo()
    quem = visitante("c1")
    os.environ["PDFTODXF_COTA_ARQUIVOS"] = "0"
    try:
        for i in range(30):
            quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
        restam, libera = quotas.restante(quem, "arquivo", AGORA)
        assert restam is None and libera is None, (restam, libera)
    finally:
        del os.environ["PDFTODXF_COTA_ARQUIVOS"]
    assert quotas.limites(visitante("c9"))["arquivos"] == 5, "ausente cai no padrão"
    print("OK: chave em 0 não limita; chave ausente cai no padrão")


def test_chave_negativa_cai_no_padrao():
    """`-1` é "sem limite" em outros sistemas; aqui é lixo, e lixo vira padrão."""
    limpar_tudo()
    for cru in ("-1", "-999"):
        os.environ["PDFTODXF_COTA_ARQUIVOS"] = cru
        try:
            assert quotas.limites(visitante("c1"))["arquivos"] == 5, cru
            quem = visitante(f"neg{cru}")
            for i in range(5):
                quotas.reservar(quem, "arquivo", f"neg{cru}-{i}", AGORA)
            try:
                quotas.reservar(quem, "arquivo", f"neg{cru}-5", AGORA)
                raise AssertionError(f"{cru} não podia abrir a cota inteira")
            except quotas.SemVaga:
                pass
        finally:
            del os.environ["PDFTODXF_COTA_ARQUIVOS"]
    print("OK: chave negativa cai no padrão, não em sem-limite")


def test_janela_em_zero_cai_no_padrao():
    os.environ["PDFTODXF_COTA_JANELA_H"] = "0"
    try:
        assert quotas.janela_s() == 2 * 60 * 60, quotas.janela_s()
    finally:
        del os.environ["PDFTODXF_COTA_JANELA_H"]
    print("OK: janela em 0 cai no padrão de 2 h, não vira janela infinita")


def test_janela_maior_que_a_limpeza_avisa_uma_vez():
    os.environ["PDFTODXF_COTA_JANELA_H"] = "48"
    quotas._avisou_janela = None
    saida = io.StringIO()
    try:
        with contextlib.redirect_stdout(saida):
            assert quotas.janela_s() == 48 * 60 * 60
            quotas.janela_s()
            quotas.janela_s()
    finally:
        del os.environ["PDFTODXF_COTA_JANELA_H"]
        quotas._avisou_janela = None
    texto = saida.getvalue()
    assert texto.count("PDFTODXF_COTA_JANELA_H") == 1, texto

    calada = io.StringIO()
    with contextlib.redirect_stdout(calada):
        quotas.janela_s()
    assert calada.getvalue() == "", calada.getvalue()
    print("OK: janela acima do prazo da limpeza avisa, e avisa uma vez só")


def test_o_aviso_da_janela_rearma_quando_o_valor_muda():
    """Avisou de 48; se alguém puser 72, o valor novo não pode passar calado."""
    quotas._avisou_janela = None
    saida = io.StringIO()
    try:
        with contextlib.redirect_stdout(saida):
            for horas in ("48", "48", "72", "72"):
                os.environ["PDFTODXF_COTA_JANELA_H"] = horas
                quotas.janela_s()
    finally:
        del os.environ["PDFTODXF_COTA_JANELA_H"]
        quotas._avisou_janela = None
    texto = saida.getvalue()
    assert texto.count("PDFTODXF_COTA_JANELA_H") == 2, texto
    assert "=48" in texto and "=72" in texto, texto
    print("OK: o aviso da janela rearma quando o valor da chave muda")


def test_tipo_desconhecido_e_erro():
    """Um `"arquivos"` no plural pegaria o teto errado e abriria um balde vazio."""
    quem = visitante("c1")
    tentativas = (
        lambda: quotas.reservar(quem, "arquivos", "jobX", AGORA),
        lambda: quotas.cobrar(quem, "downloads", "jobX", AGORA),
        lambda: quotas.restante(quem, "arquivos", AGORA),
    )
    for tentar in tentativas:
        try:
            tentar()
            raise AssertionError("tipo fora da lista tinha que levantar ValueError")
        except ValueError:
            pass
    print(f"OK: tipo fora de {quotas.TIPOS} levanta ValueError")


def test_teto_de_mb_do_logado_e_truncado_no_teto_tecnico():
    os.environ["PDFTODXF_COTA_MB_LOGADO"] = "500"
    try:
        assert quotas.limites(logado(1))["bytes"] == limits.TETO_PDF_BYTES
    finally:
        del os.environ["PDFTODXF_COTA_MB_LOGADO"]
    assert quotas.limites(visitante("c1"))["bytes"] == 10 * 1024 * 1024
    print("OK: o teto de MB do logado nunca passa do teto técnico")


def test_mb_em_zero_vale_o_teto_tecnico():
    """`0` é "sem limite" em toda chave de cota — inclusive nesta.

    Com o `min` cru, `mb == 0` dava teto **zero**: todo envio, de qualquer
    tamanho, era recusado com "O arquivo passa de 0 MB.". "Sem teto de plano"
    é o teto técnico do servidor, que continua sendo o de cima.
    """
    for chave, quem in (("PDFTODXF_COTA_MB", visitante("c1")),
                        ("PDFTODXF_COTA_MB_LOGADO", logado(1))):
        os.environ[chave] = "0"
        try:
            assert quotas.limites(quem)["bytes"] == limits.TETO_PDF_BYTES, chave
        finally:
            del os.environ[chave]
    print("OK: MB em 0 é sem teto de plano, e vale o teto técnico")


def test_conta_sem_confirmar_tem_cota_de_visitante():
    quem = logado(3, confirmado=False)
    assert quotas.limites(quem)["arquivos"] == 5
    assert quotas.limites(quem)["bytes"] == 10 * 1024 * 1024
    print("OK: conta sem confirmar fica com a cota de visitante")


def test_teto_de_tentativa_nao_multiplica_pela_folga():
    """O teto de "tentativa" já está escrito por IP — multiplicar pela folga
    do balde configuraria 3 e destrancaria 12.

    Balde de folga 4 de propósito: é a folga que `identidade._folga()` devolve
    hoje para o balde do IP. Se a multiplicação voltar a `_teto`, a chamada
    direta já falha (o teto viraria 12), e mesmo que não falhasse a quarta
    reserva — que tinha que ser a primeira recusada — passaria, e só a décima
    terceira seria barrada.
    """
    limpar_tudo()
    quem = identidade.Identidade(
        tipo="visitante", usuario_id=None, confirmado=False,
        baldes=(identidade.Balde(db.marca("ip:198.51.100.9"), 4),),
        cookie_novo=None)
    os.environ["PDFTODXF_TENTATIVAS_POR_IP"] = "3"
    try:
        assert quotas._teto(quem, "tentativa", quem.baldes[0]) == 3, (
            "o teto de tentativa não pode sair multiplicado pela folga do "
            "balde — configurar 3 não pode destrancar 12")
        for i in range(3):
            quotas.reservar(quem, "tentativa", f"tent{i}", AGORA)
        try:
            quotas.reservar(quem, "tentativa", "tent3", AGORA)
            raise AssertionError(
                "a quarta reserva tinha que ser recusada com teto 3 — só "
                "passou porque o teto virou 12 (3 x a folga do balde)")
        except quotas.SemVaga:
            pass
    finally:
        del os.environ["PDFTODXF_TENTATIVAS_POR_IP"]
    print("OK: o teto de tentativa não multiplica pela folga do balde")


if __name__ == "__main__":
    test_visitante_envia_cinco_e_para_no_sexto()
    test_limpar_o_cookie_nao_devolve_cota()
    test_a_janela_desliza()
    test_confirmar_e_soltar_sao_de_mao_unica()
    test_confirmar_nao_promove_o_que_foi_solto()
    test_refazer_a_exportacao_que_falhou_cobra_uma_vaga_so()
    test_a_falha_de_um_visitante_nao_e_cobrada_pela_confirmacao_de_outro()
    test_boa_antes_da_ruim_a_ruim_nao_desfaz()
    test_reserva_nunca_confirmada_continua_contando()
    test_a_mesma_referencia_nao_cobra_duas_vezes()
    test_cookie_novo_no_mesmo_ip_paga_no_balde_do_ip()
    test_muitos_visitantes_no_mesmo_ip_esbarram_no_teto_do_ip()
    test_cobrar_depois_de_soltar_cobra_de_verdade()
    test_libera_em_ignora_a_linha_solta_mais_antiga()
    test_libera_em_e_o_maior_entre_os_baldes_cheios()
    test_dezesseis_ao_mesmo_tempo_passam_exatamente_cinco()
    test_downloads_do_visitante_param_no_decimo_sexto()
    test_logado_tem_o_triplo()
    test_chave_em_zero_nao_limita_e_ausente_cai_no_padrao()
    test_chave_negativa_cai_no_padrao()
    test_janela_em_zero_cai_no_padrao()
    test_janela_maior_que_a_limpeza_avisa_uma_vez()
    test_o_aviso_da_janela_rearma_quando_o_valor_muda()
    test_tipo_desconhecido_e_erro()
    test_teto_de_mb_do_logado_e_truncado_no_teto_tecnico()
    test_mb_em_zero_vale_o_teto_tecnico()
    test_conta_sem_confirmar_tem_cota_de_visitante()
    test_teto_de_tentativa_nao_multiplica_pela_folga()
    print("Todos os testes de cota passaram.")
