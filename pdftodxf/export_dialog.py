"""Diálogo de exportação com opções de compactação, estimativa de tamanho
ao vivo e prévia visual na tela principal (mostra só o que vai sobrar)."""

from __future__ import annotations

import math
import threading
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from .geometry import Arc, Bezier, Polyline, Segment, TextItem, bezier_point
from .optimize import ExportOptions, estimate_bytes

PREVIEW_DEBOUNCE_MS = 350


def _fmt_mb(nbytes: int) -> str:
    if nbytes >= 1e9:
        return f"{nbytes / 1e9:.2f} GB"
    if nbytes >= 1e6:
        return f"{nbytes / 1e6:.0f} MB"
    return f"{max(1, nbytes // 1000)} kB"


class ExportDialog(tk.Toplevel):
    """Janela não-modal de opções de exportação.

    A prévia é desenhada pela própria dialog no canvas do App: quando ativa,
    o App delega a renderização do viewport para `render_preview_async`.
    """

    def __init__(self, app, result, on_export):
        super().__init__(app)
        self.app = app
        self.result = result
        self.on_export = on_export  # callback(opts: ExportOptions)
        self.title("Exportar DXF — opções de compactação")
        self.resizable(False, True)
        self.transient(app)

        self._debounce_job = None
        self._render_token = 0
        self._layer_counts = self._count_layers()
        self._baseline = estimate_bytes(result.entities, ExportOptions())

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._on_change()

    # ------------------------------------------------------------------ UI
    def _count_layers(self):
        counts: dict[str, int] = {}
        for e in self.result.entities:
            counts[e.layer] = counts.get(e.layer, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def _build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # ---- painel de layers
        lf = ttk.LabelFrame(main, text="Layers a incluir", padding=6)
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        canvas = tk.Canvas(lf, width=290, height=320, highlightthickness=0)
        vsb = ttk.Scrollbar(lf, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.bind("<MouseWheel>",
                    lambda ev: canvas.yview_scroll(-1 if ev.delta > 0 else 1, "units"))

        self.layer_vars: dict[str, tk.BooleanVar] = {}
        for layer, n in self._layer_counts.items():
            var = tk.BooleanVar(value=True)
            self.layer_vars[layer] = var
            ttk.Checkbutton(inner, text=f"{layer}  ({n:,})".replace(",", "."),
                            variable=var, command=self._on_change).pack(anchor="w")

        btns = ttk.Frame(lf)
        btns.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        ttk.Button(btns, text="Todos", width=8,
                   command=lambda: self._set_all_layers(True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Nenhum", width=8,
                   command=lambda: self._set_all_layers(False)).pack(side=tk.LEFT, padx=2)

        # ---- opções de compactação
        of = ttk.LabelFrame(main, text="Compactação", padding=6)
        of.grid(row=0, column=1, sticky="nsew")

        self.var_join = tk.BooleanVar(value=True)
        self.var_round = tk.BooleanVar(value=True)
        self.var_dedup = tk.BooleanVar(value=True)
        self.var_fills = tk.BooleanVar(value=False)
        self.var_micro = tk.BooleanVar(value=False)
        self.var_micro_mm = tk.StringVar(value="0,10")

        def chk(text, var, tip=None):
            c = ttk.Checkbutton(of, text=text, variable=var, command=self._on_change)
            c.pack(anchor="w", pady=1)
            return c

        chk("Unir segmentos em polilinhas (sem perda)", self.var_join)
        chk("Arredondar coordenadas (sem perda prática)", self.var_round)
        chk("Remover duplicados/sobrepostos (sem perda visual)", self.var_dedup)
        chk("Remover preenchimentos — triângulos de hachura", self.var_fills)

        mf = ttk.Frame(of)
        mf.pack(anchor="w", pady=1)
        ttk.Checkbutton(mf, text="Descartar segmentos menores que",
                        variable=self.var_micro, command=self._on_change).pack(side=tk.LEFT)
        ent = ttk.Entry(mf, textvariable=self.var_micro_mm, width=6)
        ent.pack(side=tk.LEFT, padx=(4, 2))
        ent.bind("<KeyRelease>", lambda e: self._on_change())
        ttk.Label(mf, text="mm (papel)").pack(side=tk.LEFT)

        self.var_preview = tk.BooleanVar(value=True)
        ttk.Checkbutton(of, text="Prévia na tela (mostra o que vai sobrar)",
                        variable=self.var_preview,
                        command=self._on_change).pack(anchor="w", pady=(10, 1))

        # ---- estimativa
        ef = ttk.LabelFrame(of, text="Estimativa", padding=8)
        ef.pack(fill=tk.X, pady=(10, 0))
        self.lbl_entities = ttk.Label(ef, text="…")
        self.lbl_entities.pack(anchor="w")
        self.lbl_size = ttk.Label(ef, text="…", font=("TkDefaultFont", 10, "bold"))
        self.lbl_size.pack(anchor="w")
        ttk.Label(ef, text="(valores aproximados)",
                  foreground="#777").pack(anchor="w")

        bf = ttk.Frame(of)
        bf.pack(fill=tk.X, pady=(12, 0))
        self.btn_export = ttk.Button(bf, text="Exportar…", command=self._export)
        self.btn_export.pack(side=tk.RIGHT, padx=2)
        ttk.Button(bf, text="Fechar", command=self._close).pack(side=tk.RIGHT, padx=2)

    def _set_all_layers(self, value: bool):
        for var in self.layer_vars.values():
            var.set(value)
        self._on_change()

    # ------------------------------------------------------------- opções
    def current_options(self) -> ExportOptions:
        try:
            micro = float(self.var_micro_mm.get().replace(",", "."))
        except ValueError:
            micro = 0.0
        return ExportOptions(
            excluded_layers={l for l, v in self.layer_vars.items() if not v.get()},
            drop_fills=self.var_fills.get(),
            min_len_mm=micro if self.var_micro.get() else 0.0,
            dedup=self.var_dedup.get(),
            join_polylines=self.var_join.get(),
            round_coords=self.var_round.get(),
        )

    def _kept_entities(self, opts: ExportOptions):
        from .optimize import apply_filters
        return apply_filters(self.result.entities, opts)

    def _on_change(self):
        if self._debounce_job:
            self.after_cancel(self._debounce_job)
        self._debounce_job = self.after(PREVIEW_DEBOUNCE_MS, self._recompute)

    def _recompute(self):
        self._debounce_job = None
        opts = self.current_options()
        preview_on = self.var_preview.get()  # ler vars Tk só na thread da UI
        token = self._render_token = self._render_token + 1

        def work():
            kept = self._kept_entities(opts)
            est = estimate_bytes(kept, opts)
            if token != self._render_token:
                return
            self.app.ui(lambda: self._show_estimate(len(kept), est))
            self.app.set_preview(kept if preview_on else None)

        threading.Thread(target=work, daemon=True).start()

    def _show_estimate(self, n_kept: int, est: int):
        total = len(self.result.entities)
        pct = (1 - est / self._baseline) * 100 if self._baseline else 0
        self.lbl_entities.config(
            text=f"Entidades: {total:,} → {n_kept:,}".replace(",", "."))
        self.lbl_size.config(
            text=f"Tamanho: ≈ {_fmt_mb(self._baseline)} → ≈ {_fmt_mb(est)}  "
                 f"(−{pct:.0f}%)")

    # ------------------------------------------------------------- ações
    def _export(self):
        self.on_export(self.current_options())

    def _close(self):
        self._render_token += 1
        self.app.set_preview(None)
        self.destroy()


class PreviewRenderer:
    """Desenha uma lista de entidades (pts de papel, Y para cima) no viewport
    do canvas principal, no lugar do pixmap do PDF."""

    def __init__(self, page_height: float):
        self.h = page_height

    def render(self, entities, clip, zoom, size) -> Image.Image:
        """clip: (x0, y0, x1, y1) em coords PDF y-para-baixo; size: (w, h) px."""
        x0, y0, x1, y1 = clip
        w, hpx = size
        img = Image.new("RGB", (max(1, w), max(1, hpx)), "white")
        draw = ImageDraw.Draw(img)
        H = self.h

        def t(p):  # ponto y-up -> pixel do viewport
            return (p[0] * zoom - x0 * zoom, (H - p[1]) * zoom - y0 * zoom)

        # limites em y-up para descarte rápido
        ylo, yhi = H - y1, H - y0

        def vis2(a, b):
            if max(a[0], b[0]) < x0 - 1 or min(a[0], b[0]) > x1 + 1:
                return False
            if max(a[1], b[1]) < ylo - 1 or min(a[1], b[1]) > yhi + 1:
                return False
            return True

        def col(e):
            if not e.color:
                return (40, 40, 40)
            return tuple(max(0, min(255, round(c * 255))) for c in e.color)

        for e in entities:
            if isinstance(e, Segment):
                if vis2(e.p1, e.p2):
                    draw.line([t(e.p1), t(e.p2)], fill=col(e), width=1)
            elif isinstance(e, Polyline):
                pts = e.points
                bx = [p[0] for p in pts]
                by = [p[1] for p in pts]
                if not vis2((min(bx), min(by)), (max(bx), max(by))):
                    continue
                path = [t(p) for p in pts]
                if e.closed:
                    path.append(path[0])
                draw.line(path, fill=col(e), width=1)
            elif isinstance(e, Arc):
                r = e.radius
                c = e.center
                if not vis2((c[0] - r, c[1] - r), (c[0] + r, c[1] + r)):
                    continue
                sweep = (e.end_angle - e.start_angle) % 360 or 360
                nseg = max(4, min(64, int(sweep / 6)))
                pts = []
                for i in range(nseg + 1):
                    a = math.radians(e.start_angle + sweep * i / nseg)
                    pts.append(t((c[0] + r * math.cos(a), c[1] + r * math.sin(a))))
                draw.line(pts, fill=col(e), width=1)
            elif isinstance(e, Bezier):
                if not vis2(e.p0, e.p3):
                    continue
                pts = [t(bezier_point(e, i / 12)) for i in range(13)]
                draw.line(pts, fill=col(e), width=1)
            elif isinstance(e, TextItem):
                p = e.position
                if not vis2(p, (p[0] + e.width, p[1] + e.height)):
                    continue
                sx, sy = t((p[0], p[1] + e.height))
                px_h = max(1, round(e.height * zoom))
                if px_h >= 4:
                    try:
                        from PIL import ImageFont
                        font = ImageFont.truetype("arial.ttf", px_h)
                    except Exception:
                        font = None
                    draw.text((sx, sy), e.text, fill=(60, 60, 160), font=font)
                else:
                    ex, ey = t((p[0] + e.width, p[1]))
                    draw.line([(sx, ey), (ex, ey)], fill=(150, 150, 200), width=1)
        return img
