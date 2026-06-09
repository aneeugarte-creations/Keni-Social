"""Siembra de la Biblioteca de Texto: materializa en el STORE los prompts/editorial base que aún
NO estén. Idempotente (no pisa lo que el equipo edite).

Por qué es un paso de DEPLOY y no del arranque: el `back` corre `uvicorn ...crear_app --factory`,
así que NO pasa por `__main__.main()` (donde vivía la siembra para no tocar el estado real en los
tests). Sin esto, los prompts/editorial NUEVOS que viajan en una imagen no aparecen en el estudio
hasta que alguien los importa. `deploy.sh` lo ejecuta tras la migración de esquema. Ejecutar:

    python -m keni_consola.sembrar
"""

from __future__ import annotations


def main() -> int:
    from . import libtexto

    n = libtexto.importar_semilla()
    print(f"Texto: {n} documento(s) base importados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
