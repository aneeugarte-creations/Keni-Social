"""Siembra de la Biblioteca de Texto: migra el esquema de nombres/ids (one-shot) y materializa
en el STORE los prompts/editorial base que aún NO estén. Idempotente (no pisa lo que el equipo edite).

Por qué es un paso de DEPLOY y no del arranque: el `back` corre `uvicorn ...crear_app --factory`,
así que NO pasa por `__main__.main()` (donde vivía la siembra para no tocar el estado real en los
tests). Sin esto, los prompts/editorial NUEVOS que viajan en una imagen no aparecen en el estudio
hasta que alguien los importa. `deploy.sh` lo ejecuta tras la migración de esquema. Ejecutar:

    python -m keni_consola.sembrar
"""

from __future__ import annotations


def main() -> int:
    from . import libtexto

    # ORDEN: la migración de nombres/ids (one-shot, por sentinela) va ANTES de importar_semilla.
    # Si no, `importar_semilla` crearía los ids NUEVOS junto a los VIEJOS del store = DUPLICADOS.
    # Esto corre en el DEPLOY (no en __main__, que el back-uvicorn no ejecuta).
    m = libtexto.migrar_nombres_biblioteca()
    if m:
        print(f"Texto: {m} documento(s) migrados al nuevo esquema de nombres.")
    o = libtexto.limpiar_prompts_obsoletos()
    if o:
        print(f"Texto: {o} prompt(s) obsoleto(s) eliminados del store.")
    d = libtexto.migrar_descripciones_editorial()
    if d:
        print(f"Texto: {d} editorial(es) con descripcion/titulo de plantilla vieja corregidos.")
    n = libtexto.importar_semilla()
    print(f"Texto: {n} documento(s) base importados.")
    # Linea base en git: que cada doc sembrado tenga HEAD (snapshot estable para los pipelines,
    # no el working copy que reescribe el autosave). Best-effort: 0 si el versionado esta off.
    b = libtexto.asegurar_linea_base()
    if b:
        print(f"Texto: {b} documento(s) versionados como linea base.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
