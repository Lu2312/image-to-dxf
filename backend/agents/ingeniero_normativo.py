"""
ingeniero_normativo.py
----------------------
Agente 2 — Motor de Reglas NTC (Ingeniero Normativo).

Recibe la TopologiaEspacial del AnalistaEspacial y aplica las reglas
de las Normas Técnicas Complementarias (NTC) del RCDF para producir
un ModeloEstructural con justificación de cada decisión.

Reglas implementadas (mampostería confinada):
  R-01  Castillo en toda esquina o intersección de muros (L, T, CROSS)
        NTC Mampostería 2017, §6.3
  R-02  Castillo intermedio si el tramo libre entre castillos > SEP_MAX
        (3 500 mm conservador; NTC §6.4 permite hasta 4 000 mm)
  R-03  Dala de cerramiento continua sobre todos los muros a la altura
        de la losa (altura_muro).  NTC Mampostería 2017, §7.2
  R-04  Sección mínima del castillo: 150 × 150 mm
  R-05  Armado mínimo del castillo: 4 varillas No.4 + estribos No.2 @ 200mm
  R-06  Sección mínima de dala: ancho ≥ espesor_muro, peralte ≥ 150 mm

Errores de concepto detectados:
  - Viga sin apoyo directo → advertencia agregada al modelo
"""
from __future__ import annotations

import math
from typing import List, Tuple

from ..agents.analista_espacial import TopologiaEspacial, SegmentoMuro, Nodo
from ..core.modelo_estructural import (
    ElementoVertical,
    ElementoHorizontal,
    MetadatosNormativos,
    ModeloEstructural,
)

# ---------------------------------------------------------------------------
# Constantes NTC
# ---------------------------------------------------------------------------

SEP_MAX_CASTILLOS_MM: float = 3500.0   # mm  (conservador, NTC §6.4)
SECCION_CASTILLO_MIN: float = 150.0    # mm
VARILLA_LONG_CASTILLO: str  = "No.4"   # 4Ø12.7mm = 506.8 mm² > mín 600 mm²
N_VARILLAS_CASTILLO: int    = 4
SEP_ESTRIBOS_CASTILLO: float = 200.0   # mm   (NTC §6.4)

VARILLA_DALA: str   = "No.3"           # 2Ø9.53mm = 142.6 mm²
N_VARILLAS_DALA: int = 2
SEP_ESTRIBOS_DALA: float = 200.0       # mm


# ---------------------------------------------------------------------------
# Agente
# ---------------------------------------------------------------------------

class IngenieroNormativo:
    """
    Aplica las reglas NTC sobre la topología y genera el ModeloEstructural.

    Uso:
        topo   = AnalistaEspacial().analizar(...)
        modelo = IngenieroNormativo().disenar(topo, metadatos)
        print(modelo.resumen())
    """

    def disenar(
        self,
        topo: TopologiaEspacial,
        metadatos: MetadatosNormativos | None = None,
    ) -> ModeloEstructural:

        if metadatos is None:
            metadatos = MetadatosNormativos()

        modelo = ModeloEstructural(metadatos_normativos=metadatos)

        # ── R-01 / R-02: Castillos ────────────────────────────────────
        self._disenar_castillos(topo, modelo)

        # ── R-03: Dalas de cerramiento ───────────────────────────────
        self._disenar_dalas(topo, modelo)

        # ── R-06: Validación final ───────────────────────────────────
        self._validar_apoyos(topo, modelo)

        modelo.cumple_ntc = len(modelo.advertencias) == 0
        return modelo

    # ------------------------------------------------------------------
    # R-01 + R-02: Castillos
    # ------------------------------------------------------------------

    def _disenar_castillos(
        self,
        topo: TopologiaEspacial,
        modelo: ModeloEstructural,
    ) -> None:
        em  = topo.espesor_muro
        alt = topo.altura_muro
        colocados: set = set()   # evitar duplicados

        def _agregar(x: float, y: float, tipo_nodo: str, razon: str) -> None:
            clave = (round(x, 1), round(y, 1))
            if clave in colocados:
                return
            colocados.add(clave)
            modelo.elementos_verticales.append(ElementoVertical(
                tipo       = "CASTILLO",
                x          = x,
                y          = y,
                seccion    = (SECCION_CASTILLO_MIN, SECCION_CASTILLO_MIN),
                altura     = alt,
                varilla    = VARILLA_LONG_CASTILLO,
                n_varillas = N_VARILLAS_CASTILLO,
                sep_estribos = SEP_ESTRIBOS_CASTILLO,
                norma      = "NTC Mampostería 2017 §6.3-6.4",
                razon      = razon,
                tipo_nodo  = tipo_nodo,
            ))

        # R-01: castillo en cada nodo de intersección
        for nodo in topo.nodos:
            if nodo.tipo in ("L", "T", "CROSS"):
                _agregar(
                    nodo.x, nodo.y, nodo.tipo,
                    f"R-01: Intersección tipo {nodo.tipo} "
                    f"en ({nodo.x:.0f}, {nodo.y:.0f}) mm",
                )

        # R-02: castillos intermedios en tramos largos
        for seg in topo.segmentos:
            long = seg.longitud
            if long <= SEP_MAX_CASTILLOS_MM:
                continue

            n_intermedios = math.ceil(long / SEP_MAX_CASTILLOS_MM) - 1
            step = long / (n_intermedios + 1)

            for i in range(1, n_intermedios + 1):
                dist = i * step
                if seg.orientacion == "V":
                    xi, yi = seg.eje_coord, seg.inicio + dist
                else:
                    xi, yi = seg.inicio + dist, seg.eje_coord

                _agregar(
                    xi, yi, "INTERMEDIO",
                    f"R-02: Castillo intermedio en tramo de {long:.0f} mm "
                    f"> {SEP_MAX_CASTILLOS_MM:.0f} mm (NTC §6.4)",
                )

    # ------------------------------------------------------------------
    # R-03: Dalas de cerramiento
    # ------------------------------------------------------------------

    def _disenar_dalas(
        self,
        topo: TopologiaEspacial,
        modelo: ModeloEstructural,
    ) -> None:
        em  = topo.espesor_muro
        z   = topo.altura_muro     # elevación de la dala = altura_muro

        # Una dala por cada segmento de muro
        for i, seg in enumerate(topo.segmentos):
            if seg.orientacion == "V":
                x0, y0 = seg.eje_coord, seg.inicio
                x1, y1 = seg.eje_coord, seg.fin
            else:
                x0, y0 = seg.inicio, seg.eje_coord
                x1, y1 = seg.fin,    seg.eje_coord

            # Etiqueta descriptiva del tramo
            if seg.orientacion == "H":
                etiqueta = (f"Dala cerramiento eje Y={seg.eje_coord:.0f}: "
                            f"X {seg.inicio:.0f}→{seg.fin:.0f} mm")
            else:
                etiqueta = (f"Dala cerramiento eje X={seg.eje_coord:.0f}: "
                            f"Y {seg.inicio:.0f}→{seg.fin:.0f} mm")

            modelo.elementos_horizontales.append(ElementoHorizontal(
                tipo        = "DALA",
                x0=x0, y0=y0, x1=x1, y1=y1,
                z           = z,
                peralte     = max(150.0, em),
                ancho       = em,
                varilla     = VARILLA_DALA,
                n_varillas  = N_VARILLAS_DALA,
                sep_estribos = SEP_ESTRIBOS_DALA,
                norma       = "NTC Mampostería 2017 §7.2",
                razon       = f"R-03: {etiqueta}",
            ))

    # ------------------------------------------------------------------
    # Validación de apoyos (error de concepto)
    # ------------------------------------------------------------------

    def _validar_apoyos(
        self,
        topo: TopologiaEspacial,
        modelo: ModeloEstructural,
    ) -> None:
        """
        Verifica que cada dala tenga al menos un castillo en cada extremo.
        Emite advertencia si una dala "cuelga" sin apoyo.
        """
        castillo_pts = {
            (round(c.x, 1), round(c.y, 1))
            for c in modelo.elementos_verticales
        }

        for dala in modelo.elementos_horizontales:
            p0 = (round(dala.x0, 1), round(dala.y0, 1))
            p1 = (round(dala.x1, 1), round(dala.y1, 1))

            if p0 not in castillo_pts:
                modelo.advertencias.append(
                    f"ERROR DE APOYO: dala en ({dala.x0:.0f},{dala.y0:.0f})→"
                    f"({dala.x1:.0f},{dala.y1:.0f}) no tiene castillo en el "
                    f"nodo inicial ({dala.x0:.0f},{dala.y0:.0f}). "
                    "Revisar NTC §7.2 — la dala debe apoyar en castillo."
                )
            if p1 not in castillo_pts:
                modelo.advertencias.append(
                    f"ERROR DE APOYO: dala en ({dala.x0:.0f},{dala.y0:.0f})→"
                    f"({dala.x1:.0f},{dala.y1:.0f}) no tiene castillo en el "
                    f"nodo final ({dala.x1:.0f},{dala.y1:.0f}). "
                    "Revisar NTC §7.2 — la dala debe apoyar en castillo."
                )
