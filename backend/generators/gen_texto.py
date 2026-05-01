"""
gen_texto.py
------------
Módulo 5 — Texto / Descripción Natural → DXF

Flujo:
  1. El usuario escribe una descripción de la vivienda en español
     (ej: "casa de 3 recamaras, sala, cocina, 2 banos, lote 8x15")
  2. El parser extrae: dimensiones del lote, programa arquitectónico,
     tipo de material, número de plantas.
  3. Se construyen PlantaParams y se llama al PlantaGenerator.
  4. Devuelve los mismos outputs: DXF, PDF, Excel, SVG, NTC.

El parser es determinista (regex + tablas de palabras clave).
Preparado para intercambiar por un LLM manteniendo la misma interfaz.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Tablas de palabras clave  (español flexible: con/sin acento)
# ---------------------------------------------------------------------------

# Mapeo de etiqueta canónica → posibles palabras en el texto
_KEYWORDS: Dict[str, List[str]] = {
    "SALA":        ["sala", "estar", "living"],
    "COMEDOR":     ["comedor", "dining"],
    "SALA_COMEDOR":["sala-comedor", "sala comedor", "sala/comedor"],
    "COCINA":      ["cocina", "kitchen", "cocineta"],
    "COCINA_COMEDOR": ["cocina-comedor", "cocina comedor"],
    "RECAMARA":    ["recamara", "recámara", "habitacion", "habitación",
                    "cuarto", "dormitorio", "bedroom"],
    "BANO":        ["baño", "bano", "wc", "sanitario", "toilet", "bathroom"],
    "BANO_MEDIO":  ["medio baño", "medio bano", "half bath", "1/2 bano"],
    "ESTUDIO":     ["estudio", "oficina", "despacho", "study"],
    "PATIO":       ["patio", "jardín", "jardin", "terraza", "balcon", "balcón"],
    "PASILLO":     ["pasillo", "corredor", "hall", "distribuidor"],
    "GARAGE":      ["garage", "garaje", "cochera", "estacionamiento"],
    "LAVANDERIA":  ["lavandería", "lavanderia", "patio servicio",
                    "cuarto lavado", "utility"],
    "BODEGA":      ["bodega", "almacén", "almacen", "storage"],
}

# Tamaños por defecto CONAVI (mm) cuando el usuario no especifica
_DEFAULT_SIZE: Dict[str, Tuple[float, float]] = {
    "SALA":         (3500, 4000),
    "COMEDOR":      (3000, 3500),
    "SALA_COMEDOR": (4500, 4000),
    "COCINA":       (2500, 3000),
    "COCINA_COMEDOR":(3500, 3000),
    "RECAMARA":     (3500, 4000),
    "BANO":         (1800, 2500),
    "BANO_MEDIO":   (1200, 2000),
    "ESTUDIO":      (3000, 3500),
    "PATIO":        (2500, 3000),
    "PASILLO":      (1200, 3000),
    "GARAGE":       (3000, 5500),
    "LAVANDERIA":   (2000, 2500),
    "BODEGA":       (2000, 2500),
}

# Nombres canónicos legibles para el DXF
_LABEL: Dict[str, str] = {
    "SALA":         "SALA",
    "COMEDOR":      "COMEDOR",
    "SALA_COMEDOR": "SALA - COMEDOR",
    "COCINA":       "COCINA",
    "COCINA_COMEDOR":"COCINA - COMEDOR",
    "RECAMARA":     "RECAMARA",
    "BANO":         "BANO",
    "BANO_MEDIO":   "1/2 BANO",
    "ESTUDIO":      "ESTUDIO",
    "PATIO":        "PATIO",
    "PASILLO":      "PASILLO",
    "GARAGE":       "GARAGE",
    "LAVANDERIA":   "LAVANDERIA",
    "BODEGA":       "BODEGA",
}


# ---------------------------------------------------------------------------
# Resultado del parser
# ---------------------------------------------------------------------------

@dataclass
class TextoParseResult:
    lote_ancho:   float = 8000.0   # mm
    lote_fondo:   float = 15000.0  # mm
    espesor_muro: float = 150.0    # mm
    altura_muro:  float = 2700.0   # mm
    project_name: str   = "Proyecto ArqGen"
    date:         str   = "2026"
    recintos:     List[Dict] = field(default_factory=list)
    notas:        List[str]  = field(default_factory=list)   # advertencias


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Normaliza texto: minúsculas, sin acentos extra, sin puntuación."""
    text = text.lower()
    for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),
                     ("ü","u"),("ñ","n"),(",",""),(";"," "),("\n"," ")]:
        text = text.replace(src, dst)
    return text


def _extract_lote(norm_text: str) -> Optional[Tuple[float, float]]:
    """
    Detecta patrones de lote:  "8x15", "8 x 15", "lote 8.5 por 20", etc.
    Devuelve (ancho_mm, fondo_mm) o None.
    """
    patterns = [
        r"lote\s+de\s+([\d.]+)\s*[xX×por]\s*([\d.]+)",
        r"lote\s+([\d.]+)\s*[xX×por]\s*([\d.]+)",
        r"([\d.]+)\s*[xX×]\s*([\d.]+)\s*m(?:etros)?",
        r"([\d.]+)\s*[xX×]\s*([\d.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, norm_text)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            # Si los valores parecen metros (<100), convertir a mm
            if a < 100:
                a *= 1000
            if b < 100:
                b *= 1000
            return a, b
    return None


def _extract_count(token: str, norm_text: str) -> int:
    """
    Extrae cuántos de 'token' hay:
    "3 recamaras", "dos recamaras", "recamara principal y secundaria"
    """
    _NUMS = {"un":1,"una":1,"dos":2,"tres":3,"cuatro":4,"cinco":5,
             "seis":6,"siete":7,"ocho":8,"nueve":9,"diez":10}
    # número escrito antes del token
    for word, val in _NUMS.items():
        if re.search(rf"\b{word}\s+{token}", norm_text):
            return val
    # dígito antes del token
    m = re.search(rf"(\d+)\s+{token}", norm_text)
    if m:
        return int(m.group(1))
    # token presente → al menos 1
    if re.search(rf"\b{token}", norm_text):
        return 1
    return 0


def _make_recinto(tipo: str, index: int = 0) -> Dict:
    """Crea un dict de recinto con dimensiones CONAVI."""
    ancho, fondo = _DEFAULT_SIZE.get(tipo, (3000, 3000))
    label = _LABEL.get(tipo, tipo)
    if index > 0:
        label = f"{label} {index + 1}"
    return {"nombre": label, "ancho": ancho, "fondo": fondo}


def parse_texto(text: str, project_name: str = "Proyecto ArqGen",
                date: str = "2026") -> TextoParseResult:
    """
    Convierte texto libre en español a un TextoParseResult con programa
    arquitectónico y dimensiones de lote.
    """
    norm = _norm(text)
    result = TextoParseResult(project_name=project_name, date=date)
    result.recintos = []

    # ── Lote ────────────────────────────────────────────────────────────
    lote = _extract_lote(norm)
    if lote:
        result.lote_ancho, result.lote_fondo = lote
    else:
        result.notas.append(
            "No se detecto dimensión de lote; usando default 8 x 15 m."
        )

    # ── Espesor de muro ──────────────────────────────────────────────────
    m_muro = re.search(r"muro\s+de\s+(\d+)\s*cm", norm)
    if m_muro:
        result.espesor_muro = float(m_muro.group(1)) * 10   # cm → mm

    # ── Altura de muro ───────────────────────────────────────────────────
    m_alt = re.search(r"altura\s+(?:de\s+)?(\d[\d.]*)\s*m", norm)
    if m_alt:
        h = float(m_alt.group(1))
        result.altura_muro = h * 1000 if h < 10 else h   # m → mm

    # ── Programa: orden de preferencia (integrados primero) ─────────────
    ORDERED_TYPES = [
        "SALA_COMEDOR", "COCINA_COMEDOR",
        "SALA", "COMEDOR", "COCINA",
        "RECAMARA", "BANO_MEDIO", "BANO",
        "ESTUDIO", "PATIO", "GARAGE", "LAVANDERIA", "BODEGA", "PASILLO",
    ]

    seen_sala   = False
    seen_comedor = False
    seen_cocina  = False

    for tipo in ORDERED_TYPES:
        keywords = _KEYWORDS[tipo]

        # Para integrados, buscar la frase completa
        found = any(kw in norm for kw in keywords)
        if not found:
            continue

        # Evitar duplicar si ya se capturó integrado
        if tipo == "SALA" and seen_sala:
            continue
        if tipo == "COMEDOR" and seen_comedor:
            continue
        if tipo == "COCINA" and seen_cocina:
            continue

        # Número de unidades (aplica a recámaras, baños, etc.)
        count_key = keywords[0]   # primera keyword para buscar cantidad
        n = _extract_count(count_key, norm)
        if n == 0:
            n = 1

        for i in range(n):
            result.recintos.append(_make_recinto(tipo, i if n > 1 else 0))

        if tipo == "SALA_COMEDOR":
            seen_sala = seen_comedor = True
        elif tipo == "SALA":
            seen_sala = True
        elif tipo == "COMEDOR":
            seen_comedor = True
        elif tipo == "COCINA_COMEDOR":
            seen_cocina = seen_comedor = True
        elif tipo == "COCINA":
            seen_cocina = True

    # Si no se detectó ningún recinto → programa mínimo
    if not result.recintos:
        result.notas.append(
            "No se detectaron recintos; se generó un programa basico CONAVI."
        )
        for tipo in ["SALA_COMEDOR", "COCINA", "RECAMARA", "BANO"]:
            result.recintos.append(_make_recinto(tipo))

    return result
