"""
image_to_dxf.py
---------------
High-quality image to DXF converter optimised for AutoCAD.

Supported strategies
--------------------
1. TRACE   – vectorises the image by tracing contours (OpenCV) and writes
              them as LWPOLYLINE / SPLINE entities.
2. HATCH   – same contours, but fills closed shapes with solid HATCH
              entities (great for logos / silhouettes).
3. PIXEL   – converts every non-white pixel to a tiny filled square
              (SOLID entity).  Use only for small images.

DXF output
----------
* Version: AC1015 (AutoCAD 2000) – compatible with all modern AutoCAD
  releases while remaining broadly supported.
* All geometry lives on named layers; colours follow AutoCAD ACI.
* Units are millimetres by default; pass `scale` to change pixel→mm ratio.
* An optional INFO layer carries a title block with metadata.
"""

from __future__ import annotations

import datetime
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import ezdxf
import numpy as np
from ezdxf.enums import TextEntityAlignment
from PIL import Image


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ConversionResult:
    """Information returned by :func:`convert`."""

    path: Path
    """Path to the created DXF file."""

    contour_count: int
    """Number of contours detected in the source image."""

    entity_count: int
    """Number of DXF entities written to the model-space."""

    img_width: int
    """Source image width in pixels."""

    img_height: int
    """Source image height in pixels."""

    dxf_width: float
    """Bounding-box width of the drawing in millimetres."""

    dxf_height: float
    """Bounding-box height of the drawing in millimetres."""

    def __str__(self) -> str:  # pragma: no cover
        return (
            f"{self.path}  "
            f"[{self.contour_count} contours, {self.entity_count} entities, "
            f"{self.dxf_width:.1f}×{self.dxf_height:.1f} mm]"
        )

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_gray(path: str | Path) -> np.ndarray:
    """Load any image and return an 8-bit grayscale array."""
    img = Image.open(path).convert("L")
    return np.array(img, dtype=np.uint8)


def _threshold(gray: np.ndarray, threshold: int) -> np.ndarray:
    """Return a binary mask: foreground = 255, background = 0."""
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    return binary


def _find_contours(
    binary: np.ndarray,
    min_area: float = 10.0,
    approx_epsilon: float = 0.5,
) -> List[np.ndarray]:
    """
    Extract external + hole contours, optionally approximate them.

    Parameters
    ----------
    binary        : uint8 mask, foreground = 255
    min_area      : discard contours with area < min_area pixels²
    approx_epsilon: Douglas-Peucker epsilon (pixels).  0 = keep all points.
    """
    contours, _ = cv2.findContours(
        binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE
    )
    result = []
    for c in contours:
        if cv2.contourArea(c) < min_area:
            continue
        if approx_epsilon > 0:
            peri = cv2.arcLength(c, True)
            c = cv2.approxPolyDP(c, approx_epsilon, True)
        result.append(c)
    return result


def _pixel_to_world(
    pt: Tuple[float, float],
    img_height: int,
    scale: float,
    origin: Tuple[float, float] = (0.0, 0.0),
) -> Tuple[float, float]:
    """
    Convert image pixel coordinates to DXF world coordinates.

    OpenCV uses (col, row) with row=0 at the top.
    DXF / AutoCAD uses (x, y) with y=0 at the bottom.
    """
    col, row = pt
    x = origin[0] + col * scale
    y = origin[1] + (img_height - 1 - row) * scale
    return x, y


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    *,
    mode: str = "trace",
    scale: float = 0.1,          # mm per pixel  (0.1 → 1 px = 0.1 mm)
    threshold: int = 127,        # 0–255 binarisation threshold
    layer_contour: str = "CONTOURS",
    layer_hatch: str = "HATCHES",
    layer_pixel: str = "PIXELS",
    color_contour: int = 7,      # AutoCAD ACI: 7 = white/black
    color_hatch: int = 2,        # AutoCAD ACI: 2 = yellow
    lineweight: int = 25,        # 1/100 mm, e.g. 25 = 0.25 mm
    min_area: float = 10.0,
    approx_epsilon: float = 0.5,
    spline: bool = False,        # use SPLINE instead of LWPOLYLINE for trace
    origin: Tuple[float, float] = (0.0, 0.0),
    title: Optional[str] = None, # optional title written to INFO layer
) -> ConversionResult:
    """
    Convert an image file to a DXF file.

    Parameters
    ----------
    input_path      : path to the source image (PNG, JPG, BMP, TIFF, …)
    output_path     : destination .dxf path; defaults to same dir/name
    mode            : "trace" | "hatch" | "pixel"
    scale           : mm per pixel
    threshold       : greyscale threshold for binarisation (0–255)
    layer_contour   : layer name for contour polylines
    layer_hatch     : layer name for hatch fills
    layer_pixel     : layer name for pixel squares
    color_contour   : AutoCAD ACI colour for contour layer
    color_hatch     : AutoCAD ACI colour for hatch layer
    lineweight      : lineweight in 1/100 mm
    min_area        : minimum contour area in pixels²
    approx_epsilon  : Douglas-Peucker simplification (pixels); 0 = off
    spline          : if True and mode="trace", write SPLINE entities
    origin          : (x, y) world-space origin in mm
    title           : optional drawing title written to the INFO layer

    Returns
    -------
    :class:`ConversionResult` with path, stats, and bounding dimensions.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_suffix(".dxf")
    output_path = Path(output_path)

    mode = mode.lower()
    if mode not in ("trace", "hatch", "pixel"):
        raise ValueError(f"Unknown mode '{mode}'. Choose trace, hatch or pixel.")

    # ---- Load & binarise -------------------------------------------------
    gray = _load_gray(input_path)
    img_h, img_w = gray.shape
    binary = _threshold(gray, threshold)

    # ---- Create DXF document ---------------------------------------------
    doc = ezdxf.new("R2000")   # AC1015 = AutoCAD 2000
    doc.header["$INSUNITS"] = 4   # 4 = millimetres
    doc.header["$MEASUREMENT"] = 1  # metric
    msp = doc.modelspace()

    # ---- Ensure layers exist ----------------------------------------------
    def _add_layer(name: str, color: int, lw: int) -> None:
        if name not in doc.layers:
            doc.layers.add(name, color=color, lineweight=lw)

    _add_layer(layer_contour, color_contour, lineweight)
    _add_layer(layer_hatch, color_hatch, lineweight)
    _add_layer(layer_pixel, 3, lineweight)  # ACI 3 = green

    # ---- PIXEL mode -------------------------------------------------------
    if mode == "pixel":
        rows, cols = np.where(binary == 255)
        for row, col in zip(rows, cols):
            x, y = _pixel_to_world((col, row), img_h, scale, origin)
            dx, dy = scale, scale
            # SOLID: 4 corners (note: AutoCAD SOLID has 3rd/4th point order swapped)
            msp.add_solid(
                [
                    (x,      y),
                    (x + dx, y),
                    (x,      y + dy),
                    (x + dx, y + dy),
                ],
                dxfattribs={"layer": layer_pixel},
            )
        _add_info_block(msp, doc, title, input_path, img_w, img_h, scale, origin)
        doc.saveas(output_path)
        entity_count = sum(1 for _ in msp)
        return ConversionResult(
            path=output_path,
            contour_count=0,
            entity_count=entity_count,
            img_width=img_w,
            img_height=img_h,
            dxf_width=img_w * scale,
            dxf_height=img_h * scale,
        )

    # ---- TRACE / HATCH mode ----------------------------------------------
    contours = _find_contours(binary, min_area=min_area, approx_epsilon=approx_epsilon)

    for contour in contours:
        pts_raw = contour.reshape(-1, 2)
        pts_world = [
            _pixel_to_world((float(p[0]), float(p[1])), img_h, scale, origin)
            for p in pts_raw
        ]

        if mode == "trace":
            if spline and len(pts_world) >= 4:
                # SPLINE entity (cubic B-spline, degree 3)
                pts_3d = [(x, y, 0.0) for x, y in pts_world]
                msp.add_open_spline(
                    pts_3d,
                    degree=3,
                    dxfattribs={"layer": layer_contour},
                )
            else:
                # LWPOLYLINE (closed)
                msp.add_lwpolyline(
                    pts_world,
                    close=True,
                    dxfattribs={"layer": layer_contour},
                )

        elif mode == "hatch":
            # Draw outer contour as LWPOLYLINE
            msp.add_lwpolyline(
                pts_world,
                close=True,
                dxfattribs={"layer": layer_contour},
            )
            # Add solid HATCH
            hatch = msp.add_hatch(
                color=color_hatch,
                dxfattribs={"layer": layer_hatch},
            )
            hatch.set_pattern_fill("SOLID")
            edge_path = hatch.paths.add_polyline_path(
                pts_world, is_closed=True
            )

    _add_info_block(msp, doc, title, input_path, img_w, img_h, scale, origin)
    doc.saveas(output_path)
    entity_count = sum(1 for _ in msp)
    return ConversionResult(
        path=output_path,
        contour_count=len(contours),
        entity_count=entity_count,
        img_width=img_w,
        img_height=img_h,
        dxf_width=img_w * scale,
        dxf_height=img_h * scale,
    )


# ---------------------------------------------------------------------------
# Title-block helper
# ---------------------------------------------------------------------------

def _add_info_block(
    msp,
    doc,
    title: Optional[str],
    source_path: Path,
    img_w: int,
    img_h: int,
    scale: float,
    origin: Tuple[float, float],
) -> None:
    """Write a metadata text block on the INFO layer below the drawing."""
    layer_name = "INFO"
    if layer_name not in doc.layers:
        doc.layers.add(layer_name, color=8, lineweight=13)  # ACI 8 = dark grey

    x0, y0 = origin
    # Place the block 14 mm below the bottom of the drawing
    base_y = y0 - 14.0
    text_height = 2.5

    drawing_title = title or source_path.stem
    lines = [
        f"TITLE: {drawing_title}",
        f"SOURCE: {source_path.name}",
        f"SIZE: {img_w} x {img_h} px  |  SCALE: 1 px = {scale} mm",
        f"DRAWING: {img_w * scale:.1f} x {img_h * scale:.1f} mm",
        f"CREATED: {datetime.date.today().isoformat()}",
    ]

    for i, line in enumerate(lines):
        msp.add_text(
            line,
            dxfattribs={
                "layer": layer_name,
                "height": text_height,
                "insert": (x0, base_y - i * (text_height + 1.5)),
                "color": 8,
            },
        )

    # Separator line above the info block
    msp.add_line(
        (x0, y0 - 2.0),
        (x0 + img_w * scale, y0 - 2.0),
        dxfattribs={"layer": layer_name, "color": 8},
    )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert an image to a DXF file optimised for AutoCAD."
    )
    parser.add_argument("input", help="Source image path")
    parser.add_argument("-o", "--output", default=None, help="Output DXF path")
    parser.add_argument(
        "-m", "--mode",
        choices=["trace", "hatch", "pixel"],
        default="trace",
        help="Conversion mode (default: trace)",
    )
    parser.add_argument(
        "-s", "--scale",
        type=float,
        default=0.1,
        help="mm per pixel (default: 0.1)",
    )
    parser.add_argument(
        "-t", "--threshold",
        type=int,
        default=127,
        help="Greyscale threshold 0-255 (default: 127)",
    )
    parser.add_argument(
        "--min-area",
        type=float,
        default=10.0,
        help="Minimum contour area in pixels² (default: 10)",
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        default=0.5,
        help="Douglas-Peucker simplification in pixels (default: 0.5, 0=off)",
    )
    parser.add_argument(
        "--spline",
        action="store_true",
        help="Use SPLINE entities instead of LWPOLYLINE (trace mode only)",
    )
    parser.add_argument(
        "--lineweight",
        type=int,
        default=25,
        help="Lineweight in 1/100 mm, e.g. 25 = 0.25 mm (default: 25)",
    )
    parser.add_argument(
        "--layer-contour",
        default="CONTOURS",
        help="Layer name for contour entities (default: CONTOURS)",
    )
    parser.add_argument(
        "--layer-hatch",
        default="HATCHES",
        help="Layer name for hatch entities (default: HATCHES)",
    )

    args = parser.parse_args()

    result = convert(
        args.input,
        args.output,
        mode=args.mode,
        scale=args.scale,
        threshold=args.threshold,
        min_area=args.min_area,
        approx_epsilon=args.epsilon,
        spline=args.spline,
        lineweight=args.lineweight,
        layer_contour=args.layer_contour,
        layer_hatch=args.layer_hatch,
    )
    print(f"DXF saved to: {result.path}")
    print(
        f"  Contours : {result.contour_count}\n"
        f"  Entities : {result.entity_count}\n"
        f"  Size     : {result.dxf_width:.1f} x {result.dxf_height:.1f} mm"
    )
