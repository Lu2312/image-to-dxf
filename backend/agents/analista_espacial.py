"""
analista_espacial.py
--------------------
Agente 1 — Analizador de Topología Espacial.

Recibe la lista de recintos del PlantaParams y produce:
  - Lista de segmentos de muro (horizontales y verticales)
  - Lista de nodos (puntos donde muros se cruzan o terminan)
  - Clasificación de cada nodo: ESQUINA_L | INTERSECCION_T | CRUCE_PLUS

No genera geometría DXF: solo procesa coordenadas y devuelve
estructuras de datos que el IngenieroNormativo consumirá.

Glosario:
  SegmentoMuro — tramo recto de muro entre dos nodos
  Nodo         — punto singular (esquina, intersección)
  tipo_nodo    — clasificación geométrica del nodo
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


# ---------------------------------------------------------------------------
# Estructuras de datos internas
# ---------------------------------------------------------------------------

@dataclass
class SegmentoMuro:
    """Segmento recto de muro entre dos nodos."""
    orientacion: str        # "H" (horizontal) | "V" (vertical)
    eje_coord: float        # Y fijo si H; X fijo si V  (centro del muro, mm)
    inicio: float           # coordenada variable en el inicio del segmento
    fin: float              # coordenada variable en el fin
    espesor: float = 150.0  # mm

    @property
    def longitud(self) -> float:
        return abs(self.fin - self.inicio)

    def contiene(self, coord: float, tolerancia: float = 1.0) -> bool:
        """True si 'coord' cae dentro del rango [inicio, fin]."""
        lo, hi = min(self.inicio, self.fin), max(self.inicio, self.fin)
        return (lo - tolerancia) <= coord <= (hi + tolerancia)


@dataclass
class Nodo:
    """Punto singular donde dos o más muros se encuentran."""
    x: float
    y: float
    tipo: str = ""          # "L" | "T" | "CROSS" | "LIBRE"
    segmentos: List[SegmentoMuro] = field(default_factory=list)

    def __hash__(self):
        return hash((round(self.x, 1), round(self.y, 1)))

    def __eq__(self, other):
        return (round(self.x, 1) == round(other.x, 1) and
                round(self.y, 1) == round(other.y, 1))


@dataclass
class TopologiaEspacial:
    """Resultado del análisis espacial."""
    segmentos: List[SegmentoMuro]
    nodos: List[Nodo]
    espesor_muro: float
    altura_muro: float


# ---------------------------------------------------------------------------
# Agente
# ---------------------------------------------------------------------------

class AnalistaEspacial:
    """
    Construye la topología de muros a partir de la distribución de recintos.

    Los recintos del PlantaParams tienen coordenadas interiores.
    El centro de cada muro queda a ± espesor/2 del borde del recinto.
    """

    def analizar(
        self,
        recintos: List[dict],
        espesor_muro: float,
        lote_ancho: float,
        lote_fondo: float,
        altura_muro: float = 2700.0,
    ) -> TopologiaEspacial:
        em = espesor_muro

        # ── 1. Reconstruir coordenadas de ejes (centros de muro) ──────
        xs_ejes: Set[float] = {em / 2, lote_ancho - em / 2}
        ys_ejes: Set[float] = {em / 2, lote_fondo - em / 2}

        for r in recintos:
            x  = float(r["x"]) if "x" in r else em
            y  = float(r["y"]) if "y" in r else em
            an = float(r["ancho"])
            fn = float(r["fondo"])
            xs_ejes.add(x - em / 2)
            xs_ejes.add(x + an + em / 2)
            ys_ejes.add(y - em / 2)
            ys_ejes.add(y + fn + em / 2)

        xs = sorted(xs_ejes)
        ys = sorted(ys_ejes)

        # ── 2. Construir segmentos de muro ────────────────────────────
        # Segmentos verticales: cada x_eje entre y_min y y_max
        y_min, y_max = ys[0], ys[-1]
        x_min, x_max = xs[0], xs[-1]

        segmentos: List[SegmentoMuro] = []

        for x in xs:
            segmentos.append(SegmentoMuro(
                orientacion="V",
                eje_coord=x,
                inicio=y_min,
                fin=y_max,
                espesor=em,
            ))

        for y in ys:
            segmentos.append(SegmentoMuro(
                orientacion="H",
                eje_coord=y,
                inicio=x_min,
                fin=x_max,
                espesor=em,
            ))

        # ── 3. Calcular nodos (intersecciones) ───────────────────────
        nodos: List[Nodo] = []
        xs_set = set(xs)
        ys_set = set(ys)

        for x in xs:
            for y in ys:
                segs_en_nodo = [
                    s for s in segmentos
                    if (s.orientacion == "V" and
                        abs(s.eje_coord - x) < 1.0 and
                        s.contiene(y))
                    or (s.orientacion == "H" and
                        abs(s.eje_coord - y) < 1.0 and
                        s.contiene(x))
                ]
                if segs_en_nodo:
                    tipo = self._clasificar_nodo(x, y, xs, ys)
                    nodos.append(Nodo(x=x, y=y, tipo=tipo,
                                      segmentos=segs_en_nodo))

        return TopologiaEspacial(
            segmentos=segmentos,
            nodos=nodos,
            espesor_muro=em,
            altura_muro=altura_muro,
        )

    # ------------------------------------------------------------------

    def _clasificar_nodo(
        self,
        x: float,
        y: float,
        xs: List[float],
        ys: List[float],
    ) -> str:
        """
        Clasifica el tipo de intersección en un nodo (x, y).

        Lógica:
          CROSS  — muros en las 4 direcciones
          T      — muros en exactamente 3 direcciones
          L      — muros en exactamente 2 direcciones perpendiculares
          LIBRE  — extremo de muro (1 dirección)
        """
        tol = 1.0
        is_x_interior = (xs[0] + tol < x < xs[-1] - tol)
        is_y_interior = (ys[0] + tol < y < ys[-1] - tol)

        # cuenta "brazos" que salen del nodo
        brazos = 0
        if x > xs[0] + tol:   brazos += 1   # ← oeste
        if x < xs[-1] - tol:  brazos += 1   # → este
        if y > ys[0] + tol:   brazos += 1   # ↓ sur
        if y < ys[-1] - tol:  brazos += 1   # ↑ norte

        if brazos == 4:
            return "CROSS"
        if brazos == 3:
            return "T"
        if brazos == 2:
            return "L"
        return "LIBRE"
