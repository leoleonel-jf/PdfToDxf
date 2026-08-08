"""As entradas digitadas na janela: rótulos dos botões e recusa de texto ruim.

Abre a janela de verdade, como `test_preview.py` faz. Não simula clique: chama
os mesmos métodos que os botões chamam, que é onde a decisão mora.

Todos os testes dividem **uma** janela. Criar um `Tk` por teste no mesmo
processo faz o Tcl reclamar de comandos órfãos ao destruir cada um — barulho do
arranjo de teste, não do programa, e barulho que esconde erro de verdade.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_roundtrip import make_test_pdf

from pdftodxf.extractor import extract_page
from pdftodxf.gui import App

_app = None


def _botoes(widget) -> list[str]:
    """Todos os textos de botão da janela, em qualquer profundidade."""
    achados = []
    for filho in widget.winfo_children():
        try:
            if filho.winfo_class() in ("TButton", "Button"):
                achados.append(str(filho.cget("text")))
        except Exception:
            pass
        achados.extend(_botoes(filho))
    return achados


def _app_com_planta():
    global _app
    if _app is None:
        pdf = os.path.join(tempfile.mkdtemp(), "planta.pdf")
        make_test_pdf(pdf)
        _app = App()
        _app.update()
        _app.open_pdf(pdf)
        _app.update()
        _app.extraction = extract_page(pdf)
    return _app


def _abrir_painel():
    app = _app_com_planta()
    app._open_export_dialog()
    app.update()
    return app, app.export_dialog


def test_o_painel_diz_cancelar_e_nao_fechar():
    app, dlg = _abrir_painel()
    try:
        textos = _botoes(dlg)
        assert "Cancelar" in textos, textos
        assert "Fechar" not in textos, f'ainda existe um botão "Fechar": {textos}'
        print("OK: o painel de exportação diz Cancelar")
    finally:
        dlg._close()


def test_exportar_recusa_o_minimo_invalido_em_vez_de_virar_zero():
    """O campo mal digitado não pode passar despercebido para a exportação.

    Antes, `float(...)` falhava e o valor virava 0.0 caladamente: o filtro
    simplesmente não se aplicava, e o usuário levava para o CAD um arquivo
    diferente do que pediu, sem nenhum aviso.
    """
    app, dlg = _abrir_painel()
    try:
        dlg.var_micro.set(True)

        for ruim in ("abc", "", "0,1,2", "3 mm", "-1"):
            dlg.var_micro_mm.set(ruim)
            assert dlg.erro_no_minimo(), f"{ruim!r} passou sem queixa"

        for bom in ("0,10", "0.10", "1", "2,5"):
            dlg.var_micro_mm.set(bom)
            assert dlg.erro_no_minimo() is None, bom

        # desmarcado, o campo não importa: nem se olha para o que está escrito
        dlg.var_micro.set(False)
        dlg.var_micro_mm.set("abc")
        assert dlg.erro_no_minimo() is None, "campo desligado não deve reclamar"
        print("OK: exportar recusa o mínimo inválido, e ignora o campo desligado")
    finally:
        dlg._close()


def test_a_virgula_chega_ate_as_opcoes_de_exportacao():
    app, dlg = _abrir_painel()
    try:
        dlg.var_micro.set(True)
        dlg.var_micro_mm.set("0,25")
        assert dlg.current_options().min_len_mm == 0.25
        dlg.var_micro_mm.set("0.25")
        assert dlg.current_options().min_len_mm == 0.25
        print("OK: a vírgula digitada no painel vira o número certo")
    finally:
        dlg._close()


def test_fechar_o_painel_nao_deixa_recalculo_agendado():
    """Cancelar logo depois de mexer numa opção não pode deixar lixo no Tk.

    A estimativa é recalculada com um atraso de ~350 ms. Fechando dentro dessa
    janela, o `after` disparava sobre uma janela já destruída e o Tk cuspia
    `invalid command name "..._recompute"` no console.
    """
    app, dlg = _abrir_painel()
    dlg.var_dedup.set(not dlg.var_dedup.get())
    dlg._on_change()
    agendado = dlg._debounce_job
    assert agendado, "o teste supõe um recálculo agendado"

    dlg._close()
    app.update()
    pendentes = str(app.tk.call("after", "info"))
    assert agendado not in pendentes, (
        f"o recálculo {agendado} continuou agendado depois de fechar")
    print("OK: fechar o painel cancela o recálculo pendente")


if __name__ == "__main__":
    test_o_painel_diz_cancelar_e_nao_fechar()
    test_exportar_recusa_o_minimo_invalido_em_vez_de_virar_zero()
    test_a_virgula_chega_ate_as_opcoes_de_exportacao()
    test_fechar_o_painel_nao_deixa_recalculo_agendado()
    if _app is not None:
        _app.destroy()
    print("Todos os testes de entrada da janela passaram.")
