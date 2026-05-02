"""
main.py
-------
ArqGen — Generador paramétrico de planos arquitectónicos bajo NTC-RCDF
FastAPI application entry-point.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.routers.router_cimentacion import router as r_cim
from backend.routers.router_planta       import router as r_pla
from backend.routers.router_carpinteria  import router as r_car
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
app.include_router(r_cim)
app.include_router(r_pla)
app.include_router(r_car)
app.include_router(r_txt)
app.include_router(r_img)


# ---------------------------------------------------------------------------
# SPA pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=FileResponse)
def home():
    return FileResponse(TEMPLATES / "index.html")


@app.get("/cimentacion", response_class=FileResponse)
def page_cimentacion():
    return FileResponse(TEMPLATES / "cimentacion.html")


@app.get("/planta", response_class=FileResponse)
def page_planta():
    return FileResponse(TEMPLATES / "planta.html")


@app.get("/carpinteria", response_class=FileResponse)
def page_carpinteria():
    return FileResponse(TEMPLATES / "carpinteria.html")


@app.get("/texto", response_class=FileResponse)
def page_texto():
    return FileResponse(TEMPLATES / "texto.html")


@app.get("/imagen", response_class=FileResponse)
def page_imagen():
    return FileResponse(TEMPLATES / "imagen.html")


@app.get("/privacidad", response_class=FileResponse)
def page_privacidad():
    return FileResponse(TEMPLATES / "privacidad.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "arqgen"}
