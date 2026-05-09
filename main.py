"""
main.py
-------
ArqGen — Generador paramétrico de planos arquitectónicos bajo NTC-RCDF
FastAPI application entry-point.
"""
from __future__ import annotations

from pathlib import Path

from io import BytesIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from PIL import Image

# Lazy-loaded rembg session cache (populated on first /remove-bg call)
_rembg_session = None

from backend.routers.router_texto        import router as r_txt
from backend.routers.router_imagen       import router as r_img

# ---------------------------------------------------------------------------
app = FastAPI(
    title="ArqGen",
    description=(
        "Generador paramétrico de planos arquitectónicos y estructurales "
        "bajo las Normas Técnicas Complementarias del RCDF (Ciudad de México)."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files & templates
BASE = Path(__file__).parent
TEMPLATES = BASE / "frontend" / "templates"
app.mount("/static", StaticFiles(directory=BASE / "frontend" / "static"), name="static")

# Routers
app.include_router(r_txt)
app.include_router(r_img)


# ---------------------------------------------------------------------------
# SPA pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=FileResponse)
def home():
    return FileResponse(TEMPLATES / "index.html")


@app.get("/texto", response_class=FileResponse)
def page_texto():
    return FileResponse(TEMPLATES / "texto.html")


@app.get("/imagen", response_class=FileResponse)
def page_imagen():
    return FileResponse(TEMPLATES / "imagen.html")


@app.get("/limpieza", response_class=FileResponse)
def page_limpieza():
    return FileResponse(TEMPLATES / "limpieza.html")


@app.get("/privacidad", response_class=FileResponse)
def page_privacidad():
    return FileResponse(TEMPLATES / "privacidad.html")


@app.get("/blog", response_class=FileResponse)
def page_blog():
    return FileResponse(TEMPLATES / "blog.html")


@app.get("/blog/preparar-logo-jpg-para-dxf", response_class=FileResponse)
def page_blog_logo():
    return FileResponse(TEMPLATES / "blog_preparar_logo.html")


@app.get("/blog/diferencias-dxf-dwg", response_class=FileResponse)
def page_blog_dxf_dwg():
    return FileResponse(TEMPLATES / "blog_dxf_dwg.html")


@app.get("/blog/convertir-fotos-modelos-3d", response_class=FileResponse)
def page_blog_3d():
    return FileResponse(TEMPLATES / "blog_3d.html")


@app.get("/ads.txt", response_class=FileResponse)
def ads_txt():
    return FileResponse(BASE / "ads.txt", media_type="text/plain")


@app.get("/health")
def health():
    return {"status": "ok", "service": "arqgen"}


@app.post("/remove-bg")
async def remove_background(file: UploadFile = File(..., description="Imagen PNG/JPG/BMP/TIFF")):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Solo se aceptan archivos de imagen.")

    image_bytes = await file.read()
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(413, "Imagen demasiado grande (máx. 20 MB).")

    try:
        from rembg import remove, new_session  # lazy: no carga onnxruntime en arranque
        global _rembg_session
        if _rembg_session is None:
            _rembg_session = new_session("isnet-general-use")  # mejor calidad que u2net/u2netp
        # rembg devuelve PNG con canal alfa; alpha_matting suaviza bordes
        result = remove(
            image_bytes,
            session=_rembg_session,
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10,
        )
        img = Image.open(BytesIO(result))
        out = BytesIO()
        img.save(out, format="PNG")
    except Exception as e:
        raise HTTPException(422, f"No se pudo quitar el fondo: {e}")

    return Response(content=out.getvalue(), media_type="image/png")
