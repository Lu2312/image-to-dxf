"""
router_carpinteria.py  —  POST /api/carpinteria
"""
from __future__ import annotations

import datetime
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

from ..generators.gen_carpinteria import CarpinteriaGenerator, CarpinteriaParams

router = APIRouter(prefix="/api/carpinteria", tags=["Carpintería / Cancelería"])


class CarpinteriaIn(BaseModel):
    tipo:         Literal["ventana_fija", "ventana_corrediza", "puerta", "closet"]
    ancho:        float = Field(..., ge=400, le=6000)
    alto:         float = Field(..., ge=600, le=3000)
    marco_ancho:  float = Field(50.0, ge=30, le=150)
    hoja_grosor:  float = Field(40.0, ge=20, le=100)
    n_hojas:      int   = Field(2, ge=1, le=6)
    material:     Literal["aluminio", "madera", "pvc"] = "aluminio"
    acabado:      str   = Field("natural", max_length=40)
    project_name: str   = Field("Proyecto", max_length=80)


def _params(body: CarpinteriaIn) -> CarpinteriaParams:
    return CarpinteriaParams(
        tipo=body.tipo,
        ancho=body.ancho,
        alto=body.alto,
        marco_ancho=body.marco_ancho,
        hoja_grosor=body.hoja_grosor,
        n_hojas=body.n_hojas,
        material=body.material,
        acabado=body.acabado,
        project_name=body.project_name,
        date=datetime.date.today().isoformat(),
    )


@router.post("/dxf")
def gen_dxf(body: CarpinteriaIn):
    result = CarpinteriaGenerator().generate(_params(body))
    fname = f"{body.project_name.replace(' ','_')}_{body.tipo}.dxf"
    return Response(
        content=result.dxf_bytes, media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/pdf")
def gen_pdf(body: CarpinteriaIn):
    result = CarpinteriaGenerator().generate(_params(body))
    fname = f"{body.project_name.replace(' ','_')}_{body.tipo}.pdf"
    return Response(
        content=result.pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/excel")
def gen_excel(body: CarpinteriaIn):
    result = CarpinteriaGenerator().generate(_params(body))
    fname = f"{body.project_name.replace(' ','_')}_{body.tipo}_catalogo.xlsx"
    return Response(
        content=result.xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/preview")
def gen_preview(body: CarpinteriaIn):
    result = CarpinteriaGenerator().generate(_params(body))
    return JSONResponse({
        "svg": result.svg_preview,
        "catalog": result.catalog.to_rows(),
    })
