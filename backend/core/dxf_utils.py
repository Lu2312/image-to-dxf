"""
dxf_utils.py  v2
----------------
Helpers compartidos para todos los generadores DXF.

Cambios v2:
  * Formato R2010 (AC1024) — soporte nativo de Unicode
  * Linetypes CENTER y DASHED cargados en el documento
  * DimStyle "ARQGEN" — oblique ticks, texto sobre línea, unidades mm
  * add_title_block: dimensiones a escala 1:50 (legibles en papel)
  * add_centered_text: texto centrado con alineación DXF
  * add_eje_bubble: globo de eje con etiqueta centrada
  * add_dimension_chain_h / _v: cadenas de cotas continuas
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace

from .ntc import LAYERS

# ---------------------------------------------------------------------------
# Módulo-level helpers
# ---------------------------------------------------------------------------

def _safe(text: str) -> str:
    """Reemplaza caracteres especiales del español para compatibilidad DXF."""
    TR = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U", "Ñ": "N",
        "°": "%%d", "²": "2", "³": "3", "—": "-", "–": "-",
    }
    for k, v in TR.items():
        text = text.replace(k, v)
    return text


def _txt(msp: Modelspace, text: str, x: float, y: float,
         height: float, layer: str, halign: int = 0) -> None:
    """Inserta texto simple; halign: 0=left, 1=center, 2=right."""
    attrs: dict = {"layer": layer, "height": height, "insert": (x, y)}
    if halign:
        attrs["halign"] = halign
        attrs["valign"] = 0
        attrs["align_point"] = (x, y)
    msp.add_text(_safe(text), dxfattribs=attrs)


def add_centered_text(msp: Modelspace, text: str,
                      cx: float, cy: float, height: float, layer: str) -> None:
    """Inserta texto centrado (horizontal + vertical) en (cx, cy)."""
    msp.add_text(
        _safe(text),
        dxfattribs={
            "layer":       layer,
            "height":      height,
            "insert":      (cx, cy),
            "align_point": (cx, cy),
            "halign":      1,   # CENTER
            "valign":      2,   # MIDDLE
        },
    )


# ---------------------------------------------------------------------------
# Documento base
# ---------------------------------------------------------------------------

def _setup_linetypes(doc: Drawing) -> None:
    """Carga linetypes CENTER y DASHED si no existen."""
    if "CENTER" not in doc.linetypes:
        doc.linetypes.add(
            "CENTER",
            pattern=[25.0, 18.0, -3.0, 3.0, -3.0],
            description="Center ____ _ ____ _ ____",
        )
    if "DASHED" not in doc.linetypes:
        doc.linetypes.add(
            "DASHED",
            pattern=[12.0, 6.0, -6.0],
            description="Dashed __ __ __ __",
        )


def _setup_dimstyle(doc: Drawing) -> None:
    """Crea estilo dimensional ARQGEN con trazo oblicuo (arquitectónico)."""
    if "ARQGEN" in doc.dimstyles:
        return
    try:
        ds = doc.dimstyles.new("ARQGEN")
        # text
        ds.dxf.dimtxt  = 150    # 150 mm texto = 3 mm en papel a 1:50
        ds.dxf.dimtad  = 1      # texto SOBRE la línea de cota
        ds.dxf.dimgap  = 60     # espacio texto↔línea
        # ticks oblicuos (arquitectónico) — dimtsz>0 desactiva las flechas
        ds.dxf.dimtsz  = 100    # tamaño del tick = 2 mm en papel a 1:50
        # extensiones
        ds.dxf.dimexe  = 120    # extensión más allá de la línea
        ds.dxf.dimexo  = 60     # offset desde el punto de origen
        # formato numérico
        ds.dxf.dimlunit = 2     # decimal
        ds.dxf.dimdec   = 0     # 0 decimales (milímetros enteros)
        ds.dxf.dimrnd   = 1.0   # redondear a 1 mm
    except Exception:
        pass  # Usar estilo Standard como fallback


def new_doc(title: str = "") -> tuple[Drawing, Modelspace]:
    """
    Crea un documento DXF R2010 (Unicode) con:
    - Capas NTC precargadas
    - Linetypes CENTER y DASHED
    - DimStyle ARQGEN (cotas arquitectónicas)
    """
    doc = ezdxf.new("R2010")           # AC1024 — soporte UTF-8
    doc.header["$INSUNITS"]    = 4     # milímetros
    doc.header["$MEASUREMENT"] = 1     # métrico
    doc.header["$DIMSCALE"]    = 1.0

    for name, props in LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name, color=props["color"], lineweight=props["lw"])

    _setup_linetypes(doc)
    _setup_dimstyle(doc)

    msp = doc.modelspace()
    return doc, msp


# ---------------------------------------------------------------------------
# Cuadro de rotulación (a escala 1:50 en mm)
# ---------------------------------------------------------------------------

def add_title_block(
    msp:       Modelspace,
    project:   str,
    drawing:   str,
    scale:     str,
    date:      str,
    sheet:     str   = "01",
    origin_x:  float = 0.0,
    origin_y:  float = -1800.0,
    width:     float = 6000.0,
    drw_scale: int   = 50,        # factor de escala (1:50 → 50)
) -> None:
    """Cuadro de rotulación proporcional a la escala del plano."""
    S = drw_scale    # 1 mm papel → S mm modelo
    x, y = origin_x, origin_y
    H   = 25 * S    # alto del cuadro = 25 mm papel = 1250 mm modelo
    mid = width / 2

    # Marco exterior
    msp.add_lwpolyline(
        [(x, y), (x + width, y), (x + width, y + H), (x, y + H)],
        close=True,
        dxfattribs={"layer": "T-TITULO", "lineweight": 50},
    )
    # Línea divisoria horizontal y vertical
    msp.add_line((x, y + H * 0.55), (x + width, y + H * 0.55),
                 dxfattribs={"layer": "T-TITULO"})
    msp.add_line((x, y + H * 0.25), (x + width, y + H * 0.25),
                 dxfattribs={"layer": "T-TITULO"})
    msp.add_line((x + mid, y), (x + mid, y + H * 0.55),
                 dxfattribs={"layer": "T-TITULO"})

    def _t(text: str, tx: float, ty: float, h_mm: float = 3.5) -> None:
        _txt(msp, text, tx, ty, h_mm * S, "T-TITULO")

    pad = 3 * S
    _t("PROYECTO:", x + pad,       y + H * 0.88, 2.5)
    _t(project,     x + pad,       y + H * 0.68, 4.5)
    _t("PLANO:",    x + pad,       y + H * 0.47, 2.5)
    _t(drawing,     x + pad,       y + H * 0.30, 3.5)
    _t("ESCALA:",   x + mid + pad, y + H * 0.47, 2.5)
    _t(scale,       x + mid + pad, y + H * 0.30, 3.5)
    _t("FECHA:",    x + pad,       y + H * 0.20, 2.5)
    _t(date,        x + pad,       y + H * 0.07, 3.5)
    _t("HOJA:",     x + mid + pad, y + H * 0.20, 2.5)
    _t(sheet,       x + mid + pad, y + H * 0.07, 3.5)
    _t("Generado bajo NTC-RCDF / CONAVI | lucadstudio.com",
       x + pad, y + H * 0.01, 1.8)


# ---------------------------------------------------------------------------
# Ejes estructurales con globo
# ---------------------------------------------------------------------------

def add_eje_bubble(
    msp:    Modelspace,
    cx:     float,
    cy:     float,
    label:  str,
    radius: float = 250,
    layer:  str   = "A-EJE",
) -> None:
    """Dibuja un globo de eje (círculo + etiqueta centrada)."""
    msp.add_circle((cx, cy), radius,
                   dxfattribs={"layer": layer, "lineweight": 18})
    add_centered_text(msp, label, cx, cy, radius * 0.80, layer)


# ---------------------------------------------------------------------------
# Cotas
# ---------------------------------------------------------------------------

def add_dimension(
    msp:    Modelspace,
    p1:     Tuple[float, float],
    p2:     Tuple[float, float],
    offset: float = 500.0,
    dimstyle: str = "ARQGEN",
) -> None:
    """Cota lineal (horizontal o vertical) con offset desde el par de puntos."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    horizontal = abs(dx) >= abs(dy)

    if horizontal:
        base_y = max(p1[1], p2[1]) + offset
        msp.add_linear_dim(
            base=(p1[0], base_y), p1=p1, p2=p2, angle=0,
            dimstyle=dimstyle, dxfattribs={"layer": "A-COTA"},
        ).render()
    else:
        base_x = max(p1[0], p2[0]) + offset
        msp.add_linear_dim(
            base=(base_x, p1[1]), p1=p1, p2=p2, angle=90,
            dimstyle=dimstyle, dxfattribs={"layer": "A-COTA"},
        ).render()


def add_dimension_chain_h(
    msp:      Modelspace,
    xs:       List[float],
    y_ref:    float,
    base_y:   float,
    dimstyle: str = "ARQGEN",
) -> None:
    """Cadena de cotas horizontales en base_y para los X en 'xs'."""
    for i in range(len(xs) - 1):
        msp.add_linear_dim(
            base=(xs[i], base_y),
            p1=(xs[i], y_ref), p2=(xs[i + 1], y_ref),
            angle=0,
            dimstyle=dimstyle,
            dxfattribs={"layer": "A-COTA"},
        ).render()


def add_dimension_chain_v(
    msp:      Modelspace,
    ys:       List[float],
    x_ref:    float,
    base_x:   float,
    dimstyle: str = "ARQGEN",
) -> None:
    """Cadena de cotas verticales en base_x para los Y en 'ys'."""
    for i in range(len(ys) - 1):
        msp.add_linear_dim(
            base=(base_x, ys[i]),
            p1=(x_ref, ys[i]), p2=(x_ref, ys[i + 1]),
            angle=90,
            dimstyle=dimstyle,
            dxfattribs={"layer": "A-COTA"},
        ).render()


# ---------------------------------------------------------------------------
# Rellenos
# ---------------------------------------------------------------------------

def add_hatch_concrete(msp: Modelspace,
                       points: List[Tuple[float, float]]) -> None:
    """Relleno estándar de concreto (ANSI31 a 45°)."""
    hatch = msp.add_hatch(dxfattribs={"layer": "E-HATCH"})
    hatch.set_pattern_fill("ANSI31", scale=3.0, angle=45)
    hatch.paths.add_polyline_path(points, is_closed=True)


def add_hatch_earth(msp: Modelspace,
                    points: List[Tuple[float, float]]) -> None:
    """Relleno de terreno natural."""
    hatch = msp.add_hatch(dxfattribs={"layer": "E-HATCH"})
    hatch.set_pattern_fill("ANSI37", scale=4.0, angle=0)
    hatch.paths.add_polyline_path(points, is_closed=True)


# ---------------------------------------------------------------------------
# Símbolo de varilla
# ---------------------------------------------------------------------------

def add_rebar_symbol(
    msp:         Modelspace,
    center:      Tuple[float, float],
    diameter_mm: float,
    scale:       float = 1.0,
) -> None:
    """Dibuja la sección transversal de una varilla (círculo + cruz)."""
    r = (diameter_mm / 2) * scale
    cx, cy = center
    msp.add_circle((cx, cy), r, dxfattribs={"layer": "E-ARMADO"})
    msp.add_line((cx - r * 0.7, cy), (cx + r * 0.7, cy),
                 dxfattribs={"layer": "E-ARMADO"})
    msp.add_line((cx, cy - r * 0.7), (cx, cy + r * 0.7),
                 dxfattribs={"layer": "E-ARMADO"})
