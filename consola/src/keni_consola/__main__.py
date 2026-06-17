"""Arranca la Consola Keni: servidor (Starlette/uvicorn).

    python -m keni_consola                  # arranca el servidor

Puerto configurable con `KENI_CONSOLA_PORT` (def: 8765) y host con
`KENI_CONSOLA_HOST` (def: 127.0.0.1). Por defecto solo escucha en localhost: es una
app que toca el disco y lanza procesos. Bind a `0.0.0.0` SOLO detras de un proxy de
confianza y CON auth (login multiusuario + token, #130/#134); el proxy es quien la
expone y termina TLS (entonces pon `KENI_CONSOLA_HTTPS=1` para cookies `Secure`).
Imprime la URL y, best-effort, la abre en el navegador.

NOTA: el contenido editorial vive en ficheros YAML por marca (`ficheros.py`) y el
dato operacional (contenido + comercial + rota + usuarios) en Postgres (`db.py`,
ADR 0004). `DATABASE_URL` es obligatoria; sin ella el arranque falla con un mensaje
accionable.
"""

from __future__ import annotations

import sys
import webbrowser

import uvicorn

from . import config
from .app import crear_app

# Bind por defecto a localhost. Configurable con `KENI_CONSOLA_HOST` (#130): en
# contenedor se pone `0.0.0.0` para que un reverse-proxy de confianza la exponga. Es
# seguro porque YA hay auth (login multiusuario + token, #130/#134); NO la pongas en
# `0.0.0.0` sin un proxy delante. El nombre/default de la var vive en `config`.
HOST = config.host()
# Puerto por defecto (re-exportado de `config`; algunos tests lo referencian aqui).
PUERTO_DEF = config.PORT_DEF


def _puerto() -> int:
    return config.port()


def main() -> int:
    # Logging del paquete (issue #123): nivel via KENI_CONSOLA_LOG_LEVEL (def: INFO).
    # Se configura aqui, en el arranque real; los tests no lo necesitan (usan caplog).
    from .observabilidad import configurar_logging

    configurar_logging()

    puerto = _puerto()

    # Seguridad (#134/#150): resolvemos el token de mantenimiento AQUI para pasarselo a la
    # app (un unico token por proceso). Si el operador fijo `KENI_CONSOLA_TOKEN`, usamos
    # ese; si no, generamos uno. NUNCA lo metemos en la URL ni lo imprimimos (#150): un
    # token en la URL/log es un vector de fuga trivial (historial, capturas, logs). La
    # cookie del token la inicializa el propio index del SPA al cargar la pagina (ver
    # `app._respuesta_index_spa`), sin necesidad de `?token=` en la URL.
    from . import seguridad

    token, generado = seguridad.resolver_token()

    # Host navegable para la URL: si el bind es `0.0.0.0` (todas las interfaces) no es
    # una direccion a la que el navegador pueda ir, asi que mostramos `localhost`.
    host_url = "localhost" if HOST in ("0.0.0.0", "::") else HOST
    # URL LIMPIA, SIN el token (#150): la cookie se inicializa al servir el index.
    url = f"http://{host_url}:{puerto}/"
    print(f"Consola Keni escuchando en {HOST}:{puerto}")
    if HOST in ("0.0.0.0", "::"):
        print(
            "AVISO: bind a todas las interfaces. Hazlo SOLO detras de un proxy de "
            "confianza y CON auth (login multiusuario); el proxy es quien la expone."
        )
    else:
        print(f"Privacidad por diseno: solo escucha en {HOST} (no expuesta a la red).")
    if generado:
        # NO imprimimos el token (#150). El operador local entra por el LOGIN multiusuario
        # (el admin de bootstrap se loguea aparte). El token es solo una credencial de
        # mantenimiento opcional y se entrega fuera de banda, nunca por la URL/log.
        print(
            "Token de mantenimiento generado para esta ejecucion (no habia "
            "KENI_CONSOLA_TOKEN). Entra con tu usuario y contraseña (login multiusuario).\n"
            f"  Abre la Consola en: {url}"
        )
    else:
        print(
            "Auth multiusuario activa (login user/pass). Hay un KENI_CONSOLA_TOKEN de "
            "mantenimiento configurado (entregado fuera de banda; NO viaja en la URL).\n"
            f"  Abre la Consola en: {url}"
        )

    # Abrir el navegador es best-effort: si falla (sin entorno grafico, etc.) no debe
    # impedir que el servidor arranque. Abrimos la URL LIMPIA (sin token, #150): la cookie
    # del token la inicializa el index del SPA al cargar, asi que la UI funciona igual.
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    # Pasamos el token ya resuelto a la app (asi no se vuelve a generar otro).
    app = crear_app(token=token)

    # Inicializacion de la Texto (best-effort): en el PRIMER arranque copia la linea editorial
    # y los prompts base al store si aun no estan. Idempotente; no pisa lo que el equipo edite.
    # Vive aqui (servidor real), NO en `crear_app`, para no tocar el estado real en los tests.
    try:
        from . import libprompts

        m = libprompts.migrar_nombres_prompts()
        if m:
            print(f"Texto: {m} documento(s) migrados al nuevo esquema de nombres.")
        o = libprompts.limpiar_prompts_obsoletos()
        if o:
            print(f"Texto: {o} prompt(s) obsoleto(s) eliminados del store.")
        o2 = libprompts.limpiar_prompts_obsoletos_v2()
        if o2:
            print(f"Texto: {o2} prompt(s) obsoleto(s) (ola v2) eliminados del store.")
        ed = libprompts.limpiar_editoriales_duplicados()
        if ed:
            print(f"Texto: {ed} editorial(es) duplicado(s) eliminados del store.")
        d = libprompts.migrar_descripciones_editorial()
        if d:
            print(f"Texto: {d} editorial(es) con descripcion/titulo de plantilla vieja corregidos.")
        n = libprompts.importar_inicial()
        if n:
            print(f"Texto: {n} documento(s) base importados.")
        # Reformato (one-shot): propaga al store el cuerpo reformateado de los prompts del sistema,
        # respetando ediciones del equipo. Antes de publicar, para que el "first commit" sea el nuevo.
        r = libprompts.reformatear_prompts()
        if r:
            print(f"Texto: {r} prompt(s) reformateados en el store.")
        # Saca el contrato de salida del cuerpo editable a un placeholder gestionado por codigo
        # (`{{CONTRATO_SALIDA}}`); el editor lo muestra read-only. One-shot, re-publica los que toca.
        cs = libprompts.migrar_contrato_salida()
        if cs:
            print(f"Texto: {cs} prompt(s) con el contrato de salida movido a placeholder.")
        # redactar: re-siembra simplificado + contrato y publica (quedo fuera de la migracion de contrato).
        rd = libprompts.migrar_redactar_v1()
        if rd:
            print("Texto: redactar re-sembrado (simplificado + contrato) y publicado.")
        pa = libprompts.migrar_parrilla_v1()
        if pa:
            print("Texto: parrilla re-sembrada (contrato de salida a codigo) y publicada.")
        # Titulos de una palabra agrupados por etapa (one-shot, in place, re-publica).
        tp = libprompts.migrar_titulos_prompts()
        if tp:
            print(f"Texto: {tp} prompt(s) renombrados a titulo de una palabra.")
        # Descripciones de prompt acortadas (one-shot, in place, re-publica).
        dp = libprompts.migrar_descripciones_prompt()
        if dp:
            print(f"Texto: {dp} prompt(s) con descripcion acortada.")
        # Alcance editorial: propaga el campo `pipelines` al store (acota el auto-adjunto; re-publica).
        ae = libprompts.migrar_alcance_editorial()
        if ae:
            print(f"Texto: {ae} editorial(es) acotados por pipeline.")
        # Linea base en git: cada doc inicializado con HEAD (snapshot estable para los pipelines).
        b = libprompts.asegurar_linea_base()
        if b:
            print(f"Texto: {b} documento(s) versionados como linea base.")
        # Publica una version inicial ("first commit") de cada doc sin puntero (best-effort: necesita BD).
        p = libprompts.publicar_linea_base()
        if p:
            print(f"Texto: {p} documento(s) publicados como linea base (first commit).")
    except Exception:  # noqa: BLE001 -- la inicializacion nunca debe impedir el arranque
        pass

    # Refresco de metricas: un hilo demonio que mantiene caliente la cache de metricas
    # (Postgres), refrescandola al arrancar y cada N horas (def 4h, KENI_METRICAS_REFRESCO_HORAS).
    # Asi la UI lee datos ya calculados (instantaneo) sin golpear las APIs externas en cada
    # apertura; el boton "Actualizar" dispara un refresco extra a demanda. Vive aqui (servidor
    # real), NO en `crear_app`, para no arrancarlo en los tests (igual que el programador).
    from .metricas_refresco import iniciar_refresco_metricas

    iniciar_refresco_metricas()

    # Refresco PROACTIVO de la cache POR PIEZA (Fase 3 auto-operativa): un hilo demonio que
    # recalcula el rendimiento de las piezas publicadas recientes (con `id_post_metricool`)
    # desde Metricool cada N horas (def 4h, KENI_METRICAS_PIEZAS_REFRESCO_HORAS), para que el
    # tablero vea datos frescos sin lazy-fill en la apertura. Vive aqui
    # (servidor real), NO en `crear_app`, para no arrancarlo en los tests.
    from .metricas_piezas_refresco import iniciar_refresco_piezas

    iniciar_refresco_piezas()

    # Alertas de rendimiento (Fase 3 auto-operativa): un hilo demonio
    # que cada N horas (def 6h, KENI_ALERTAS_RENDIMIENTO_HORAS) emite eventos internos
    # `pieza.bajo_rendimiento` (piezas
    # publicadas bajo el umbral de engagement), repartidos a los webhooks salientes si los
    # hay. SAFE BY DEFAULT: sin webhooks no toca la red. KENI_ALERTAS_RENDIMIENTO=0 lo apaga.
    # Vive aqui (servidor real), NO en `crear_app`.
    from .alertas_rendimiento import iniciar_alertas_rendimiento

    iniciar_alertas_rendimiento()

    # Worker de generacion (#130 Fase 2 / ADR 0002 Fase B): el back ENCOLA y un WORKER
    # corre `claude -p`. En el perfil LOCAL / un solo proceso, el worker corre EN PROCESO
    # (hilo daemon) para que la UX de una sola maquina no cambie (no hace falta un servicio
    # aparte). En HOSTED hay un servicio `worker` aparte: el back arranca con
    # `KENI_WORKER_EXTERNO=1` y aqui NO se arranca el in-proceso. Vive aqui (servidor real),
    # NO en `crear_app`, para no arrancarlo en los tests (igual que el programador).
    if not config.worker_externo():
        from .worker import iniciar_worker_inproceso

        iniciar_worker_inproceso()

    # Auto-refresco de ALGORITMOS (inteligencia de plataforma): un hilo demonio que, si
    # `KENI_ALGORITMOS_AUTO` esta activo (def OFF), ingiere cada N horas los feeds de blogs
    # oficiales/agregadores y mantiene al dia la pagina Algoritmos y el panel. SOLO LEE feeds
    # RSS publicos; no publica ni genera. SAFE BY DEFAULT: sin el flag no ingiere. Vive aqui
    # (servidor real), NO en `crear_app`, para no arrancarlo en los tests.
    from .algoritmos_refresco import iniciar_refresco_algoritmos

    iniciar_refresco_algoritmos()

    # MÁQUINA DE CONTENIDO (Flujo C): el pipeline es el núcleo de la auto-producción. Si está
    # activo (`KENI_PIPELINE_REDACTAR`, bajo el maestro `KENI_MAQUINA`), cada N horas ingiere del news-pool,
    # genera copy (etapa de Redactar) y arte (etapa de Ilustrar, `KENI_PIPELINE_ILUSTRAR`) y valida los
    # borradores recientes (verificación), registrando cada etapa en "Actividad IA". Deja borradores en la
    # cola de revision; NO publica solo. SAFE BY DEFAULT: sin el flag no barre. Vive aqui (servidor
    # real), NO en `crear_app`, para no arrancarlo en los tests.
    from .pipeline_contenido import iniciar_pipeline

    iniciar_pipeline()

    # GC de MEDIA SUELTA (Estudio §5): un hilo demonio que, si `KENI_MEDIA_GC` esta activo
    # (def OFF), barre cada N horas el almacen de media y borra los objetos SUELTOS (no
    # referenciados por ninguna pieza) y mas viejos que el umbral. SAFE BY DEFAULT: sin
    # el flag no borra nada. Vive aqui (servidor real), NO en `crear_app`, para no arrancarlo
    # en los tests.
    from .media_gc_daemon import iniciar_media_gc

    iniciar_media_gc()

    # GC del POOL DE NOTICIAS por relevancia (no por edad): un hilo demonio gateado por
    # `KENI_NOTICIAS_GC` (def OFF) que purga lo irrelevante de baja relevancia (historias `nuevo` de una
    # fuente, score bajo e inactivas + items sueltos viejos), conservando lo usado/corroborado/
    # reciente. SAFE BY DEFAULT: sin el flag no borra nada. Vive aquí (servidor real), no en tests.
    from .noticias_gc_daemon import iniciar_noticias_gc

    iniciar_noticias_gc()

    # Limpiador de GENERACIONES atascadas: un hilo demonio (SIEMPRE activo) que cierra como `error`
    # las generaciones colgadas en `ejecutando` cuyo proceso murio (reinicio/OOM/cuelgue), para
    # que el Monitor de Actividad no las muestre "Ejecutando…" indefinidamente. Barre al
    # arrancar (limpia las sueltas del crash anterior) y cada N min. Vive aqui (servidor
    # real), NO en `crear_app`, para no arrancarlo en los tests.
    from .limpiador_generaciones import iniciar_limpiador

    iniciar_limpiador()

    uvicorn.run(app, host=HOST, port=puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
