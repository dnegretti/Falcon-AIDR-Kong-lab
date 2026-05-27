# App de consultas a Anthropic vía Kong AI Gateway + CrowdStrike AIDR

App simple en Python que consulta a Claude (Anthropic) **a través de Kong**,
con los plugins de **CrowdStrike AIDR** inspeccionando el tráfico de entrada y
salida (detección de prompts maliciosos, redacción de PII, telemetría).

```
                          ┌─────────────── Kong AI Gateway ───────────────┐
  app.py ──HTTP──▶ /chat ─┤ AIDR request ▶ AI Proxy ▶ AIDR response        ├──HTTPS──▶ api.anthropic.com
                          └────────┬───────────────────────┬──────────────┘
                                   ▼                        ▼
                            CrowdStrike AIDR API     (inspección y políticas)
```

La app solo habla con Kong en formato OpenAI. Kong traduce a Anthropic, agrega
la API key, y pasa el tráfico por AIDR antes y después del modelo.

## Archivos

| Archivo               | Para qué sirve                                                  |
|-----------------------|-----------------------------------------------------------------|
| `Dockerfile`          | Construye Kong + plugins AIDR (compilados con luarocks)         |
| `kong.template.yaml`  | Config de Kong: AI Proxy (Anthropic) + AIDR request/response   |
| `start-kong.sh`       | Construye la imagen, inyecta valores y arranca Kong            |
| `app.py`              | La app de Python (modo interactivo o pregunta única)           |
| `requirements.txt`    | Dependencias de Python (`requests`)                            |
| `kong.yaml`           | Generado automáticamente por el script (no lo edites)          |

---

## Requisitos previos

1. **Docker Desktop** abierto y corriendo (`docker --version`).
2. **Python 3**.
3. **Credenciales:**
   - `ANTHROPIC_API_KEY` — tu key de Anthropic (`sk-ant-...`).
   - `CS_AIDR_TOKEN` — token de API de AIDR, de la pestaña **Config** del
     collector Kong que registraste en la consola de AIDR.
   - `CS_AIDR_BASE_URL` — base URL de AIDR según tu región (US-1 / US-2 / EU-1),
     también en la pestaña **Config**. Por defecto suele ser
     `https://api.crowdstrike.com/aidr/aiguard`.

> Recomendación: registra el collector con **"No Policy, Log Only"** al inicio,
> para verificar que el flujo funciona antes de activar reglas que bloqueen.

---

## Paso a paso

### 1. Entra a la carpeta

```bash
cd kong-anthropic-app
```

### 2. Exporta tus credenciales

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export CS_AIDR_TOKEN=pts_...
export CS_AIDR_BASE_URL=https://api.crowdstrike.com/aidr/aiguard
```

### 3. Construye y arranca Kong

```bash
./start-kong.sh
```

El script:
- comprueba que las tres variables estén definidas,
- genera `kong.yaml` inyectando la key de Anthropic y la base URL de AIDR,
- **construye la imagen** `kong-plugin-crowdstrike-aidr` (compila los plugins
  desde el repo oficial de CrowdStrike — la primera vez tarda varios minutos),
- arranca el contenedor en modo DB-less con el vault `env`,
- pasa `CS_AIDR_TOKEN` al contenedor (el plugin lo lee vía el vault, no queda
  escrito en `kong.yaml`).

Cuando termine verás:
```
Kong esta listo en http://localhost:8000 (proxy) y http://localhost:8001 (admin).
```

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
python3 app.py "Explícame qué es un proxy de LLM en una frase"
```

---

## Probar Kong directamente (sin la app)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hola, ¿funcionas?"}]}'
```

Para ver la inspección de AIDR en acción, revisa la página **Findings** en la
consola de AIDR después de hacer algunas peticiones.

---

## Detener y limpiar

```bash
docker stop kong-ai          # detener
docker start kong-ai         # reiniciar
docker rm -f kong-ai         # eliminar contenedor
docker rmi kong-plugin-crowdstrike-aidr   # eliminar la imagen construida
```

---

## Cómo encajan los plugins (referencia)

En `kong.template.yaml`, la ruta `/chat` tiene tres plugins en orden:

1. **`ai-proxy`** — traduce el request a formato Anthropic y enruta al modelo.
2. **`crowdstrike-aidr-request`** — inspecciona la entrada (Input Rules de tu
   política de AIDR). Puede bloquear prompts maliciosos antes de llegar al modelo.
3. **`crowdstrike-aidr-response`** — inspecciona la salida (Output Rules). Puede
   redactar PII o bloquear la respuesta del modelo.

Los dos plugins de AIDR usan `provider: "kong"` y `api_uri: "/llm/v1/chat"` para
rutear a través del AI Proxy en lugar de apuntar a un proveedor directo. El token
de AIDR se resuelve en runtime con `{vault://env-cs-aidr/token}`, que lee la
variable de entorno `CS_AIDR_TOKEN` (prefijo `CS_AIDR_` del vault `env`).

## Notas

- **Nombre del modelo:** la config usa `claude-sonnet-4-6`. Si obtienes un error
  de "model not found", edita el campo `name` (y el metadato `model` de los
  plugins AIDR) en `kong.template.yaml`, vuelve a correr `./start-kong.sh`.

- **Seguridad del token:** el `CS_AIDR_TOKEN` se pasa como variable de entorno y
  se lee vía vault; no queda escrito en `kong.yaml`. La doc de CrowdStrike
  recomienda este método de vault sobre escribir la key inline.

- **Build de plugins de terceros:** el Dockerfile clona y compila código desde
  `github.com/CrowdStrike/aidr-kong`. Es el repo oficial referenciado en la
  documentación de CrowdStrike, pero ten presente que estás compilando y
  ejecutando código externo dentro de tu imagen.
