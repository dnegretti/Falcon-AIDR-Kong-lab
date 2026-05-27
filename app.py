#!/usr/bin/env python3
"""
app.py - Consulta a Anthropic a traves de Kong AI Gateway.

Kong expone un endpoint compatible con OpenAI en /chat, traduce el request
al formato de Anthropic, agrega la API key, y devuelve la respuesta.
La app NO conoce la API key de Anthropic: solo habla con Kong.
"""

import sys
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# URL del endpoint de Kong (la ruta /chat definida en kong.yaml).
KONG_URL = "https://localhost:8443/chat"

# Timeout generoso para respuestas largas del modelo.
TIMEOUT_SECONDS = 120


def preguntar(mensaje, historial=None):
    """
    Envia un mensaje a Anthropic via Kong y devuelve el texto de la respuesta.

    mensaje:   str con la pregunta del usuario.
    historial: lista opcional de mensajes previos en formato
               [{"role": "user"/"assistant", "content": "..."}].
    """
    mensajes = list(historial) if historial else []
    mensajes.append({"role": "user", "content": mensaje})

    payload = {
        "messages": mensajes,
    }

    try:
        resp = requests.post(KONG_URL, json=payload, timeout=TIMEOUT_SECONDS, verify=False)
    except requests.exceptions.ConnectionError:
        raise SystemExit(
            "No se pudo conectar a Kong en http://localhost:8000.\n"
            "Asegurate de haber arrancado Kong con:  ./start-kong.sh"
        )

    if resp.status_code != 200:
        raise SystemExit(
            f"Kong respondio con error {resp.status_code}:\n{resp.text}"
        )

    data = resp.json()

    # Caso normal: respuesta en formato OpenAI (lo que produce el AI Proxy).
    if "choices" in data:
        return data["choices"][0]["message"]["content"]

    # Caso AIDR: la petición o respuesta fue bloqueada/transformada.
    if "status" in data or "reason" in data:
        motivo = data.get("reason", "")
        estado = data.get("status", "")
        return f"[AIDR] {estado} {motivo}".strip()

    # Caso formato nativo de Anthropic (por si el AI Proxy no tradujo).
    if "content" in data:
        bloques = data["content"]
        if isinstance(bloques, list) and bloques:
            return bloques[0].get("text", str(data))
        return str(bloques)

    # Cualquier otra cosa: mostrar el JSON crudo para diagnosticar.
    return f"[Respuesta inesperada] {data}"


def modo_interactivo():
    """Chat por terminal con memoria de la conversacion."""
    print("Chat con Claude via Kong. Escribe 'salir' para terminar.\n")
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
    # Si pasan un argumento, lo tratamos como pregunta unica.
    # Si no, entramos en modo interactivo.
    if len(sys.argv) > 1:
        pregunta = " ".join(sys.argv[1:])
        print(preguntar(pregunta))
    else:
        modo_interactivo()
