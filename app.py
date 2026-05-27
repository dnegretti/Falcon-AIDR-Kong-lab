#!/usr/bin/env python3
"""
app.py - Consulta a Anthropic a traves de Kong AI Gateway + CrowdStrike AIDR.

Flujo de una peticion:
  app.py --HTTPS--> Kong /chat --> AIDR request --> AI Proxy --> Anthropic
                                <-- AIDR response <-------------/

IMPORTANTE: la conexion DEBE ser por HTTPS (puerto 8443). El plugin de AIDR
rechaza el trafico HTTP plano con un error 426 "Please use HTTPS protocol".
"""

import sys
import requests
import urllib3

# Kong en local usa un certificado autofirmado en el puerto 8443.
# Silenciamos el warning de certificado no verificado SOLO porque es localhost.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Endpoint HTTPS de Kong (ruta /chat definida en kong.yaml).
# Debe ser HTTPS/8443: AIDR rechaza HTTP plano con error 426.
KONG_URL = "https://localhost:8443/chat"

# verify=False acepta el certificado autofirmado de Kong en local.
# En un entorno real se usa un certificado valido y verify=True.
VERIFY_TLS = False

# Timeout generoso para respuestas largas del modelo.
TIMEOUT_SECONDS = 120


def _extraer_texto(data):
    """
    Extrae el texto de la respuesta sin importar el formato que devuelva Kong.

    Maneja tres casos:
      1. Formato OpenAI (data["choices"]) -> lo normaliza el AI Proxy.
      2. Formato nativo de Anthropic (data["content"]) -> lo que llega cuando
         AIDR esta en la cadena de respuesta.
      3. Bloqueo/transformacion de AIDR (data["status"]/"reason").
    Si llega algo distinto, devuelve el JSON crudo para diagnosticar.
    """
    # Caso 1: formato OpenAI.
    if "choices" in data:
        return data["choices"][0]["message"]["content"]

    # Caso 2: formato nativo de Anthropic.
    if "content" in data:
        bloques = data["content"]
        if isinstance(bloques, list) and bloques:
            return bloques[0].get("text", str(data))
        return str(bloques)

    # Caso 3: AIDR bloqueo o transformo la peticion/respuesta.
    if "status" in data or "reason" in data:
        motivo = data.get("reason", "")
        estado = data.get("status", "")
        return f"[AIDR] {estado} {motivo}".strip()

    # Cualquier otra cosa: mostrar el JSON crudo.
    return f"[Respuesta inesperada] {data}"


def preguntar(mensaje, historial=None):
    """
    Envia un mensaje a Anthropic via Kong y devuelve el texto de la respuesta.

    mensaje:   str con la pregunta del usuario.
    historial: lista opcional de mensajes previos en formato
               [{"role": "user"/"assistant", "content": "..."}].
    """
    mensajes = list(historial) if historial else []
    mensajes.append({"role": "user", "content": mensaje})

    payload = {"messages": mensajes}

    try:
        resp = requests.post(
            KONG_URL,
            json=payload,
            timeout=TIMEOUT_SECONDS,
            verify=VERIFY_TLS,
        )
    except requests.exceptions.SSLError:
        raise SystemExit(
            "Error TLS al conectar con Kong.\n"
            "Verifica que Kong escuche HTTPS en el puerto 8443 (KONG_PROXY_LISTEN)."
        )
    except requests.exceptions.ConnectionError:
        raise SystemExit(
            "No se pudo conectar a Kong en https://localhost:8443.\n"
            "Asegurate de haber arrancado Kong con:  ./start-kong.sh"
        )

    if resp.status_code != 200:
        raise SystemExit(
            f"Kong respondio con error {resp.status_code}:\n{resp.text}"
        )

    return _extraer_texto(resp.json())


def modo_interactivo():
    """Chat por terminal con memoria de la conversacion."""
    print("Chat con Claude via Kong + AIDR. Escribe 'salir' para terminar.\n")
    historial = []
    while True:
        try:
            pregunta = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if pregunta.lower() in ("salir", "exit", "quit"):
            print("Hasta luego.")
            break
        if not pregunta:
            continue

        respuesta = preguntar(pregunta, historial)
        print(f"\nClaude: {respuesta}\n")

        # Guardar el turno en el historial para mantener contexto.
        historial.append({"role": "user", "content": pregunta})
        historial.append({"role": "assistant", "content": respuesta})


if __name__ == "__main__":
    # Con argumento => pregunta unica. Sin argumento => modo interactivo.
    if len(sys.argv) > 1:
        pregunta = " ".join(sys.argv[1:])
        print(preguntar(pregunta))
    else:
        modo_interactivo()
