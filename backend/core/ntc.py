"""
ntc.py
------
Constantes y reglas de las Normas Técnicas Complementarias (NTC)
del Reglamento de Construcción del Distrito Federal (RCDF),
aplicadas a la generación paramétrica de planos.

Referencia base: NTC para Diseño y Construcción de Estructuras de
Concreto (2017) y NTC para Criterios y Acciones para el Diseño
Estructural de las Edificaciones (2020).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Recubrimientos mínimos (mm)  – NTC Concreto 2017, tabla 3.1
# ---------------------------------------------------------------------------
RECUBRIMIENTO = {
    "zapata":       75,   # Concreto en contacto con el suelo
    "losa_ext":     40,   # Losa expuesta a la intemperie
    "losa_int":     20,   # Losa interior
    "muro_ext":     40,   # Muro exterior
    "muro_int":     20,   # Muro interior
    "trabe":        40,   # Trabe / viga principal
    "columna":      40,   # Columna
    "castillo":     25,   # Castillo de mampostería
}

# ---------------------------------------------------------------------------
# Separación máx. entre castillos (m) – NTC Mampostería 2017, §6.4
# ---------------------------------------------------------------------------
MAX_SEP_CASTILLOS = 4.0      # metros

# ---------------------------------------------------------------------------
# Secciones mínimas de castillos (mm) – NTC Mampostería 2017
# ---------------------------------------------------------------------------
CASTILLO_MIN = {
    "lado": 150,            # Dimensión mínima de la sección
    "area_acero_min": 3 * 200,   # 3 varillas Ø10 = 3 × 200 mm² ≈ 600 mm²
    "estribos_sep_max": 200,     # Separación máxima de estribos (mm)
}

# ---------------------------------------------------------------------------
# Secciones mínimas de dalas / vigas de cerramiento
# ---------------------------------------------------------------------------
DALA_MIN = {
    "alto": 150,    # mm
    "ancho": 150,   # mm  (≥ espesor del muro)
}

# ---------------------------------------------------------------------------
# Cargas mínimas de diseño – NTC Cargas 2020 (kPa)
# ---------------------------------------------------------------------------
CARGA = {
    "muerta_losa_concreto":  2.40,   # kPa  (losa maciza 10 cm)
    "viva_habitacional":     1.80,   # kPa
    "viva_oficinas":         2.50,   # kPa
    "viva_estacionamiento":  3.00,   # kPa
}

# ---------------------------------------------------------------------------
# Dimensiones de zapatas corridas mínimas (mm) – NTC Cimentaciones 2017
# ---------------------------------------------------------------------------
ZAPATA_CORRIDA_MIN = {
    "ancho":     400,    # mm – mínimo bajo muro de 150 mm
    "desplante": 500,    # mm – profundidad mínima de desplante
    "alto":      300,    # mm – peralte mínimo
}

ZAPATA_AISLADA_MIN = {
    "largo":     600,
    "ancho":     600,
    "alto":      300,
    "desplante": 700,
}

# ---------------------------------------------------------------------------
# Espesor mínimo de muros de mampostería (mm) – NTC Mampostería
# ---------------------------------------------------------------------------
ESPESOR_MURO_MIN = 120    # mm  (tabique rojo recocido ½ pie)
ESPESOR_MURO_STD = 150    # mm  (bloque de concreto o tabique a una vista)

# ---------------------------------------------------------------------------
# Capas estándar de un plano arquitectónico ejecutivo
# ---------------------------------------------------------------------------
LAYERS: Dict[str, Dict] = {
    "A-MURO":      {"color": 7,  "lw": 50,  "desc": "Muros y divisiones"},
    "A-EJE":       {"color": 1,  "lw": 18,  "desc": "Ejes y retículas"},
    "A-COTA":      {"color": 3,  "lw": 18,  "desc": "Cotas y acotaciones"},
    "A-PUERTA":    {"color": 4,  "lw": 25,  "desc": "Puertas y vanos"},
    "A-VENTANA":   {"color": 4,  "lw": 25,  "desc": "Ventanas"},
    "A-MUEBLE":    {"color": 8,  "lw": 13,  "desc": "Muebles y equipos"},
    "E-CASTILLO":  {"color": 2,  "lw": 35,  "desc": "Castillos"},
    "E-DALA":      {"color": 5,  "lw": 35,  "desc": "Dalas / vigas de cerramiento"},
    "E-ZAPATA":    {"color": 6,  "lw": 50,  "desc": "Zapatas y cimentación"},
    "E-ARMADO":    {"color": 2,  "lw": 25,  "desc": "Armado de acero de refuerzo"},
    "E-HATCH":     {"color": 8,  "lw": 13,  "desc": "Rellenos y hatches"},
    "T-TEXTO":     {"color": 7,  "lw": 13,  "desc": "Textos y notas"},
    "T-TITULO":    {"color": 7,  "lw": 25,  "desc": "Cuadro de rotulación"},
    "INFO":        {"color": 8,  "lw": 13,  "desc": "Metadatos del archivo"},
}

# ---------------------------------------------------------------------------
# Simbología de acero de refuerzo (diámetros nominales en mm)
# ---------------------------------------------------------------------------
VARILLA: Dict[str, float] = {
    "No.2":  6.35,
    "No.3":  9.53,
    "No.4": 12.70,
    "No.5": 15.88,
    "No.6": 19.05,
    "No.8": 25.40,
}
AREA_VARILLA: Dict[str, float] = {  # mm²
    "No.2":  31.7,
    "No.3":  71.3,
    "No.4": 126.7,
    "No.5": 198.6,
    "No.6": 284.5,
    "No.8": 506.7,
}


# ---------------------------------------------------------------------------
# CONAVI — Criterios Técnicos para Vivienda Adecuada (2023)
# Secretaría de Desarrollo Agrario, Territorial y Urbano (SEDATU)
# Aplica a programas de vivienda social e interés social en México
# ---------------------------------------------------------------------------
CONAVI_AREA_MIN: Dict[str, float] = {
    # m² mínimos por tipo de recinto  (CONAVI / RCDF Art. 73)
    "SALA":            12.0,   # Sala de estar
    "COMEDOR":          6.0,   # Comedor independiente
    "SALA_COMEDOR":    16.0,   # Sala-comedor integrado
    "COCINA":           5.0,   # Cocina independiente
    "COCINA_COMEDOR":   9.0,   # Cocina-comedor integrado
    "RECAMARA":         9.0,   # Recámara principal  (≥2.70 m libre)
    "RECAMARA2":        7.0,   # Recámara secundaria (≥2.40 m libre)
    "BANO":             2.4,   # Baño completo       (≥1.20×2.00 m)
    "BANO_MEDIO":       1.2,   # Medio baño
    "PATIO":            4.0,   # Patio de servicio
    "GARAGE":          13.5,   # Un cajón  2.50×5.50 m
    "PASILLO":          1.8,   # Pasillo (mínimo 0.90 m libre)
}

CONAVI_ANCHO_MIN: Dict[str, float] = {
    # mm — ancho libre mínimo por tipo de recinto
    "RECAMARA":   2700,
    "RECAMARA2":  2400,
    "COCINA":     1500,   # libre entre muebles enfrentados
    "BANO":       1200,
    "PASILLO":     900,   # SEDATU / accesibilidad
}

# Infonavit: superficie mínima de construcción (Art. reglamento interno)
INFONAVIT_AREA_CONST_MIN = 42.0   # m²  vivienda de interés social
INFONAVIT_AREA_REC       = 55.0   # m²  recomendada para familia de 4 personas

# ---------------------------------------------------------------------------
# RCDF — Reglamento de Construcciones del Distrito Federal
# Habitabilidad: Artículos 73-76
# ---------------------------------------------------------------------------
RCDF_ALTURA_LIBRE_MIN = 2300   # mm — altura libre mínima    (Art. 75)
RCDF_ALTURA_LIBRE_REC = 2700   # mm — altura recomendada
RCDF_VENTANA_PCT_MIN  = 0.15   # 15 % del área del recinto  (Art. 76)
RCDF_VENTANA_PCT_REC  = 0.20   # 20 % recomendado
RCDF_ILUM_PCT_MIN     = 0.15   # 15 % del área (iluminación natural)

RCDF_PUERTA_ANCHO_MIN: Dict[str, float] = {
    "exterior":    900,   # mm  acceso principal
    "interior":    750,   # mm
    "bano":        700,   # mm
}

# ---------------------------------------------------------------------------
# NOM-001-SEDATU-2021 + accesibilidad universal
# ---------------------------------------------------------------------------
SEDATU_ACCESIBILIDAD: Dict[str, float] = {
    "ancho_paso_min":     900,   # mm — libre para silla de ruedas
    "radio_giro":        1500,   # mm — espacio de giro silla
    "ancho_rampa_min":    900,   # mm
    "pendiente_rampa":    0.08,  # 8 % máximo
    "huella_escalon_min": 270,   # mm
    "contrahuella_max":   180,   # mm
}


@dataclass
class NTCValidator:
    """Valida parámetros contra NTC-RCDF / CONAVI / Infonavit."""

    warnings: List[str] = field(default_factory=list)
    errors:   List[str] = field(default_factory=list)

    # ── estructural ────────────────────────────────────────────────────────
    def check_muro(self, espesor_mm: float) -> None:
        if espesor_mm < ESPESOR_MURO_MIN:
            self.errors.append(
                f"Espesor de muro {espesor_mm} mm < minimo NTC "
                f"({ESPESOR_MURO_MIN} mm)."
            )

    def check_castillos(self, separacion_m: float) -> None:
        if separacion_m > MAX_SEP_CASTILLOS:
            self.errors.append(
                f"Separacion entre castillos {separacion_m:.2f} m > "
                f"maximo NTC ({MAX_SEP_CASTILLOS} m)."
            )

    def check_zapata_corrida(self, ancho_mm: float, alto_mm: float) -> None:
        if ancho_mm < ZAPATA_CORRIDA_MIN["ancho"]:
            self.warnings.append(
                f"Ancho de zapata corrida {ancho_mm} mm < recomendado NTC "
                f"({ZAPATA_CORRIDA_MIN['ancho']} mm)."
            )
        if alto_mm < ZAPATA_CORRIDA_MIN["alto"]:
            self.warnings.append(
                f"Peralte de zapata {alto_mm} mm < minimo NTC "
                f"({ZAPATA_CORRIDA_MIN['alto']} mm)."
            )

    # ── habitabilidad CONAVI / RCDF ────────────────────────────────────────
    def check_altura(self, altura_mm: float) -> None:
        if altura_mm < RCDF_ALTURA_LIBRE_MIN:
            self.errors.append(
                f"Altura libre {altura_mm} mm < minimo RCDF Art.75 "
                f"({RCDF_ALTURA_LIBRE_MIN} mm)."
            )
        elif altura_mm < RCDF_ALTURA_LIBRE_REC:
            self.warnings.append(
                f"Altura libre {altura_mm} mm < recomendado ({RCDF_ALTURA_LIBRE_REC} mm)."
            )

    def check_recinto(self, nombre: str, area_m2: float,
                      es_principal: bool = False) -> None:
        """Valida area minima CONAVI segun tipo de recinto."""
        n = nombre.upper()
        key = None
        if "SALA" in n and "COMEDOR" in n:
            key = "SALA_COMEDOR"
        elif "SALA" in n:
            key = "SALA"
        elif "COMEDOR" in n:
            key = "COMEDOR"
        elif "COCINA" in n and "COMEDOR" in n:
            key = "COCINA_COMEDOR"
        elif "COCINA" in n:
            key = "COCINA"
        elif any(k in n for k in ("RECAMARA", "HABITACION", "CUARTO")):
            key = "RECAMARA" if es_principal else "RECAMARA2"
        elif any(k in n for k in ("BANO", "BAO", "WC", "SANITARIO")):
            key = "BANO"
        elif "PATIO" in n:
            key = "PATIO"
        elif "PASILLO" in n or "CORREDOR" in n:
            key = "PASILLO"

        if key and key in CONAVI_AREA_MIN:
            minimo = CONAVI_AREA_MIN[key]
            if area_m2 < minimo:
                self.errors.append(
                    f"{nombre}: {area_m2:.2f} m2 < minimo CONAVI {minimo} m2."
                )
            elif area_m2 < minimo * 1.10:
                self.warnings.append(
                    f"{nombre}: {area_m2:.2f} m2 — marginal vs CONAVI {minimo} m2."
                )

    def check_programa(self, total_m2: float) -> None:
        """Verifica superficie total contra Infonavit."""
        if total_m2 < INFONAVIT_AREA_CONST_MIN:
            self.errors.append(
                f"Area total {total_m2:.1f} m2 < minimo Infonavit "
                f"({INFONAVIT_AREA_CONST_MIN} m2)."
            )
        elif total_m2 < INFONAVIT_AREA_REC:
            self.warnings.append(
                f"Area total {total_m2:.1f} m2 — recomendado Infonavit "
                f"{INFONAVIT_AREA_REC} m2 para familia de 4 personas."
            )

    # ── resultado ─────────────────────────────────────────────────────────
    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def report(self) -> Dict:
        return {"errors": self.errors, "warnings": self.warnings, "valid": self.is_valid}
