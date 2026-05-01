"""
gen_carpinteria.py
------------------
Módulo 3 — Generador de Detalles de Carpintería y Cancelería.

El usuario define el vano (ancho × alto) y el tipo:
  • Ventana de cancelería de aluminio (fija, corrediza, abatible)
  • Puerta (interior, exterior, vaivén)
  • Closet / mueble de madera (puertas batientes, corredizas)

El sistema genera:
  • Alzado técnico con cotas
  • Despiece de piezas (marcos, hojas, travesaños, herrajes)
  • Catálogo de conceptos por pieza
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO, StringIO
from typing import List, Tuple

from ..core.dxf_utils import new_doc, add_title_block, add_dimension
from ..core.catalog import CatalogoConceptos


@dataclass
class CarpinteriaParams:
    tipo:          str    # "ventana_fija" | "ventana_corrediza" | "puerta" | "closet"
    ancho:         float  # mm  (vano libre)
    alto:          float  # mm  (vano libre)
    marco_ancho:   float = 50.0   # mm  (perfil del marco)
    hoja_grosor:   float = 40.0   # mm  (grosor de hoja / perfil)
    n_hojas:       int   = 2      # número de hojas (ventana corrediza/closet)
    material:      str   = "aluminio"   # "aluminio" | "madera" | "pvc"
    acabado:       str   = "natural"
    project_name:  str   = "Proyecto"
    date:          str   = "2026"


@dataclass
class CarpinteriaResult:
    dxf_bytes:   bytes
    pdf_bytes:   bytes
    xlsx_bytes:  bytes
    catalog:     CatalogoConceptos
    svg_preview: str


class CarpinteriaGenerator:

    def generate(self, p: CarpinteriaParams) -> CarpinteriaResult:
        doc, msp = new_doc(p.project_name)

        if p.tipo in ("ventana_fija", "ventana_corrediza"):
            self._draw_ventana(msp, p)
        elif p.tipo == "puerta":
            self._draw_puerta(msp, p)
        elif p.tipo == "closet":
            self._draw_closet(msp, p)
        else:
            self._draw_ventana(msp, p)

        add_title_block(
            msp,
            project=p.project_name,
            drawing=f"DETALLE DE {p.tipo.upper().replace('_',' ')}",
            scale="1:20",
            date=p.date,
            origin_x=0.0,
            origin_y=-(p.alto * 0.5 + 900),
            width=p.ancho + 500,
        )

        buf = StringIO()
        doc.write(buf)
        dxf_bytes = buf.getvalue().encode("utf-8")

        cat = self._build_catalog(p)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(dxf_bytes)
            tmp_path = tmp.name
        try:
            from ..core.pdf_utils import dxf_to_pdf_bytes
            pdf_bytes = dxf_to_pdf_bytes(tmp_path,
                                          title=f"{p.project_name} — Detalle {p.tipo}",
                                          paper="A3")
        finally:
            os.unlink(tmp_path)

        xlsx_bytes = cat.to_excel_bytes(p.project_name)
        svg = self._build_svg(p)

        return CarpinteriaResult(
            dxf_bytes=dxf_bytes, pdf_bytes=pdf_bytes,
            xlsx_bytes=xlsx_bytes, catalog=cat, svg_preview=svg,
        )

    # ------------------------------------------------------------------
    def _draw_ventana(self, msp, p: CarpinteriaParams) -> None:
        m = p.marco_ancho
        h = p.hoja_grosor
        W, H = p.ancho, p.alto

        # Marco exterior
        msp.add_lwpolyline(
            [(0, 0), (W, 0), (W, H), (0, H)],
            close=True, dxfattribs={"layer": "A-VENTANA", "lineweight": 50}
        )
        # Marco interior (vano vidrio)
        msp.add_lwpolyline(
            [(m, m), (W - m, m), (W - m, H - m), (m, H - m)],
            close=True, dxfattribs={"layer": "A-VENTANA", "lineweight": 25}
        )

        if p.tipo == "ventana_fija":
            # Diagonal de vidrio
            msp.add_line((m, m), (W - m, H - m), dxfattribs={"layer": "A-VENTANA"})
            msp.add_line((W - m, m), (m, H - m), dxfattribs={"layer": "A-VENTANA"})
            msp.add_text("VIDRIO FIJO", dxfattribs={
                "layer": "T-TEXTO", "height": min(120, W * 0.05),
                "insert": (W * 0.3, H * 0.5),
            })
        else:
            # Hojas corredizas
            hoja_w = (W - 2 * m) / p.n_hojas
            for i in range(p.n_hojas):
                x0 = m + i * hoja_w
                msp.add_lwpolyline(
                    [(x0, m), (x0 + hoja_w, m),
                     (x0 + hoja_w, H - m), (x0, H - m)],
                    close=True, dxfattribs={"layer": "A-VENTANA"}
                )
                msp.add_text(f"HOJA {i+1}", dxfattribs={
                    "layer": "T-TEXTO", "height": min(100, hoja_w * 0.1),
                    "insert": (x0 + hoja_w * 0.2, H * 0.5),
                })
            # Flecha de corredera
            cx = W / 2
            msp.add_line((cx - 200, H * 0.15), (cx + 200, H * 0.15),
                         dxfattribs={"layer": "T-TEXTO"})

        # Cotas
        add_dimension(msp, (0, H + 200), (W, H + 200))
        add_dimension(msp, (W + 200, 0), (W + 200, H))

        msp.add_text(
            f"ALZADO  {p.tipo.replace('_',' ').upper()}  {p.material.upper()}  "
            f"{int(W)}×{int(H)} mm  ESC. 1:20",
            dxfattribs={"layer": "T-TITULO", "height": 150,
                        "insert": (0, H + 500)},
        )

    def _draw_puerta(self, msp, p: CarpinteriaParams) -> None:
        m = p.marco_ancho
        W, H = p.ancho, p.alto

        # Marco
        msp.add_lwpolyline(
            [(0, 0), (W, 0), (W, H), (0, H)],
            close=True, dxfattribs={"layer": "A-PUERTA", "lineweight": 50}
        )
        # Hoja de puerta
        msp.add_lwpolyline(
            [(m, 0), (W - m, 0), (W - m, H - m), (m, H - m)],
            close=True, dxfattribs={"layer": "A-PUERTA", "lineweight": 35}
        )
        # Arco de apertura (cuarto de círculo)
        r = W - 2 * m
        msp.add_arc((m, 0), r, 0, 90,
                    dxfattribs={"layer": "A-PUERTA", "linetype": "DASHED"})

        # Travesaño intermedio
        y_trav = H * 0.4
        msp.add_line((m, y_trav), (W - m, y_trav),
                     dxfattribs={"layer": "A-PUERTA"})

        # Herraje
        msp.add_circle((W - m - 60, H * 0.5), 20,
                       dxfattribs={"layer": "A-MUEBLE"})

        add_dimension(msp, (0, H + 200), (W, H + 200))
        add_dimension(msp, (W + 200, 0), (W + 200, H))

        msp.add_text(
            f"ALZADO PUERTA {p.material.upper()}  {int(W)}×{int(H)} mm  ESC. 1:20",
            dxfattribs={"layer": "T-TITULO", "height": 150,
                        "insert": (0, H + 500)},
        )

    def _draw_closet(self, msp, p: CarpinteriaParams) -> None:
        m = p.marco_ancho
        W, H = p.ancho, p.alto
        hoja_w = (W - 2 * m) / p.n_hojas

        msp.add_lwpolyline(
            [(0, 0), (W, 0), (W, H), (0, H)],
            close=True, dxfattribs={"layer": "A-MUEBLE", "lineweight": 50}
        )
        for i in range(p.n_hojas):
            x0 = m + i * hoja_w
            msp.add_lwpolyline(
                [(x0, m), (x0 + hoja_w - 5, m),
                 (x0 + hoja_w - 5, H - m), (x0, H - m)],
                close=True, dxfattribs={"layer": "A-MUEBLE"}
            )
            # Línea central (tablero)
            msp.add_line((x0, H * 0.5), (x0 + hoja_w - 5, H * 0.5),
                         dxfattribs={"layer": "A-MUEBLE"})
            # Jaladero
            msp.add_line(
                (x0 + hoja_w * 0.1, H * 0.5 + 50),
                (x0 + hoja_w * 0.1, H * 0.5 - 50),
                dxfattribs={"layer": "A-MUEBLE"},
            )

        add_dimension(msp, (0, H + 200), (W, H + 200))
        add_dimension(msp, (W + 200, 0), (W + 200, H))
        msp.add_text(
            f"ALZADO CLOSET {p.material.upper()}  {p.n_hojas} HOJAS  "
            f"{int(W)}×{int(H)} mm  ESC. 1:20",
            dxfattribs={"layer": "T-TITULO", "height": 150,
                        "insert": (0, H + 500)},
        )

    # ------------------------------------------------------------------
    def _build_catalog(self, p: CarpinteriaParams) -> CatalogoConceptos:
        cat = CatalogoConceptos()
        W_m = p.ancho / 1000
        H_m = p.alto  / 1000
        m_m = p.marco_ancho / 1000
        area = W_m * H_m

        ml_marco = 2 * (W_m + H_m)
        if p.tipo.startswith("ventana"):
            cat.agregar("20.01",
                        f"Marco de {p.material} para ventana {int(p.ancho)}×{int(p.alto)} mm",
                        "ml", ml_marco)
            n_hojas = p.n_hojas if "corrediza" in p.tipo else 1
            for i in range(1, n_hojas + 1):
                hw = (W_m - 2 * m_m) / n_hojas
                cat.agregar(f"20.0{i+1}",
                            f"Hoja de vidrio {p.tipo.replace('ventana_','')} "
                            f"{p.material}, hoja {i}",
                            "m²", hw * (H_m - 2 * m_m))
            cat.agregar("20.09", "Herrajes y fijaciones (tornillos, sellador, remaches)", "jgo", 1)
        elif p.tipo == "puerta":
            cat.agregar("21.01",
                        f"Marco de {p.material} para puerta {int(p.ancho)}×{int(p.alto)} mm",
                        "pza", 1)
            cat.agregar("21.02",
                        f"Hoja de puerta {p.material} {int(p.ancho - 2*p.marco_ancho)}×{int(p.alto)} mm",
                        "pza", 1)
            cat.agregar("21.03", "Chapa / cerradura de palanca", "pza", 1)
            cat.agregar("21.04", "Bisagras (juego 3 pzas)", "jgo", 1)
        elif p.tipo == "closet":
            cat.agregar("22.01",
                        f"Tablero de {p.material} para closet {int(p.ancho)}×{int(p.alto)} mm",
                        "m²", area)
            cat.agregar("22.02", f"Puertas corredizas ({p.n_hojas} hojas)", "pza", p.n_hojas)
            cat.agregar("22.03", "Rieles y roldanas para puertas corredizas", "jgo", 1)
            cat.agregar("22.04", "Jaladeras de aluminio", "pza", p.n_hojas)

        return cat

    def _build_svg(self, p: CarpinteriaParams) -> str:
        W_svg, H_svg = 500, 400
        mx = p.ancho
        my = p.alto
        s = min((W_svg - 80) / mx, (H_svg - 80) / my)
        ox, oy = 40, 40

        def tx(x): return ox + x * s
        def ty(y): return H_svg - oy - y * s

        m = p.marco_ancho
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W_svg}" height="{H_svg}" '
            f'style="background:#1e1e1e; font-family:monospace">',
            f'<rect x="{tx(0):.1f}" y="{ty(p.alto):.1f}" '
            f'width="{p.ancho*s:.1f}" height="{p.alto*s:.1f}" '
            f'fill="#1a2a3a" stroke="#5BA3E0" stroke-width="2"/>',
        ]
        if p.tipo == "ventana_fija":
            lines += [
                f'<rect x="{tx(m):.1f}" y="{ty(p.alto-m):.1f}" '
                f'width="{(p.ancho-2*m)*s:.1f}" height="{(p.alto-2*m)*s:.1f}" '
                f'fill="#0a1a2a" stroke="#88bbdd" stroke-width="1"/>',
                f'<line x1="{tx(m):.1f}" y1="{ty(m):.1f}" '
                f'x2="{tx(p.ancho-m):.1f}" y2="{ty(p.alto-m):.1f}" stroke="#88bbdd" stroke-width="1"/>',
                f'<line x1="{tx(p.ancho-m):.1f}" y1="{ty(m):.1f}" '
                f'x2="{tx(m):.1f}" y2="{ty(p.alto-m):.1f}" stroke="#88bbdd" stroke-width="1"/>',
            ]
        elif p.tipo == "ventana_corrediza":
            hw = (p.ancho - 2 * m) / p.n_hojas
            for i in range(p.n_hojas):
                x0 = m + i * hw
                lines.append(
                    f'<rect x="{tx(x0):.1f}" y="{ty(p.alto-m):.1f}" '
                    f'width="{hw*s:.1f}" height="{(p.alto-2*m)*s:.1f}" '
                    f'fill="#0a1a2a" stroke="#88bbdd" stroke-width="1"/>'
                )
        elif p.tipo == "puerta":
            lines.append(
                f'<rect x="{tx(m):.1f}" y="{ty(p.alto-m):.1f}" '
                f'width="{(p.ancho-2*m)*s:.1f}" height="{(p.alto-m)*s:.1f}" '
                f'fill="#2a1a0a" stroke="#ddaa55" stroke-width="1"/>'
            )
        elif p.tipo == "closet":
            hw = (p.ancho - 2 * m) / p.n_hojas
            for i in range(p.n_hojas):
                x0 = m + i * hw
                lines.append(
                    f'<rect x="{tx(x0):.1f}" y="{ty(p.alto-m):.1f}" '
                    f'width="{hw*s:.1f}" height="{(p.alto-2*m)*s:.1f}" '
                    f'fill="#1a1a0a" stroke="#aa8844" stroke-width="1"/>'
                )

        lines += [
            f'<text x="{tx(p.ancho/2):.1f}" y="{oy-8}" fill="#aaaaaa" '
            f'font-size="10" text-anchor="middle">{int(p.ancho)} mm</text>',
            f'<text x="{tx(0)-28}" y="{ty(p.alto/2):.1f}" fill="#aaaaaa" '
            f'font-size="10" text-anchor="middle" '
            f'transform="rotate(-90,{tx(0)-28},{ty(p.alto/2):.1f})">{int(p.alto)} mm</text>',
            f'<text x="10" y="{H_svg-8}" fill="#cccccc" font-size="10">'
            f'{p.tipo.replace("_"," ").upper()} — {p.material.upper()} — {p.project_name}</text>',
            "</svg>",
        ]
        return "\n".join(lines)
