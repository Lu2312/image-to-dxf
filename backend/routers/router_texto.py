"""
router_texto.py  —  POST /api/texto
Descripción en lenguaje natural → DXF / PDF / Excel de planta arquitectónica.
"""
from __future__ import annotations

import datetime
from fastapi import APIRouter
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

from ..generators.gen_texto import parse_texto
from ..generators.gen_planta import PlantaGenerator, PlantaParams

router = APIRouter(prefix="/api/texto", tags=["Texto a DXF"])


class TextoRequest(BaseModel):
    texto:        str = Field(..., min_length=10,
                              example="Casa de 3 recamaras, sala-comedor, cocina, "
                                      "2 banos, patio de servicio, lote 8x15 m")
    project_name: str = Field("Proyecto Lu CAD Studio", max_length=80)


def _build_params(req: TextoRequest) -> tuple[PlantaParams, list]:
    parsed = parse_texto(
        req.texto,
        project_name=req.project_name,
        date=datetime.date.today().isoformat(),
    )
    params = PlantaParams(
        lote_ancho   = parsed.lote_ancho,
        lote_fondo   = parsed.lote_fondo,
        espesor_muro = parsed.espesor_muro,
        altura_muro  = parsed.altura_muro,
        recintos     = parsed.recintos,
        project_name = parsed.project_name,
        date         = parsed.date,
    )
    return params, parsed.notas


@router.post("/preview")
def texto_preview(req: TextoRequest):
    """Analiza el texto, genera la planta y devuelve SVG + catálogo + NTC."""
    params, notas = _build_params(req)
    result = PlantaGenerator().generate(params)
    return JSONResponse({
        "svg":      result.svg_preview,
        "ntc":      result.ntc_report,
        "catalog":  result.catalog.to_rows(),
        "programa": [r["nombre"] for r in params.recintos],
        "lote":     {"ancho_m": params.lote_ancho / 1000,
                     "fondo_m": params.lote_fondo / 1000},
        "notas":    notas,
    })


@router.post("/dxf")
def texto_dxf(req: TextoRequest):
    params, _ = _build_params(req)
    result = PlantaGenerator().generate(params)
    fname = req.project_name.replace(" ", "_") + "_planta_texto.dxf"
    return Response(
        content=result.dxf_bytes, media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/pdf")
def texto_pdf(req: TextoRequest):
    params, _ = _build_params(req)
    result = PlantaGenerator().generate(params)
    fname = req.project_name.replace(" ", "_") + "_planta_texto.pdf"
    return Response(
        content=result.pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/excel")
def texto_excel(req: TextoRequest):
    params, _ = _build_params(req)
    result = PlantaGenerator().generate(params)
    fname = req.project_name.replace(" ", "_") + "_catalogo_texto.xlsx"
    return Response(
        content=result.xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
