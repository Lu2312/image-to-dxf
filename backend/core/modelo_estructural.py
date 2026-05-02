"""
modelo_estructural.py
---------------------
Contrato de datos intermedio del sistema de agentes ArqGen.

El modelo separa la *decisión estructural* (cuántos castillos, dónde,
por qué) de la *generación de geometría* (dibujo en DXF).  Esto permite:
  - Auditar el diseño como ingeniero antes de que ezdxf escriba el archivo.
  - Intercambiar el motor normativo sin tocar el generador DXF.
  - Escribir tests unitarios sobre la lógica, no sobre el dibujo.

Jerarquía:
  ModeloEstructural
    ├── metadatos_normativos : MetadatosNormativos
    ├── elementos_verticales : List[ElementoVertical]   (castillos / columnas)
    ├── elementos_horizontales : List[ElementoHorizontal] (dalas / trabes)
    ├── advertencias : List[str]
    └── cumple_ntc : bool
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Elementos Verticales  (castillos y columnas)
# ---------------------------------------------------------------------------

@dataclass
class ElementoVertical:
    """Representa un castillo o columna de confinamiento."""

    tipo: str               # "CASTILLO" | "COLUMNA"
    x: float                # coordenada X del centroide (mm)
    y: float                # coordenada Y del centroide (mm)
    seccion: Tuple[float, float] = (150.0, 150.0)  # (ancho, fondo) mm
    altura: float = 2700.0  # mm — altura libre del nivel

    # Armado
    varilla: str   = "No.4"     # denominación ASTM (No.2 … No.8)
    n_varillas: int = 4         # cantidad de varillas longitudinales
    sep_estribos: float = 200.0 # mm — separación máx. estribos (NTC §6.4)

    # Trazabilidad normativa
    norma: str  = "NTC Mampostería 2017 §6.4"
    razon: str  = ""            # p.ej. "Esquina tipo L en nodo (1,A)"
    tipo_nodo: str = ""         # "L" | "T" | "CROSS" | "INTERMEDIO"


# ---------------------------------------------------------------------------
# Elementos Horizontales  (dalas y trabes de cerramiento)
# ---------------------------------------------------------------------------

@dataclass
class ElementoHorizontal:
    """Representa una dala de cerramiento o trabe."""

    tipo: str               # "DALA" | "TRABE"
    x0: float               # inicio (mm)
    y0: float
    x1: float               # fin (mm)
    y1: float
    z: float = 2700.0       # elevación respecto a NPT (mm)  = altura_muro

    # Sección
    peralte: float = 150.0  # mm
    ancho: float   = 150.0  # mm  (≥ espesor del muro, NTC Mampostería)

    # Armado
    varilla: str    = "No.3"
    n_varillas: int = 2
    sep_estribos: float = 200.0

    # Trazabilidad
    norma: str  = "NTC Mampostería 2017 §7.2"
    razon: str  = ""        # p.ej. "Dala de cerramiento eje A: nodo 1A → 3A"

    @property
    def longitud(self) -> float:
        import math
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


# ---------------------------------------------------------------------------
# Metadatos Normativos  (encabezado del modelo)
# ---------------------------------------------------------------------------

@dataclass
class MetadatosNormativos:
    norma: str  = "NTC-RCDF 2017"
    fc: float   = 200.0          # kg/cm²  — resistencia concreto f'c
    fy: float   = 4200.0         # kg/cm²  — límite fluencia acero f_y
    recubrimiento: float = 25.0  # mm      — castillos de mampostería
    zona_sismica: str = "IIId"   # zona sísmica CDMX  (IIIa…IIId)
    tipo_suelo: str   = "III"    # tipo de suelo CDMX (I, II, III)


# ---------------------------------------------------------------------------
# Modelo Estructural  (raíz)
# ---------------------------------------------------------------------------

@dataclass
class ModeloEstructural:
    metadatos_normativos: MetadatosNormativos = field(
        default_factory=MetadatosNormativos
    )
    elementos_verticales: List[ElementoVertical] = field(default_factory=list)
    elementos_horizontales: List[ElementoHorizontal] = field(default_factory=list)
    advertencias: List[str] = field(default_factory=list)
    cumple_ntc: bool = True

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Exporta el modelo a un dict serializable (JSON-friendly)."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    # ------------------------------------------------------------------
    # Estadísticas rápidas
    # ------------------------------------------------------------------

    @property
    def n_castillos(self) -> int:
        return sum(1 for e in self.elementos_verticales if e.tipo == "CASTILLO")

    @property
    def n_dalas(self) -> int:
        return sum(1 for e in self.elementos_horizontales if e.tipo == "DALA")

    def resumen(self) -> str:
        lines = [
            f"ModeloEstructural — {'OK' if self.cumple_ntc else 'NO CUMPLE NTC'}",
            f"  Castillos  : {self.n_castillos}",
            f"  Dalas      : {self.n_dalas}",
            f"  Advertencias: {len(self.advertencias)}",
        ]
        for w in self.advertencias:
            lines.append(f"    ⚠ {w}")
        return "\n".join(lines)
