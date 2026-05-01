# ArqGen — Deploy en Digital Ocean + Cloudflare

## 1. Crear Droplet en Digital Ocean

- Ubuntu 22.04 LTS, plan Basic $12/mes (2 GB RAM / 1 vCPU)
- Habilitar SSH key al crear el droplet
- Anotar la IP pública (`SERVER_IP`)

## 2. Configurar DNS en Cloudflare

1. Agrega el dominio en Cloudflare (plan Free es suficiente).
2. Crea un registro **A**:
   - Nombre: `arqgen` (o `@` para raíz)
   - IPv4: `SERVER_IP`
   - Proxy: **Proxied** (nube naranja)
3. SSL/TLS → Overview → selecciona **Full (strict)**.
4. Descarga un **Origin Certificate** (Cloudflare → SSL/TLS → Origin Server)
   y guarda `cert.pem` y `key.pem`.

## 3. Configurar el servidor

```bash
# Conectarse al droplet
ssh root@SERVER_IP

# Actualizar sistema
apt update && apt upgrade -y

# Instalar dependencias
apt install -y python3.11 python3.11-venv python3-pip nginx git

# Clonar o subir el proyecto
git clone https://github.com/TU_USUARIO/arqgen.git /app
cd /app

# Entorno virtual
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Certificados Cloudflare (copiar desde local)
mkdir -p /etc/ssl/cloudflare
# scp cert.pem key.pem root@SERVER_IP:/etc/ssl/cloudflare/

# Nginx
cp deploy/nginx.conf /etc/nginx/sites-available/arqgen
sed -i "s/arqgen.example.com/TU_DOMINIO/" /etc/nginx/sites-available/arqgen
ln -s /etc/nginx/sites-available/arqgen /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

## 4. Servicio systemd

```ini
# /etc/systemd/system/arqgen.service
[Unit]
Description=ArqGen FastAPI
After=network.target

[Service]
User=www-data
WorkingDirectory=/app
ExecStart=/app/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable arqgen
systemctl start arqgen
systemctl status arqgen
```

## 5. Verificar

```
https://TU_DOMINIO/          → página principal
https://TU_DOMINIO/docs      → Swagger UI
https://TU_DOMINIO/health    → {"status":"ok"}
```

## 6. Actualizaciones

```bash
cd /app
git pull
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart arqgen
```
