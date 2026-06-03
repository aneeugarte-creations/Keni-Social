"""Programador de publicaciones (#9, Fase 3): prepara/publica las piezas vencidas.

Que hace y, sobre todo, que NO hace
===================================
Una pieza APROBADA puede PROGRAMARSE para una fecha-hora (via `api/aprobacion.py`):
pasa a estado `programado` con su `fecha_programada`. Este modulo es el reloj del
servidor: un hilo demonio que, cuando una pieza programada VENCE (su
`fecha_programada <= ahora`), la PREPARA estampando `preparado_en` y, si el flag
`KENI_PUBLICAR_REAL` esta activo, la entrega al scheduler de Metricool.

GATING (frontera del producto, CRITICO):
  - Por defecto (`KENI_PUBLICAR_REAL` ausente o falso) el barrido es DRY-RUN:
    solo estampa `preparado_en` y deja la pieza en `programado`. NADA va a
    Metricool. Comportamiento identico al anterior.
  - Con `KENI_PUBLICAR_REAL=1` el barrido llama a `AdaptadorPublicacionMetricool`
    con `dry_run=False` para la marca de la pieza. Si Metricool confirma, la pieza
    pasa a `publicado` con `id_post_metricool` guardado. Si falla o la marca no
    tiene credenciales, la pieza SIGUE en `programado` y el error se loguea sin
    romper el barrido (degradacion honesta).
  - "El humano aprueba; el sistema no publica solo": el humano programa la pieza
    con una fecha; el sistema ejecuta el despacho al scheduler de Metricool cuando
    vence esa fecha. Metricool luego publica en las redes sociales al momento
    programado (autoPublish=true).

FLOW: fila publicacion -> BorradorMetricool -> AdaptadorPublicacionMetricool -> Metricool
  1. `pub["red"]` (id canonico, p.ej. "x") -> `Plataforma` de keni_metricas.
  2. `pub["marca"]` (slug-guion, p.ej. "claro-sports") ->
     `marcas.id_metricas_de(...)` (guion_bajo, p.ej. "claro_sports") ->
     credenciales de MetricoolConfig.marcas_configuradas()[id_metricas].
  3. `pub["imagen"]` (nombre de archivo) + `KENI_CONSOLA_URL_PUBLICA` ->
     URL absoluta publica que Metricool puede ingerir. Sin URL publica, se omite
     la media y se loguea (el post va solo con texto, si la red lo permite).
  4. `pub["contenido"]` -> `BorradorMetricool.texto`.
     `pub["fecha_programada"]` -> `BorradorMetricool.publicar_en`.

El calculo de "que esta vencido" es una funcion PURA y DETERMINISTA (`piezas_vencidas`)
que recibe `ahora` inyectado, para poder testearla sin reloj real ni hilo. El hilo
(`iniciar_programador`) vive en el servidor real (`__main__`), NO en `crear_app`: los
tests no lo arrancan (igual que la captura comercial). Cada operacion abre/cierra su
propia conexion, asi que correr en un hilo aparte es seguro.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

from . import config, marcas, repos
from .estados import ESTADO_PROGRAMADO

_log = logging.getLogger("keni_consola.programador")

# Cadencia por defecto del barrido del programador (segundos). Un minuto basta: la
# granularidad de las fechas programadas es el minuto.
INTERVALO_SEGUNDOS_DEF = 60.0


def _a_utc(dt: datetime) -> datetime:
    """Normaliza un datetime a UTC consciente. Naive → se asume UTC (convención del
    sistema: el servidor corre en UTC y los timestamps sin zona SON UTC)."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _parsear_fecha(valor: str) -> datetime | None:
    """Parsea una `fecha_programada` ISO a un instante UTC consciente; None si no es valida.

    Acepta 'YYYY-MM-DDTHH:MM' (o con segundos) y formatos con zona ('...Z'/'+00:00',
    que es lo que envía la UI: el picker es hora CDMX y se manda como instante UTC). Las
    cadenas SIN zona se interpretan como UTC. Así la comparación con `ahora` (UTC) en
    `piezas_vencidas` siempre es aware-vs-aware (nunca naive-vs-aware → TypeError)."""
    if not valor:
        return None
    try:
        return _a_utc(datetime.fromisoformat(valor))
    except ValueError:
        return None


def piezas_vencidas(
    programadas: list[dict[str, Any]], ahora: datetime
) -> list[dict[str, Any]]:
    """Subconjunto de `programadas` que ya vencio y aun NO se preparo (PURA, testeable).

    Una pieza esta vencida si: su estado es `programado`, tiene `fecha_programada`
    valida <= `ahora`, y NO tiene `preparado_en` (no se preparo ya). Determinista:
    depende solo de sus argumentos (no del reloj real ni de la BD).
    """
    # `ahora` puede llegar naive (p.ej. desde tests o un llamador antiguo): se normaliza a
    # UTC para comparar aware-vs-aware con las fechas parseadas (que siempre son UTC).
    ahora = _a_utc(ahora)
    vencidas: list[dict[str, Any]] = []
    for pub in programadas:
        if pub.get("estado") != ESTADO_PROGRAMADO:
            continue
        if pub.get("preparado_en"):  # ya preparada en un barrido anterior
            continue
        fecha = _parsear_fecha(pub.get("fecha_programada") or "")
        if fecha is None or fecha > ahora:
            continue
        vencidas.append(pub)
    return vencidas


# --------------------------------------------------------------------------- #
# Resolucion de credenciales Metricool por marca (pura, testeable)             #
# --------------------------------------------------------------------------- #


def _creds_metricool(marca_id: str) -> dict | None:
    """Credenciales Metricool para la marca `marca_id` (slug-guion) o None si no estan.

    Carga la config de keni_metricas (TOML + env), traduce el id canonico al
    id_metricas y resuelve user_token + user_id + blog_id. Devuelve None si la
    marca no tiene credenciales completas (sin romper; el llamante degrada).
    """
    try:
        from keni_metricas.config import cargar_config
    except ImportError:
        _log.warning("keni_metricas no disponible; no se puede resolver creds Metricool.")
        return None

    id_mc = marcas.id_metricas_de(marca_id)  # slug-guion -> guion_bajo
    try:
        cfg = cargar_config()
        configuradas = cfg.metricool.marcas_configuradas()
    except Exception:  # noqa: BLE001 -- config rota no debe romper el barrido
        _log.exception("Error cargando config de Metricool para marca %r.", marca_id)
        return None

    creds = configuradas.get(id_mc)
    if not creds:
        return None
    return creds


# --------------------------------------------------------------------------- #
# Construccion del BorradorMetricool desde la fila de publicacion              #
# --------------------------------------------------------------------------- #


def _url_media_publica(nombre_imagen: str) -> str | None:
    """URL absoluta de la imagen para que Metricool la ingiera, o None si no hay base.

    Requiere `KENI_CONSOLA_URL_PUBLICA` (p.ej. `https://social.kenitech.io`). Sin
    esa var el programador omite las media URLs del borrador y lo loguea.
    """
    if not nombre_imagen:
        return None
    base = config.consola_url_publica()
    if not base:
        return None
    return f"{base}/api/media/{nombre_imagen}"


def _borrador_de_publicacion(pub: dict[str, Any]) -> object | None:
    """Construye un `BorradorMetricool` desde la fila de publicacion, o None si no aplica.

    Devuelve None (sin lanzar) si:
      - La red no es soportada por Metricool (no esta en Plataforma).
      - La red exige media (instagram/tiktok/youtube) y no hay imagen con URL publica.
      - El contenido (texto) esta vacio Y no hay media: nada que publicar.
    Todos los casos se loguean a nivel WARNING para que sean trazables.
    """
    try:
        from keni_metricas.publicacion.metricool import BorradorMetricool
        from keni_metricas.publicacion.modelos import MediaRef, TipoMedia
        from keni_metricas.schema import Plataforma
        from pydantic import ValidationError
    except ImportError:
        _log.warning("keni_metricas no disponible; no se puede construir BorradorMetricool.")
        return None

    red_id = pub.get("red") or ""
    try:
        plataforma = Plataforma(red_id)
    except ValueError:
        _log.warning(
            "Pieza %r: red %r no es una Plataforma soportada por Metricool; se omite.",
            pub.get("id"), red_id,
        )
        return None

    texto = (pub.get("contenido") or "").strip()
    nombre_imagen = pub.get("imagen") or ""
    media: list[MediaRef] = []

    url_img = _url_media_publica(nombre_imagen)
    if url_img:
        media.append(MediaRef(tipo=TipoMedia.imagen, url=url_img))
    elif nombre_imagen:
        # Hay imagen pero sin URL publica: loguear que se va a omitir.
        _log.warning(
            "Pieza %r: hay imagen %r pero KENI_CONSOLA_URL_PUBLICA no esta configurada; "
            "se publicara sin media. Configura la variable para incluirla.",
            pub.get("id"), nombre_imagen,
        )

    # Parsear la fecha programada como datetime (ya paso la validacion de vencimiento,
    # pero la reusamos para el campo publicar_en del borrador).
    publicar_en = _parsear_fecha(pub.get("fecha_programada") or "")

    try:
        borrador = BorradorMetricool(
            redes=[plataforma],
            texto=texto,
            media=media,
            publicar_en=publicar_en,
        )
    except ValidationError as exc:
        _log.warning(
            "Pieza %r: no se pudo construir BorradorMetricool (%s); se omite.",
            pub.get("id"), exc.errors()[0]["msg"] if exc.errors() else str(exc),
        )
        return None

    return borrador


# --------------------------------------------------------------------------- #
# Preparacion de UNA pieza (enganche del posteo real)                          #
# --------------------------------------------------------------------------- #


def _preparar(pub: dict[str, Any], ahora: datetime) -> dict[str, Any] | None:
    """Prepara UNA pieza vencida: estampa `preparado_en` y, si el gate esta activo,
    entrega el borrador a Metricool.

    Gate `KENI_PUBLICAR_REAL`:
      - OFF (default): solo estampa `preparado_en` en dry-run. La pieza SIGUE en
        `programado`. Comportamiento identico al anterior al enganche.
      - ON: construye el borrador, resuelve las creds de la marca y llama al
        adaptador con `dry_run=False`. Si Metricool acepta el post, la pieza pasa
        a `publicado` y se guarda `id_post_metricool`. Si hay cualquier error
        (creds faltantes, fallo de red, red no soportada), se loguea y la pieza
        SIGUE en `programado` con `preparado_en` estampado (no rompe el barrido).
    """
    publicar_real_flag = config.publicar_real()

    campos_base: dict[str, Any] = {"preparado_en": ahora.isoformat(timespec="seconds")}

    if not publicar_real_flag:
        # DRY-RUN: comportamiento original intacto.
        return repos.actualizar_publicacion(pub["id"], campos_base)

    # --- camino REAL: intentar entregar a Metricool ---------------------------
    pub_id = pub["id"]
    marca_id = pub.get("marca") or ""

    creds = _creds_metricool(marca_id)
    if not creds:
        _log.warning(
            "Pieza %r (marca %r): sin credenciales Metricool; se prepara en dry-run "
            "y sigue en 'programado'. Configura [metricool.marcas.%s] con "
            "user_token + user_id + blog_id.",
            pub_id, marca_id, marcas.id_metricas_de(marca_id),
        )
        return repos.actualizar_publicacion(pub_id, campos_base)

    borrador = _borrador_de_publicacion(pub)
    if borrador is None:
        # Motivo ya logueado en `_borrador_de_publicacion`.
        return repos.actualizar_publicacion(pub_id, campos_base)

    try:
        from keni_metricas.publicacion.metricool import AdaptadorPublicacionMetricool
    except ImportError:
        _log.warning("keni_metricas no disponible; publicacion real imposible.")
        return repos.actualizar_publicacion(pub_id, campos_base)

    try:
        adaptador = AdaptadorPublicacionMetricool(creds=creds)
        resultado = adaptador.programar(borrador, dry_run=False, ahora=ahora)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 -- cualquier fallo de red/auth no mata el barrido
        _log.exception(
            "Pieza %r: fallo al enviar a Metricool; se prepara en dry-run y sigue en 'programado'.",
            pub_id,
        )
        return repos.actualizar_publicacion(pub_id, campos_base)

    # Metricool acepto el post: marcar como publicado.
    id_post = resultado.id_post or ""
    estados_str = ", ".join(f"{r}={s}" for r, s in resultado.estados.items())
    _log.info(
        "Pieza %r publicada en Metricool: id_post=%r redes=[%s] estados={%s}",
        pub_id, id_post, ", ".join(resultado.redes), estados_str,
    )
    campos_publicado: dict[str, Any] = {
        **campos_base,
        "estado": "publicado",
        "id_post_metricool": id_post,
    }
    return repos.actualizar_publicacion(pub_id, campos_publicado)


def programar_pieza_metricool(
    pub: dict[str, Any], *, ahora: datetime | None = None
) -> dict[str, Any]:
    """Programa UNA pieza en Metricool a demanda (botón de la UI). Reusa los helpers.

    Respeta el MISMO gate que el barrido (`KENI_PUBLICAR_REAL`):
      - OFF (default): DRY-RUN. NO toca la red ni persiste: devuelve el cuerpo
        EXACTO que se enviaria, para previsualizar. (`dry_run: true`.)
      - ON: envia de verdad; si Metricool acepta, persiste `id_post_metricool` y
        pasa la pieza a `publicado`. (`dry_run: false`.)

    Degradacion honesta (nunca lanza): si faltan credenciales de la marca, no se
    puede construir el borrador o falla la red, devuelve `ok: false` + `motivo`.
    Forma del resultado:
        {ok, dry_run, motivo?, redes, cuerpo?, id_post?, estados?}
    """
    ahora = _a_utc(ahora) if ahora is not None else datetime.now(UTC)
    dry_run = not config.publicar_real()
    marca_id = pub.get("marca") or ""

    # GUARDA DE RE-PUBLICACION (solo camino REAL): el barrido automatico evita el doble envio
    # via `preparado_en` (claim atomico), pero el boton manual no pasaba por ahi. Si la pieza
    # YA fue publicada (tiene `id_post_metricool` o estado `publicado`), no la re-enviamos a
    # Metricool. En dry-run NO bloqueamos: previsualizar el cuerpo de una pieza ya publicada
    # es inofensivo y util.
    if not dry_run and (pub.get("id_post_metricool") or pub.get("estado") == "publicado"):
        return {
            "ok": False,
            "dry_run": dry_run,
            "motivo": "Esta pieza ya fue publicada en Metricool; no se vuelve a publicar.",
        }

    creds = _creds_metricool(marca_id)
    if not creds:
        return {
            "ok": False,
            "dry_run": dry_run,
            "motivo": (
                f"La marca {marca_id!r} no tiene credenciales de Metricool configuradas "
                f"([metricool.marcas.{marcas.id_metricas_de(marca_id)}])."
            ),
        }

    borrador = _borrador_de_publicacion(pub)
    if borrador is None:
        return {
            "ok": False,
            "dry_run": dry_run,
            "motivo": "No se pudo construir el borrador (¿sin contenido o red no soportada?).",
        }

    try:
        from keni_metricas.publicacion.metricool import AdaptadorPublicacionMetricool
    except ImportError:
        return {"ok": False, "dry_run": dry_run, "motivo": "keni_metricas no está disponible."}

    try:
        adaptador = AdaptadorPublicacionMetricool(creds=creds)
        resultado = adaptador.programar(borrador, dry_run=dry_run, ahora=ahora)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001 -- degrada con mensaje, no rompe el endpoint
        _log.exception("Pieza %r: fallo al programar en Metricool a demanda.", pub.get("id"))
        return {"ok": False, "dry_run": dry_run, "motivo": f"Fallo al contactar Metricool: {e}"}

    base = {
        "ok": True,
        "dry_run": resultado.dry_run,
        "redes": list(resultado.redes),
        "cuerpo": resultado.peticion.body,
    }
    if resultado.dry_run:
        # Preview: NO se persiste nada (no se publicó).
        return base

    # Camino REAL: Metricool aceptó el post -> persistir y marcar publicado.
    id_post = resultado.id_post or ""
    repos.actualizar_publicacion(
        pub["id"],
        {
            "preparado_en": ahora.isoformat(timespec="seconds"),
            "estado": "publicado",
            "id_post_metricool": id_post,
        },
    )
    return {**base, "id_post": id_post, "estados": dict(resultado.estados)}


def preparar_vencidas(ahora: datetime | None = None) -> int:
    """Prepara (dry-run o real) todas las piezas programadas ya vencidas. Devuelve cuantas preparo.

    Es lo que corre cada barrido del hilo y tambien se puede llamar a mano (test/CLI).
    Lee SOLO las piezas en estado `programado` (filtro en el indice), no todo el catalogo.
    """
    ahora = _a_utc(ahora) if ahora is not None else datetime.now(UTC)
    ts = ahora.isoformat(timespec="seconds")
    programadas = repos.listar_publicaciones(estado=ESTADO_PROGRAMADO)
    preparadas = 0
    for pub in piezas_vencidas(programadas, ahora):
        # CLAIM ATOMICO antes de publicar: estampa `preparado_en` solo si nadie lo hizo ya
        # (UPDATE condicional, ver `repos.reclamar_preparacion`). Sustituye el patron previo
        # SELECT(`piezas_vencidas`)->UPDATE, que con >1 replica/barrido en paralelo podia
        # preparar/publicar DOS veces la misma pieza. Solo el barrido que GANA el claim
        # procede a `_preparar` (publicar real). Los demas la ven ya reclamada y la saltan.
        if not repos.reclamar_preparacion(pub["id"], ts):
            continue
        if _preparar(pub, ahora) is not None:
            preparadas += 1
    return preparadas


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (configurable por entorno; util en demo/tests)."""
    seg = config.programador_intervalo_segundos()
    if seg is not None:
        return seg
    return INTERVALO_SEGUNDOS_DEF


def iniciar_programador(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca un hilo demonio que prepara las piezas vencidas en bucle.

    Pensado para el servidor real (`__main__`), NO para `crear_app`: los tests crean la
    app sin arrancar esto. El hilo es daemon: muere al cerrar el proceso. Prepara una vez
    al arrancar y luego cada `intervalo`. Un fallo de un barrido se loguea y NO mata el
    hilo (el siguiente barrido reintenta).
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        while True:
            try:
                n = preparar_vencidas()
                if n:
                    _log.info(
                        "Programador: %d pieza(s) preparada(s) (KENI_PUBLICAR_REAL=%s).",
                        n, config.publicar_real(),
                    )
            except Exception:  # noqa: BLE001 -- un fallo de barrido no debe matar el hilo
                _log.exception("Fallo en el barrido del programador.")
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="programador-publicaciones", daemon=True)
    hilo.start()
    modo = "REAL (Metricool)" if config.publicar_real() else "DRY-RUN (sin publicar)"
    _log.info(
        "Programador de publicaciones activo cada %.0f s (modo: %s).",
        intervalo, modo,
    )
    return hilo
