"""Leitura tolerante de números digitados por gente.

O usuário deste programa é brasileiro e digita "3,50". O Python só entende
"3.50". Entre os dois há mais coisa do que um `replace`: milhar, espaço colado
no número, a unidade digitada junto por engano, e — o mais traiçoeiro — os
textos que o `float()` aceita mas não são medida nenhuma, como "nan" e "inf".
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.numeros import ler_inteiro, ler_numero


def erro_de(texto, funcao=None) -> str:
    """Devolve a mensagem de erro, ou falha se o texto tiver sido aceito."""
    funcao = funcao or ler_numero
    try:
        valor = funcao(texto)
    except ValueError as e:
        return str(e)
    raise AssertionError(f"{texto!r} foi aceito como {valor!r}")


def test_aceita_virgula_e_ponto_como_separador_decimal():
    assert ler_numero("3,50") == 3.5
    assert ler_numero("3.50") == 3.5
    assert ler_numero("0,01") == 0.01
    assert ler_numero("50") == 50.0
    print("OK: vírgula e ponto valem a mesma coisa")


def test_aceita_espaco_em_volta_e_dentro():
    """Espaço colado acontece ao copiar de planilha ou de PDF.

    O `\\xa0` é o espaço não-quebrável que vem junto quando se copia número
    formatado do Excel ou de uma página web.
    """
    assert ler_numero("  3,5  ") == 3.5
    assert ler_numero("3 , 5") == 3.5
    assert ler_numero("1\xa0234,5") == 1234.5
    print("OK: espaço em volta e dentro do número não atrapalha")


def test_entende_o_separador_de_milhar():
    """Com os dois separadores presentes, o último é o decimal."""
    assert ler_numero("1.234,56") == 1234.56      # jeito brasileiro
    assert ler_numero("1,234.56") == 1234.56      # jeito americano
    assert ler_numero("1.234.567,8") == 1234567.8
    print("OK: milhar não vira lixo")


def test_aceita_sinal_e_notacao_cientifica():
    assert ler_numero("+3,5") == 3.5
    assert ler_numero("-2") == -2.0
    assert ler_numero("1e3") == 1000.0
    assert ler_numero("1,5e2") == 150.0
    print("OK: sinal e notação científica passam")


def test_recusa_nan_e_infinito():
    """O buraco que o `float()` sozinho deixa aberto.

    `float("nan")` não levanta erro nenhum, e `nan <= 0` é falso — então uma
    escala "nan" atravessa até a validação de positividade do núcleo e sai do
    outro lado como um DXF de coordenadas corrompidas, sem um aviso sequer.
    """
    for texto in ("nan", "NaN", "inf", "-inf", "Infinity", "1e999"):
        mensagem = erro_de(texto)
        assert "número" in mensagem.lower(), (texto, mensagem)
    print("OK: nan e infinito são recusados, não repassados")


def test_recusa_vazio_com_mensagem_que_ensina():
    mensagem = erro_de("")
    assert "digite" in mensagem.lower(), mensagem
    assert erro_de("   ") == mensagem, "só espaço é o mesmo que vazio"
    print("OK: campo vazio pede que se digite algo")


def test_recusa_lixo_mostrando_o_que_foi_digitado():
    """A mensagem tem de ser em português e citar o texto recusado.

    Antes disto, a GUI mostrava o `str()` do ValueError do Python:
    "could not convert string to float: 'abc'" — inglês, e sobre uma função
    que o usuário não sabe que existe.
    """
    mensagem = erro_de("abc")
    assert "abc" in mensagem, mensagem
    assert "convert" not in mensagem, "vazou a mensagem do Python: " + mensagem
    for texto in ("3,5,5", "1..2", "3-4", "--5", "1,2.3,4"):
        erro_de(texto)
    print("OK: lixo é recusado em português, citando o texto")


def test_explica_quando_a_unidade_vem_junto():
    """Digitar "3,50 m" é engano comum: a unidade fica na lista ao lado."""
    for texto in ("3,50 m", "3,5m", "50 mm", "2 cm"):
        mensagem = erro_de(texto)
        assert "unidade" in mensagem.lower(), (texto, mensagem)
    print("OK: unidade digitada junto ganha explicação, não erro genérico")


def test_ler_inteiro_recusa_fracao():
    assert ler_inteiro("2") == 2
    assert ler_inteiro(" 12 ") == 12
    erro_de("2,5", ler_inteiro)
    erro_de("abc", ler_inteiro)
    print("OK: ler_inteiro aceita inteiro e recusa fração")


def test_a_mensagem_diz_de_que_campo_se_trata():
    """Quem chama pode nomear o campo, para o erro não ficar solto na tela."""
    try:
        ler_numero("abc", o_que="a medida real")
    except ValueError as e:
        assert "a medida real" in str(e), str(e)
    print("OK: a mensagem nomeia o campo quando quem chama informa")


def test_o_nucleo_recusa_escala_nan_ou_infinita():
    """A última linha de defesa, para quem não passar pelo `ler_numero`.

    A web manda a escala por JSON, e `float("nan")` também sai de um
    `json.loads('NaN')`. A comparação `nan <= 0` é falsa, então a validação de
    positividade que já existia deixava passar — e o DXF saía com coordenadas
    `nan`, que nenhum CAD abre.
    """
    from pdftodxf.calibration import scale_from_plot_scale, scale_from_two_points

    for ruim in (float("nan"), float("inf"), float("-inf")):
        try:
            scale_from_plot_scale(ruim)
        except ValueError:
            pass
        else:
            raise AssertionError(f"scale_from_plot_scale aceitou {ruim}")

        try:
            scale_from_two_points((0.0, 0.0), (100.0, 0.0), ruim)
        except ValueError:
            pass
        else:
            raise AssertionError(f"scale_from_two_points aceitou {ruim}")
    print("OK: o núcleo recusa escala nan ou infinita")


if __name__ == "__main__":
    test_aceita_virgula_e_ponto_como_separador_decimal()
    test_aceita_espaco_em_volta_e_dentro()
    test_entende_o_separador_de_milhar()
    test_aceita_sinal_e_notacao_cientifica()
    test_recusa_nan_e_infinito()
    test_recusa_vazio_com_mensagem_que_ensina()
    test_recusa_lixo_mostrando_o_que_foi_digitado()
    test_explica_quando_a_unidade_vem_junto()
    test_ler_inteiro_recusa_fracao()
    test_a_mensagem_diz_de_que_campo_se_trata()
    test_o_nucleo_recusa_escala_nan_ou_infinita()
    print("Todos os testes de leitura de número passaram.")
