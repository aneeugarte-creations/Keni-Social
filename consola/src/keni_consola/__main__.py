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
    # cookie del token la siembra el propio index del SPA al cargar la pagina (ver
    # `app._respuesta_index_spa`), sin necesidad de `?token=` en la URL.
    from . import seguridad

    token, generado = seguridad.resolver_token()

    # Host navegable para la URL: si el bind es `0.0.0.0` (todas las interfaces) no es
    # una direccion a la que el navegador pueda ir, asi que mostramos `localhost`.
    host_url = "localhost" if HOST in ("0.0.0.0", "::") else HOST
    # URL LIMPIA, SIN el token (#150): la cookie se siembra al servir el index.
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
    # del token la siembra el index del SPA al cargar, asi que la UI funciona igual.
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    # Pasamos el token ya resuelto a la app (asi no se vuelve a generar otro).
    app = crear_app(token=token)

    # Siembra de la Biblioteca (best-effort): en el PRIMER arranque copia la linea editorial
    # y los prompts base al store si aun no estan. Idempotente; no pisa lo que el equipo edite.
    # Vive aqui (servidor real), NO en `crear_app`, para no tocar el estado real en los tests.
    try:
        from . import biblioteca

        n = biblioteca.importar_semilla()
        if n:
            print(f"Biblioteca: {n} documento(s) base importados.")
    except Exception:  # noqa: BLE001 -- la siembra nunca debe impedir el arranque
        pass

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

    # Barrido de EVENTOS INTERNOS del tablero (pieza vencida): un hilo demonio que, cuando
    # un contenido pasa su `fecha_entrega` sin cerrarse, emite `contenido.vencido` y lo
    # reparte a los webhooks salientes que el equipo haya dado de alta. SAFE BY DEFAULT: sin
    # webhooks activos no toca la red. Vive aqui (servidor real), NO en `crear_app`.
    from .eventos_scanner import iniciar_scanner_vencimientos

    iniciar_scanner_vencimientos()

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
    # tablero y el reciclaje vean datos frescos sin lazy-fill en la apertura. Vive aqui
    # (servidor real), NO en `crear_app`, para no arrancarlo en los tests.
    from .metricas_piezas_refresco import iniciar_refresco_piezas

    iniciar_refresco_piezas()

    # Alertas de rendimiento / reciclaje proactivo (Fase 3 auto-operativa): un hilo demonio
    # que cada N horas (def 6h, KENI_ALERTAS_RENDIMIENTO_HORAS) emite eventos internos
    # `pieza.reciclaje_sugerida` (candidatas del archivo) y `pieza.bajo_rendimiento` (piezas
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

    # Auto-promocion del Radar (fase3 auto-planificacion): un hilo demonio que, si
    # `KENI_RADAR_AUTO` esta activo (def OFF), promueve cada N horas los temas del Radar que
    # superan el umbral de señal a contenido `flujo='importante'` (revisable en el tablero).
    # SAFE BY DEFAULT: sin el flag no arranca (el Radar sigue siendo solo-propone). Vive aqui
    # (servidor real), NO en `crear_app`, para no arrancarlo en los tests.
    from .radar_auto import iniciar_radar_auto

    iniciar_radar_auto()

    uvicorn.run(app, host=HOST, port=puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
