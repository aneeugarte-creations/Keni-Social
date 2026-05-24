"""Arranca la Consola Keni: servidor LOCAL (Starlette/uvicorn) en 127.0.0.1.

    python -m keni_metricas.consola

Puerto configurable con `KENI_CONSOLA_PORT` (def: 8765). Bind SIEMPRE a 127.0.0.1
(nunca 0.0.0.0): es una app que toca el disco y lanza procesos, no debe quedar
expuesta a la red. Imprime la URL y, best-effort, la abre en el navegador.
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
    url = f"http://{HOST}:{puerto}/proyectos"
    print(f"Consola Keni en {url}")
    print("Privacidad por diseno: solo escucha en 127.0.0.1 (no expuesta a la red).")

    # Abrir el navegador es best-effort: si falla (sin entorno grafico, etc.) no
    # debe impedir que el servidor arranque.
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    app = crear_app()
    uvicorn.run(app, host=HOST, port=puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
