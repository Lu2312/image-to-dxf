"""
router_imagen.py  —  POST /api/imagen
Convierte una imagen subida (PNG/JPG/BMP) a DXF.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import Response

from ..generators.gen_imagen import ImagenGenerator, ImagenParams, clean_image_bytes
from ..generators.gen_mueble_pdf import Mueble3DGenerator, Mueble3DParams

router = APIRouter(prefix="/api/imagen", tags=["Imagen a DXF"])


@router.post("/dxf")
async def imagen_to_dxf(
    file:           UploadFile = File(..., description="Imagen PNG/JPG/BMP/TIFF o PDF"),
    mode:           str   = Form("trace",  description="trace | hatch | pixel"),
    scale:          float = Form(0.1,      description="mm/px (0.1 = 1px → 0.1mm)"),
    threshold:      int   = Form(127,      description="Umbral binarización 0-255"),
    min_area:       float = Form(10.0,     description="Área mínima de contorno (px²)"),
    approx_epsilon: float = Form(0.5,      description="Simplificación Douglas-Peucker"),
    spline:         bool  = Form(False,    description="Usar SPLINE en modo trace"),
    lineweight:     int   = Form(25,       description="Grosor de línea 1/100 mm"),
    title:          str   = Form("",       description="Título del plano"),
    pre_clean:      bool  = Form(False,    description="Limpieza de ruido"),
    bg_remove:      bool  = Form(False,    description="Quitar fondo"),
    adaptive:       bool  = Form(False,    description="Binarización adaptativa"),
    invert:         bool  = Form(True,     description="Invertir blanco/negro"),
    denoise_ksize:  int   = Form(3,        description="Kernel mediano (impar)"),
    morph_open:     int   = Form(0,        description="Apertura morfologica"),
    morph_close:    int   = Form(0,        description="Cierre morfologico"),
    pdf_dpi:        int   = Form(200,      description="DPI para rasterizar PDF"),
):
    """Convierte la imagen subida a DXF y devuelve el archivo binario."""
    if not file.content_type or not (
        file.content_type.startswith("image/") or file.content_type == "application/pdf"
    ):
        raise HTTPException(400, "Solo se aceptan archivos de imagen (PNG, JPG, BMP, TIFF) o PDF.")
    if mode not in ("trace", "hatch", "pixel"):
        raise HTTPException(400, "mode debe ser: trace | hatch | pixel")

    image_bytes = await file.read()
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(413, "Imagen demasiado grande (máx. 20 MB).")

    params = ImagenParams(
        image_bytes    = image_bytes,
        content_type   = file.content_type or "",
        mode           = mode,
        scale          = scale,
        threshold      = threshold,
        min_area       = min_area,
        approx_epsilon = approx_epsilon,
        spline         = spline,
        lineweight     = lineweight,
        title          = title or file.filename or "Imagen",
        pre_clean      = pre_clean,
        bg_remove      = bg_remove,
        adaptive       = adaptive,
        invert         = invert,
        denoise_ksize  = denoise_ksize,
        morph_open     = morph_open,
        morph_close    = morph_close,
        pdf_dpi        = pdf_dpi,
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
    pre_clean:      bool  = Form(False),
    bg_remove:      bool  = Form(False),
    adaptive:       bool  = Form(False),
    invert:         bool  = Form(True),
    denoise_ksize:  int   = Form(3),
    morph_open:     int   = Form(0),
    morph_close:    int   = Form(0),
    pdf_dpi:        int   = Form(200),
):
    """Procesa la imagen y devuelve estadísticas (sin descargar el DXF)."""
    image_bytes = await file.read()
    params = ImagenParams(
        image_bytes=image_bytes,
        content_type=file.content_type or "",
        mode=mode,
        scale=scale,
        threshold=threshold,
        min_area=min_area,
        approx_epsilon=approx_epsilon,
        pre_clean=pre_clean,
        bg_remove=bg_remove,
        adaptive=adaptive,
        invert=invert,
        denoise_ksize=denoise_ksize,
        morph_open=morph_open,
        morph_close=morph_close,
        pdf_dpi=pdf_dpi,
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


@router.post("/clean")
async def imagen_clean(
    file:           UploadFile = File(..., description="Imagen PNG/JPG/BMP/TIFF o PDF"),
    threshold:      int   = Form(127,      description="Umbral binarización 0-255"),
    pre_clean:      bool  = Form(False,    description="Limpieza de ruido"),
    bg_remove:      bool  = Form(False,    description="Quitar fondo"),
    adaptive:       bool  = Form(False,    description="Binarización adaptativa"),
    invert:         bool  = Form(True,     description="Invertir blanco/negro"),
    denoise_ksize:  int   = Form(3,        description="Kernel mediano (impar)"),
    morph_open:     int   = Form(0,        description="Apertura morfológica"),
    morph_close:    int   = Form(0,        description="Cierre morfológica"),
    pdf_dpi:        int   = Form(200,      description="DPI para rasterizar PDF"),
):
    if not file.content_type or not (
        file.content_type.startswith("image/") or file.content_type == "application/pdf"
    ):
        raise HTTPException(400, "Solo se aceptan archivos de imagen (PNG, JPG, BMP, TIFF) o PDF.")

    image_bytes = await file.read()
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(413, "Imagen demasiado grande (máx. 20 MB).")

    params = ImagenParams(
        image_bytes    = image_bytes,
        content_type   = file.content_type or "",
        threshold      = threshold,
        pre_clean      = pre_clean,
        bg_remove      = bg_remove,
        adaptive       = adaptive,
        invert         = invert,
        denoise_ksize  = denoise_ksize,
        morph_open     = morph_open,
        morph_close    = morph_close,
        pdf_dpi        = pdf_dpi,
    )

    try:
        png_bytes = clean_image_bytes(params)
    except ValueError as e:
        raise HTTPException(422, str(e))

    return Response(content=png_bytes, media_type="image/png")


@router.post("/mueble3d")
async def mueble_3d(
    file:       UploadFile = File(..., description="PDF con vista 3D"),
    width:      float = Form(0.0, description="Ancho total en mm (0 = OCR)"),
    height:     float = Form(0.0, description="Alto total en mm (0 = OCR)"),
    depth:      float = Form(0.0, description="Fondo total en mm (0 = OCR)"),
    thickness:  float = Form(19.0, description="Espesor de tablero en mm"),
    use_ocr:    bool  = Form(True, description="Usar OCR para cotas"),
    ocr_lang:   str   = Form("spa", description="Idioma OCR (spa, eng)"),
    pdf_dpi:    int   = Form(200, description="DPI para rasterizar PDF"),
):
    if not file.content_type or file.content_type != "application/pdf":
        raise HTTPException(400, "Solo se aceptan archivos PDF.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 25 * 1024 * 1024:
        raise HTTPException(413, "PDF demasiado grande (max. 25 MB).")

    params = Mueble3DParams(
        pdf_bytes=pdf_bytes,
        width=width,
        height=height,
        depth=depth,
        thickness=thickness,
        use_ocr=use_ocr,
        ocr_lang=ocr_lang,
        pdf_dpi=pdf_dpi,
    )

    try:
        result = Mueble3DGenerator().generate(params)
    except ValueError as e:
        raise HTTPException(422, str(e))

    stem = (file.filename or "mueble").rsplit(".", 1)[0]
    fname = f"{stem}_mueble3d.dxf"
    ocr_dims = "x".join(str(x) for x in result.ocr_dims) if result.ocr_dims else ""
    return Response(
        content=result.dxf_bytes,
        media_type="application/dxf",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Width": f"{result.width:.1f}",
            "X-Height": f"{result.height:.1f}",
            "X-Depth": f"{result.depth:.1f}",
            "X-Thickness": f"{result.thickness:.1f}",
            "X-OCR-Dims": ocr_dims,
        },
    )


@router.post("/mueble3d/preview")
async def mueble_3d_preview(
    file:       UploadFile = File(..., description="PDF con vista 3D"),
    width:      float = Form(0.0, description="Ancho total en mm (0 = OCR)"),
    height:     float = Form(0.0, description="Alto total en mm (0 = OCR)"),
    depth:      float = Form(0.0, description="Fondo total en mm (0 = OCR)"),
    thickness:  float = Form(75.0, description="Espesor de tablero en mm"),
    use_ocr:    bool  = Form(True, description="Usar OCR para cotas"),
    ocr_lang:   str   = Form("spa", description="Idioma OCR (spa, eng)"),
    pdf_dpi:    int   = Form(200, description="DPI para rasterizar PDF"),
):
    if not file.content_type or file.content_type != "application/pdf":
        raise HTTPException(400, "Solo se aceptan archivos PDF.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 25 * 1024 * 1024:
        raise HTTPException(413, "PDF demasiado grande (max. 25 MB).")

    params = Mueble3DParams(
        pdf_bytes=pdf_bytes,
        width=width,
        height=height,
        depth=depth,
        thickness=thickness,
        use_ocr=use_ocr,
        ocr_lang=ocr_lang,
        pdf_dpi=pdf_dpi,
    )

    try:
        svg, result = Mueble3DGenerator().preview_svg(params)
    except ValueError as e:
        raise HTTPException(422, str(e))

    return {
        "svg": svg,
        "width": result.width,
        "height": result.height,
        "depth": result.depth,
        "thickness": result.thickness,
        "ocr_dims": result.ocr_dims,
        "notes": result.notes,
    }


@router.post("/mueble3d/cutlist")
async def mueble_3d_cutlist(
    file:       UploadFile = File(..., description="PDF con tabla de piezas"),
    ocr_lang:   str   = Form("spa", description="Idioma OCR (spa, eng)"),
    pdf_dpi:    int   = Form(250, description="DPI para rasterizar PDF"),
):
    if not file.content_type or file.content_type != "application/pdf":
        raise HTTPException(400, "Solo se aceptan archivos PDF.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 25 * 1024 * 1024:
        raise HTTPException(413, "PDF demasiado grande (max. 25 MB).")

    params = Mueble3DParams(
        pdf_bytes=pdf_bytes,
        width=0.0,
        height=0.0,
        depth=0.0,
        thickness=75.0,
        use_ocr=False,
        ocr_lang=ocr_lang,
        pdf_dpi=pdf_dpi,
    )

    try:
        items, notes = Mueble3DGenerator().cutlist(params)
    except ValueError as e:
        raise HTTPException(422, str(e))

    return {
        "items": [
            {
                "idx": i.idx,
                "name": i.name,
                "length": i.length,
                "width": i.width,
                "qty": i.qty,
            }
            for i in items
        ],
        "notes": notes,
    }
