# Lu CAD Studio — Image & Text to DXF

Herramienta web para convertir imágenes y texto a planos DXF, con eliminación de fondo por IA.  
Disponible en [lucadstudio.com](https://lucadstudio.com).

## Funcionalidades

| Módulo | Descripción |
|---|---|
| **Imagen → DXF** | Convierte PNG/JPG a entidades DXF (trazado de contornos con OpenCV) |
| **Quitar fondo** | Eliminación de fondo por IA usando rembg (modelo U2Net) |
| **Texto → DXF** | Genera planos DXF a partir de parámetros de texto |

## Requisitos

- Python 3.11+
- pip

## Instalación local

```bash
git clone https://github.com/Lu2312/image-to-dxf.git
cd image-to-dxf

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## Ejecutar en desarrollo

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Abre http://localhost:8000.

---

## Despliegue en producción (Ubuntu/Debian VPS)

### 1. Dependencias del sistema

```bash
apt-get update
apt-get install -y python3 python3-venv python3-pip git nginx libgl1 libglib2.0-0 libgomp1
```

> `libgl1` y `libglib2.0-0` son requeridos por OpenCV headless.
> `libgomp1` es requerido por onnxruntime (usado por rembg).

### 2. Clonar el repositorio

```bash
mkdir -p /var/www/arqgen
cd /var/www/arqgen
git clone https://github.com/Lu2312/image-to-dxf.git .
```

### 3. Crear el entorno virtual e instalar dependencias

```bash
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

### 4. Permisos

```bash
chown -R www-data:www-data /var/www/arqgen
```

### 5. Servicio systemd

Crea `/etc/systemd/system/arqgen.service`:

```ini
[Unit]
Description=Lu CAD Studio - FastAPI App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/arqgen
ExecStart=/var/www/arqgen/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8002 --workers 1
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

> **Importante:** Usar `--workers 1`. Con rembg/onnxruntime cargados, 2 workers superan el limite de RAM en un droplet de 1 GB.

Activar y arrancar:

```bash
systemctl daemon-reload
systemctl enable arqgen
systemctl start arqgen
systemctl status arqgen
```

### 6. Nginx como proxy inverso

Crea `/etc/nginx/sites-available/lucadstudio`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name lucadstudio.com www.lucadstudio.com;

    location /static/ {
        alias /var/www/arqgen/frontend/static/;
        expires 30d;
        add_header Cache-Control public;
    }

    location / {
        proxy_pass         http://127.0.0.1:8002;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_redirect     off;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
        client_max_body_size 20M;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/lucadstudio /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 7. SSL con Cloudflare

Si usas Cloudflare con SSL en modo **Full (strict)**:

1. En Cloudflare: activa el proxy (nube naranja) para el dominio.
2. En el VPS: instala el certificado de origen de Cloudflare en `/etc/ssl/cloudflare/` y configura el bloque `443 ssl` en nginx apuntando a el.
3. Alternativamente, usa SSL modo **Flexible** si el certificado del servidor es autofirmado.

---

## Script de actualizacion

Guarda este script en `/root/update-arqgen.sh` para futuros deploys:

```bash
#!/bin/bash
set -e
echo '=== Actualizando Lu CAD Studio ==='
cd /var/www/arqgen
git fetch origin main
git reset --hard origin/main
chown -R www-data:www-data /var/www/arqgen
/var/www/arqgen/venv/bin/pip install -r requirements.txt -q
systemctl restart arqgen
sleep 3
systemctl status arqgen --no-pager
echo '=== Listo ==='
```

```bash
chmod +x /root/update-arqgen.sh
/root/update-arqgen.sh
```

---

## Estructura del proyecto

```
image-to-dxf/
├── main.py                  # Entrada FastAPI, rutas, endpoint /remove-bg
├── requirements.txt
├── backend/
│   ├── routers/             # Endpoints: router_imagen, router_texto
│   └── generators/          # Logica DXF: gen_imagen, gen_texto
├── frontend/
│   ├── static/              # CSS, JS
│   └── templates/           # HTML: index, imagen, texto, limpieza, privacidad
├── deploy/
│   ├── Dockerfile
│   └── lucadstudio.nginx.conf
└── tests/
```

## Gestión de memoria en producción (droplet 1 GB)

El endpoint `/remove-bg` usa `rembg` con `onnxruntime` para inferencia de IA. En un servidor con RAM limitada esto requiere varias medidas:

### Problema original y soluciones aplicadas

| Síntoma | Causa | Solución |
|---|---|---|
| OOM killer terminaba el proceso | `--workers 2` = 2 instancias de onnxruntime en RAM | Usar **`--workers 1`** en uvicorn |
| OOM en la primera inferencia (549 MB pico) | Modelo `u2net.onnx` pesa 176 MB y ocupa ~500 MB en inferencia | Cambiar al modelo **`u2netp`** (4.7 MB, ~80 MB en inferencia) |
| Sin margen para picos de RAM | Solo 1 GB físico, sin swap | Añadir **2 GB de swap** permanente |
| Sesión ONNX recreada en cada request | Nueva sesión = recarga del modelo en RAM | **Cachear la sesión** en variable global |

### Cómo se configuró el swap (ya hecho en el VPS)

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab   # permanente tras reboot
```

Verificar:
```bash
free -h   # debe mostrar Swap: 2.0Gi
```

### Comportamiento bajo carga concurrente

Con `--workers 1` uvicorn procesa requests de forma **concurrente pero no paralela** (single-process async). Dos usuarios que suban imágenes al mismo tiempo serán atendidos en secuencia, no simultáneamente, lo que evita duplicar el uso de RAM.

- **Uso en reposo:** ~70 MB
- **Pico durante inferencia:** ~130 MB (modelo `u2netp`) + swap como colchón
- **Requests concurrentes:** encolan en el event loop, no bloquean el servidor

Si en el futuro el tráfico justifica paralelismo real, la opción correcta es escalar verticalmente (droplet 2 GB) antes de aumentar workers.

### Modelo u2netp vs u2net

| | `u2net` (original) | `u2netp` (producción) |
|---|---|---|
| Tamaño del modelo | 176 MB | 4.7 MB |
| RAM en inferencia | ~500 MB | ~130 MB |
| Calidad | Alta | Ligeramente inferior en bordes complejos |
| Adecuado para | GPU / RAM ≥ 4 GB | VPS 1 GB / CPU |

El modelo se descarga automáticamente en la primera llamada al endpoint y se cachea en `/var/www/arqgen/.u2net/u2netp.onnx`.

---

## Dependencias principales

| Paquete | Uso |
|---|---|
| `fastapi` + `uvicorn` | Servidor web |
| `ezdxf` | Generacion de archivos DXF |
| `opencv-python-headless` | Procesamiento de imagenes (sin GUI) |
| `Pillow` | Manejo de imagenes |
| `rembg[cpu]` | Eliminacion de fondo por IA (U2Net) |
| `PyMuPDF` | Extraccion de texto desde PDF |
| `python-multipart` | Soporte de subida de archivos en FastAPI |
