#!/usr/bin/env bash
#
# start-kong.sh
# Construye la imagen de Kong con los plugins de CrowdStrike AIDR y arranca
# el gateway en modo DB-less apuntando a Anthropic, con inspeccion AIDR.
#
# Variables de entorno requeridas (exportalas antes de correr el script):
#   ANTHROPIC_API_KEY  - tu key de Anthropic (sk-ant-...)
#   CS_AIDR_TOKEN      - token de API de AIDR (pts_... / pmt_...)
#   CS_AIDR_BASE_URL   - base URL de AIDR segun tu region
#                        (ej. https://api.crowdstrike.com/aidr/aiguard)

set -euo pipefail

IMAGE_NAME="kong-plugin-crowdstrike-aidr"

# --- Verificar variables requeridas ---
missing=0
for var in ANTHROPIC_API_KEY CS_AIDR_TOKEN CS_AIDR_BASE_URL; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: la variable $var no esta definida."
    missing=1
  fi
done
if [[ $missing -eq 1 ]]; then
  echo ""
  echo "Exporta las variables antes de correr este script, por ejemplo:"
  echo "  export ANTHROPIC_API_KEY=sk-ant-..."
  echo "  export CS_AIDR_TOKEN=pts_..."
  echo "  export CS_AIDR_BASE_URL=https://api.crowdstrike.com/aidr/aiguard"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Generar kong.yaml desde la plantilla, inyectando valores no secretos ---
# La API key de Anthropic se inyecta aqui (es propia del proxy).
# El token de AIDR NO se inyecta: se lee en runtime via el vault env.
sed -e "s|__ANTHROPIC_API_KEY__|${ANTHROPIC_API_KEY}|g" \
    -e "s|__CS_AIDR_BASE_URL__|${CS_AIDR_BASE_URL}|g" \
    kong.template.yaml > kong.yaml
echo "Generado kong.yaml."

# --- Construir la imagen con los plugins de AIDR ---
echo "Construyendo la imagen ${IMAGE_NAME} (compila los plugins AIDR)..."
echo "Esto puede tardar varios minutos la primera vez."
docker build -t "${IMAGE_NAME}" .

# --- Eliminar contenedor previo si existe ---
if docker ps -a --format '{{.Names}}' | grep -q '^kong-ai$'; then
  echo "Eliminando contenedor kong-ai previo..."
  docker rm -f kong-ai >/dev/null
fi

# --- Arrancar Kong en modo DB-less con el vault env ---
echo "Arrancando Kong AI Gateway con AIDR..."
docker run -d --name kong-ai \
  -v "$SCRIPT_DIR/kong.yaml:/usr/local/kong/kong.yaml" \
  -e "KONG_DATABASE=off" \
  -e "KONG_DECLARATIVE_CONFIG=/usr/local/kong/kong.yaml" \
  -e "KONG_VAULTS=env" \
  -e "KONG_PROXY_LISTEN=0.0.0.0:8000, 0.0.0.0:8443 ssl" \
  -e "KONG_ADMIN_LISTEN=0.0.0.0:8001" \
  -e "CS_AIDR_TOKEN=${CS_AIDR_TOKEN}" \
  -p 8000:8000 \
  -p 8443:8443 \
  -p 8001:8001 \
  "${IMAGE_NAME}" >/dev/null

echo "Esperando a que Kong arranque..."
for i in {1..20}; do
  if curl -sf http://localhost:8001/status >/dev/null 2>&1; then
    echo "Kong esta listo en http://localhost:8000 (proxy) y http://localhost:8001 (admin)."
    echo "El trafico /chat pasa por: AI Proxy (Anthropic) + AIDR request/response."
    exit 0
  fi
  sleep 2
done

echo "Kong tardo en responder. Revisa los logs con:  docker logs kong-ai"
exit 1
