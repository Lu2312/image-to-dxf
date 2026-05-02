"""
generador_geometria.py
----------------------
Agente 3 — Generador de Geometría DXF.

Recibe un ModeloEstructural (producido por el IngenieroNormativo)
y lo traduce a entidades ezdxf en el modelspace entregado.

Cada elemento se dibuja en su capa estándar:
  CASTILLO  → E-CASTILLO  (LWPOLYLINE cerrada + HATCH SOLID + texto armado)
  DALA      → E-DALA      (LWPOLYLINE cerrada + HATCH SOLID + texto armado)

El agente NO crea el documento DXF ni el modelspace.
El llamador (gen_planta.py) crea el doc y se lo entrega.
Esto respeta el principio de responsabilidad única (SRP).

Capas creadas si no existen:
  E-CASTILLO  ACI 6 (magenta),  lw=35
  E-DALA      ACI 5 (azul),     lw=35
  E-ARMADO    ACI 2 (amarillo),  lw=13
"""
from __future__ import annotations

from typing import List

import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import BaseLayout

from ..core.modelo_estructural import (
    ElementoVertical,
    ElementoHorizontal,
    ModeloEstructural,
)

# AutoCAD ACI colours
ACI_MAGENTA = 6
ACI_BLUE    = 5
ACI_YELLOW  = 2
ACI_GRAY    = 8


class GeneradorGeometria:
    """
    Escribe las entidades estructurales del ModeloEstructural en el
    modelspace DXF suministrado.
    """

    def dibujar(
        self,
        doc: Drawing,
        msp: BaseLayout,
        modelo: ModeloEstructural,
    ) -> None:
        self._setup_layers(doc)

        for ev in modelo.elementos_verticales:
            if ev.tipo == "CASTILLO":
                self._dibujar_castillo(msp, ev)

        for eh in modelo.elementos_horizontales:
            if eh.tipo == "DALA":
                self._dibujar_dala(msp, eh)

    # ------------------------------------------------------------------
    # Capas
    # ------------------------------------------------------------------

    def _setup_layers(self, doc: Drawing) -> None:
        defs = {
            "E-CASTILLO": (ACI_MAGENTA, 35),
            "E-DALA":     (ACI_BLUE,    35),
            "E-ARMADO":   (ACI_YELLOW,  13),
        }
        for name, (color, lw) in defs.items():
            if name not in doc.layers:
                doc.layers.add(name, color=color, lineweight=lw)

    # ------------------------------------------------------------------
    # Castillo: LWPOLYLINE cerrada + HATCH SOLID + etiqueta armado
    # ------------------------------------------------------------------

    def _dibujar_castillo(self, msp: BaseLayout, ev: ElementoVertical) -> None:
        hx = ev.seccion[0] / 2
        hy = ev.seccion[1] / 2
        cx, cy = ev.x, ev.y

        pts = [
            (cx - hx, cy - hy),
            (cx + hx, cy - hy),
            (cx + hx, cy + hy),
            (cx - hx, cy + hy),
        ]

        # Contorno
        msp.add_lwpolyline(
            pts, close=True,
            dxfattribs={"layer": "E-CASTILLO", "lineweight": 35},
        )

        # Relleno HATCH SOLID (sección de concreto)
        hatch = msp.add_hatch(color=ACI_MAGENTA,
                               dxfattribs={"layer": "E-CASTILLO"})
        hatch.paths.add_polyline_path(pts + [pts[0]], is_closed=True)

        # Diagonales internas (símbolo de columna en planta)
        msp.add_line((cx - hx, cy - hy), (cx + hx, cy + hy),
                     dxfattribs={"layer": "E-CASTILLO"})
        msp.add_line((cx + hx, cy - hy), (cx - hx, cy + hy),
                     dxfattribs={"layer": "E-CASTILLO"})

        # Etiqueta de armado junto al castillo
        tag = f"K {ev.n_varillas}{ev.varilla} E.No.2@{ev.sep_estribos:.0f}"
        msp.add_text(
            tag,
            dxfattribs={
                "layer": "E-ARMADO",
                "height": 80,
                "insert": (cx + hx + 50, cy + hy / 2),
            },
        )

    # ------------------------------------------------------------------
    # Dala: LWPOLYLINE cerrada (perfil longitudinal) + etiqueta
    # ------------------------------------------------------------------

    def _dibujar_dala(self, msp: BaseLayout, eh: ElementoHorizontal) -> None:
        """
        Dibuja la dala como un rectángulo fino sobre el muro en planta
        (vista desde arriba) al nivel z=altura_muro.
        En planta la dala se representa como el espesor del muro.
        """
        em = eh.ancho
        hw = em / 2

        if abs(eh.x1 - eh.x0) >= abs(eh.y1 - eh.y0):
            # Dala horizontal
            pts = [
                (eh.x0, eh.y0 - hw),
                (eh.x1, eh.y1 - hw),
                (eh.x1, eh.y1 + hw),
                (eh.x0, eh.y0 + hw),
            ]
        else:
            # Dala vertical
            pts = [
                (eh.x0 - hw, eh.y0),
                (eh.x1 - hw, eh.y1),
                (eh.x1 + hw, eh.y1),
                (eh.x0 + hw, eh.y0),
            ]

        msp.add_lwpolyline(
            pts, close=True,
            dxfattribs={"layer": "E-DALA", "lineweight": 35},
        )

        # Hatch de concreto (color gris claro)
        hatch = msp.add_hatch(color=ACI_BLUE,
                               dxfattribs={"layer": "E-DALA"})
        hatch.paths.add_polyline_path(pts + [pts[0]], is_closed=True)

        # Texto de armado al centro
        cx = (eh.x0 + eh.x1) / 2
        cy = (eh.y0 + eh.y1) / 2
        tag = (f"D {eh.n_varillas}{eh.varilla} "
               f"E.No.2@{eh.sep_estribos:.0f} "
               f"z+{eh.z / 1000:.2f}m")
        msp.add_text(
            tag,
            dxfattribs={
                "layer": "E-ARMADO",
                "height": 70,
                "insert": (cx, cy - hw - 120),
            },
        )
