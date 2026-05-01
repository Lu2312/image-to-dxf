"""
router_imagen.py  —  POST /api/imagen
Convierte una imagen subida (PNG/JPG/BMP) a DXF.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import Response

from ..generators.gen_imagen import ImagenGenerator, ImagenParams

router = APIRouter(prefix="/api/imagen", tags=["Imagen a DXF"])


@router.post("/dxf")
async def imagen_to_dxf(
    file:           UploadFile = File(..., description="Imagen PNG/JPG/BMP"),
    mode:           str   = Form("trace",  description="trace | hatch | pixel"),
    scale:          float = Form(0.1,      description="mm/px (0.1 = 1px → 0.1mm)"),
    threshold:      int   = Form(127,      description="Umbral binarización 0-255"),
    min_area:       float = Form(10.0,     description="Área mínima de contorno (px²)"),
    approx_epsilon: float = Form(0.5,      description="Simplificación Douglas-Peucker"),
    spline:         bool  = Form(False,    description="Usar SPLINE en modo trace"),
    lineweight:     int   = Form(25,       description="Grosor de línea 1/100 mm"),
    title:          str   = Form("",       description="Título del plano"),
):
    """Convierte la imagen subida a DXF y devuelve el archivo binario."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Solo se aceptan archivos de imagen (PNG, JPG, BMP, TIFF).")
    if mode not in ("trace", "hatch", "pixel"):
        raise HTTPException(400, "mode debe ser: trace | hatch | pixel")

    image_bytes = await file.read()
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(413, "Imagen demasiado grande (máx. 20 MB).")

    params = ImagenParams(
        image_bytes    = image_bytes,
        mode           = mode,
        scale          = scale,
        threshold      = threshold,
        min_area       = min_area,
        approx_epsilon = approx_epsilon,
        spline         = spline,
        lineweight     = lineweight,
        title          = title or file.filename or "Imagen",
    )

    try:
        result = ImagenGenerator().generate(params)
    except ValueError as e:
        raise HTTPException(422, str(e))

    stem = (file.filename or "imagen").rsplit(".", 1)[0]
    fname = f"{stem}_{mode}.dxf"
    return Response(
        content=result.dxf_bytes,
        media_type="application/dxf",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Contours":  str(result.contour_count),
            "X-Entities":  str(result.entity_count),
            "X-DXF-Width": f"{result.dxf_width_mm:.1f}",
            "X-DXF-Height": f"{result.dxf_height_mm:.1f}",
        },
    )


@router.post("/info")
async def imagen_info(
    file:           UploadFile = File(...),
    mode:           str   = Form("trace"),
    scale:          float = Form(0.1),
    threshold:      int   = Form(127),
    min_area:       float = Form(10.0),
    approx_epsilon: float = Form(0.5),
):
    """Procesa la imagen y devuelve estadísticas (sin descargar el DXF)."""
    image_bytes = await file.read()
    params = ImagenParams(
        image_bytes=image_bytes, mode=mode, scale=scale,
        threshold=threshold, min_area=min_area, approx_epsilon=approx_epsilon,
    )
    result = ImagenGenerator().generate(params)
    return {
        "mode":          result.mode,
        "contour_count": result.contour_count,
        "entity_count":  result.entity_count,
        "img_width":     result.img_width,
        "img_height":    result.img_height,
        "dxf_width_mm":  result.dxf_width_mm,
        "dxf_height_mm": result.dxf_height_mm,
    }
