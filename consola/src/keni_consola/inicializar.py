"""Inicialización de la Biblioteca de Texto: migra el esquema de nombres/ids (one-shot) y materializa
en el STORE los prompts/editorial base que aún NO estén. Idempotente (no pisa lo que el equipo edite).

Por qué es un paso de DEPLOY y no del arranque: el `back` corre `uvicorn ...crear_app --factory`,
así que NO pasa por `__main__.main()` (donde vivía la inicialización para no tocar el estado real en los
tests). Sin esto, los prompts/editorial NUEVOS que viajan en una imagen no aparecen en el estudio
hasta que alguien los importa. `deploy.sh` lo ejecuta tras la migración de esquema. Ejecutar:

    python -m keni_consola.inicializar
"""

from __future__ import annotations


def main() -> int:
    from . import libtexto

    # ORDEN: la migración de nombres/ids (one-shot, por sentinela) va ANTES de importar_inicial.
    # Si no, `importar_inicial` crearía los ids NUEVOS junto a los VIEJOS del store = DUPLICADOS.
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
    n = libtexto.importar_inicial()
    print(f"Texto: {n} documento(s) base importados.")
    # Reformato de los prompts del sistema (one-shot): propaga al store el cuerpo reformateado de la
    # inicial RESPETANDO ediciones del equipo (solo pisa el prompt cuyo cuerpo casa con el viejo). Va
    # ANTES de publicar para que la version "first commit" sea la reformateada.
    r = libtexto.reformatear_prompts()
    if r:
        print(f"Texto: {r} prompt(s) reformateados en el store.")
    # Saca el contrato de salida (forma del JSON) del cuerpo editable a un placeholder gestionado
    # por codigo (`{{CONTRATO_SALIDA}}`); el editor lo muestra read-only. One-shot; re-publica los
    # que toca para no dejarlos "sin publicar". El prompt que ve el modelo queda byte-identico.
    cs = libtexto.migrar_contrato_salida()
    if cs:
        print(f"Texto: {cs} prompt(s) con el contrato de salida movido a placeholder.")
    # redactar: re-siembra la version simplificada + contrato y la publica (quedo fuera de la
    # migracion de contrato porque su contrato no era un substring limpio). One-shot.
    rd = libtexto.migrar_redactar_v1()
    if rd:
        print("Texto: redactar re-sembrado (simplificado + contrato) y publicado.")
    # Linea base en git: que cada doc inicial tenga HEAD (snapshot estable para los pipelines,
    # no el working copy que reescribe el autosave). Best-effort: 0 si el versionado esta off.
    b = libtexto.asegurar_linea_base()
    if b:
        print(f"Texto: {b} documento(s) versionados como linea base.")
    # Publica una version inicial ("first commit") de cada doc activo sin puntero de produccion, para
    # que la UI deje de mostrarlos "sin publicar". Idempotente (salta los ya publicados) y best-effort
    # (necesita Postgres; 0 si no esta disponible).
    p = libtexto.publicar_linea_base()
    if p:
        print(f"Texto: {p} documento(s) publicados como linea base (first commit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
