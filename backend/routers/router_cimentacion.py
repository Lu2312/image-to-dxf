"""
router_cimentacion.py  —  POST /api/cimentacion
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field, field_validator

from ..generators.gen_cimentacion import CimentacionGenerator, CimentacionParams

router = APIRouter(prefix="/api/cimentacion", tags=["Cimentación"])


class EjesList(BaseModel):
    ejes_x: List[float] = Field(..., min_length=2, example=[0, 3000, 6000])
    ejes_y: List[float] = Field(..., min_length=2, example=[0, 4000, 8000])
    espesor_muro:  float = Field(150.0, ge=120, le=400)
    ancho_zapata:  float = Field(500.0, ge=400, le=2000)
    alto_zapata:   float = Field(350.0, ge=300, le=1000)
    desplante:     float = Field(600.0, ge=400, le=3000)
    varilla_long:  str   = Field("No.4", pattern=r"^No\.[2-9]$|^No\.1[0-9]$")
    varilla_trans: str   = Field("No.4", pattern=r"^No\.[2-9]$|^No\.1[0-9]$")
    sep_long_mm:   float = Field(200.0, ge=100, le=300)
    sep_trans_mm:  float = Field(200.0, ge=100, le=300)
    project_name:  str   = Field("Proyecto", max_length=80)
    fc:            float = Field(200.0, ge=150, le=400)
    fy:            float = Field(4200.0, ge=4200, le=6000)


def _params(body: EjesList) -> CimentacionParams:
    return CimentacionParams(
        ejes_x=body.ejes_x,
        ejes_y=body.ejes_y,
        espesor_muro=body.espesor_muro,
        ancho_zapata=body.ancho_zapata,
        alto_zapata=body.alto_zapata,
        desplante=body.desplante,
        varilla_long=body.varilla_long,
        varilla_trans=body.varilla_trans,
        sep_long_mm=body.sep_long_mm,
        sep_trans_mm=body.sep_trans_mm,
        project_name=body.project_name,
        date=datetime.date.today().isoformat(),
        fc=body.fc,
        fy=body.fy,
    )


@router.post("/dxf")
def gen_dxf(body: EjesList):
    result = CimentacionGenerator().generate(_params(body))
    if not result.ntc_report["valid"]:
        raise HTTPException(422, detail=result.ntc_report)
    fname = body.project_name.replace(" ", "_") + "_cimentacion.dxf"
    return Response(
        content=result.dxf_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/pdf")
def gen_pdf(body: EjesList):
    result = CimentacionGenerator().generate(_params(body))
    fname = body.project_name.replace(" ", "_") + "_cimentacion.pdf"
    return Response(
        content=result.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/excel")
def gen_excel(body: EjesList):
    result = CimentacionGenerator().generate(_params(body))
    fname = body.project_name.replace(" ", "_") + "_catalogo.xlsx"
    return Response(
        content=result.xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/preview")
def gen_preview(body: EjesList):
    result = CimentacionGenerator().generate(_params(body))
    return JSONResponse({
        "svg": result.svg_preview,
        "ntc": result.ntc_report,
        "catalog": result.catalog.to_rows(),
    })
