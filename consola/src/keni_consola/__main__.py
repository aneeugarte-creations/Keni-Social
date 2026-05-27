"""Arranca la Consola Keni: servidor (Starlette/uvicorn).

    python -m keni_consola                  # arranca el servidor

Puerto configurable con `KENI_CONSOLA_PORT` (def: 8765) y host con
`KENI_CONSOLA_HOST` (def: 127.0.0.1). Por defecto solo escucha en localhost: es una
app que toca el disco y lanza procesos. Bind a `0.0.0.0` SOLO detras de un proxy de
confianza y CON auth (login multiusuario + token, #130/#134); el proxy es quien la
expone y termina TLS (entonces pon `KENI_CONSOLA_HTTPS=1` para cookies `Secure`).
Imprime la URL y, best-effort, la abre en el navegador.

NOTA: el contenido editorial vive en ficheros YAML por marca (`ficheros.py`) y el
dato operacional (tareas + comercial) en SQLite (`db.py`). La vieja migracion
one-shot SQLite->YAML se ARCHIVO en `consola/scripts/migrar_a_ficheros.py` (ya no es
un subcomando: el backend de contenido es YAML fijo).
"""

from __future__ import annotations

import os
import sys
import webbrowser

import uvicorn

from .app import crear_app

# Bind por defecto a localhost. Configurable con `KENI_CONSOLA_HOST` (#130): en
# contenedor se pone `0.0.0.0` para que un reverse-proxy de confianza la exponga. Es
# seguro porque YA hay auth (login multiusuario + token, #130/#134); NO la pongas en
# `0.0.0.0` sin un proxy delante.
HOST = os.environ.get("KENI_CONSOLA_HOST", "127.0.0.1")
PUERTO_DEF = 8765


def _puerto() -> int:
    crudo = os.environ.get("KENI_CONSOLA_PORT", str(PUERTO_DEF))
    try:
        return int(crudo)
    except ValueError:
        return PUERTO_DEF


def main() -> int:
    # Logging del paquete (issue #123): nivel via KENI_CONSOLA_LOG_LEVEL (def: INFO).
    # Se configura aqui, en el arranque real; los tests no lo necesitan (usan caplog).
    from .observabilidad import configurar_logging

    configurar_logging()

    puerto = _puerto()

    # Seguridad (#134): resolvemos el token de sesion AQUI para poder componer la URL
    # con `?token=...` (que siembra la cookie en el navegador) y mostrarlo. Si el
    # operador fijo `KENI_CONSOLA_TOKEN`, usamos ese; si no, generamos uno y avisamos.
    from . import seguridad

    token, generado = seguridad.resolver_token()

    # Host navegable para la URL: si el bind es `0.0.0.0` (todas las interfaces) no es
    # una direccion a la que el navegador pueda ir, asi que mostramos `localhost`.
    host_url = "localhost" if HOST in ("0.0.0.0", "::") else HOST
    base = f"http://{host_url}:{puerto}/"
    # La URL con `?token` siembra la cookie del token; el SPA luego autentica solo.
    url = f"{base}?token={token}"
    print(f"Consola Keni escuchando en {HOST}:{puerto}")
    if HOST in ("0.0.0.0", "::"):
        print(
            "AVISO: bind a todas las interfaces. Hazlo SOLO detras de un proxy de "
            "confianza y CON auth (login + token); el proxy es quien la expone."
        )
    else:
        print(f"Privacidad por diseno: solo escucha en {HOST} (no expuesta a la red).")
    if generado:
        print(
            "Token de sesion generado para esta ejecucion (no habia KENI_CONSOLA_TOKEN).\n"
            f"  Abre la Consola con: {url}\n"
            "  O exporta KENI_CONSOLA_TOKEN=<tu-token> para fijar uno estable."
        )
    else:
        print("Auth activa con KENI_CONSOLA_TOKEN. Abre la Consola con tu token en la URL "
              "(?token=...) la primera vez.")

    # Abrir el navegador es best-effort: si falla (sin entorno grafico, etc.) no
    # debe impedir que el servidor arranque. Abrimos la URL CON el token para que la
    # cookie quede sembrada y la UI funcione sin pasos manuales.
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    # Pasamos el token ya resuelto a la app (asi no se vuelve a generar/loguear otro).
    app = crear_app(token=token)

    # Captura programada del apartado Comercial: un hilo demonio que va tomando
    # snapshots de las piezas activas (interacciones/alcance) aunque nadie mire.
    # Vive aqui (servidor real) y NO en `crear_app`, para no arrancarlo en los tests.
    from .comercial import iniciar_captura_programada

    iniciar_captura_programada()

    # Programador de publicaciones (#9, Fase 3): un hilo demonio que, al vencer la
    # `fecha_programada` de una pieza `programado`, la PREPARA en dry-run (estampa
    # `preparado_en`). NO publica en ninguna plataforma: el posteo real esta gated por
    # #5/#8 ("el humano aprueba; el sistema no publica solo"). Vive aqui (servidor real),
    # NO en `crear_app`, para no arrancarlo en los tests.
    from .programador import iniciar_programador

    iniciar_programador()

    uvicorn.run(app, host=HOST, port=puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
