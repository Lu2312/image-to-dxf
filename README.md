# ArqGen — Generador Paramétrico de Planos Arquitectónicos

SaaS para generación automática de planos arquitectónicos y estructurales en DXF bajo las **Normas Técnicas Complementarias del RCDF** (Ciudad de México).

**Demo en producción:** http://159.89.157.63:8080  
**API interactiva:** http://159.89.157.63:8080/docs

## Módulos

| Módulo | Descripción |
|---|---|
| **Planta Arquitectónica** | Planta tipo, alzado frontal y corte A-A' con validación NTC-RCDF |
| **Cimentación** | Zapatas corridas, zapatas aisladas con armado y catálogo de conceptos |
| **Carpintería / Cancelería** | Detalles de ventanas, puertas y closets con despiece |
| **Imagen a DXF** | Conversión de imágenes (PNG/JPG) a entidades DXF vectoriales |
| **Texto a DXF** | Descripción en lenguaje natural → planta arquitectónica completa |

## Salidas por módulo

Todos los módulos de arquitectura generan:
- Archivo **DXF** (AC1024 / AutoCAD 2010+, unidades mm)
- Archivo **PDF** (render del plano)
- Archivo **Excel** con catálogo de conceptos y cantidades
- **Vista previa SVG** en el navegador
- **Reporte NTC** con validaciones y observaciones

## Conversion modes

## Instalación

```bash
git clone https://github.com/Lu2312/image-to-dxf.git
cd image-to-dxf
pip install -r requirements.txt
uvicorn main:app --reload
```

La app queda disponible en `http://127.0.0.1:8000`.

### Dependencias

| Paquete | Versión mínima | Uso |
|---|---|---|
| `fastapi` | 0.110.0 | Framework API REST |
| `uvicorn` | 0.29.0 | Servidor ASGI |
| `pydantic` | 2.0.0 | Validación de parámetros |
| `ezdxf` | 1.1.0 | Generación de archivos DXF |
| `Pillow` | 10.0.0 | Renderizado de imágenes / PDF |
| `numpy` | 1.24.0 | Operaciones matriciales |
| `matplotlib` | 3.7.0 | Generación de PDFs |
| `openpyxl` | 3.1.0 | Generación de Excel |
| `opencv-python` | 4.8.0 | Trazado de contornos (módulo imagen) |

---

## Módulo 1 — Planta Arquitectónica

Genera planta tipo de vivienda de interés social con alzado frontal y corte transversal.

**Endpoint:** `POST /api/planta/{dxf|pdf|excel|preview|validate}`

### Parámetros

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `lote_ancho` | float (mm) | 6000 | Ancho del lote |
| `lote_fondo` | float (mm) | 12000 | Fondo del lote |
| `espesor_muro` | float (mm) | 150 | Espesor de muros portantes |
| `altura_muro` | float (mm) | 2700 | Altura libre del nivel |
| `recintos` | lista | — | Cada recinto: `nombre`, `ancho`, `fondo` |
| `project_name` | string | "Proyecto" | Nombre del proyecto |

### Recintos disponibles

`SALA`, `COMEDOR`, `SALA_COMEDOR`, `COCINA`, `RECAMARA`, `BANO`, `BANO_MEDIO`, `ESTUDIO`, `PATIO`, `PASILLO`, `GARAGE`, `LAVANDERIA`, `BODEGA`

### Capas DXF generadas

| Capa | Color | Grosor | Contenido |
|---|---|---|---|
| `A-EJE` | Rojo | 0.18mm | Ejes de trazo (linetype CENTER) |
| `A-MURO` | Blanco | 0.30mm | Muros portantes en corte |
| `A-COTA` | Amarillo | 0.18mm | Dimensiones y cotas |
| `A-PUERTA` | Verde | 0.18mm | Umbral + arco de batiente 90° |
| `A-VENTANA` | Cian | 0.18mm | Triple línea paralela en muro |
| `A-CORTADO` | Blanco | 0.50mm | Elementos en corte (alzado/sección) |
| `A-PROYECTADO` | Gris | 0.09mm | Elementos proyectados |
| `E-CASTILLO` | Magenta | 0.18mm | Castillos sugeridos por NTC |

### Estándares CAD implementados

- Malla de ejes primero (sobresalen 1000mm del edificio), muros desfasados del eje
- Globos de eje: verticales 1,2,3… / horizontales A,B,C…
- Entidades `DIMENSION` reales de AutoCAD (no líneas sueltas)
- Alzado frontal con niveles NPT±0.00, cerramiento y losa
- Corte A-A' con elementos cortados vs. proyectados diferenciados por grosor
- Validación SEDATU: paso mínimo ≥ 900mm entre muros

### Validación NTC-RCDF incluida

- Área mínima CONAVI / INFONAVIT (42 m²)
- Altura libre mínima RCDF: 2,300mm
- Separación máxima entre castillos: 4.0m (NTC Mampostería 2017)
- Dimensiones mínimas de castillos: sección 150×150mm
- Recubrimientos mínimos de concreto según NTC 2017

### Ejemplo de request

```json
POST /api/planta/dxf
{
  "lote_ancho": 6000,
  "lote_fondo": 12000,
  "espesor_muro": 150,
  "altura_muro": 2700,
  "project_name": "Casa tipo A",
  "recintos": [
    {"nombre": "SALA",     "ancho": 3500, "fondo": 4000},
    {"nombre": "COCINA",   "ancho": 2500, "fondo": 3000},
    {"nombre": "RECAMARA", "ancho": 3500, "fondo": 4000},
    {"nombre": "BANO",     "ancho": 1800, "fondo": 2500}
  ]
}
```

---

## Módulo 2 — Cimentación

Genera expediente técnico de cimentación: planta, cortes con armado y catálogo.

**Endpoint:** `POST /api/cimentacion/{dxf|pdf|excel|preview|validate}`

### Parámetros

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `ejes_x` | lista float (mm) | — | Posiciones de ejes verticales |
| `ejes_y` | lista float (mm) | — | Posiciones de ejes horizontales |
| `espesor_muro` | float (mm) | 150 | Espesor de muros |
| `ancho_zapata` | float (mm) | 500 | Ancho de zapata corrida |
| `alto_zapata` | float (mm) | 350 | Peralte de zapata corrida |
| `desplante` | float (mm) | 600 | Profundidad de desplante |
| `varilla_long` | string | "No.4" | Varilla longitudinal |
| `varilla_trans` | string | "No.4" | Varilla transversal |
| `sep_long_mm` | float (mm) | 200 | Separación varilla longitudinal |
| `fc` | float (kg/cm²) | 200 | Resistencia del concreto |
| `fy` | float (kg/cm²) | 4200 | Límite de fluencia del acero |

### Contenido del DXF

- Planta de cimentación con zapatas corridas bajo muros y zapatas aisladas en columnas
- Corte de zapata corrida con representación de armado, achurado de tierra y concreto
- Corte de zapata aislada con armado
- Tabla de armados en capa `T-TEXTO`
- Catálogo de conceptos: concreto, acero, excavación, plantilla

---

## Módulo 3 — Carpintería y Cancelería

Genera detalles técnicos de ventanas, puertas y closets con despiece de piezas.

**Endpoint:** `POST /api/carpinteria/{dxf|pdf|excel|preview}`

### Tipos soportados

| Tipo | Descripción |
|---|---|
| `ventana_fija` | Ventana fija con marco y cristal |
| `ventana_corrediza` | Ventana con hojas corredizas |
| `puerta` | Puerta interior o exterior con umbral |
| `closet` | Mueble de closet con puertas batientes o corredizas |

### Parámetros

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `tipo` | string | — | Tipo de elemento (ver tabla arriba) |
| `ancho` | float (mm) | — | Ancho del vano libre |
| `alto` | float (mm) | — | Alto del vano libre |
| `marco_ancho` | float (mm) | 50 | Perfil del marco |
| `hoja_grosor` | float (mm) | 40 | Grosor de hoja / perfil |
| `n_hojas` | int | 2 | Número de hojas |
| `material` | string | "aluminio" | `aluminio` / `madera` / `pvc` |

---

## Módulo 4 — Imagen a DXF

Convierte imágenes rasterizadas a entidades DXF vectoriales usando detección de contornos con OpenCV.

**Endpoint:** `POST /api/imagen/{dxf|preview}`

### Modos de conversión

| Modo | Entidades generadas | Ideal para |
|---|---|---|
| `trace` | `LWPOLYLINE` / `SPLINE` | Arte lineal, logos, firmas |
| `hatch` | `LWPOLYLINE` + `HATCH SOLID` | Siluetas, logos rellenos |
| `pixel` | `SOLID` (un cuadro por píxel) | Pixel art, imágenes pequeñas |

### Parámetros

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `mode` | string | `trace` | Modo de conversión |
| `scale` | float | 0.1 | mm por píxel |
| `threshold` | int (0-255) | 127 | Umbral de binarización |
| `min_area` | float (px²) | 10.0 | Área mínima de contorno |
| `approx_epsilon` | float | 0.5 | Simplificación Douglas-Peucker |
| `spline` | bool | false | Usar `SPLINE` en vez de `LWPOLYLINE` |
| `lineweight` | int | 25 | Grosor de línea (1/100 mm) |

### Capas DXF generadas

| Capa | Contenido |
|---|---|
| `CONTORNOS` | Polilíneas / splines trazados |
| `RELLENOS` | Rellenos sólidos (modo hatch) |
| `PIXELES` | Cuadros sólidos (modo pixel) |
| `INFO` | Bloque de título con metadatos |

---

## Módulo 5 — Texto a DXF

Genera una planta arquitectónica completa a partir de una descripción en lenguaje natural en español.

**Endpoint:** `POST /api/texto/{dxf|pdf|excel|preview|validate}`

### Cómo funciona

1. El usuario escribe una descripción libre: _"casa de 3 recamaras, sala-comedor, cocina, 2 baños, lote 8x15"_
2. El parser extrae dimensiones del lote, programa arquitectónico, número de plantas y material
3. Construye `PlantaParams` y delega al `PlantaGenerator`
4. Devuelve los mismos outputs que el módulo de Planta

### Palabras clave reconocidas (español flexible)

| Recinto | Variantes |
|---|---|
| Sala | sala, estar, living |
| Comedor | comedor, dining |
| Cocina | cocina, kitchen, cocineta |
| Recámara | recamara, habitacion, cuarto, dormitorio, bedroom |
| Baño | baño, wc, sanitario, toilet, bathroom |
| Garage | garage, garaje, cochera, estacionamiento |
| Lavandería | lavandería, patio servicio, cuarto lavado |

---

## API REST completa

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Página principal |
| GET | `/planta` | UI — Planta arquitectónica |
| GET | `/cimentacion` | UI — Cimentación |
| GET | `/carpinteria` | UI — Carpintería |
| GET | `/texto` | UI — Texto a DXF |
| GET | `/imagen` | UI — Imagen a DXF |
| GET | `/health` | Estado del servidor |
| GET | `/docs` | Swagger UI interactivo |
| POST | `/api/planta/dxf` | Generar DXF de planta |
| POST | `/api/planta/pdf` | Generar PDF de planta |
| POST | `/api/planta/excel` | Generar Excel de planta |
| POST | `/api/planta/preview` | Vista previa SVG de planta |
| POST | `/api/planta/validate` | Validar parámetros NTC |
| POST | `/api/cimentacion/dxf` | Generar DXF de cimentación |
| POST | `/api/cimentacion/pdf` | Generar PDF de cimentación |
| POST | `/api/cimentacion/excel` | Generar Excel de cimentación |
| POST | `/api/cimentacion/preview` | Vista previa SVG |
| POST | `/api/cimentacion/validate` | Validar parámetros NTC |
| POST | `/api/carpinteria/dxf` | Generar DXF de carpintería |
| POST | `/api/carpinteria/pdf` | Generar PDF |
| POST | `/api/carpinteria/excel` | Generar Excel |
| POST | `/api/carpinteria/preview` | Vista previa SVG |
| POST | `/api/texto/dxf` | Texto → DXF |
| POST | `/api/texto/pdf` | Texto → PDF |
| POST | `/api/texto/excel` | Texto → Excel |
| POST | `/api/texto/preview` | Texto → SVG |
| POST | `/api/texto/validate` | Validar texto NTC |
| POST | `/api/imagen/dxf` | Imagen → DXF |
| POST | `/api/imagen/preview` | Imagen → SVG |

---

## Estructura del proyecto

```
arqgen/
├── main.py                          # FastAPI entry-point, 30 rutas
├── requirements.txt
├── backend/
│   ├── core/
│   │   ├── dxf_utils.py             # Utilidades DXF (capas, cotas, ejes)
│   │   ├── ntc.py                   # Constantes y validador NTC-RCDF
│   │   ├── catalog.py               # Catálogo de conceptos
│   │   └── pdf_utils.py             # Render PDF con matplotlib
│   ├── generators/
│   │   ├── gen_planta.py            # Módulo 1 — Planta arquitectónica
│   │   ├── gen_cimentacion.py       # Módulo 2 — Cimentación
│   │   ├── gen_carpinteria.py       # Módulo 3 — Carpintería
│   │   ├── gen_imagen.py            # Módulo 4 — Imagen a DXF
│   │   └── gen_texto.py             # Módulo 5 — Texto a DXF
│   └── routers/
│       ├── router_planta.py
│       ├── router_cimentacion.py
│       ├── router_carpinteria.py
│       ├── router_imagen.py
│       └── router_texto.py
├── frontend/
│   ├── static/
│   │   ├── css/arqgen.css
│   │   └── js/arqgen.js
│   └── templates/
│       ├── index.html
│       ├── planta.html
│       ├── cimentacion.html
│       ├── carpinteria.html
│       ├── texto.html
│       └── imagen.html
└── deploy/
    ├── Dockerfile
    ├── nginx.conf
    └── README_deploy.md
```

---

## Despliegue en producción

El servidor corre en Ubuntu 25.10 con:
- **nginx** como reverse proxy en puerto 8080
- **uvicorn** con 2 workers en `127.0.0.1:8002`
- **systemd** service (`arqgen.service`) con arranque automático

Para actualizar el servidor desde este repositorio:

```bash
cd /var/www/arqgen
git pull origin main
sudo systemctl restart arqgen
```

---

## Normas aplicadas

| Norma | Descripción |
|---|---|
| NTC-RCDF 2017 | Normas Técnicas Complementarias del RCDF (Ciudad de México) |
| NTC Concreto 2017 | Recubrimientos mínimos, armado de zapatas y castillos |
| NTC Mampostería 2017 | Separación máxima entre castillos (4.0m), secciones mínimas |
| CONAVI | Área mínima de vivienda de interés social |
| INFONAVIT | Área mínima de construcción (42m²) |
| SEDATU | Paso mínimo 900mm, criterios de accesibilidad |
