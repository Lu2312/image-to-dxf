"""
router_planta.py  —  POST /api/planta
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

from ..generators.gen_planta import PlantaGenerator, PlantaParams

router = APIRouter(prefix="/api/planta", tags=["Planta Arquitectónica"])


class RecintoIn(BaseModel):
    nombre: str
    ancho:  float = Field(..., ge=1000, le=12000)
    fondo:  float = Field(..., ge=1000, le=12000)


class PlantaIn(BaseModel):
    lote_ancho:   float = Field(6000.0, ge=3000, le=30000)
    lote_fondo:   float = Field(12000.0, ge=4000, le=60000)
    espesor_muro: float = Field(150.0, ge=120, le=400)
    recintos:     List[RecintoIn]
    project_name: str   = Field("Proyecto", max_length=80)
    altura_muro:  float = Field(2700.0, ge=2200, le=4000)


def _params(body: PlantaIn) -> PlantaParams:
    return PlantaParams(
        lote_ancho=body.lote_ancho,
        lote_fondo=body.lote_fondo,
        espesor_muro=body.espesor_muro,
        recintos=[r.model_dump() for r in body.recintos],
        project_name=body.project_name,
        date=datetime.date.today().isoformat(),
        altura_muro=body.altura_muro,
    )


@router.post("/dxf")
def gen_dxf(body: PlantaIn):
    result = PlantaGenerator().generate(_params(body))
    fname = body.project_name.replace(" ", "_") + "_planta.dxf"
    return Response(
        content=result.dxf_bytes, media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/pdf")
def gen_pdf(body: PlantaIn):
    result = PlantaGenerator().generate(_params(body))
    fname = body.project_name.replace(" ", "_") + "_planta.pdf"
    return Response(
        content=result.pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/excel")
def gen_excel(body: PlantaIn):
    result = PlantaGenerator().generate(_params(body))
    fname = body.project_name.replace(" ", "_") + "_catalogo.xlsx"
    return Response(
        content=result.xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/preview")
def gen_preview(body: PlantaIn):
    result = PlantaGenerator().generate(_params(body))
    return JSONResponse({
        "svg": result.svg_preview,
        "ntc": result.ntc_report,
        "catalog": result.catalog.to_rows(),
    })


@router.post("/modelo")
def gen_modelo(body: PlantaIn):
    """
    Devuelve el ModeloEstructural en JSON antes de generar el DXF.
    Permite auditar la decisión estructural (castillos, dalas, advertencias)
    como ingeniero, sin necesidad de abrir AutoCAD.
    """
    result = PlantaGenerator().generate(_params(body))
    if result.modelo_estructural is None:
        return JSONResponse({"error": "modelo no disponible"}, status_code=500)
    return JSONResponse(result.modelo_estructural.to_dict())
