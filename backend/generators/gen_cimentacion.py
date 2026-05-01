"""
gen_cimentacion.py
------------------
Módulo 1 — Generador de Expediente Técnico de Cimentación.

Genera bajo NTC-RCDF:
  • Planta de cimentación (zapatas corridas bajo muros, zapatas aisladas en columnas)
  • Corte de zapata corrida con armado
  • Corte de zapata aislada con armado
  • Tabla de armados en capa T-TEXTO
  • Catálogo de conceptos (concreto, acero, excavación, plantilla)

Parámetros de entrada (todos en mm salvo indicación):
  ejes_x      : lista de posiciones X de ejes verticales [0, 3000, 6000, ...]
  ejes_y      : lista de posiciones Y de ejes horizontales [0, 3000, ...]
  espesor_muro: espesor de muros portantes (mm), default 150
  ancho_zapata: ancho de zapata corrida (mm), default 500
  alto_zapata : peralte de zapata corrida (mm), default 350
  desplante   : profundidad de desplante (mm), default 600
  varilla_long: designación varilla longitudinal ("No.4", "No.5", ...)
  varilla_trans: designación varilla transversal
  sep_long_mm : separación varilla longitudinal (mm)
  project_name: nombre del proyecto
  scale_factor: factor mm→mm para el dibujo (1.0 = escala 1:1)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from pathlib import Path
from typing import List, Optional, Tuple

import ezdxf

from ..core.dxf_utils import (
    new_doc, add_title_block, add_dimension,
    add_hatch_concrete, add_hatch_earth, add_rebar_symbol,
)
from ..core.ntc import (
    NTCValidator, ZAPATA_CORRIDA_MIN, RECUBRIMIENTO,
    VARILLA, AREA_VARILLA, MAX_SEP_CASTILLOS,
)
from ..core.catalog import CatalogoConceptos


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

@dataclass
class CimentacionParams:
    ejes_x:        List[float]          # posiciones en mm
    ejes_y:        List[float]
    espesor_muro:  float = 150.0        # mm
    ancho_zapata:  float = 500.0        # mm
    alto_zapata:   float = 350.0        # mm
    desplante:     float = 600.0        # mm
    varilla_long:  str   = "No.4"
    varilla_trans: str   = "No.4"
    sep_long_mm:   float = 200.0        # mm
    sep_trans_mm:  float = 200.0        # mm
    project_name:  str   = "Proyecto"
    date:          str   = "2026"
    fc:            float = 200.0        # kg/cm² — resistencia concreto
    fy:            float = 4200.0       # kg/cm² — resistencia acero


@dataclass
class CimentacionResult:
    dxf_bytes:  bytes
    pdf_bytes:  bytes
    xlsx_bytes: bytes
    catalog:    CatalogoConceptos
    ntc_report: dict
    svg_preview: str


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class CimentacionGenerator:

    SCALE = 1.0   # dibujo a escala 1:1 en mm

    def generate(self, p: CimentacionParams) -> CimentacionResult:
        # Validar NTC
        validator = NTCValidator()
        validator.check_muro(p.espesor_muro)
        validator.check_zapata_corrida(p.ancho_zapata, p.alto_zapata)

        doc, msp = new_doc(p.project_name)

        # --- Planta de cimentación ---
        self._draw_planta(msp, p)

        # --- Corte de zapata corrida (debajo de la planta) ---
        offset_y = -(max(p.ejes_y) + 600)
        self._draw_corte_zc(msp, p, offset_y=offset_y)

        # --- Cuadro de rotulación ---
        width = max(p.ejes_x) + p.ancho_zapata * 2
        add_title_block(
            msp,
            project=p.project_name,
            drawing="PLANTA Y CORTE DE CIMENTACIÓN",
            scale="1:50",
            date=p.date,
            origin_x=0.0,
            origin_y=offset_y - 900,
            width=min(width, 24000),
        )

        # Serializar DXF
        buf = StringIO()
        doc.write(buf)
        dxf_bytes = buf.getvalue().encode("utf-8")

        # Catálogo
        cat = self._build_catalog(p)

        # PDF (renderizado desde DXF en memoria)
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(dxf_bytes)
            tmp_path = tmp.name
        try:
            from ..core.pdf_utils import dxf_to_pdf_bytes
            pdf_bytes = dxf_to_pdf_bytes(
                tmp_path,
                title=f"{p.project_name} — Planta y Corte de Cimentación",
                paper="A1",
            )
        finally:
            os.unlink(tmp_path)

        xlsx_bytes = cat.to_excel_bytes(p.project_name)
        svg = self._build_svg_preview(p)

        return CimentacionResult(
            dxf_bytes=dxf_bytes,
            pdf_bytes=pdf_bytes,
            xlsx_bytes=xlsx_bytes,
            catalog=cat,
            ntc_report=validator.report(),
            svg_preview=svg,
        )

    # ------------------------------------------------------------------
    # Planta de cimentación
    # ------------------------------------------------------------------

    def _draw_planta(self, msp, p: CimentacionParams) -> None:
        aw = p.ancho_zapata / 2   # semi-ancho zapata
        em = p.espesor_muro / 2   # semi-espesor muro

        # Ejes
        for x in p.ejes_x:
            msp.add_line((x, -200), (x, max(p.ejes_y) + 200),
                         dxfattribs={"layer": "A-EJE", "linetype": "CENTER"})
        for y in p.ejes_y:
            msp.add_line((-200, y), (max(p.ejes_x) + 200, y),
                         dxfattribs={"layer": "A-EJE", "linetype": "CENTER"})

        # Zapatas corridas bajo muros en X (por cada par de ejes Y)
        for y in p.ejes_y:
            x0 = min(p.ejes_x) - aw
            x1 = max(p.ejes_x) + aw
            pts = [
                (x0, y - aw), (x1, y - aw),
                (x1, y + aw), (x0, y + aw),
            ]
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "E-ZAPATA", "lineweight": 50})
            add_hatch_concrete(msp, pts)

            # Muro sobre zapata
            msp.add_lwpolyline([
                (min(p.ejes_x), y - em), (max(p.ejes_x), y - em),
                (max(p.ejes_x), y + em), (min(p.ejes_x), y + em),
            ], close=True, dxfattribs={"layer": "A-MURO", "lineweight": 50})

        # Zapatas corridas bajo muros en Y
        for x in p.ejes_x:
            y0 = min(p.ejes_y) - aw
            y1 = max(p.ejes_y) + aw
            pts = [
                (x - aw, y0), (x + aw, y0),
                (x + aw, y1), (x - aw, y1),
            ]
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "E-ZAPATA", "lineweight": 50})
            add_hatch_concrete(msp, pts)
            msp.add_lwpolyline([
                (x - em, min(p.ejes_y)), (x + em, min(p.ejes_y)),
                (x + em, max(p.ejes_y)), (x - em, max(p.ejes_y)),
            ], close=True, dxfattribs={"layer": "A-MURO", "lineweight": 50})

        # Cotas de ejes
        for i in range(len(p.ejes_x) - 1):
            add_dimension(msp,
                          (p.ejes_x[i], max(p.ejes_y) + 400),
                          (p.ejes_x[i+1], max(p.ejes_y) + 400),
                          offset=300)
        for i in range(len(p.ejes_y) - 1):
            add_dimension(msp,
                          (max(p.ejes_x) + 400, p.ejes_y[i]),
                          (max(p.ejes_x) + 400, p.ejes_y[i+1]),
                          offset=300)

        # Etiqueta
        msp.add_text(
            "PLANTA DE CIMENTACIÓN  ESC. 1:50",
            dxfattribs={"layer": "T-TITULO", "height": 200,
                        "insert": (0, max(p.ejes_y) + 800)},
        )
        msp.add_text(
            f"Zapata corrida: {int(p.ancho_zapata)}×{int(p.alto_zapata)} mm  "
            f"f'c={int(p.fc)} kg/cm²  Desplante={int(p.desplante)} mm",
            dxfattribs={"layer": "T-TEXTO", "height": 120,
                        "insert": (0, max(p.ejes_y) + 550)},
        )

    # ------------------------------------------------------------------
    # Corte de zapata corrida
    # ------------------------------------------------------------------

    def _draw_corte_zc(self, msp, p: CimentacionParams, offset_y: float = -4000) -> None:
        aw = p.ancho_zapata / 2
        em = p.espesor_muro / 2
        az = p.alto_zapata
        ds = p.desplante
        rec = RECUBRIMIENTO["zapata"]

        # Origen del corte
        ox, oy = 0.0, offset_y

        # Terreno natural
        suelo_pts = [
            (ox - aw - 200, oy),
            (ox + aw + 200, oy),
            (ox + aw + 200, oy - ds - 200),
            (ox - aw - 200, oy - ds - 200),
        ]
        add_hatch_earth(msp, suelo_pts)

        # Plantilla de concreto pobre (50 mm)
        plant = 50
        msp.add_lwpolyline([
            (ox - aw, oy - ds + plant),
            (ox + aw, oy - ds + plant),
            (ox + aw, oy - ds),
            (ox - aw, oy - ds),
        ], close=True, dxfattribs={"layer": "E-ZAPATA"})
        add_hatch_concrete(msp, [
            (ox - aw, oy - ds + plant), (ox + aw, oy - ds + plant),
            (ox + aw, oy - ds),         (ox - aw, oy - ds),
        ])

        # Cuerpo de zapata
        zpts = [
            (ox - aw, oy),
            (ox + aw, oy),
            (ox + aw, oy - ds + plant),
            (ox - aw, oy - ds + plant),
        ]
        msp.add_lwpolyline(zpts, close=True,
                           dxfattribs={"layer": "E-ZAPATA", "lineweight": 50})
        add_hatch_concrete(msp, zpts)

        # Muro sobre zapata
        muro_pts = [
            (ox - em, oy), (ox + em, oy),
            (ox + em, oy + az), (ox - em, oy + az),
        ]
        msp.add_lwpolyline(muro_pts, close=True,
                           dxfattribs={"layer": "A-MURO", "lineweight": 50})

        # Varillas longitudinales (sección transversal)
        d_var = VARILLA.get(p.varilla_long, 12.7)
        n_varillas = max(2, int((p.ancho_zapata - 2 * rec) / p.sep_long_mm) + 1)
        spacing = (p.ancho_zapata - 2 * rec) / max(n_varillas - 1, 1)
        y_acero = oy - ds + plant + rec + d_var / 2
        for i in range(n_varillas):
            cx = ox - aw + rec + i * spacing
            add_rebar_symbol(msp, (cx, y_acero), d_var, scale=0.8)

        # Varilla transversal (longitudinal al muro, como línea)
        msp.add_line(
            (ox - aw + rec, y_acero + d_var * 2),
            (ox + aw - rec, y_acero + d_var * 2),
            dxfattribs={"layer": "E-ARMADO"},
        )

        # Cotas del corte
        add_dimension(msp, (ox - aw, oy - ds + plant), (ox + aw, oy - ds + plant), offset=-300)
        add_dimension(msp,
                      (ox + aw + 200, oy - ds + plant),
                      (ox + aw + 200, oy),
                      offset=200)

        # Notas
        varilla_nota = (
            f"ACERO LONG: {n_varillas} @ {int(p.varilla_long.replace('No.',''))} "
            f"Ø{d_var:.0f}mm  SEP.{int(spacing)}mm\n"
            f"REC.LIBRE: {rec}mm  f'c={int(p.fc)}kg/cm²  fy={int(p.fy)}kg/cm²"
        )
        msp.add_text(
            f"CORTE ZAPATA CORRIDA  ESC. 1:20",
            dxfattribs={"layer": "T-TITULO", "height": 200,
                        "insert": (ox - aw, oy + az + 300)},
        )
        msp.add_text(
            f"{int(n_varillas)} var. {p.varilla_long} @ {int(spacing)} mm  "
            f"|  Rec. {rec} mm  |  f'c {int(p.fc)} kg/cm²",
            dxfattribs={"layer": "T-TEXTO", "height": 100,
                        "insert": (ox - aw, oy + az + 100)},
        )

    # ------------------------------------------------------------------
    # Catálogo de conceptos
    # ------------------------------------------------------------------

    def _build_catalog(self, p: CimentacionParams) -> CatalogoConceptos:
        cat = CatalogoConceptos()

        ejes_x = sorted(p.ejes_x)
        ejes_y = sorted(p.ejes_y)
        lon_total_x = sum(ejes_x[i+1] - ejes_x[i] for i in range(len(ejes_x) - 1))
        lon_total_y = sum(ejes_y[i+1] - ejes_y[i] for i in range(len(ejes_y) - 1))
        lon_total_m = (lon_total_x * len(ejes_y) + lon_total_y * len(ejes_x)) / 1000

        aw = p.ancho_zapata / 1000   # m
        az = p.alto_zapata  / 1000   # m
        ds = p.desplante    / 1000   # m

        # 01 Trazo y nivelación
        area_total_m2 = (max(ejes_x) - min(ejes_x)) * (max(ejes_y) - min(ejes_y)) / 1e6
        cat.agregar("01.01", "Trazo y nivelación con aparatos", "m²", area_total_m2)

        # 02 Excavación
        vol_exc = lon_total_m * aw * (ds + 0.05)
        cat.agregar("02.01", "Excavación en cepa para zapata corrida (mat. tipo II)", "m³", vol_exc)

        # 03 Plantilla
        vol_plant = lon_total_m * aw * 0.05
        cat.agregar("03.01", "Plantilla de concreto f'c=100 kg/cm² e=5 cm", "m³", vol_plant)

        # 04 Concreto zapata
        vol_zap = lon_total_m * aw * az
        cat.agregar("04.01",
                    f"Concreto hecho en obra f'c={int(p.fc)} kg/cm² en zapata corrida",
                    "m³", vol_zap)

        # 05 Acero de refuerzo (estimado)
        d_var = VARILLA.get(p.varilla_long, 12.7) / 1000   # m
        area_var = AREA_VARILLA.get(p.varilla_long, 126.7)  # mm²
        n_var = max(2, int((p.ancho_zapata - 2 * RECUBRIMIENTO["zapata"]) / p.sep_long_mm) + 1)
        kg_acero = lon_total_m * n_var * (area_var / 1e6 * 7850)  # densidad acero 7850 kg/m³
        cat.agregar("05.01",
                    f"Acero de refuerzo {p.varilla_long} (f'y={int(p.fy)} kg/cm²), habilitado y colocado",
                    "kg", round(kg_acero, 1))

        # 06 Relleno compactado
        vol_rel = vol_exc - vol_zap - vol_plant
        cat.agregar("06.01", "Relleno y compactación con material producto de excavación", "m³",
                    max(0, vol_rel))

        # 07 Acarreo de material sobrante
        vol_acarm = vol_exc * 0.3
        cat.agregar("07.01", "Acarreo de material sobrante", "m³", vol_acarm)

        return cat

    # ------------------------------------------------------------------
    # SVG preview (miniatura para el navegador)
    # ------------------------------------------------------------------

    def _build_svg_preview(self, p: CimentacionParams) -> str:
        W, H = 600, 400
        mx, my = max(p.ejes_x) or 1, max(p.ejes_y) or 1
        sx = (W - 60) / mx
        sy = (H - 60) / my
        s = min(sx, sy)

        def tx(x): return 30 + x * s
        def ty(y): return H - 30 - y * s

        lines = ['<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{W}" height="{H}" style="background:#1e1e1e">']

        aw = p.ancho_zapata / 2

        # Zapatas
        for y in p.ejes_y:
            x0, x1 = min(p.ejes_x) - aw, max(p.ejes_x) + aw
            lines.append(
                f'<rect x="{tx(x0):.1f}" y="{ty(y + aw):.1f}" '
                f'width="{(x1-x0)*s:.1f}" height="{aw*2*s:.1f}" '
                f'fill="#2E75B6" opacity="0.6" stroke="#5BA3E0" stroke-width="1"/>'
            )
        for x in p.ejes_x:
            y0, y1 = min(p.ejes_y) - aw, max(p.ejes_y) + aw
            lines.append(
                f'<rect x="{tx(x - aw):.1f}" y="{ty(y1):.1f}" '
                f'width="{aw*2*s:.1f}" height="{(y1-y0)*s:.1f}" '
                f'fill="#2E75B6" opacity="0.6" stroke="#5BA3E0" stroke-width="1"/>'
            )

        # Ejes
        for x in p.ejes_x:
            lines.append(
                f'<line x1="{tx(x):.1f}" y1="10" x2="{tx(x):.1f}" y2="{H-10}" '
                f'stroke="#ff4444" stroke-width="1" stroke-dasharray="6,4"/>'
            )
        for y in p.ejes_y:
            lines.append(
                f'<line x1="10" y1="{ty(y):.1f}" x2="{W-10}" y2="{ty(y):.1f}" '
                f'stroke="#ff4444" stroke-width="1" stroke-dasharray="6,4"/>'
            )

        lines.append(
            f'<text x="10" y="20" fill="#cccccc" font-size="11" font-family="monospace">'
            f'PLANTA CIMENTACIÓN — {p.project_name}</text>'
        )
        lines.append("</svg>")
        return "\n".join(lines)
