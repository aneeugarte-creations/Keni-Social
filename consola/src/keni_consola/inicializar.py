"""Inicialización de la Prompts de Texto: migra el esquema de nombres/ids (one-shot) y materializa
en el STORE los prompts/editorial base que aún NO estén. Idempotente (no pisa lo que el equipo edite).

Por qué es un paso de DEPLOY y no del arranque: el `back` corre `uvicorn ...crear_app --factory`,
así que NO pasa por `__main__.main()` (donde vivía la inicialización para no tocar el estado real en los
tests). Sin esto, los prompts/editorial NUEVOS que viajan en una imagen no aparecen en el estudio
hasta que alguien los importa. `deploy.sh` lo ejecuta tras la migración de esquema. Ejecutar:

    python -m keni_consola.inicializar
"""

from __future__ import annotations


def main() -> int:
    from . import libprompts

    # ORDEN: la migración de nombres/ids (one-shot, por sentinela) va ANTES de importar_inicial.
    # Si no, `importar_inicial` crearía los ids NUEVOS junto a los VIEJOS del store = DUPLICADOS.
    # Esto corre en el DEPLOY (no en __main__, que el back-uvicorn no ejecuta).
    m = libprompts.migrar_nombres_prompts()
    if m:
        print(f"Texto: {m} documento(s) migrados al nuevo esquema de nombres.")
    o = libprompts.limpiar_prompts_obsoletos()
    if o:
        print(f"Texto: {o} prompt(s) obsoleto(s) eliminados del store.")
    o2 = libprompts.limpiar_prompts_obsoletos_v2()
    if o2:
        print(f"Texto: {o2} prompt(s) obsoleto(s) (ola v2) eliminados del store.")
    o3 = libprompts.limpiar_prompts_obsoletos_v3()
    if o3:
        print(f"Texto: {o3} prompt(s) obsoleto(s) (ola v3: macro-evento fundido en fusionar) eliminados.")
    ed = libprompts.limpiar_editoriales_duplicados()
    if ed:
        print(f"Texto: {ed} editorial(es) duplicado(s) eliminados del store.")
    d = libprompts.migrar_descripciones_editorial()
    if d:
        print(f"Texto: {d} editorial(es) con descripcion/titulo de plantilla vieja corregidos.")
    n = libprompts.importar_inicial()
    print(f"Texto: {n} documento(s) base importados.")
    # Reformato de los prompts del sistema (one-shot): propaga al store el cuerpo reformateado de la
    # inicial RESPETANDO ediciones del equipo (solo pisa el prompt cuyo cuerpo casa con el viejo). Va
    # ANTES de publicar para que la version "first commit" sea la reformateada.
    r = libprompts.reformatear_prompts()
    if r:
        print(f"Texto: {r} prompt(s) reformateados en el store.")
    # Funde macro-evento en fusionar: propaga el cuerpo NUEVO de `prompt/fusionar` (grupos + familias
    # en una pasada) al store, respetando ediciones del equipo. Tras retirar el macro (ola v3).
    ff = libprompts.propagar_fusionar_fundido()
    if ff:
        print(f"Texto: {ff} prompt(s) fusionar propagados (macro-evento fundido).")
    # Saca el contrato de salida (forma del JSON) del cuerpo editable a un placeholder gestionado
    # por codigo (`{{CONTRATO_SALIDA}}`); el editor lo muestra read-only. One-shot; re-publica los
    # que toca para no dejarlos "sin publicar". El prompt que ve el modelo queda byte-identico.
    cs = libprompts.migrar_contrato_salida()
    if cs:
        print(f"Texto: {cs} prompt(s) con el contrato de salida movido a placeholder.")
    # redactar: re-siembra la version simplificada + contrato y la publica (quedo fuera de la
    # migracion de contrato porque su contrato no era un substring limpio). One-shot.
    rd = libprompts.migrar_redactar_v1()
    if rd:
        print("Texto: redactar re-sembrado (simplificado + contrato) y publicado.")
    # parrilla: re-siembra sin la seccion «## Salida» (su contrato pasa a inyectarse desde codigo) y
    # la publica. One-shot.
    pa = libprompts.migrar_parrilla_v1()
    if pa:
        print("Texto: parrilla re-sembrada (contrato de salida a codigo) y publicada.")
    # ideas de audio: re-siembra la version ampliada (todo tipo, por categoria) y la publica (el
    # store conserva la vieja porque importar_inicial no pisa lo ya sembrado). One-shot.
    ia = libprompts.migrar_ideas_audio_v1()
    if ia:
        print("Texto: ideas de audio re-sembrado (todo tipo) y publicado.")
    # Titulos de una palabra agrupados por etapa: renombra los prompts del sistema (in place, solo si
    # el titulo casa con el viejo conocido) y re-publica. One-shot.
    tp = libprompts.migrar_titulos_prompts()
    if tp:
        print(f"Texto: {tp} prompt(s) renombrados a titulo de una palabra.")
    # Descripciones de prompt acortadas: reescribe las descripciones infladas (in place, solo si la
    # descripcion casa con la vieja conocida) y re-publica. One-shot.
    dp = libprompts.migrar_descripciones_prompt()
    if dp:
        print(f"Texto: {dp} prompt(s) con descripcion acortada.")
    # Alcance editorial: propaga el campo `pipelines` de la inicial al store (acota el auto-adjunto a
    # las etapas donde aplica; fin del sobre-prompteo) y re-publica. One-shot.
    ae = libprompts.migrar_alcance_editorial()
    if ae:
        print(f"Texto: {ae} editorial(es) acotados por pipeline.")
    # Linea base en git: que cada doc inicial tenga HEAD (snapshot estable para los pipelines,
    # no el working copy que reescribe el autosave). Best-effort: 0 si el versionado esta off.
    b = libprompts.asegurar_linea_base()
    if b:
        print(f"Texto: {b} documento(s) versionados como linea base.")
    # Publica una version inicial ("first commit") de cada doc activo sin puntero de produccion, para
    # que la UI deje de mostrarlos "sin publicar". Idempotente (salta los ya publicados) y best-effort
    # (necesita Postgres; 0 si no esta disponible).
    p = libprompts.publicar_linea_base()
    if p:
        print(f"Texto: {p} documento(s) publicados como linea base (first commit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
