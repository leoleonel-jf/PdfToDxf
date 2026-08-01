"""Janela Tkinter: visualiza o PDF, calibra a escala por 2 pontos e exporta DXF."""

from __future__ import annotations

import math
import os
import queue
import tempfile
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import fitz
from PIL import Image, ImageTk

from .calibration import scale_from_plot_scale, scale_from_two_points
from .dxf_writer import export_dxf as run_export
from .export_dialog import ExportDialog, PreviewRenderer
from .extractor import extract_page

ZOOM_STEP = 1.2
ZOOM_MIN = 0.05
ZOOM_MAX = 40.0
MARKER_COLOR = "#e53935"


class App(tk.Tk):
    def __init__(self, pdf_path: str | None = None):
        super().__init__()
        self.title("PdfToDxf — plantas PDF → DXF em escala real")
        self.geometry("1200x800")

        self.doc: fitz.Document | None = None
        self.pdf_path: str | None = None
        self.page_index = 0
        self.zoom = 1.0          # pixels por pt de papel
        self.ox = 0.0            # posição na tela da origem (0,0) da página
        self.oy = 0.0
        self._photo = None       # referência viva da imagem renderizada
        self._drag_start: tuple[float, float] | None = None
        self._render_job: str | None = None

        self.calibrating = False
        self.cal_points: list[tuple[float, float]] = []  # coords PDF (y p/ baixo)
        self.scale: float | None = None
        self.unit = "m"
        self.scale_desc = "sem escala"

        self.extraction = None           # ExtractionResult da página atual
        self.export_dialog = None
        self._preview_entities = None    # prévia ativa (lista filtrada) ou None
        self._preview_token = 0
        self._bg_item = None    # id da imagem de fundo no canvas (PDF ou prévia)
        self._bg_meta = None    # (x0, y0, zoom) da prévia exibida; None se for o PDF

        # fila thread-safe para atualizar a UI a partir de threads de trabalho
        self._ui_queue: queue.Queue = queue.Queue()
        self.after(50, self._poll_ui)

        self._build_ui()
        if pdf_path:
            self.after(100, lambda: self.open_pdf(pdf_path))

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        bar = ttk.Frame(self, padding=4)
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="Abrir PDF…", command=self.open_pdf).pack(side=tk.LEFT, padx=2)

        ttk.Label(bar, text="Página:").pack(side=tk.LEFT, padx=(12, 2))
        self.page_var = tk.IntVar(value=1)
        self.page_spin = ttk.Spinbox(bar, from_=1, to=1, width=4,
                                     textvariable=self.page_var,
                                     command=self._on_page_change, state="disabled")
        self.page_spin.pack(side=tk.LEFT)
        self.page_total = ttk.Label(bar, text="/ 0")
        self.page_total.pack(side=tk.LEFT, padx=(2, 12))

        self.cal_btn = ttk.Button(bar, text="Calibrar (2 pontos)",
                                  command=self.start_calibration, state="disabled")
        self.cal_btn.pack(side=tk.LEFT, padx=2)
        self.scale_btn = ttk.Button(bar, text="Escala 1:N…",
                                    command=self.ask_plot_scale, state="disabled")
        self.scale_btn.pack(side=tk.LEFT, padx=2)
        self.export_btn = ttk.Button(bar, text="Exportar DXF…",
                                     command=self.export_dxf, state="disabled")
        self.export_btn.pack(side=tk.LEFT, padx=12)

        ttk.Button(bar, text="Ajustar à janela", command=self.fit_page).pack(side=tk.LEFT, padx=2)

        self.canvas = tk.Canvas(self, bg="#4a4a4a", highlightthickness=0, cursor="fleur")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.status = ttk.Label(self, text="Abra um PDF vetorial plotado do AutoCAD.",
                                padding=4, anchor="w")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)          # Windows
        self.canvas.bind("<Configure>", lambda e: self._schedule_render())
        self.bind("<Escape>", lambda e: self.cancel_calibration())

    def set_status(self, text: str) -> None:
        self.status.config(text=f"{text}    |    Escala: {self.scale_desc}")

    def ui(self, fn) -> None:
        """Agenda `fn` para rodar na thread da UI (seguro de qualquer thread)."""
        self._ui_queue.put(fn)

    def _poll_ui(self) -> None:
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except tk.TclError:
                    pass  # janela/diálogo já fechado
        except queue.Empty:
            pass
        self.after(50, self._poll_ui)

    # ------------------------------------------------------------- arquivo
    def open_pdf(self, path: str | None = None) -> None:
        if path is None:
            path = filedialog.askopenfilename(
                title="Abrir planta em PDF",
                filetypes=[("Arquivos PDF", "*.pdf"), ("Todos", "*.*")])
            if not path:
                return
        try:
            doc = fitz.open(path)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o PDF:\n{e}")
            return
        if self.doc:
            self.doc.close()
        self.doc = doc
        self.pdf_path = path
        self.page_index = 0
        self.scale = None
        self.scale_desc = "sem escala"
        self.cal_points.clear()
        self.calibrating = False
        self._reset_extraction()

        n = len(doc)
        self.page_spin.config(from_=1, to=n, state="normal")
        self.page_var.set(1)
        self.page_total.config(text=f"/ {n}")
        for b in (self.cal_btn, self.scale_btn, self.export_btn):
            b.config(state="normal")
        self.title(f"PdfToDxf — {os.path.basename(path)}")
        self.fit_page()
        self.set_status(f"{os.path.basename(path)} aberto ({n} página(s)). "
                        "Calibre a escala antes de exportar.")

    def _on_page_change(self) -> None:
        if not self.doc:
            return
        idx = self.page_var.get() - 1
        if 0 <= idx < len(self.doc) and idx != self.page_index:
            self.page_index = idx
            self.cal_points.clear()
            self._reset_extraction()
            self.fit_page()

    def _reset_extraction(self) -> None:
        self.extraction = None
        self._preview_entities = None
        if self.export_dialog is not None:
            try:
                self.export_dialog.destroy()
            except tk.TclError:
                pass
            self.export_dialog = None

    @property
    def page(self) -> fitz.Page:
        return self.doc[self.page_index]

    # --------------------------------------------------------- visualização
    def fit_page(self) -> None:
        if not self.doc:
            return
        self.update_idletasks()
        cw = max(self.canvas.winfo_width(), 50)
        ch = max(self.canvas.winfo_height(), 50)
        r = self.page.rect
        self.zoom = min(cw / r.width, ch / r.height) * 0.95
        self.ox = (cw - r.width * self.zoom) / 2
        self.oy = (ch - r.height * self.zoom) / 2
        self._render()

    def _schedule_render(self) -> None:
        if self._render_job:
            self.after_cancel(self._render_job)
        self._render_job = self.after(40, self._render)

    def _render(self) -> None:
        self._render_job = None
        if not self.doc:
            return
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        r = self.page.rect
        # região da página visível na janela (coords PDF)
        x0 = max(r.x0, (0 - self.ox) / self.zoom)
        y0 = max(r.y0, (0 - self.oy) / self.zoom)
        x1 = min(r.x1, (cw - self.ox) / self.zoom)
        y1 = min(r.y1, (ch - self.oy) / self.zoom)
        if x1 <= x0 or y1 <= y0:
            self._clear_canvas()
            return
        if self._preview_entities is not None:
            # não limpa o canvas aqui: a imagem atual continua visível até a
            # nova ficar pronta (evita o "piscar" branco durante o desenho)
            self._render_preview((x0, y0, x1, y1))
            return
        self._clear_canvas()
        clip = fitz.Rect(x0, y0, x1, y1)
        pix = self.page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), clip=clip)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        self._photo = ImageTk.PhotoImage(img)
        self._bg_item = self.canvas.create_image(
            x0 * self.zoom + self.ox, y0 * self.zoom + self.oy,
            image=self._photo, anchor="nw")
        self._bg_meta = None
        self._draw_markers()

    def _clear_canvas(self) -> None:
        """Limpa o canvas invalidando a referência da imagem de fundo."""
        self.canvas.delete("all")
        self._bg_item = None
        self._bg_meta = None

    # ------------------------------------------------------------ prévia
    def set_preview(self, entities) -> None:
        """Chamado pelo diálogo de exportação (de qualquer thread)."""
        self._preview_entities = entities
        self.ui(self._schedule_render)

    def _render_preview(self, clip) -> None:
        x0, y0, x1, y1 = clip
        zoom = self.zoom
        size = (max(1, int((x1 - x0) * zoom)), max(1, int((y1 - y0) * zoom)))
        entities = self._preview_entities
        renderer = PreviewRenderer(self.page.rect.height)
        self._preview_token += 1
        token = self._preview_token

        # enquanto a nova imagem não fica pronta, reposiciona a antiga para
        # acompanhar o pan (no mesmo zoom ela continua alinhada ao desenho)
        if self._bg_item is not None and self._bg_meta is not None:
            px, py, pzoom = self._bg_meta
            if abs(pzoom - zoom) < 1e-9:
                self.canvas.coords(self._bg_item,
                                   px * zoom + self.ox, py * zoom + self.oy)
                self._draw_markers()
        self.set_status("Prévia: desenhando…")

        def work():
            img = renderer.render(entities, clip, zoom, size)
            if token == self._preview_token:
                self.ui(lambda: self._show_preview(img, x0, y0, zoom))

        threading.Thread(target=work, daemon=True).start()

    def _show_preview(self, img, x0, y0, zoom) -> None:
        if self._preview_entities is None:
            return
        # troca atômica: cria a nova imagem e só então apaga a anterior
        photo = ImageTk.PhotoImage(img)
        item = self.canvas.create_image(x0 * zoom + self.ox, y0 * zoom + self.oy,
                                        image=photo, anchor="nw")
        if self._bg_item is not None:
            self.canvas.delete(self._bg_item)
        self._photo = photo          # mantém a referência viva
        self._bg_item = item
        self._bg_meta = (x0, y0, zoom)
        self._draw_markers()
        n = len(self._preview_entities)
        self.set_status(f"Prévia: {n:,} entidades exibidas".replace(",", "."))

    def _to_pdf(self, sx: float, sy: float) -> tuple[float, float]:
        return ((sx - self.ox) / self.zoom, (sy - self.oy) / self.zoom)

    def _to_screen(self, px: float, py: float) -> tuple[float, float]:
        return (px * self.zoom + self.ox, py * self.zoom + self.oy)

    def _draw_markers(self) -> None:
        self.canvas.delete("marker")
        pts = [self._to_screen(*p) for p in self.cal_points]
        for x, y in pts:
            self.canvas.create_line(x - 8, y, x + 8, y, fill=MARKER_COLOR,
                                    width=2, tags="marker")
            self.canvas.create_line(x, y - 8, x, y + 8, fill=MARKER_COLOR,
                                    width=2, tags="marker")
        if len(pts) == 2:
            self.canvas.create_line(*pts[0], *pts[1], fill=MARKER_COLOR,
                                    width=1, dash=(4, 3), tags="marker")

    # ------------------------------------------------------- pan e zoom
    def _on_press(self, ev) -> None:
        if self.calibrating:
            self._add_cal_point(ev.x, ev.y)
        else:
            self._drag_start = (ev.x, ev.y)

    def _on_drag(self, ev) -> None:
        if self._drag_start:
            dx = ev.x - self._drag_start[0]
            dy = ev.y - self._drag_start[1]
            self._drag_start = (ev.x, ev.y)
            self.ox += dx
            self.oy += dy
            self._schedule_render()

    def _on_release(self, _ev) -> None:
        self._drag_start = None

    def _on_wheel(self, ev) -> None:
        if not self.doc:
            return
        factor = ZOOM_STEP if ev.delta > 0 else 1 / ZOOM_STEP
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * factor))
        factor = new_zoom / self.zoom
        if abs(factor - 1.0) < 1e-9:
            return
        # zoom ancorado no cursor
        self.ox = ev.x - (ev.x - self.ox) * factor
        self.oy = ev.y - (ev.y - self.oy) * factor
        self.zoom = new_zoom
        self._schedule_render()

    # ------------------------------------------------------- calibração
    def start_calibration(self) -> None:
        if not self.doc:
            return
        self.calibrating = True
        self.cal_points.clear()
        self.canvas.config(cursor="crosshair")
        self.set_status("Calibração: clique no 1º ponto da medida conhecida "
                        "(use o zoom para precisão; Esc cancela).")
        self._draw_markers()

    def cancel_calibration(self) -> None:
        if self.calibrating:
            self.calibrating = False
            self.cal_points.clear()
            self.canvas.config(cursor="fleur")
            self.set_status("Calibração cancelada.")
            self._draw_markers()

    def _add_cal_point(self, sx: float, sy: float) -> None:
        self.cal_points.append(self._to_pdf(sx, sy))
        self._draw_markers()
        if len(self.cal_points) == 1:
            self.set_status("Calibração: agora clique no 2º ponto.")
            return
        self.calibrating = False
        self.canvas.config(cursor="fleur")
        self._ask_real_distance()

    def _ask_real_distance(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Medida real")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        frm = ttk.Frame(dlg, padding=12)
        frm.pack()
        ttk.Label(frm, text="Qual é a medida real entre os dois pontos?").grid(
            row=0, column=0, columnspan=2, pady=(0, 8))
        val_var = tk.StringVar()
        unit_var = tk.StringVar(value=self.unit)
        ent = ttk.Entry(frm, textvariable=val_var, width=12)
        ent.grid(row=1, column=0, sticky="e", padx=(0, 6))
        ttk.Combobox(frm, textvariable=unit_var, values=("m", "cm", "mm"),
                     width=5, state="readonly").grid(row=1, column=1, sticky="w")

        def ok(_ev=None):
            raw = val_var.get().strip().replace(",", ".")
            try:
                dist = float(raw)
                scale = scale_from_two_points(self.cal_points[0],
                                              self.cal_points[1], dist)
            except ValueError as e:
                messagebox.showerror("Valor inválido", str(e) if str(e) else
                                     f"Não entendi a medida: {raw!r}", parent=dlg)
                return
            self.scale = scale
            self.unit = unit_var.get()
            paper_pt = math.hypot(
                self.cal_points[1][0] - self.cal_points[0][0],
                self.cal_points[1][1] - self.cal_points[0][1])
            paper_mm = paper_pt * 25.4 / 72
            ratio = dist * {"m": 1000, "cm": 10, "mm": 1}[self.unit] / paper_mm
            self.scale_desc = (f"calibrada — {dist:g} {self.unit} "
                               f"(≈ 1:{ratio:.0f})")
            dlg.destroy()
            self.set_status("Escala calibrada. Pode exportar o DXF.")

        def cancel():
            dlg.destroy()
            self.cal_points.clear()
            self._draw_markers()
            self.set_status("Calibração cancelada.")

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btns, text="OK", command=ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=cancel).pack(side=tk.LEFT, padx=4)
        ent.bind("<Return>", ok)
        ent.focus_set()
        dlg.protocol("WM_DELETE_WINDOW", cancel)

    def ask_plot_scale(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Escala de plotagem")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        frm = ttk.Frame(dlg, padding=12)
        frm.pack()
        ttk.Label(frm, text="Escala de plotagem do PDF (1:N):").grid(
            row=0, column=0, columnspan=3, pady=(0, 8))
        ttk.Label(frm, text="1 :").grid(row=1, column=0, sticky="e")
        n_var = tk.StringVar(value="50")
        unit_var = tk.StringVar(value=self.unit)
        ent = ttk.Entry(frm, textvariable=n_var, width=8)
        ent.grid(row=1, column=1, padx=4)
        ttk.Combobox(frm, textvariable=unit_var, values=("m", "cm", "mm"),
                     width=5, state="readonly").grid(row=1, column=2)

        def ok(_ev=None):
            try:
                ratio = float(n_var.get().strip().replace(",", "."))
                scale = scale_from_plot_scale(ratio, unit_var.get())
            except ValueError as e:
                messagebox.showerror("Valor inválido", str(e), parent=dlg)
                return
            self.scale = scale
            self.unit = unit_var.get()
            self.scale_desc = f"1:{ratio:g} (informada)"
            dlg.destroy()
            self.set_status("Escala definida. Atenção: se o PDF foi plotado com "
                            "'fit to page', prefira calibrar por 2 pontos.")

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=3, pady=(10, 0))
        ttk.Button(btns, text="OK", command=ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
        ent.bind("<Return>", ok)
        ent.focus_set()

    # --------------------------------------------------------- exportação
    def export_dxf(self) -> None:
        """Abre o diálogo de opções (extrai a geometria antes, se preciso)."""
        if not self.doc or not self.pdf_path:
            return
        if self.export_dialog is not None:
            try:
                self.export_dialog.lift()
                return
            except tk.TclError:
                self.export_dialog = None
        if self.scale is None:
            if not messagebox.askyesno(
                    "Sem escala",
                    "Nenhuma escala foi definida — o DXF sairá em milímetros de "
                    "papel.\n\nContinuar mesmo assim?"):
                return
        if self.extraction is not None:
            self._open_export_dialog()
            return
        self.export_btn.config(state="disabled")
        self.set_status("Analisando a geometria do PDF…")
        pdf_path, page_index = self.pdf_path, self.page_index

        def work():
            try:
                result = extract_page(pdf_path, page_number=page_index)
            except Exception as e:
                tb = traceback.format_exc()
                self.ui(lambda: self._export_failed(e, tb))
                return
            self.ui(lambda: self._extraction_ready(result))

        threading.Thread(target=work, daemon=True).start()

    def _extraction_ready(self, result) -> None:
        self.extraction = result
        self.export_btn.config(state="normal")
        n = len(result.entities)
        self.set_status(f"Geometria analisada: {n:,} entidades.".replace(",", "."))
        self._open_export_dialog()

    def _open_export_dialog(self) -> None:
        self.export_dialog = ExportDialog(self, self.extraction,
                                          on_export=self._do_export)

    def _do_export(self, opts) -> None:
        base = os.path.splitext(os.path.basename(self.pdf_path))[0]
        out = filedialog.asksaveasfilename(
            title="Salvar DXF",
            defaultextension=".dxf",
            initialfile=f"{base}.dxf",
            filetypes=[("Arquivo DXF", "*.dxf")],
            parent=self.export_dialog or self)
        if not out:
            return
        if self.export_dialog is not None:
            self.export_dialog.btn_export.config(state="disabled")
        self.set_status("Convertendo… (arquivos grandes levam alguns minutos)")
        result = self.extraction
        scale = self.scale or (25.4 / 72.0)  # sem escala: mm de papel
        unit = self.unit if self.scale else "mm"

        def work():
            try:
                counts = run_export(result, out, scale=scale, unit=unit, opts=opts)
            except Exception as e:
                tb = traceback.format_exc()
                self.ui(lambda: self._export_failed(e, tb))
                return
            size_mb = os.path.getsize(out) / 1e6
            self.ui(lambda: self._export_done(out, counts, size_mb, unit))

        threading.Thread(target=work, daemon=True).start()

    def _export_done(self, out, counts, size_mb, unit) -> None:
        if self.export_dialog is not None:
            try:
                self.export_dialog.btn_export.config(state="normal")
            except tk.TclError:
                pass
        resumo = ", ".join(f"{v:,} {k}".replace(",", ".")
                           for k, v in sorted(counts.items()))
        self.set_status(f"DXF salvo: {os.path.basename(out)} ({size_mb:.1f} MB)")
        messagebox.showinfo(
            "Concluído",
            f"DXF gerado com sucesso:\n{out}\n\nTamanho: {size_mb:.1f} MB\n"
            f"Entidades: {resumo}\nUnidade: {unit}")

    def _export_failed(self, e: Exception, tb: str = "") -> None:
        self.export_btn.config(state="normal")
        if self.export_dialog is not None:
            try:
                self.export_dialog.btn_export.config(state="normal")
            except tk.TclError:
                pass
        log_path = os.path.join(tempfile.gettempdir(), "pdftodxf_erro.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"PDF: {self.pdf_path}\npágina: {self.page_index + 1}\n\n")
            f.write(tb or traceback.format_exc())
        messagebox.showerror("Erro na conversão",
                             f"{e}\n\nDetalhes gravados em:\n{log_path}")
        self.set_status("Falha na conversão.")


def run(pdf_path: str | None = None) -> None:
    App(pdf_path).mainloop()
