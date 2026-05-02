"""
gen_planta.py  v4
-----------------
Módulo 2 — Configurador de Planta Tipo (vivienda de interés social).

Estándares CAD implementados:
  1. Capas con color/grosor/linetype definidos
  2. Malla de ejes primero (CENTER linetype, sobresalen 1000mm)
  3. Globos de eje: verticales 1,2,3... / horizontales A,B,C...
  4. Entidades DIMENSION reales de AutoCAD
  5. Puertas: LINE umbral + ARC de batiente 90°
  6. Ventanas: triple línea paralela en muro exterior
  7. Alzado frontal con niveles NPT±0.00, Cerramiento y Losa
  8. Corte A-A' con grosor diferenciado cortado vs. proyectado
  9. Distancias mínimas validadas (SEDATU/RCDF)

Sistema de Agentes Estructurales (v4):
  AnalistaEspacial  → detecta muros, nodos e intersecciones (L/T/CROSS)
  IngenieroNormativo → aplica NTC Mampostería §6.3-6.4: castillos en esquinas
                       e intermedios; dalas de cerramiento §7.2
  GeneradorGeometria → dibuja castillos (E-CASTILLO) y dalas (E-DALA) en DXF
                       con LWPOLYLINE+HATCH+etiqueta de armado
"""
from __future__ import annotations

import math
import os
import string
import tempfile
from dataclasses import dataclass, field
from io import StringIO
from typing import Dict, List, Optional, Tuple

from ..core.dxf_utils import (
    new_doc, add_title_block, add_dimension,
    add_dimension_chain_h, add_dimension_chain_v,
    add_eje_bubble, add_centered_text, _safe,
)
from ..core.ntc import (
    NTCValidator, MAX_SEP_CASTILLOS,
    CASTILLO_MIN, ESPESOR_MURO_STD, LAYERS,
)
from ..core.catalog import CatalogoConceptos
from ..core.modelo_estructural import MetadatosNormativos, ModeloEstructural
from ..agents.analista_espacial import AnalistaEspacial
from ..agents.ingeniero_normativo import IngenieroNormativo
from ..agents.generador_geometria import GeneradorGeometria


# ---------------------------------------------------------------------------
# Constantes de diseño
# ---------------------------------------------------------------------------

PUERTA_EXT     = 900    # mm  mínimo exterior  (RCDF / SEDATU)
PUERTA_INT     = 750    # mm  interior general
PUERTA_BANO    = 700    # mm  baños
VENTANA_ANCHO  = 1200   # mm
VENTANA_ALTO   = 1200   # mm
ANTEPECHO      = 900    # mm desde NPT
EXT_EJE        = 1000   # mm que sobresalen los ejes del edificio
RADIO_GLOBO    = 250    # mm radio del globo de eje
LOSA_GROSOR    = 100    # mm espesor losa
PISO_GROSOR    = 80     # mm firme de concreto

# AutoCAD ACI
ACI_RED     = 1
ACI_YELLOW  = 2
ACI_GREEN   = 3
ACI_CYAN    = 4
ACI_WHITE   = 7
ACI_GRAY    = 8
ACI_MAGENTA = 6


# ---------------------------------------------------------------------------
# Parámetros y resultado
# ---------------------------------------------------------------------------

@dataclass
class Recinto:
    nombre:   str
    x:        float   # interior lower-left (mm)
    y:        float
    ancho:    float   # interior width  (mm)
    fondo:    float   # interior depth  (mm)
    es_banyo: bool = False
    es_cocina: bool = False


@dataclass
class PlantaParams:
    lote_ancho:   float = 6000.0
    lote_fondo:   float = 12000.0
    espesor_muro: float = 150.0
    recintos:     List[Dict] = field(default_factory=list)
    project_name: str   = "Proyecto"
    date:         str   = "2026"
    altura_muro:  float = 2700.0   # mm


@dataclass
class PlantaResult:
    dxf_bytes:   bytes
    pdf_bytes:   bytes
    xlsx_bytes:  bytes
    catalog:     CatalogoConceptos
    ntc_report:  dict
    svg_preview: str
    modelo_estructural: ModeloEstructural | None = None


# ---------------------------------------------------------------------------
# Generador principal
# ---------------------------------------------------------------------------

class PlantaGenerator:

    def generate(self, p: PlantaParams) -> PlantaResult:
        validator = NTCValidator()
        validator.check_muro(p.espesor_muro)
        validator.check_altura(p.altura_muro)

        doc, msp = new_doc(p.project_name)
        self._setup_layers(doc)

        em = p.espesor_muro

        # ── 1. Distribución de recintos ──────────────────────────────
        recintos = self._layout_recintos(p)

        for r in recintos:
            validator.check_recinto(r.nombre, r.ancho * r.fondo / 1_000_000)
        validator.check_programa(sum(r.ancho * r.fondo / 1_000_000 for r in recintos))

        # ── 2. Ejes (centro de cada muro) ────────────────────────────
        xs_axis, ys_axis = self._collect_axes(recintos, em)
        bx1 = p.lote_ancho
        by1 = (max(r.y + r.fondo + em for r in recintos)
               if recintos else p.lote_fondo)

        # ── 3. Malla de ejes (CENTER, sobresalen EXT_EJE) ────────────
        self._draw_axes(msp, xs_axis, ys_axis, bx1, by1)

        # ── 4. Muros (LWPOLYLINE + LINE, regla eje ± em/2) ───────────
        self._draw_walls(msp, p, recintos, em, bx1, by1)

        # ── 5. Etiquetas de recintos ─────────────────────────────────
        for r in recintos:
            self._draw_room_label(msp, r)

        # ── 6. Puertas (LINE umbral + ARC batiente 90°) ───────────────
        for r in recintos:
            self._draw_door(msp, r, em)

        # ── 7. Ventanas (triple línea, muro exterior) ─────────────────
        for r in recintos:
            self._draw_window(msp, r, p, em)

        # ── 8. Sistema de agentes estructurales ──────────────────────
        #   AnalistaEspacial → IngenieroNormativo → GeneradorGeometria
        by1_calc = (max(r.y + r.fondo + em for r in recintos)
                    if recintos else p.lote_fondo)
        recintos_dicts = [
            {"x": r.x, "y": r.y, "ancho": r.ancho,
             "fondo": r.fondo, "nombre": r.nombre}
            for r in recintos
        ]
        topo = AnalistaEspacial().analizar(
            recintos=recintos_dicts,
            espesor_muro=em,
            lote_ancho=p.lote_ancho,
            lote_fondo=by1_calc,
            altura_muro=p.altura_muro,
        )
        meta = MetadatosNormativos(
            norma="NTC-RCDF 2017",
            fc=200.0,
            fy=4200.0,
            recubrimiento=25.0,
        )
        modelo = IngenieroNormativo().disenar(topo, meta)
        GeneradorGeometria().dibujar(doc, msp, modelo)

        # Lista de coordenadas de castillos para el catálogo y SVG
        castillos = [(ev.x, ev.y) for ev in modelo.elementos_verticales
                     if ev.tipo == "CASTILLO"]

        # ── 9. Cadenas de cotas DIMENSION reales ─────────────────────
        if len(xs_axis) > 1:
            add_dimension_chain_h(msp, xs_axis, 0.0, -700)
        if len(ys_axis) > 1:
            add_dimension_chain_v(msp, ys_axis, 0.0, -700)
        add_dimension(msp, (0, 0), (bx1, 0), offset=1500)
        add_dimension(msp, (0, 0), (0, by1),  offset=1500)

        # ── 10. Marcador de corte A-A' ────────────────────────────────
        cut_y = ys_axis[len(ys_axis) // 2] if ys_axis else by1 / 2
        self._draw_cut_marker(msp, 0.0, bx1, cut_y)

        # ── 11. Alzado frontal ────────────────────────────────────────
        alzado_y0 = -(EXT_EJE * 2 + p.altura_muro + LOSA_GROSOR + 2500)
        self._draw_alzado(msp, p, recintos, em, 0.0, alzado_y0, xs_axis, bx1)

        # ── 12. Corte A-A' ────────────────────────────────────────────
        corte_x0 = bx1 + EXT_EJE * 2 + 3000
        self._draw_corte(msp, p, recintos, em, cut_y, corte_x0, bx1)

        # ── 13. Cuadro de rotulación ──────────────────────────────────
        add_title_block(
            msp,
            project=p.project_name,
            drawing="PLANTA ARQUITECTONICA  ESC. 1:50",
            scale="1:50",
            date=p.date,
            origin_x=0.0,
            origin_y=alzado_y0 - 1700,
            width=max(bx1, 12000),
        )

        # ── Serializar ────────────────────────────────────────────────
        buf = StringIO()
        doc.write(buf)
        dxf_bytes = buf.getvalue().encode("utf-8")

        cat = self._build_catalog(p, recintos, castillos)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(dxf_bytes)
            tmp_path = tmp.name
        try:
            from ..core.pdf_utils import dxf_to_pdf_bytes
            pdf_bytes = dxf_to_pdf_bytes(
                tmp_path,
                title=f"{p.project_name} — Planta Arquitectonica",
                paper="A1",
            )
        finally:
            os.unlink(tmp_path)

        xlsx_bytes = cat.to_excel_bytes(p.project_name)
        svg = self._build_svg(p, recintos, castillos, xs_axis, ys_axis)

        return PlantaResult(
            dxf_bytes=dxf_bytes, pdf_bytes=pdf_bytes, xlsx_bytes=xlsx_bytes,
            catalog=cat, ntc_report=validator.report(), svg_preview=svg,
            modelo_estructural=modelo,
        )

    # ------------------------------------------------------------------
    # Setup de capas  (Estándar 1)
    # ------------------------------------------------------------------

    def _setup_layers(self, doc) -> None:
        """Capas arquitectónicas con colores, grosores y linetypes."""
        defs = {
            "A-EJE":        (ACI_RED,     13,  "CENTER"),
            "A-MURO":       (ACI_WHITE,   30,  "Continuous"),
            "A-COTA":       (ACI_YELLOW,  13,  "Continuous"),
            "A-PUERTA":     (ACI_GREEN,   18,  "Continuous"),
            "A-VENTANA":    (ACI_CYAN,    18,  "Continuous"),
            "A-MUEBLE":     (ACI_GRAY,     9,  "Continuous"),
            "A-CORTADO":    (ACI_WHITE,   50,  "Continuous"),
            "A-PROYECTADO": (ACI_GRAY,     9,  "Continuous"),
            "T-TITULO":     (ACI_WHITE,   25,  "Continuous"),
            "T-TEXTO":      (ACI_WHITE,   13,  "Continuous"),
            "E-CASTILLO":   (ACI_MAGENTA, 35,  "Continuous"),
        }
        for name, (color, lw, lt) in defs.items():
            if name not in doc.layers:
                doc.layers.add(name, color=color, lineweight=lw)
            else:
                lay = doc.layers.get(name)
                lay.dxf.color = color
                lay.dxf.lineweight = lw
            if lt != "Continuous":
                try:
                    doc.layers.get(name).dxf.linetype = lt
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Distribución de recintos
    # ------------------------------------------------------------------

    def _layout_recintos(self, p: PlantaParams) -> List[Recinto]:
        em = p.espesor_muro
        recintos: List[Recinto] = []
        cur_x, cur_y = em, em
        row_height = 0.0

        for rd in p.recintos:
            nombre = rd.get("nombre", "RECINTO")
            an = max(float(rd.get("ancho", 3000)), 900.0)
            fn = max(float(rd.get("fondo", 3000)), 900.0)

            if cur_x + an + em > p.lote_ancho:
                cur_x = em
                cur_y += row_height + em
                row_height = 0.0

            recintos.append(Recinto(
                nombre=nombre, x=cur_x, y=cur_y, ancho=an, fondo=fn,
                es_banyo=any(k in nombre.upper() for k in
                             ["BANO", "BAÑ", "WC", "SANITARIO"]),
                es_cocina="COCINA" in nombre.upper(),
            ))
            cur_x += an + em
            row_height = max(row_height, fn)

        return recintos

    # ------------------------------------------------------------------
    # Posiciones de ejes  (Estándar 2)
    # ------------------------------------------------------------------

    def _collect_axes(self, recintos: List[Recinto],
                      em: float) -> Tuple[List[float], List[float]]:
        """
        xs = posiciones X (ejes verticales)   → 1, 2, 3...
        ys = posiciones Y (ejes horizontales) → A, B, C...
        Centro de muro = cara interior ± em/2
        """
        xs: set = set()
        ys: set = set()
        for r in recintos:
            xs.add(r.x - em / 2)
            xs.add(r.x + r.ancho + em / 2)
            ys.add(r.y - em / 2)
            ys.add(r.y + r.fondo + em / 2)
        return sorted(xs), sorted(ys)

    # ------------------------------------------------------------------
    # Malla de ejes (Estándar 2 + globos Estándar 3)
    # ------------------------------------------------------------------

    def _draw_axes(self, msp, xs: List[float], ys: List[float],
                   bx1: float, by1: float) -> None:
        ext   = EXT_EJE
        r     = RADIO_GLOBO
        attrs = {"layer": "A-EJE", "linetype": "CENTER", "lineweight": 13}
        alpha = string.ascii_uppercase

        # Ejes verticales → 1, 2, 3...
        for i, x in enumerate(xs):
            msp.add_line((x, -ext), (x, by1 + ext), dxfattribs=attrs)
            label = str(i + 1)
            add_eje_bubble(msp, x, by1 + ext + r, label, radius=r)
            add_eje_bubble(msp, x, -ext - r,       label, radius=r)

        # Ejes horizontales → A, B, C...
        for i, y in enumerate(ys):
            msp.add_line((-ext, y), (bx1 + ext, y), dxfattribs=attrs)
            label = alpha[i] if i < 26 else f"A{i - 25}"
            add_eje_bubble(msp, -ext - r,      y, label, radius=r)
            add_eje_bubble(msp, bx1 + ext + r, y, label, radius=r)

    # ------------------------------------------------------------------
    # Muros (Estándar 2: eje ± em/2)
    # ------------------------------------------------------------------

    def _draw_walls(self, msp, p: PlantaParams, recintos: List[Recinto],
                    em: float, bx1: float, by1: float) -> None:
        # Perímetro exterior
        msp.add_lwpolyline(
            [(0, 0), (bx1, 0), (bx1, by1), (0, by1)],
            close=True,
            dxfattribs={"layer": "A-MURO", "lineweight": 50},
        )
        msp.add_lwpolyline(
            [(em, em), (bx1 - em, em), (bx1 - em, by1 - em), (em, by1 - em)],
            close=True,
            dxfattribs={"layer": "A-MURO", "lineweight": 25},
        )

        # Muros interiores (dos líneas por pared)
        drawn: set = set()
        for r in recintos:
            xw = r.x + r.ancho + em / 2
            key_v = ("v", round(xw, 1))
            if key_v not in drawn:
                drawn.add(key_v)
                for offset in (-em / 2, em / 2):
                    msp.add_line(
                        (xw + offset, r.y - em / 2),
                        (xw + offset, r.y + r.fondo + em / 2),
                        dxfattribs={"layer": "A-MURO", "lineweight": 25},
                    )
            yw = r.y + r.fondo + em / 2
            key_h = ("h", round(yw, 1))
            if key_h not in drawn:
                drawn.add(key_h)
                for offset in (-em / 2, em / 2):
                    msp.add_line(
                        (r.x - em / 2, yw + offset),
                        (r.x + r.ancho + em / 2, yw + offset),
                        dxfattribs={"layer": "A-MURO", "lineweight": 25},
                    )

    # ------------------------------------------------------------------
    # Etiquetas de recintos
    # ------------------------------------------------------------------

    def _draw_room_label(self, msp, r: Recinto) -> None:
        cx = r.x + r.ancho / 2
        cy = r.y + r.fondo / 2
        h  = min(200, max(80, r.ancho * 0.07))
        add_centered_text(msp, _safe(r.nombre), cx, cy + h * 0.6, h, "T-TEXTO")
        area = r.ancho * r.fondo / 1_000_000
        add_centered_text(msp, f"{area:.2f} m2", cx, cy - h * 0.4, h * 0.75, "T-TEXTO")

    # ------------------------------------------------------------------
    # Puertas (LINE umbral + ARC batiente 90°)
    # ------------------------------------------------------------------

    def _draw_door(self, msp, r: Recinto, em: float) -> None:
        pw = (PUERTA_BANO if r.es_banyo else
              PUERTA_INT  if r.ancho < 2000 else PUERTA_EXT)
        pw = min(pw, r.ancho * 0.8)

        px0 = r.x + (r.ancho - pw) / 2
        wy  = r.y

        msp.add_line(
            (px0, wy), (px0 + pw, wy),
            dxfattribs={"layer": "A-PUERTA", "lineweight": 25},
        )
        msp.add_line(
            (px0, wy), (px0, wy + pw),
            dxfattribs={"layer": "A-PUERTA", "lineweight": 13},
        )
        msp.add_arc(
            center=(px0, wy),
            radius=pw,
            start_angle=0,
            end_angle=90,
            dxfattribs={"layer": "A-PUERTA", "lineweight": 9},
        )

    # ------------------------------------------------------------------
    # Ventanas (triple línea en muro exterior)
    # ------------------------------------------------------------------

    def _draw_window(self, msp, r: Recinto, p: PlantaParams,
                     em: float) -> None:
        nombre_up = r.nombre.upper()
        tiene_ventana = any(k in nombre_up for k in
                            ["SALA", "RECAMARA", "COMEDOR", "COCINA", "ESTUDIO"])
        if not tiene_ventana:
            return
        if r.y > em * 1.5:
            return

        ww  = min(VENTANA_ANCHO, r.ancho * 0.55)
        wx0 = r.x + (r.ancho - ww) / 2
        wy  = r.y

        for offset, lw in [(-em * 0.85, 25), (-em * 0.5, 13), (-em * 0.15, 25)]:
            msp.add_line(
                (wx0, wy + offset), (wx0 + ww, wy + offset),
                dxfattribs={"layer": "A-VENTANA", "lineweight": lw},
            )

    # ------------------------------------------------------------------
    # Castillos NTC
    # ------------------------------------------------------------------

    def _suggest_castillos(self, p: PlantaParams, recintos: List[Recinto],
                           em: float) -> List[Tuple[float, float]]:
        pts: set = set()
        sep_mm = MAX_SEP_CASTILLOS * 1000
        for r in recintos:
            for ax in (r.x - em / 2, r.x + r.ancho + em / 2):
                for ay in (r.y - em / 2, r.y + r.fondo + em / 2):
                    pts.add((ax, ay))
            for n in range(1, int(r.ancho / sep_mm) + 1):
                pts.add((r.x + n * sep_mm, r.y - em / 2))
                pts.add((r.x + n * sep_mm, r.y + r.fondo + em / 2))
            for n in range(1, int(r.fondo / sep_mm) + 1):
                pts.add((r.x - em / 2, r.y + n * sep_mm))
                pts.add((r.x + r.ancho + em / 2, r.y + n * sep_mm))
        return list(pts)

    def _draw_castillo(self, msp, cx: float, cy: float, lado: float) -> None:
        h = lado / 2
        msp.add_lwpolyline(
            [(cx - h, cy - h), (cx + h, cy - h),
             (cx + h, cy + h), (cx - h, cy + h)],
            close=True,
            dxfattribs={"layer": "E-CASTILLO", "lineweight": 35},
        )
        msp.add_line((cx - h, cy - h), (cx + h, cy + h),
                     dxfattribs={"layer": "E-CASTILLO"})
        msp.add_line((cx + h, cy - h), (cx - h, cy + h),
                     dxfattribs={"layer": "E-CASTILLO"})

    # ------------------------------------------------------------------
    # Marcador de corte A-A'
    # ------------------------------------------------------------------

    def _draw_cut_marker(self, msp, bx0: float, bx1: float,
                         cut_y: float) -> None:
        ext = 400
        msp.add_line(
            (bx0 - ext, cut_y), (bx1 + ext, cut_y),
            dxfattribs={"layer": "A-COTA", "linetype": "DASHED", "lineweight": 35},
        )
        for x_tag, tag in ((bx0 - ext - 200, "A"), (bx1 + ext + 200, "A'")):
            add_centered_text(msp, tag, x_tag, cut_y, 300, "A-COTA")

    # ------------------------------------------------------------------
    # Alzado frontal (Estándar 3)
    # ------------------------------------------------------------------

    def _draw_alzado(self, msp, p: PlantaParams, recintos: List[Recinto],
                     em: float, ax0: float, ay0: float,
                     xs_axis: List[float], bx1: float) -> None:
        am = p.altura_muro
        ls = LOSA_GROSOR
        w  = bx1

        add_centered_text(
            msp, "ALZADO FRONTAL  ESC. 1:50",
            ax0 + w / 2, ay0 + am + ls + 500, 200, "T-TITULO",
        )

        # Líneas de nivel
        for dz, label in [
            (0,       "NPT +- 0.00"),
            (am,      f"CERRAMIENTO +{am/1000:.2f}m"),
            (am + ls, f"LOSA  +{(am+ls)/1000:.2f}m"),
        ]:
            y = ay0 + dz
            msp.add_line(
                (ax0 - 800, y), (ax0 + w + 200, y),
                dxfattribs={"layer": "A-PROYECTADO", "lineweight": 9},
            )
            add_centered_text(msp, _safe(label), ax0 - 1500, y, 100, "A-COTA")

        # Silueta exterior
        msp.add_line(
            (ax0, ay0), (ax0 + w, ay0),
            dxfattribs={"layer": "A-CORTADO", "lineweight": 70},
        )
        for xx in (ax0, ax0 + w):
            msp.add_line(
                (xx, ay0), (xx, ay0 + am),
                dxfattribs={"layer": "A-CORTADO", "lineweight": 50},
            )
        msp.add_line(
            (ax0, ay0 + am), (ax0 + w, ay0 + am),
            dxfattribs={"layer": "A-CORTADO", "lineweight": 50},
        )
        msp.add_lwpolyline(
            [(ax0, ay0 + am), (ax0 + w, ay0 + am),
             (ax0 + w, ay0 + am + ls), (ax0, ay0 + am + ls)],
            close=True,
            dxfattribs={"layer": "A-CORTADO", "lineweight": 35},
        )

        # Proyecciones de ejes alineadas (Regla 3)
        for x_ax in xs_axis:
            xa = ax0 + x_ax
            msp.add_line(
                (xa, ay0 - 300), (xa, ay0 + am + ls + 300),
                dxfattribs={"layer": "A-EJE", "linetype": "CENTER", "lineweight": 9},
            )

        # Vanos de fachada
        for r in recintos:
            if r.y > em * 1.5:
                continue
            pw  = (PUERTA_BANO if r.es_banyo else PUERTA_EXT)
            pw  = min(pw, r.ancho * 0.8)
            pdx = r.x + (r.ancho - pw) / 2
            ph  = min(2100, int(am * 0.78))
            xa0 = ax0 + pdx
            xa1 = ax0 + pdx + pw
            for xx in (xa0, xa1):
                msp.add_line((xx, ay0), (xx, ay0 + ph),
                             dxfattribs={"layer": "A-PUERTA", "lineweight": 25})
            msp.add_line((xa0, ay0 + ph), (xa1, ay0 + ph),
                         dxfattribs={"layer": "A-PUERTA", "lineweight": 18})

            nombre_up = r.nombre.upper()
            if any(k in nombre_up for k in
                   ["SALA", "RECAMARA", "COMEDOR", "ESTUDIO"]):
                ww  = min(VENTANA_ANCHO, r.ancho * 0.55)
                wdx = r.x + (r.ancho - ww) / 2
                wx0 = ax0 + wdx
                wx1 = ax0 + wdx + ww
                wy0 = ay0 + ANTEPECHO
                wy1 = ay0 + ANTEPECHO + VENTANA_ALTO
                if wy1 <= ay0 + am - 100:
                    for xx in (wx0, wx1):
                        msp.add_line((xx, wy0), (xx, wy1),
                                     dxfattribs={"layer": "A-VENTANA",
                                                 "lineweight": 25})
                    for yy, lw in ((wy0, 25), (wy1, 25), ((wy0 + wy1) / 2, 13)):
                        msp.add_line((wx0, yy), (wx1, yy),
                                     dxfattribs={"layer": "A-VENTANA",
                                                 "lineweight": lw})

        # Cotas de altura
        add_dimension(msp, (ax0 + w + 300, ay0),
                      (ax0 + w + 300, ay0 + am), offset=600)
        add_dimension(msp, (ax0 + w + 300, ay0 + am),
                      (ax0 + w + 300, ay0 + am + ls), offset=600)

    # ------------------------------------------------------------------
    # Corte A-A' (Estándar 4: cortado vs proyectado)
    # ------------------------------------------------------------------

    def _draw_corte(self, msp, p: PlantaParams, recintos: List[Recinto],
                    em: float, cut_y: float, cx0: float, bx1: float) -> None:
        am = p.altura_muro
        ls = LOSA_GROSOR
        w  = bx1

        add_centered_text(
            msp, "CORTE  A - A'  ESC. 1:50",
            cx0 + w / 2, am + ls + 500, 200, "T-TITULO",
        )

        # Suelo
        msp.add_line(
            (cx0, 0), (cx0 + w, 0),
            dxfattribs={"layer": "A-CORTADO", "lineweight": 70},
        )
        for di in (200, 380):
            msp.add_line(
                (cx0, -di), (cx0 + w, -di),
                dxfattribs={"layer": "A-PROYECTADO", "lineweight": 9},
            )

        # Muros exteriores cortados
        for xw in (0.0, bx1 - em):
            pts = [(cx0 + xw, 0), (cx0 + xw + em, 0),
                   (cx0 + xw + em, am), (cx0 + xw, am)]
            msp.add_lwpolyline(
                pts, close=True,
                dxfattribs={"layer": "A-CORTADO", "lineweight": 50},
            )
            for hh in range(0, int(am), 300):
                msp.add_line(
                    (cx0 + xw, hh), (cx0 + xw + em, hh + 150),
                    dxfattribs={"layer": "A-CORTADO", "lineweight": 9},
                )

        # Muros interiores cortados
        recintos_en_corte = [
            r for r in recintos
            if (r.y - em / 2) <= cut_y <= (r.y + r.fondo + em / 2)
        ]
        x_paredes: set = set()
        for r in recintos_en_corte:
            x_paredes.add(r.x + r.ancho)

        for xp in sorted(x_paredes):
            if xp <= 0 or xp >= bx1:
                continue
            xa0 = cx0 + xp
            xa1 = cx0 + xp + em
            msp.add_lwpolyline(
                [(xa0, 0), (xa1, 0), (xa1, am), (xa0, am)],
                close=True,
                dxfattribs={"layer": "A-CORTADO", "lineweight": 50},
            )
            for hh in range(0, int(am), 300):
                msp.add_line(
                    (xa0, hh), (xa1, hh + 150),
                    dxfattribs={"layer": "A-CORTADO", "lineweight": 9},
                )

        # Etiquetas
        for r in recintos_en_corte:
            cx = cx0 + r.x + r.ancho / 2
            add_centered_text(msp, _safe(r.nombre), cx, am * 0.5, 120, "T-TEXTO")

        # Proyección de muros traseros (thin)
        for r in recintos:
            if r.y > cut_y:
                for xv in (cx0 + r.x, cx0 + r.x + r.ancho):
                    msp.add_line(
                        (xv, 0), (xv, am),
                        dxfattribs={"layer": "A-PROYECTADO", "lineweight": 9},
                    )

        # Losa cortada
        msp.add_lwpolyline(
            [(cx0, am), (cx0 + w, am), (cx0 + w, am + ls), (cx0, am + ls)],
            close=True,
            dxfattribs={"layer": "A-CORTADO", "lineweight": 35},
        )
        for xi in range(0, int(w), 400):
            msp.add_line(
                (cx0 + xi, am), (cx0 + xi + 200, am + ls),
                dxfattribs={"layer": "A-PROYECTADO", "lineweight": 9},
            )

        # Firme
        msp.add_lwpolyline(
            [(cx0, -PISO_GROSOR), (cx0 + w, -PISO_GROSOR),
             (cx0 + w, 0), (cx0, 0)],
            close=True,
            dxfattribs={"layer": "A-CORTADO", "lineweight": 25},
        )

        # Líneas de nivel
        for dz, label in [
            (0,       "NPT +- 0.00"),
            (am,      f"CERR. +{am/1000:.2f}m"),
            (am + ls, f"LOSA +{(am+ls)/1000:.2f}m"),
        ]:
            msp.add_line(
                (cx0 - 200, dz), (cx0 + w + 100, dz),
                dxfattribs={"layer": "A-PROYECTADO", "lineweight": 9},
            )
            add_centered_text(msp, _safe(label), cx0 - 800, dz, 100, "A-COTA")

        # Cotas
        add_dimension(msp, (cx0 + w + 400, 0),
                      (cx0 + w + 400, am), offset=600)
        add_dimension(msp, (cx0 + w + 400, am),
                      (cx0 + w + 400, am + ls), offset=600)

    # ------------------------------------------------------------------
    # Catálogo de conceptos
    # ------------------------------------------------------------------

    def _build_catalog(self, p: PlantaParams, recintos: List[Recinto],
                       castillos: List[Tuple]) -> CatalogoConceptos:
        cat = CatalogoConceptos()
        em  = p.espesor_muro / 1000
        am  = p.altura_muro  / 1000

        ml_muro = (sum(2 * (r.ancho + r.fondo) / 1000 for r in recintos)
                   + 2 * (p.lote_ancho + p.lote_fondo) / 1000)
        m2_muro = ml_muro * am

        cat.agregar("10.01",
                    "Muro tabique rojo (15x20x30 cm), junteado y plomado", "m2",
                    round(m2_muro, 2))
        m2_aplano = m2_muro * 2
        cat.agregar("11.01",
                    "Aplanado mortero cemento-arena 1:4, e=1.5 cm", "m2",
                    round(m2_aplano, 2))
        area_piso = sum(r.ancho * r.fondo / 1e6 for r in recintos)
        cat.agregar("12.01",
                    "Firme de concreto fc=150 kg/cm2, e=8 cm, pulido", "m2",
                    round(area_piso, 2))
        cat.agregar("13.01",
                    f"Castillo concreto {int(CASTILLO_MIN['lado'])}x"
                    f"{int(CASTILLO_MIN['lado'])} mm, fc=200 kg/cm2, 3 var No.3", "pza",
                    len(castillos))
        cat.agregar("13.02",
                    "Dala de cerramiento 15x15 cm, fc=200 kg/cm2, 2 var No.3", "ml",
                    round(ml_muro, 2))
        cat.agregar("14.01",
                    "Pintura vinilica, 2 manos (incluye sellador)", "m2",
                    round(m2_aplano, 2))
        return cat

    # ------------------------------------------------------------------
    # SVG preview
    # ------------------------------------------------------------------

    def _build_svg(self, p: PlantaParams, recintos: List[Recinto],
                   castillos: List[Tuple],
                   xs_axis: List[float], ys_axis: List[float]) -> str:
        W, H = 600, 500
        pad  = 50
        sx   = (W - pad * 2) / p.lote_ancho
        sy   = (H - pad * 2 - 20) / p.lote_fondo
        s    = min(sx, sy)

        def tx(x): return pad + x * s
        def ty(y): return H - pad - y * s

        ln = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'style="background:#1e1e1e;font-family:monospace">',
        ]

        # Ejes
        for x in xs_axis:
            ln.append(
                f'<line x1="{tx(x):.1f}" y1="{pad}" x2="{tx(x):.1f}" '
                f'y2="{H-pad}" stroke="#ff4444" stroke-width="0.6" '
                f'stroke-dasharray="4,3" opacity="0.7"/>'
            )
        for y in ys_axis:
            ln.append(
                f'<line x1="{pad}" y1="{ty(y):.1f}" x2="{W-pad}" '
                f'y2="{ty(y):.1f}" stroke="#ff4444" stroke-width="0.6" '
                f'stroke-dasharray="4,3" opacity="0.7"/>'
            )

        # Perímetro
        ln.append(
            f'<rect x="{tx(0):.1f}" y="{ty(p.lote_fondo):.1f}" '
            f'width="{p.lote_ancho*s:.1f}" height="{p.lote_fondo*s:.1f}" '
            f'fill="none" stroke="#888" stroke-width="2"/>',
        )

        COLORS = {
            "SALA":     "#1a3a5c", "COMEDOR":  "#1a4a3a",
            "COCINA":   "#3a2a1a", "RECAMARA": "#2a1a3a",
            "BANO":     "#1a3a3a", "PATIO":    "#1a3a2a",
            "ESTUDIO":  "#2a3a1a", "GARAGE":   "#3a3a1a",
        }

        for r in recintos:
            col = "#1a2a3a"
            for k, v in COLORS.items():
                if k in r.nombre.upper():
                    col = v
                    break
            ln.append(
                f'<rect x="{tx(r.x):.1f}" y="{ty(r.y + r.fondo):.1f}" '
                f'width="{r.ancho*s:.1f}" height="{r.fondo*s:.1f}" '
                f'fill="{col}" stroke="#5BA3E0" stroke-width="1.5"/>'
            )
            # Arco de puerta
            pw  = (PUERTA_BANO if r.es_banyo else PUERTA_INT) * s
            dcx = tx(r.x + (r.ancho - (PUERTA_BANO if r.es_banyo
                                        else PUERTA_INT)) / 2)
            dcy = ty(r.y)
            ln.append(
                f'<path d="M{dcx:.1f},{dcy:.1f} '
                f'A{pw:.1f},{pw:.1f} 0 0,1 {dcx:.1f},{dcy - pw:.1f}" '
                f'fill="none" stroke="#44cc44" stroke-width="0.8"/>'
            )
            ln.append(
                f'<line x1="{dcx:.1f}" y1="{dcy:.1f}" '
                f'x2="{dcx + pw:.1f}" y2="{dcy:.1f}" '
                f'stroke="#44cc44" stroke-width="0.8"/>'
            )
            fs = max(7, min(12, int(r.ancho * s * 0.12)))
            ln.append(
                f'<text x="{tx(r.x + r.ancho/2):.1f}" '
                f'y="{ty(r.y + r.fondo/2):.1f}" fill="#cccccc" '
                f'font-size="{fs}" text-anchor="middle" '
                f'dominant-baseline="middle">{r.nombre}</text>'
            )

        # Castillos
        for cxc, cyc in castillos:
            h = CASTILLO_MIN["lado"] / 2 * s
            ln.append(
                f'<rect x="{tx(cxc) - h:.1f}" y="{ty(cyc) - h:.1f}" '
                f'width="{h*2:.1f}" height="{h*2:.1f}" '
                f'fill="#ff44aa" opacity="0.85"/>'
            )

        # Leyenda
        row = H - 22
        ln += [
            f'<rect x="10" y="{row-8}" width="10" height="10" '
            f'fill="#ff44aa" opacity="0.85"/>',
            f'<text x="24" y="{row}" fill="#999" font-size="9">Castillo NTC</text>',
            f'<line x1="100" y1="{row-3}" x2="115" y2="{row-3}" '
            f'stroke="#44cc44" stroke-width="1.5"/>',
            f'<text x="119" y="{row}" fill="#999" font-size="9">Puerta</text>',
            f'<line x1="160" y1="{row-3}" x2="175" y2="{row-3}" '
            f'stroke="#ff4444" stroke-dasharray="3,2" stroke-width="0.8"/>',
            f'<text x="179" y="{row}" fill="#999" font-size="9">Eje</text>',
            f'<line x1="205" y1="{row-3}" x2="220" y2="{row-3}" '
            f'stroke="#4499ff" stroke-width="1.5"/>',
            f'<text x="224" y="{row}" fill="#999" font-size="9">Muro</text>',
        ]

        ln.append("</svg>")
        return "\n".join(ln)
