# App de consultas a Anthropic vía Kong AI Gateway + CrowdStrike AIDR

App simple en Python que consulta a Claude (Anthropic) **a través de Kong**, con
los plugins de **CrowdStrike AIDR** inspeccionando el tráfico de entrada y salida.

```
                     ┌──────────────── Kong AI Gateway ─────────────────┐
  app.py ─HTTPS─▶ /chat ─┤ AIDR request ▶ AI Proxy ▶ AIDR response       ├─HTTPS─▶ api.anthropic.com
   (8443)            └────────┬──────────────────────────┬──────────────┘
                              ▼                           ▼
                       CrowdStrike AIDR API        (inspección y políticas)
```

La app habla con Kong en HTTPS. Kong traduce a Anthropic, agrega la API key, y
pasa el tráfico por AIDR antes y después del modelo.

> **IMPORTANTE — HTTPS obligatorio:** el plugin de AIDR **rechaza el tráfico HTTP
> plano** con un error `426 "Please use HTTPS protocol"`. Por eso la app y los
> curls de prueba usan siempre `https://localhost:8443`, nunca el puerto 8000.

---

## Archivos

| Archivo               | Para qué sirve                                                 |
|-----------------------|----------------------------------------------------------------|
| `Dockerfile`          | Construye Kong + plugins AIDR (compilados con luarocks)        |
| `kong.template.yaml`  | Config de Kong: AI Proxy (Anthropic) + AIDR request/response  |
| `start-kong.sh`       | Construye la imagen, inyecta valores y arranca Kong (8000+8443)|
| `app.py`              | La app de Python (modo interactivo o pregunta única)          |
| `requirements.txt`    | Dependencias de Python (`requests`)                           |
| `kong.yaml`           | Generado automáticamente por el script (no lo edites)         |

---

## Requisitos previos

1. **Docker Desktop ABIERTO Y CORRIENDO.** No basta con tenerlo instalado: el
   daemon debe estar activo. Ábrelo y espera a que la ballena 🐳 de la barra de
   menú deje de animarse. Confirma con:
   ```bash
   docker info
   ```
   Si ese comando da error, Docker aún no está listo (no sigas hasta que funcione).

2. **Python 3.**

3. **Credenciales:**
   - `ANTHROPIC_API_KEY` — tu key de Anthropic (`sk-ant-...`).
   - `CS_AIDR_TOKEN` — token de API de AIDR (pestaña **Config** de tu collector Kong).
   - `CS_AIDR_BASE_URL` — base URL de AIDR según tu región. Ejemplos:
     - US-1: `https://api.crowdstrike.com/aidr/aiguard`
     - US-2: `https://api.us-2.crowdstrike.com/aidr/aiguard`
     - EU-1: `https://api.eu-1.crowdstrike.com/aidr/aiguard`

> Recomendación: registra el collector con **"No Policy, Log Only"** al inicio
> para verificar el flujo antes de activar reglas que bloqueen tráfico.

---

## Paso a paso

### 1. Entra a la carpeta
```bash
cd kong-anthropic-app
```

### 2. Exporta tus credenciales
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export CS_AIDR_TOKEN=...
export CS_AIDR_BASE_URL=https://api.us-2.crowdstrike.com/aidr/aiguard
```

### 3. Construye y arranca Kong
```bash
./start-kong.sh
```
El script verifica que las variables estén definidas y que Docker corra, genera
`kong.yaml`, construye la imagen con los plugins AIDR (la primera vez tarda
varios minutos), y arranca Kong con listeners HTTP (8000) y **HTTPS (8443)**.

Al terminar verás las URLs, incluida `https://localhost:8443` (la que se usa).

### 4. Instala las dependencias de Python
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Usa la app
**Interactivo:**
```bash
python3 app.py
```
**Pregunta única:**
```bash
python3 app.py "dime el clima en cdmx"
```

---

## Probar Kong directamente (sin la app)

Usa HTTPS, puerto 8443, y `-k` (acepta el certificado autofirmado de local):
```bash
curl -sk -X POST https://localhost:8443/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hola, ¿funcionas?"}]}' \
  | python3 -m json.tool
```

> Si usas `http://localhost:8000` obtendrás `426 Please use HTTPS protocol`.
> Es el comportamiento esperado de AIDR, no un fallo.

Para ver la inspección de AIDR, revisa la página **Findings** en la consola de
AIDR después de hacer algunas peticiones.

---

## Detener y limpiar
```bash
docker stop kong-ai          # detener
docker start kong-ai         # reiniciar
docker rm -f kong-ai         # eliminar contenedor
docker rmi kong-plugin-crowdstrike-aidr   # eliminar la imagen construida
```

---

## Cómo encaja todo (referencia)

En `kong.template.yaml`, la ruta `/chat` tiene tres plugins:

1. **`ai-proxy`** — traduce el request al formato de Anthropic y enruta al modelo.
2. **`crowdstrike-aidr-request`** — inspecciona la entrada (Input Rules). Puede
   bloquear prompts maliciosos antes de llegar al modelo.
3. **`crowdstrike-aidr-response`** — inspecciona la salida (Output Rules). Puede
   redactar PII o bloquear la respuesta.

Los plugins de AIDR usan `provider: "kong"` y `api_uri: "/llm/v1/chat"` para
rutear a través del AI Proxy. El token de AIDR se resuelve en runtime con
`{vault://env-cs-aidr/token}`, que lee la variable `CS_AIDR_TOKEN`.

### Formato de la respuesta
Con los plugins de AIDR en la cadena, Kong devuelve la respuesta en el **formato
nativo de Anthropic** (`{"content": [{"type":"text","text":"..."}]}`), no en el
formato OpenAI (`choices`). Por eso `app.py` tiene un parseo robusto que maneja:
formato Anthropic, formato OpenAI, bloqueos de AIDR (`status`/`reason`), y
cualquier otro caso (imprime el JSON crudo para diagnóstico).

---

## Notas

- **HTTPS y certificado:** `app.py` usa `verify=False` y los curls usan `-k`
  porque Kong en local tiene un certificado autofirmado. Esto es aceptable SOLO
  en localhost de desarrollo. En un entorno real se usa un certificado válido y
  se reactiva la verificación TLS.

- **Nombre del modelo:** la config usa `claude-sonnet-4-6`. Si obtienes "model
  not found", edita el campo `name` (y el metadato `model` de los plugins AIDR)
  en `kong.template.yaml` y vuelve a correr `./start-kong.sh`.

- **Seguridad de la API key:** el `ANTHROPIC_API_KEY` se inyecta en `kong.yaml`
  (queda en texto plano en ese archivo local generado). No subas `kong.yaml` a
  control de versiones ni lo compartas. Si tu key se expone, revócala y genera
  una nueva en console.anthropic.com.

- **Build de plugins de terceros:** el Dockerfile clona y compila código desde
  `github.com/CrowdStrike/aidr-kong` (repo oficial referenciado en la doc de
  CrowdStrike). Estás compilando y ejecutando código externo en tu imagen.

- **Docker debe estar corriendo:** el error más común al arrancar es
  `failed to connect to the docker API ... /var/run/docker.sock`. Significa que
  Docker Desktop no está activo. Ábrelo y espera a que `docker info` funcione.
