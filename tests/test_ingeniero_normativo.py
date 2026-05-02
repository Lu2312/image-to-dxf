"""
test_ingeniero_normativo.py
---------------------------
Tests unitarios del IngenieroNormativo (Agente 2).

Verifican que las reglas NTC se aplican correctamente sobre
distintas configuraciones de muros, independientemente del DXF.

Ejecutar:
    pytest tests/test_ingeniero_normativo.py -v
"""
import math
import sys
import os

# Asegura que el root del proyecto esté en el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agents.analista_espacial import AnalistaEspacial
from backend.agents.ingeniero_normativo import (
    IngenieroNormativo,
    SEP_MAX_CASTILLOS_MM,
)
from backend.core.modelo_estructural import MetadatosNormativos


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _analizar_simple(recintos, espesor=150.0, lote_ancho=None, lote_fondo=None):
    """Analiza y diseña a partir de una lista de recintos simples."""
    if not lote_ancho:
        lote_ancho = max(r["x"] + r["ancho"] for r in recintos) + espesor
    if not lote_fondo:
        lote_fondo = max(r["y"] + r["fondo"] for r in recintos) + espesor

    topo = AnalistaEspacial().analizar(
        recintos=recintos,
        espesor_muro=espesor,
        lote_ancho=lote_ancho,
        lote_fondo=lote_fondo,
        altura_muro=2700.0,
    )
    modelo = IngenieroNormativo().disenar(topo, MetadatosNormativos())
    return modelo


# ---------------------------------------------------------------------------
# R-01: Castillos en esquinas
# ---------------------------------------------------------------------------

class TestCastillosEnEsquinas:

    def test_recinto_unico_tiene_4_castillos_minimo(self):
        """Un recinto simple genera al menos 4 castillos (una por esquina)."""
        recintos = [{"x": 150, "y": 150, "ancho": 3000, "fondo": 4000,
                     "nombre": "SALA"}]
        modelo = _analizar_simple(recintos)
        assert modelo.n_castillos >= 4, (
            f"Se esperaban ≥4 castillos, se obtuvieron {modelo.n_castillos}"
        )

    def test_castillo_en_esquina_inferior_izquierda(self):
        """Debe existir un castillo en la esquina (0, 0) del edificio."""
        recintos = [{"x": 150, "y": 150, "ancho": 3000, "fondo": 3000,
                     "nombre": "SALA"}]
        modelo = _analizar_simple(recintos, espesor=150)
        pts = {(round(e.x, 0), round(e.y, 0))
               for e in modelo.elementos_verticales}
        # la esquina inferior-izquierda queda en eje (75, 75) = em/2
        assert any(abs(x - 75) < 5 and abs(y - 75) < 5 for x, y in pts), (
            f"No hay castillo cerca de (75,75). Puntos: {pts}"
        )

    def test_dos_recintos_comparten_castillos_en_muro_comun(self):
        """Dos recintos contiguos comparten los castillos del muro medianero."""
        recintos = [
            {"x": 150, "y": 150, "ancho": 3000, "fondo": 3000, "nombre": "SALA"},
            {"x": 3300, "y": 150, "ancho": 3000, "fondo": 3000, "nombre": "COCINA"},
        ]
        modelo = _analizar_simple(recintos)
        # No debe duplicar castillos en el mismo punto
        pts = [(round(e.x, 1), round(e.y, 1))
               for e in modelo.elementos_verticales]
        assert len(pts) == len(set(pts)), "Hay castillos duplicados en el mismo nodo"


# ---------------------------------------------------------------------------
# R-02: Castillos intermedios en tramos largos
# ---------------------------------------------------------------------------

class TestCastillosIntermedios:

    def test_muro_7m_genera_castillo_intermedio(self):
        """
        Muro de 7 000 mm > SEP_MAX (3 500 mm) debe generar al menos
        1 castillo intermedio según NTC Mampostería 2017 §6.4.
        """
        recintos = [{"x": 150, "y": 150, "ancho": 7000, "fondo": 3000,
                     "nombre": "SALON"}]
        modelo = _analizar_simple(recintos)
        intermedios = [e for e in modelo.elementos_verticales
                       if e.tipo_nodo == "INTERMEDIO"]
        assert len(intermedios) >= 1, (
            f"Muro de 7m debería generar ≥1 castillo intermedio. "
            f"Se obtuvieron {len(intermedios)}"
        )

    def test_muro_7m_castillo_intermedio_en_rango(self):
        """El castillo intermedio debe estar entre 0 y 7 000 mm del inicio."""
        recintos = [{"x": 150, "y": 150, "ancho": 7000, "fondo": 3000,
                     "nombre": "SALON"}]
        modelo = _analizar_simple(recintos)
        intermedios = [e for e in modelo.elementos_verticales
                       if e.tipo_nodo == "INTERMEDIO"]
        for c in intermedios:
            assert 200 < c.x < 7450, (
                f"Castillo intermedio fuera de rango: x={c.x}"
            )

    def test_muro_de_exactamente_sep_max_no_genera_intermedio(self):
        """
        Un muro exactamente igual a SEP_MAX no necesita castillo intermedio.
        """
        recintos = [{"x": 150, "y": 150,
                     "ancho": SEP_MAX_CASTILLOS_MM, "fondo": 3000,
                     "nombre": "SALA"}]
        modelo = _analizar_simple(recintos)
        intermedios_h = [
            e for e in modelo.elementos_verticales
            if e.tipo_nodo == "INTERMEDIO" and
            abs(e.y - 150) < 10   # en el muro inferior (y=150)
        ]
        assert len(intermedios_h) == 0, (
            f"Muro igual a SEP_MAX no debería tener intermedio, "
            f"se generaron {len(intermedios_h)}"
        )

    def test_muro_doble_sep_max_genera_al_menos_2_intermedios(self):
        """Muro de 2×SEP_MAX debe tener ≥2 castillos intermedios."""
        largo = int(SEP_MAX_CASTILLOS_MM * 2) + 100
        recintos = [{"x": 150, "y": 150, "ancho": largo, "fondo": 3000,
                     "nombre": "PASILLO"}]
        modelo = _analizar_simple(recintos)
        intermedios = [e for e in modelo.elementos_verticales
                       if e.tipo_nodo == "INTERMEDIO"]
        assert len(intermedios) >= 2, (
            f"Muro de {largo}mm debería tener ≥2 intermedios, "
            f"se obtuvieron {len(intermedios)}"
        )


# ---------------------------------------------------------------------------
# R-03: Dalas de cerramiento
# ---------------------------------------------------------------------------

class TestDalasDeCerramiento:

    def test_cada_segmento_tiene_dala(self):
        """Cada segmento de muro debe tener una dala de cerramiento."""
        recintos = [{"x": 150, "y": 150, "ancho": 3000, "fondo": 3000,
                     "nombre": "SALA"}]
        topo = AnalistaEspacial().analizar(
            recintos=recintos, espesor_muro=150,
            lote_ancho=3450, lote_fondo=3450, altura_muro=2700,
        )
        modelo = IngenieroNormativo().disenar(topo)
        assert modelo.n_dalas == len(topo.segmentos), (
            f"Se esperaban {len(topo.segmentos)} dalas, "
            f"se obtuvieron {modelo.n_dalas}"
        )

    def test_dala_a_altura_correcta(self):
        """Todas las dalas deben estar a la altura_muro (2 700 mm)."""
        recintos = [{"x": 150, "y": 150, "ancho": 3000, "fondo": 3000,
                     "nombre": "SALA"}]
        modelo = _analizar_simple(recintos)
        for dala in modelo.elementos_horizontales:
            assert dala.z == 2700.0, (
                f"Dala a z={dala.z}, se esperaba 2700"
            )

    def test_dala_tiene_apoyo_en_castillo(self):
        """
        Ninguna dala debe tener advertencias de 'ERROR DE APOYO'
        en una configuración válida.
        """
        recintos = [{"x": 150, "y": 150, "ancho": 3000, "fondo": 4000,
                     "nombre": "SALA"}]
        modelo = _analizar_simple(recintos)
        errores_apoyo = [w for w in modelo.advertencias
                         if "ERROR DE APOYO" in w]
        assert len(errores_apoyo) == 0, (
            f"Advertencias de apoyo inesperadas:\n" +
            "\n".join(errores_apoyo)
        )


# ---------------------------------------------------------------------------
# Clasificación de nodos
# ---------------------------------------------------------------------------

class TestClasificacionNodos:

    def test_esquinas_exteriores_son_tipo_L(self):
        """Las 4 esquinas del edificio deben clasificarse como nodos L."""
        recintos = [{"x": 150, "y": 150, "ancho": 3000, "fondo": 3000,
                     "nombre": "SALA"}]
        topo = AnalistaEspacial().analizar(
            recintos=recintos, espesor_muro=150,
            lote_ancho=3450, lote_fondo=3450, altura_muro=2700,
        )
        nodos_L = [n for n in topo.nodos if n.tipo == "L"]
        assert len(nodos_L) == 4, (
            f"Se esperaban 4 nodos L (esquinas), se encontraron {len(nodos_L)}"
        )

    def test_nodo_interior_es_tipo_cross(self):
        """
        Cuando 4 recintos comparten una esquina central,
        ese nodo debe ser CROSS.
        """
        # 2×2 recintos: el nodo central debe ser CROSS
        recintos = [
            {"x": 150,  "y": 150,  "ancho": 2000, "fondo": 2000, "nombre": "R1"},
            {"x": 2300, "y": 150,  "ancho": 2000, "fondo": 2000, "nombre": "R2"},
            {"x": 150,  "y": 2300, "ancho": 2000, "fondo": 2000, "nombre": "R3"},
            {"x": 2300, "y": 2300, "ancho": 2000, "fondo": 2000, "nombre": "R4"},
        ]
        topo = AnalistaEspacial().analizar(
            recintos=recintos, espesor_muro=150,
            lote_ancho=4450, lote_fondo=4450, altura_muro=2700,
        )
        nodos_cross = [n for n in topo.nodos if n.tipo == "CROSS"]
        assert len(nodos_cross) >= 1, (
            "Se esperaba al menos 1 nodo CROSS en la intersección central"
        )


# ---------------------------------------------------------------------------
# ModeloEstructural — serialización
# ---------------------------------------------------------------------------

class TestSerializacion:

    def test_to_dict_es_serializable(self):
        """El modelo debe exportar a dict sin errores."""
        recintos = [{"x": 150, "y": 150, "ancho": 3000, "fondo": 3000,
                     "nombre": "SALA"}]
        modelo = _analizar_simple(recintos)
        d = modelo.to_dict()
        assert "elementos_verticales" in d
        assert "elementos_horizontales" in d
        assert "metadatos_normativos" in d

    def test_to_json_es_valido(self):
        """El JSON resultante debe poder parsearse de vuelta."""
        import json
        recintos = [{"x": 150, "y": 150, "ancho": 3000, "fondo": 3000,
                     "nombre": "SALA"}]
        modelo = _analizar_simple(recintos)
        j = modelo.to_json()
        parsed = json.loads(j)
        assert isinstance(parsed["elementos_verticales"], list)
