"""Arranca la Consola Keni: servidor LOCAL (Starlette/uvicorn) en 127.0.0.1.

    python -m keni_consola                  # arranca el servidor

Puerto configurable con `KENI_CONSOLA_PORT` (def: 8765). Bind SIEMPRE a 127.0.0.1
(nunca 0.0.0.0): es una app que toca el disco y lanza procesos, no debe quedar
expuesta a la red. Imprime la URL y, best-effort, la abre en el navegador.

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

# Bind FIJO a localhost. No se expone por env var a proposito (decision de
# seguridad: la consola nunca debe escuchar en una interfaz de red).
HOST = "127.0.0.1"
PUERTO_DEF = 8765


def _puerto() -> int:
    crudo = os.environ.get("KENI_CONSOLA_PORT", str(PUERTO_DEF))
    try:
        return int(crudo)
    except ValueError:
        return PUERTO_DEF


def main() -> int:
    puerto = _puerto()
    url = f"http://{HOST}:{puerto}/"
    print(f"Consola Keni en {url}")
    print("Privacidad por diseno: solo escucha en 127.0.0.1 (no expuesta a la red).")

    # Abrir el navegador es best-effort: si falla (sin entorno grafico, etc.) no
    # debe impedir que el servidor arranque.
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    app = crear_app()

    # Captura programada del apartado Comercial: un hilo demonio que va tomando
    # snapshots de las piezas activas (interacciones/alcance) aunque nadie mire.
    # Vive aqui (servidor real) y NO en `crear_app`, para no arrancarlo en los tests.
    from .comercial import iniciar_captura_programada

    iniciar_captura_programada()

    uvicorn.run(app, host=HOST, port=puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
