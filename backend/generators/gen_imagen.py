"""
gen_imagen.py
-------------
Módulo 4 — Conversión de Imagen a DXF.

Portado del proyecto image-to-dxf e integrado en arqgen.
Soporta tres modos:
  * trace  — trazado de contornos con LWPOLYLINE / SPLINE
  * hatch  — contornos rellenos (HATCH SOLID)
  * pixel  — cada píxel → entidad SOLID  (solo imágenes pequeñas)

Devuelve bytes del DXF directamente (sin escribir al disco).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from io import StringIO
from typing import List, Optional, Tuple

import cv2
import numpy as np
import ezdxf
from PIL import Image


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ImagenResult:
    dxf_bytes:     bytes
    contour_count: int
    entity_count:  int
    img_width:     int
    img_height:    int
    dxf_width_mm:  float
    dxf_height_mm: float
    mode:          str


# ---------------------------------------------------------------------------
# Params
# ---------------------------------------------------------------------------

@dataclass
class ImagenParams:
    image_bytes:    bytes           # contenido del archivo de imagen
    mode:           str  = "trace"  # trace | hatch | pixel
    scale:          float = 0.1     # mm/px  (0.1 → 1 px = 0.1 mm)
    threshold:      int   = 127     # 0–255  umbral de binarización
    min_area:       float = 10.0    # px²   área mínima de contorno
    approx_epsilon: float = 0.5     # Douglas-Peucker simplificación
    spline:         bool  = False   # usar SPLINE en vez de LWPOLYLINE
    lineweight:     int   = 25      # 1/100 mm
    title:          str   = ""      # título para bloque INFO
    layer_contour:  str   = "CONTORNOS"
    layer_hatch:    str   = "RELLENOS"
    layer_pixel:    str   = "PIXELES"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_gray_from_bytes(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("No se pudo decodificar la imagen.")
    return gray


def _threshold_img(gray: np.ndarray, thr: int) -> np.ndarray:
    _, binary = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY_INV)
    return binary


def _find_contours(binary: np.ndarray, min_area: float,
                   epsilon: float) -> List[np.ndarray]:
    contours, _ = cv2.findContours(binary, cv2.RETR_CCOMP,
                                   cv2.CHAIN_APPROX_NONE)
    result = []
    for c in contours:
        if cv2.contourArea(c) < min_area:
            continue
        if epsilon > 0:
            c = cv2.approxPolyDP(c, epsilon, True)
        result.append(c)
    return result


def _px2w(pt: Tuple[float, float], h: int,
          scale: float) -> Tuple[float, float]:
    """Pixel (col, row) → coordenadas mundo DXF (mm)."""
    return pt[0] * scale, (h - 1 - pt[1]) * scale


def _add_info_block(msp, title: str, img_w: int, img_h: int,
                    scale: float) -> None:
    doc = msp.doc
    if "INFO" not in doc.layers:
        doc.layers.add("INFO", color=8, lineweight=13)
    x0, y0 = 0.0, -30.0
    lines = [
        title or "Imagen convertida a DXF",
        f"Dimensiones imagen: {img_w} x {img_h} px",
        f"Escala: 1 px = {scale} mm",
        f"Tamano DXF: {img_w*scale:.1f} x {img_h*scale:.1f} mm",
        "Generado con ArqGen | arqgen.io",
    ]
    for i, line in enumerate(lines):
        msp.add_text(line, dxfattribs={
            "layer": "INFO", "height": 5.0,
            "insert": (x0, y0 - i * 7),
        })


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class ImagenGenerator:

    def generate(self, p: ImagenParams) -> ImagenResult:
        gray   = _load_gray_from_bytes(p.image_bytes)
        img_h, img_w = gray.shape
        binary = _threshold_img(gray, p.threshold)

        doc = ezdxf.new("R2010")
        doc.header["$INSUNITS"]    = 4
        doc.header["$MEASUREMENT"] = 1
        msp = doc.modelspace()

        # Crear capas
        for lname, color in [
            (p.layer_contour, 7),
            (p.layer_hatch,   2),
            (p.layer_pixel,   3),
        ]:
            if lname not in doc.layers:
                doc.layers.add(lname, color=color,
                               lineweight=p.lineweight)

        mode = p.mode.lower()

        if mode == "pixel":
            rows, cols = np.where(binary == 255)
            s = p.scale
            for row, col in zip(rows, cols):
                x, y = _px2w((col, row), img_h, s)
                msp.add_solid(
                    [(x, y), (x+s, y), (x, y+s), (x+s, y+s)],
                    dxfattribs={"layer": p.layer_pixel},
                )
        else:
            contours = _find_contours(binary, p.min_area, p.approx_epsilon)
            for c in contours:
                pts = [_px2w((float(pt[0]), float(pt[1])), img_h, p.scale)
                       for pt in c.reshape(-1, 2)]
                if mode == "trace":
                    if p.spline and len(pts) >= 4:
                        msp.add_open_spline(
                            [(x, y, 0.0) for x, y in pts], degree=3,
                            dxfattribs={"layer": p.layer_contour},
                        )
                    else:
                        msp.add_lwpolyline(
                            pts, close=True,
                            dxfattribs={"layer": p.layer_contour},
                        )
                else:  # hatch
                    msp.add_lwpolyline(
                        pts, close=True,
                        dxfattribs={"layer": p.layer_contour},
                    )
                    hatch = msp.add_hatch(dxfattribs={"layer": p.layer_hatch})
                    hatch.set_pattern_fill("SOLID")
                    hatch.paths.add_polyline_path(pts, is_closed=True)

        _add_info_block(msp, p.title, img_w, img_h, p.scale)

        buf = StringIO()
        doc.write(buf)
        dxf_bytes = buf.getvalue().encode("utf-8")

        entity_count = sum(1 for _ in msp)
        n_cont = 0 if mode == "pixel" else len(
            _find_contours(binary, p.min_area, p.approx_epsilon))

        return ImagenResult(
            dxf_bytes     = dxf_bytes,
            contour_count = n_cont,
            entity_count  = entity_count,
            img_width     = img_w,
            img_height    = img_h,
            dxf_width_mm  = img_w * p.scale,
            dxf_height_mm = img_h * p.scale,
            mode          = p.mode,
        )
