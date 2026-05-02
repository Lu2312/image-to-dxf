"""
gui.py
------
Modern Tkinter GUI for image_to_dxf converter.

Layout
------
Left pane  : file paths, conversion options, convert button, status, stats.
Right pane : tabbed notebook with "Original image" and "DXF preview" tabs.
             • Original image – thumbnail updated whenever a file is selected.
             • DXF preview    – matplotlib rendering via ezdxf drawing addon,
                                refreshed after each successful conversion.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk

from image_to_dxf import convert, ConversionResult


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Image → DXF Converter")
        self.geometry("1150x700")
        self.minsize(820, 520)
        self._pil_image: Image.Image | None = None
        self._img_preview: ImageTk.PhotoImage | None = None
        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        for name in ("vista", "winnative", "clam"):
            try:
                style.theme_use(name)
                break
            except tk.TclError:
                continue

        style.configure("Convert.TButton", font=("Segoe UI", 10, "bold"), padding=6)
        style.configure("Stats.TLabel", font=("Consolas", 9), foreground="#333333")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(pane, width=390)
        left.pack_propagate(False)
        pane.add(left, weight=0)

        right = ttk.Frame(pane)
        pane.add(right, weight=1)

        self._build_controls(left)
        self._build_preview(right)

    # ------------------------------------------------------------------
    # Left panel – controls
    # ------------------------------------------------------------------

    def _build_controls(self, parent: ttk.Frame) -> None:
        pad = {"padx": 8, "pady": 4}

        # Input file
        frm_in = ttk.LabelFrame(parent, text="Input image")
        frm_in.pack(fill="x", **pad)
        self.var_input = tk.StringVar()
        self.var_input.trace_add("write", self._on_input_changed)
        ent_in = ttk.Entry(frm_in, textvariable=self.var_input)
        ent_in.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        ttk.Button(frm_in, text="Browse…", command=self._browse_input).pack(
            side="right", padx=4, pady=4
        )

        # Output file
        frm_out = ttk.LabelFrame(parent, text="Output DXF")
        frm_out.pack(fill="x", **pad)
        self.var_output = tk.StringVar()
        ent_out = ttk.Entry(frm_out, textvariable=self.var_output)
        ent_out.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        ttk.Button(frm_out, text="Browse…", command=self._browse_output).pack(
            side="right", padx=4, pady=4
        )

        # Options
        frm_opt = ttk.LabelFrame(parent, text="Conversion options")
        frm_opt.pack(fill="x", **pad)
        g = ttk.Frame(frm_opt)
        g.pack(fill="x", padx=4, pady=4)

        def _row(label: str, var: tk.Variable, row: int, col: int,
                 kind: str = "entry", values=None, width: int = 10) -> None:
            ttk.Label(g, text=label).grid(row=row, column=col * 2, sticky="w", padx=4, pady=2)
            if kind == "combo":
                w = ttk.Combobox(g, textvariable=var, values=values,
                                 state="readonly", width=width)
            else:
                w = ttk.Entry(g, textvariable=var, width=width)
            w.grid(row=row, column=col * 2 + 1, sticky="w", padx=4, pady=2)

        self.var_mode      = tk.StringVar(value="trace")
        self.var_scale     = tk.StringVar(value="0.1")
        self.var_threshold = tk.StringVar(value="127")
        self.var_min_area  = tk.StringVar(value="10")
        self.var_epsilon   = tk.StringVar(value="0.5")
        self.var_lw        = tk.StringVar(value="25")

        _row("Mode:",                self.var_mode,      0, 0, "combo", ["trace", "hatch", "pixel"])
        _row("Scale (mm/px):",       self.var_scale,     0, 1)
        _row("Threshold (0-255):",   self.var_threshold, 1, 0)
        _row("Min area (px²):",      self.var_min_area,  1, 1)
        _row("Simplify epsilon:",    self.var_epsilon,   2, 0)
        _row("Lineweight (1/100mm):", self.var_lw,       2, 1)

        self.var_spline = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frm_opt, text="Use SPLINE entities (trace mode only)",
            variable=self.var_spline,
        ).pack(anchor="w", padx=8, pady=(0, 4))

        # Title / metadata
        frm_meta = ttk.LabelFrame(parent, text="Drawing title (written to INFO layer)")
        frm_meta.pack(fill="x", **pad)
        self.var_title = tk.StringVar()
        ttk.Entry(frm_meta, textvariable=self.var_title).pack(
            fill="x", padx=4, pady=4
        )

        # Convert button
        self.btn_convert = ttk.Button(
            parent, text="⚙  Convert to DXF",
            command=self._on_convert, style="Convert.TButton",
        )
        self.btn_convert.pack(fill="x", padx=8, pady=(8, 2))

        # Progress bar
        self.progress = ttk.Progressbar(parent, mode="indeterminate")
        self.progress.pack(fill="x", padx=8, pady=(0, 4))

        # Status label
        self.lbl_status = ttk.Label(parent, text="Ready.", foreground="gray",
                                     wraplength=360)
        self.lbl_status.pack(padx=8, pady=2, anchor="w")

        # Statistics
        frm_stats = ttk.LabelFrame(parent, text="Conversion statistics")
        frm_stats.pack(fill="x", **pad)
        self.lbl_stats = ttk.Label(
            frm_stats, text="—  Run a conversion to see stats.",
            style="Stats.TLabel", justify="left", wraplength=360,
        )
        self.lbl_stats.pack(padx=6, pady=6, anchor="w")

    # ------------------------------------------------------------------
    # Right panel – preview notebook
    # ------------------------------------------------------------------

    def _build_preview(self, parent: ttk.Frame) -> None:
        self._nb = ttk.Notebook(parent)
        self._nb.pack(fill="both", expand=True)

        # Tab 1 – original image
        tab_img = ttk.Frame(self._nb)
        self._nb.add(tab_img, text=" 🖼  Original image ")

        self._img_canvas = tk.Canvas(tab_img, bg="#1e1e1e", highlightthickness=0)
        self._img_canvas.pack(fill="both", expand=True)
        self._img_canvas.bind("<Configure>", lambda _e: self._redraw_image())

        # Tab 2 – DXF preview (matplotlib)
        tab_dxf = ttk.Frame(self._nb)
        self._nb.add(tab_dxf, text=" 📐  DXF preview ")
        self._tab_dxf = tab_dxf

        self._fig, self._ax = plt.subplots(figsize=(6, 6))
        self._fig.patch.set_facecolor("#1e1e1e")
        self._ax.set_facecolor("#1e1e1e")
        self._ax.tick_params(colors="#888888", labelsize=7)
        for spine in self._ax.spines.values():
            spine.set_edgecolor("#444444")
        self._ax.set_aspect("equal")
        self._ax.text(
            0.5, 0.5,
            "Convert an image to see the\nDXF preview here.",
            ha="center", va="center", color="#555555",
            fontsize=11, transform=self._ax.transAxes,
        )
        self._ax.set_axis_off()
        self._mpl_canvas = FigureCanvasTkAgg(self._fig, master=tab_dxf)
        self._mpl_canvas.get_tk_widget().pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Image preview helpers
    # ------------------------------------------------------------------

    def _on_input_changed(self, *_args) -> None:
        path = self.var_input.get().strip()
        if path and Path(path).is_file():
            self._load_image_preview(path)

    def _load_image_preview(self, path: str) -> None:
        try:
            self._pil_image = Image.open(path)
            self._redraw_image()
            self._nb.select(0)
        except Exception:
            pass

    def _redraw_image(self) -> None:
        if self._pil_image is None:
            return
        canvas = self._img_canvas
        cw = canvas.winfo_width() or 500
        ch = canvas.winfo_height() or 400

        img = self._pil_image.copy()
        img.thumbnail((cw - 4, ch - 4), Image.LANCZOS)
        self._img_preview = ImageTk.PhotoImage(img)

        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, anchor="center", image=self._img_preview)

        # Info overlay
        w, h = self._pil_image.size
        ext = Path(self.var_input.get()).suffix.upper()
        canvas.create_rectangle(0, 0, 220, 20, fill="#00000099", outline="")
        canvas.create_text(
            6, 10, anchor="w", fill="#dddddd",
            text=f"{w} × {h} px  {ext}",
            font=("Consolas", 9),
        )

    # ------------------------------------------------------------------
    # File dialogs
    # ------------------------------------------------------------------

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.var_input.set(path)
            if not self.var_output.get():
                self.var_output.set(str(Path(path).with_suffix(".dxf")))
            if not self.var_title.get():
                self.var_title.set(Path(path).stem)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save DXF as",
            defaultextension=".dxf",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")],
        )
        if path:
            self.var_output.set(path)

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _on_convert(self) -> None:
        inp = self.var_input.get().strip()
        if not inp:
            messagebox.showwarning("Missing input", "Please select an input image.")
            return
        if not Path(inp).is_file():
            messagebox.showerror("File not found", f"File not found:\n{inp}")
            return

        out = self.var_output.get().strip() or None

        try:
            scale     = float(self.var_scale.get())
            threshold = int(self.var_threshold.get())
            min_area  = float(self.var_min_area.get())
            epsilon   = float(self.var_epsilon.get())
            lw        = int(self.var_lw.get())
        except ValueError as exc:
            messagebox.showerror("Invalid option", str(exc))
            return

        self.btn_convert.configure(state="disabled")
        self.progress.start(10)
        self.lbl_status.configure(text="Converting…", foreground="#1a6fbf")
        self.lbl_stats.configure(text="—  Working…")

        def _run() -> None:
            try:
                result = convert(
                    inp, out,
                    mode=self.var_mode.get(),
                    scale=scale,
                    threshold=threshold,
                    min_area=min_area,
                    approx_epsilon=epsilon,
                    spline=self.var_spline.get(),
                    lineweight=lw,
                    title=self.var_title.get() or None,
                )
                self.after(0, lambda r=result: self._done(r))
            except Exception as exc:
                self.after(0, lambda e=exc: self._error(e))

        threading.Thread(target=_run, daemon=True).start()

    def _done(self, result: ConversionResult) -> None:
        self.progress.stop()
        self.btn_convert.configure(state="normal")
        self.lbl_status.configure(
            text=f"✓  Saved → {result.path}", foreground="#1a7f37"
        )

        stats = (
            f"Contours  : {result.contour_count}\n"
            f"Entities  : {result.entity_count}\n"
            f"Image     : {result.img_width} × {result.img_height} px\n"
            f"DXF size  : {result.dxf_width:.1f} × {result.dxf_height:.1f} mm"
        )
        self.lbl_stats.configure(text=stats, foreground="#111111")

        self._render_dxf_preview(str(result.path))
        messagebox.showinfo("Conversion complete", f"DXF saved to:\n{result.path}")

    def _error(self, exc: Exception) -> None:
        self.progress.stop()
        self.btn_convert.configure(state="normal")
        self.lbl_status.configure(text=f"Error: {exc}", foreground="#c0392b")
        self.lbl_stats.configure(text="—")
        messagebox.showerror("Conversion failed", str(exc))

    # ------------------------------------------------------------------
    # DXF preview
    # ------------------------------------------------------------------

    def _render_dxf_preview(self, dxf_path: str) -> None:
        try:
            import ezdxf
            from ezdxf.addons.drawing import RenderContext, Frontend
            from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

            doc = ezdxf.readfile(dxf_path)
            self._ax.cla()
            self._ax.set_facecolor("#1e1e1e")
            self._fig.patch.set_facecolor("#1e1e1e")
            backend = MatplotlibBackend(self._ax)
            Frontend(RenderContext(doc), backend).draw_layout(doc.modelspace())
            self._ax.set_aspect("equal")
            self._ax.autoscale()
            self._ax.tick_params(colors="#888888", labelsize=7)
            for spine in self._ax.spines.values():
                spine.set_edgecolor("#444444")
            self._fig.tight_layout(pad=0.5)
            self._mpl_canvas.draw()
            self._nb.select(self._tab_dxf)
        except Exception as exc:
            # Preview failure is non-fatal – conversion already succeeded
            self.lbl_status.configure(
                text=f"✓  Saved (preview unavailable: {exc})",
                foreground="#1a7f37",
            )


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
