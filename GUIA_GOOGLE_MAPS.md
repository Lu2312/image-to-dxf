<!DOCTYPE html>plemented Improvementsntsgle Maps to DXF

## Problema Común
Las capturas de Google Maps a menudo tienen bajo contraste, múltiples colores y detalles que dificultan la detección de trazos (calles, límites, etc.).

## Recomendaciones para Mejores Resultados

### 1. **Preparación de la Captura**
- **Usar el modo satélite simplificado**: En Google Maps, cambia a la vista "Mapa" (no satélite) para obtener líneas más claras
- **Zoom adecuado**: Ajusta el zoom para que las calles/trazos sean de al menos 3-5 píxeles de ancho
- **Contraste**: Si es posible, usa el modo de alto contraste del navegador o edita la imagen antes

### 2. **Configuraciones Recomendadas para Mapas**

#### Para calles y vías:
```
Modo: trace
Escala: 0.5 - 1.0 mm/px (dependiendo del zoom)
Umbral: 150-180 (para capturar solo las líneas oscuras)
Área mínima: 50-100 px² (eliminar ruido de etiquetas)
Simplificación D-P: 1.5-3.0 (suavizar las calles)
```

#### Para límites/perímetros:
```
Modo: trace
Umbral: 100-140 (capturar más elementos)
Área mínima: 200+ px² (solo elementos grandes)
Simplificación D-P: 2.0-5.0 (líneas más suaves)
```

### 3. **Proceso Recomendado**

1. **Subir la imagen** del mapa
    enhance_contrast: bool = Form(False,   description="Auto Contrast Enhancement (great for maps)"),
   - Si no detecta suficientes líneas → BAJAR el umbral (100-120)
   - Si detecta demasiado ruido → SUBIR el umbral (160-200)
3. **Aumentar área mínima** para eliminar:
   - Etiquetas de texto
   - Iconos pequeños
   - Marcadores
4. **Previsualizar** con el botón "🔍 Previsualizar DXF"
5. **Ajustar** si es necesario y volver a previsualizar
6. **Descargar** cuando esté satisfecho

### 4. ** Automatic Preprocessing (NEW)** ⭐

La herramienta ahora incluye **mejora de contraste automática** específicamente diseñada para mapas:

#### Usando la función "Mejorar contraste automáticamente":
1. Sube tu mapa de Google Maps
2. **Activa la casilla "🎨 Mejorar contraste automáticamente"**
3. Esto realiza automáticamente:
   - Conversión a escala de grises
   - Ecualización adaptativa de histograma (CLAHE)
   - Mejora de contraste inteligente
4. Luego configura el resto de parámetros y previsualiza

**Resultado**: No necesitas editar la imagen manualmente en GIMP o Photoshop. La herramienta lo hace por ti.

### 5. **Preprocesamiento Manual (Opcional)**

Si prefieres editar la imagen antes de subirla:

#### Usando Paint / GIMP / Photoshop:
1. Convertir a escala de grises
2. Aumentar el contraste (Ctrl+L en GIMP)
3. Eliminar elementos no deseados:
   - Etiquetas de texto
   - Iconos de lugares
   - Marcadores personalizados
4. Guardar como PNG de alta calidad

#### Usando la herramienta "Quitar fondo":
1. Sube tu mapa
2. Haz clic en "🪄 Quitar fondo" 
3. Luego convierte a DXF con las configuraciones ajustadas

### 5. **Ejemplos de Configuración por Tipo**

| Tipo de Mapa | Umbral | Área Mín | Epsilon | Observaciones |
|--------------|--------|----------|---------|---------------|
        enhance_contrast = enhance_contrast,5 | Líneas finas, mucho detalle |
    pdf_dpi:        int   = 200     # raster PDFás gruesas |
| Límites territoriales | 120-150 | 200-500 | 3.0-5.0 | Solo contornos grandes |
| Topografía | 100-130 | 30-80 | 1.0-2.0 | Curvas de nivel |

### 6. **Solución de Problemas**

**No detecta casi nada:**
- BAJAR el umbral a 80-100
- REDUCIR área mínima a 10-20
- Verificar que la imagen tenga suficiente contraste

**Detecta demasiado ruido:**
- SUBIR el umbral a 180-220
- AUMENTAR área mínima a 150-300
- Usar simplificación D-P más agresiva (3.0-5.0)

**Líneas muy pixeladas:**
- AUMENTAR simplificación D-P (2.0-4.0)
- Considerar usar modo SPLINE

**DXF muy grande:**
- Aumentar área mínima
- Aumentar simplificación D-P
- Usar escala más pequeña (0.05-0.1)

### 7. **Tips Avanzados**

- **Para ríos/cuerpos de agua**: Usa modo "hatch" para obtener áreas rellenas
- **Para editar después**: El modo "trace" es más fácil de modificar en AutoCAD
- **Para impresión**: Ajusta la escala según el tamaño final deseado
- **Combinación**: Puedes generar múltiples DXF con diferentes configuraciones y combinarlos en AutoCAD

## Ejemplo Paso a Paso

1. Captura de Google Maps: Vista "Mapa", zoom medio
2. **Subir a la herramienta** (sin necesidad de editar previamente)
3. **Activar "🎨 Mejorar contraste automáticamente"** ⭐ NUEVO
4. Configurar:
   - Modo: trace
   - Umbral: 160 (ajustar según vista previa)
   - Área mínima: 80
   - Simplificación: 2.0
5. **Previsualizar DXF** para verificar
6. Ajustar umbral si es necesario
7. Descargar cuando sea satisfactorio

**Nota**: Con la mejora de contraste automática, ya NO necesitas editar en Paint/GIMP.

## Nueva Funcionalidad de Vista Previa y Mejora de Contraste

### Vista Previa DXF
Ahora puedes ver exactamente qué contornos se detectarán ANTES de descargar:

1. Haz clic en "🔍 Previsualizar DXF"
2. Se mostrará un SVG con los contornos detectados en color rojo (trace) o azul relleno (hatch)
3. Revisa si se detectaron bien las calles/elementos
4. Ajusta configuraciones según sea necesario
5. Vuelve a previsualizar
6. Descarga cuando estés satisfecho

Esta vista previa te ahorra tiempo porque NO necesitas abrir AutoCAD para verificar si la conversión fue exitosa.

### Mejora de Contraste Automática ⭐ NUEVO

La nueva función "🎨 Mejorar contraste automáticamente" es **ideal para mapas de Google Maps**:

- ✅ Convierte automáticamente a escala de grises
- ✅ Aplica ecualización adaptativa de histograma (CLAHE)
- ✅ Mejora el contraste sin perder detalles
- ✅ Especialmente útil para imágenes con bajo contraste
- ✅ **Ahorra el paso de editar en GIMP/Photoshop**

**Cómo usar**:
1. Sube tu captura de Google Maps directamente
2. **Marca la casilla "🎨 Mejorar contraste automáticamente"**
3. Previsualiza para ver el resultado
4. Ajusta el umbral si es necesario
5. Descarga

**Antes vs Después**:
- **Sin mejora**: Muchas calles no se detectan por bajo contraste
- **Con mejora**: Detecta más elementos, líneas más claras, mejor resultado
        enhance_contrast=enhance_contrast,    enhance_contrast: bool = Form(False),              <input id="enhance_contrast" type="checkbox" style="width:auto"/>  fd.append("enhance_contrast", document.getElementById("enhance_contrast").checked ? "true" : "false");