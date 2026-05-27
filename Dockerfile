# Dockerfile - Kong Gateway con los plugins de CrowdStrike AIDR.
#
# Construye una imagen propia sobre la imagen oficial de Kong, compilando
# los plugins crowdstrike-aidr-request y crowdstrike-aidr-response desde
# el codigo fuente del repo oficial de CrowdStrike.

FROM kong/kong-gateway:latest

# Los pasos de compilacion necesitan permisos de root.
USER root

# Instalar git para clonar el repo de los plugins.
# (la imagen base es Ubuntu; si cambia la base, ajusta el gestor de paquetes)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Clonar el repo oficial de los plugins de AIDR para Kong.
RUN git clone https://github.com/crowdstrike/aidr-kong.git /tmp/aidr-kong

WORKDIR /tmp/aidr-kong

# Compilar los tres rockspecs con luarocks (el utilitario que trae Kong).
# El orden importa: primero el modulo compartido, luego request y response.
RUN luarocks make kong-plugin-crowdstrike-aidr-shared-*.rockspec \
  && luarocks make kong-plugin-crowdstrike-aidr-request-*.rockspec \
  && luarocks make kong-plugin-crowdstrike-aidr-response-*.rockspec

# Indicar a Kong que cargue los plugins por defecto MAS los de AIDR.
ENV KONG_PLUGINS=bundled,crowdstrike-aidr-request,crowdstrike-aidr-response

# Volver al usuario kong para la ejecucion de la imagen.
USER kong

# Configuracion estandar de arranque de Kong.
ENTRYPOINT ["/entrypoint.sh"]
EXPOSE 8000 8443 8001 8444
STOPSIGNAL SIGQUIT
HEALTHCHECK --interval=10s --timeout=10s --retries=10 CMD kong health
CMD ["kong", "docker-start"]
