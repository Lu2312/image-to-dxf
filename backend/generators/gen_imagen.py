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
    content_type:   str  = ""       # image/* o application/pdf
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
    pre_clean:      bool  = False   # limpieza de ruido
    bg_remove:      bool  = False   # remover fondo
    adaptive:       bool  = False   # binarización adaptativa
    invert:         bool  = True    # invertir (fondo blanco, líneas negras)
    denoise_ksize:  int   = 3       # kernel mediano (impar)
    morph_open:     int   = 0       # apertura morfológica
    morph_close:    int   = 0       # cierre morfológico
    pdf_dpi:        int   = 200     # rasterizado PDF
    enhance_contrast: bool = False  # mejora de contraste automática (CLAHE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pdf_first_page_to_gray(data: bytes, dpi: int) -> np.ndarray:
    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        raise ValueError("PyMuPDF no esta instalado para leer PDFs.") from exc

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
        gray = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)
        return gray
    finally:
        doc.close()


def _load_gray_from_bytes(data: bytes, content_type: str, pdf_dpi: int) -> np.ndarray:
    if content_type == "application/pdf":
        return _pdf_first_page_to_gray(data, pdf_dpi)

    arr = np.frombuffer(data, np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("No se pudo decodificar la imagen.")
    return gray


def _odd_ksize(value: int) -> int:
    if value < 3:
        return 0
    return value if value % 2 == 1 else value + 1


def _preprocess(gray: np.ndarray, p: ImagenParams) -> np.ndarray:
    img = gray
    
    # Mejora de contraste usando CLAHE (ideal para mapas)
    if p.enhance_contrast:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        img = clahe.apply(img)
    
    if p.bg_remove:
        blur = cv2.GaussianBlur(img, (0, 0), sigmaX=15)
        img = cv2.divide(img, blur, scale=255)
    if p.pre_clean:
        k = _odd_ksize(p.denoise_ksize)
        if k:
            img = cv2.medianBlur(img, k)
    return img


def _threshold_img(gray: np.ndarray, thr: int, adaptive: bool, invert: bool) -> np.ndarray:
    mode = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    if adaptive:
        block = 31
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, mode, block, 2
        )
        return binary

    _, binary = cv2.threshold(gray, thr, 255, mode)
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
        "Generado con Lu CAD Studio | lucadstudio.com",
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
        gray = _load_gray_from_bytes(p.image_bytes, p.content_type, p.pdf_dpi)
        gray = _preprocess(gray, p)
        img_h, img_w = gray.shape
        binary = _threshold_img(gray, p.threshold, p.adaptive, p.invert)
        if p.morph_open > 0:
            k = _odd_ksize(p.morph_open) or 3
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        if p.morph_close > 0:
            k = _odd_ksize(p.morph_close) or 3
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

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

        contours: List[np.ndarray] = []
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
        n_cont = 0 if mode == "pixel" else len(contours)

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


def clean_image_bytes(p: ImagenParams) -> bytes:
    """
    Preprocesa la imagen y devuelve un PNG binario (limpio) para vista previa.
    """
    gray = _load_gray_from_bytes(p.image_bytes, p.content_type, p.pdf_dpi)
    gray = _preprocess(gray, p)
    binary = _threshold_img(gray, p.threshold, p.adaptive, p.invert)
    if p.morph_open > 0:
        k = _odd_ksize(p.morph_open) or 3
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    if p.morph_close > 0:
        k = _odd_ksize(p.morph_close) or 3
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    ok, buf = cv2.imencode(".png", binary)
    if not ok:
        raise ValueError("No se pudo generar la imagen limpia.")
    return buf.tobytes()


def generate_preview_svg(p: ImagenParams) -> str:
    """
    Genera un SVG con los contornos detectados superpuestos a la imagen binarizada.
    Útil para previsualizar el DXF antes de descargar.
    """
    gray = _load_gray_from_bytes(p.image_bytes, p.content_type, p.pdf_dpi)
    gray = _preprocess(gray, p)
    img_h, img_w = gray.shape
    binary = _threshold_img(gray, p.threshold, p.adaptive, p.invert)
    
    if p.morph_open > 0:
        k = _odd_ksize(p.morph_open) or 3
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    if p.morph_close > 0:
        k = _odd_ksize(p.morph_close) or 3
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    # Encontrar contornos
    contours = _find_contours(binary, p.min_area, p.approx_epsilon)
    
    # Generar SVG
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{img_w}" height="{img_h}" viewBox="0 0 {img_w} {img_h}">',
        f'<rect width="{img_w}" height="{img_h}" fill="#f0f0f0"/>',
    ]
    
    # Dibujar contornos
    mode = p.mode.lower()
    for c in contours:
        pts = c.reshape(-1, 2)
        if len(pts) < 2:
            continue
            
        # Construir path
        path_data = f"M {pts[0][0]} {pts[0][1]}"
        for pt in pts[1:]:
            path_data += f" L {pt[0]} {pt[1]}"
        path_data += " Z"  # Cerrar path
        
        if mode == "hatch":
            # Relleno sólido
            svg_parts.append(
                f'<path d="{path_data}" fill="#2f75b6" stroke="#1a4d7a" stroke-width="1" opacity="0.8"/>'
            )
        else:  # trace o pixel
            # Solo contorno
            svg_parts.append(
                f'<path d="{path_data}" fill="none" stroke="#e74c3c" stroke-width="2"/>'
            )
    
    # Agregar información de estadísticas
    svg_parts.append(
        f'<text x="10" y="20" fill="#333" font-family="Arial" font-size="14" font-weight="bold">'
        f'Contornos detectados: {len(contours)}</text>'
    )
    svg_parts.append(
        f'<text x="10" y="40" fill="#666" font-family="Arial" font-size="12">'
        f'Modo: {p.mode} | Tamaño: {img_w}×{img_h}px | Escala: {p.scale}mm/px</text>'
    )
    
    svg_parts.append('</svg>')
    
    return ''.join(svg_parts)
