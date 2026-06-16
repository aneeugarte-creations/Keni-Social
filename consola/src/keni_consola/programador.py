"""Programador de piezas (#9, Fase 3): prepara/publica las piezas vencidas.

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

FLOW: fila pieza -> BorradorMetricool -> AdaptadorPublicacionMetricool -> Metricool
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

import httpx

from . import config, marcas, repos
from .estados import ESTADO_PROGRAMADO
from .tiempo import iso_utc

_log = logging.getLogger("keni_consola.programador")

# Marcador de `id_post_metricool` cuando el POST de pieza se va por TIMEOUT.
# Un ReadTimeout salta DESPUES de enviar la peticion entera (body incluido): Metricool
# casi seguro recibio el post, pero la respuesta con el id real no llego. En ese caso
# marcamos la pieza `publicado` con ESTE marcador en vez de reintentar: reenviar a ciegas
# es lo que provoca el DOBLE-POST (el barrido y el boton reusan esta misma logica). No es
# un id real (no enlaza metricas); es deliberadamente legible para auditar y reconciliar.
ID_POST_INCIERTO = "incierto-timeout"

# Cadencia por defecto del barrido del programador (segundos). Un minuto basta: la
# granularidad de las fechas programadas es el minuto.
INTERVALO_SEGUNDOS_DEF = 60.0

# Canal de publicación POSTPROXY (el alternativo a Metricool). El default es Metricool
# (cero cambio de comportamiento): solo se desvía al camino Postproxy una marca que lo
# elija explícitamente en `[postproxy.marcas.<id>].canal`. Valor espejo de
# `keni_metricas.config.CANAL_POSTPROXY` (se duplica para NO importar keni_metricas a
# nivel de módulo: todo el acceso a keni_metricas es perezoso aquí, ver imports abajo).
_CANAL_POSTPROXY = "postproxy"

# Plataforma keni (`pub["red"]`) -> nombre de plataforma en Postproxy. Idéntico salvo X,
# que en Postproxy se llama "twitter" (igual que en Metricool). Las demás coinciden. Se
# usa como destino en `profiles` cuando no se resuelve un profile_id concreto.
_RED_POSTPROXY: dict[str, str] = {
    "facebook": "facebook",
    "instagram": "instagram",
    "x": "twitter",
    "tiktok": "tiktok",
    "youtube": "youtube",
}


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
# Resolucion de credenciales/perfiles Postproxy por marca (canal alternativo)  #
# --------------------------------------------------------------------------- #


def _creds_postproxy(marca_id: str) -> tuple[str | None, str | None]:
    """`(api_key, profile_group_id)` de la marca para Postproxy, o `(None, None)`.

    api_key es GLOBAL (`[postproxy] api_key`); el grupo es por marca
    (`[postproxy.marcas.<id_metricas>] profile_group_id`). Devuelve None en cualquier
    pieza que falte para que el llamante DEGRADE igual que con creds Metricool ausentes.
    """
    try:
        from keni_metricas.config import cargar_config
    except ImportError:
        _log.warning("keni_metricas no disponible; no se puede resolver creds Postproxy.")
        return None, None

    id_mc = marcas.id_metricas_de(marca_id)  # slug-guion -> guion_bajo
    try:
        cfg = cargar_config()
    except Exception:  # noqa: BLE001 -- config rota no debe romper el barrido
        _log.exception("Error cargando config de Postproxy para marca %r.", marca_id)
        return None, None

    pp = cfg.postproxy
    api_key = pp.api_key or None
    group_id = pp.grupo_de(pp.marcas.get(id_mc) or {}) or None
    return api_key, group_id


def _red_postproxy(pub: dict[str, Any]) -> str:
    """Nombre de plataforma Postproxy de la pieza (x->twitter); cae al id crudo si no mapea."""
    red = pub.get("red") or ""
    return _RED_POSTPROXY.get(red, red)


def _profiles_postproxy(pub: dict[str, Any], api_key: str, group_id: str) -> list[str]:
    """Destinos `profiles` para Postproxy: profile_id resuelto o, si no, nombre de plataforma.

    Best-effort: intenta resolver el profile_id REAL de la plataforma de la pieza vía
    `listar_perfiles(api_key, group_id)` (Postproxy acepta ids o plataformas en `profiles`).
    Si la consulta falla o no hay match, cae al NOMBRE de plataforma (camino siempre válido).
    Nunca lanza: ante cualquier fallo, fallback al nombre de plataforma.
    """
    plataforma = _red_postproxy(pub)
    try:
        from keni_metricas.fuentes.postproxy import listar_perfiles

        ok, _msg, perfiles = listar_perfiles(api_key, group_id)
        if ok:
            for p in perfiles:
                if p.get("platform") == plataforma and p.get("id"):
                    return [str(p["id"])]
    except Exception:  # noqa: BLE001 -- resolver el id es best-effort; fallback a plataforma
        _log.debug("Pieza %r: no se pudo resolver el profile_id Postproxy; uso plataforma %r.",
                   pub.get("id"), plataforma)
    return [plataforma]


# --------------------------------------------------------------------------- #
# Construccion del BorradorMetricool desde la fila de pieza              #
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


def slides_de_carrusel(crudo: object) -> list[dict[str, str]]:
    """Parsea el campo `carrusel` (JSON) a una lista reparada de slides (PURA, testeable).

    Forma de entrada: `[{"tipo":"imagen"|"video","objeto":"<media id>"}, …]`. Devuelve solo
    los elementos bien formados, preservando el orden; tipo desconocido/vacío cae a "imagen"
    (el caso abrumadoramente común). Entrada ilegible -> lista vacía (degrada sin romper).
    """
    import json

    try:
        datos = json.loads(crudo) if isinstance(crudo, str) and crudo.strip() else []
    except ValueError:
        return []
    if not isinstance(datos, list):
        return []
    slides: list[dict[str, str]] = []
    for el in datos:
        if not isinstance(el, dict):
            continue
        objeto = str(el.get("objeto") or "").strip()
        if not objeto:
            continue
        tipo = str(el.get("tipo") or "").strip().lower()
        slides.append({"tipo": tipo if tipo == "video" else "imagen", "objeto": objeto})
    return slides


def _slides_carrusel(pub: dict[str, Any], media_ref: Any, tipo_media: Any) -> list[Any]:
    """MediaRefs de los slides extra de un carrusel (tras la portada), en orden.

    Slides sin URL pública (falta `KENI_CONSOLA_URL_PUBLICA`) se omiten con warning.
    """
    refs: list[Any] = []
    for slide in slides_de_carrusel(pub.get("carrusel")):
        url = _url_media_publica(slide["objeto"])
        if not url:
            _log.warning(
                "Pieza %r (carrusel): slide %r sin URL publica; se omite del post.",
                pub.get("id"), slide["objeto"],
            )
            continue
        tipo = tipo_media.video if slide["tipo"] == "video" else tipo_media.imagen
        refs.append(media_ref(tipo=tipo, url=url))
    return refs


def _borrador_de_publicacion(pub: dict[str, Any]) -> object | None:
    """Construye un `BorradorMetricool` desde la fila de pieza, o None si no aplica.

    Devuelve None (sin lanzar) si:
      - La red no es soportada por Metricool (no esta en Plataforma).
      - La red exige media (instagram/tiktok/youtube) y no hay imagen con URL publica.
      - El contenido (texto) esta vacio Y no hay media: nada que publicar.
    Todos los casos se loguean a nivel WARNING para que sean trazables.
    """
    try:
        from keni_metricas.pieza.metricool import BorradorMetricool
        from keni_metricas.pieza.modelos import MediaRef, TipoMedia
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

    # VIDEO (pieza `formato='video'`): se publica el asset de video en vez de la imagen. La capa
    # Metricool ya distingue foto/video (`TipoMedia.video`). Si no hay asset de video, NO se
    # publica esta red (queda pendiente; el barrido la reintentará cuando se adjunte) — sin romper.
    from . import redes

    if redes.normalizar_formato(pub.get("formato")) == redes.FORMATO_VIDEO:
        nombre_video = (pub.get("video") or "").strip()
        if not nombre_video:
            _log.warning(
                "Pieza %r (video): no hay asset de video; se omite la publicación (pendiente).",
                pub.get("id"),
            )
            return None
        url_video = _url_media_publica(nombre_video)
        if not url_video:
            _log.warning(
                "Pieza %r (video): hay asset %r pero KENI_CONSOLA_URL_PUBLICA no está "
                "configurada; no se puede publicar. Configura la variable.",
                pub.get("id"), nombre_video,
            )
            return None
        media_video: list[MediaRef] = [
            MediaRef(tipo=TipoMedia.video, url=url_video)
        ]
        publicar_en = _parsear_fecha(pub.get("fecha_programada") or "")
        try:
            return BorradorMetricool(
                redes=[plataforma],
                texto=texto,
                media=media_video,
                publicar_en=publicar_en,
            )
        except ValidationError as exc:
            _log.warning(
                "Pieza %r (video): no se pudo construir BorradorMetricool (%s); se omite.",
                pub.get("id"), exc.errors()[0]["msg"] if exc.errors() else str(exc),
            )
            return None

    # Imagen publicable (formatos FOTO y CARRUSEL): si está horneada (`imagen`) se usa; si no,
    # se RENDERIZA on-demand desde la receta (placa de marca / plantilla del estudio) y se
    # MATERIALIZA en este momento (content-addressed, una sola vez) para que Metricool la
    # ingiera por una URL estable `/api/media/{id}`. Tolerante: si el render falla, se publica
    # sin media (warning), igual que cuando no hay imagen. En CARRUSEL esa imagen compuesta es
    # la PORTADA (slide 1) y detrás van EN CRUDO los slides extra del campo `carrusel`.
    from . import repos
    from .dominio import estudio_imagen, render_pieza

    imagen_previa = (pub.get("imagen") or "").strip()
    try:
        nombre_imagen = render_pieza.imagen_compuesta_id(pub)
    except estudio_imagen.EstudioError as exc:
        _log.warning(
            "Pieza %r: no se pudo componer la imagen para publicar (%s); se publica sin media.",
            pub.get("id"), exc,
        )
        nombre_imagen = ""
    # CONGELAR el registro de lo publicado: si la imagen se DERIVÓ de la receta (no estaba
    # horneada), la materializamos y la REFERENCIAMOS en la pieza (`imagen`). Así el composite
    # publicado es un asset VIVO (no uno suelto) y la pieza queda con el PNG exacto que se posteó
    # —no un re-render que podría diferir si luego se edita la receta—.
    if nombre_imagen and nombre_imagen != imagen_previa and render_pieza.tiene_receta(pub):
        try:
            repos.actualizar_pieza(pub["id"], {"imagen": nombre_imagen})
        except Exception:  # noqa: BLE001 -- referenciar es best-effort; no debe abortar el posteo
            _log.warning("Pieza %r: no se pudo fijar la imagen publicada.", pub.get("id"))
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

    # CARRUSEL: detrás de la portada van los slides EXTRA en crudo (campo `carrusel`,
    # JSON `[{tipo:"imagen"|"video",objeto}, …]` en orden de publicación). El cuerpo de
    # Metricool ya admite varias URLs en `media[]` (un solo post multi-media). Slides
    # ilegibles o sin URL pública se OMITEN con warning (no rompen el posteo del resto).
    if redes.normalizar_formato(pub.get("formato")) == redes.FORMATO_CARRUSEL:
        media.extend(_slides_carrusel(pub, MediaRef, TipoMedia))

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


def _preparar_postproxy(
    pub: dict[str, Any], ahora: datetime, campos_base: dict[str, Any], marca_id: str
) -> dict[str, Any] | None:
    """Camino REAL del barrido para una marca con canal=postproxy. Análogo a Metricool.

    Misma postura de degradación honesta y mismo manejo de timeout/fallo que el camino
    Metricool de `_preparar`: si faltan credenciales (api_key global o grupo de la marca)
    o el borrador es inviable, la pieza se prepara en dry-run y SIGUE en `programado`; un
    TIMEOUT marca `publicado` (incierto) para no duplicar; un fallo de entrega claro LIBERA
    `preparado_en` para reintentar. El id del post de Postproxy se guarda en la columna
    EXISTENTE `id_post_metricool` (reusada como "id de post externo"; NO se cambia el
    esquema: con canal=postproxy esa columna contiene el id de Postproxy).
    """
    pub_id = pub["id"]

    api_key, group_id = _creds_postproxy(marca_id)
    if not api_key or not group_id:
        _log.warning(
            "Pieza %r (marca %r): sin credenciales Postproxy (api_key global y/o "
            "profile_group_id); se prepara en dry-run y sigue en 'programado'. Configura "
            "[postproxy] api_key y [postproxy.marcas.%s] profile_group_id.",
            pub_id, marca_id, marcas.id_metricas_de(marca_id),
        )
        return repos.actualizar_pieza(pub_id, campos_base)

    # Reusa la MISMA construcción de borrador que Metricool (texto+hashtags, media,
    # video/carrusel, publicar_en). El adaptador Postproxy lee de él lo que necesita.
    borrador = _borrador_de_publicacion(pub)
    if borrador is None:
        return repos.actualizar_pieza(pub_id, campos_base)

    try:
        from keni_metricas.pieza.postproxy import AdaptadorPublicacionPostproxy
    except ImportError:
        _log.warning("keni_metricas no disponible; pieza real imposible.")
        return repos.actualizar_pieza(pub_id, campos_base)

    profiles = _profiles_postproxy(pub, api_key, group_id)
    try:
        adaptador = AdaptadorPublicacionPostproxy(api_key=api_key)
        resultado = adaptador.programar(borrador, dry_run=False, profiles=profiles)
    except httpx.TimeoutException:
        _log.warning(
            "Pieza %r: TIMEOUT al enviar a Postproxy; el post pudo entregarse. Se marca "
            "'publicado' (incierto) para NO reenviar y evitar doble-post. Verificar en redes.",
            pub_id,
        )
        return repos.actualizar_pieza(
            pub_id,
            {**campos_base, "estado": "publicado", "id_post_metricool": ID_POST_INCIERTO},
        )
    except Exception:  # noqa: BLE001 -- cualquier fallo de red/auth no mata el barrido
        _log.exception(
            "Pieza %r: fallo al enviar a Postproxy; se libera la preparacion y se "
            "reintentara en el proximo barrido.",
            pub_id,
        )
        try:
            repos.actualizar_pieza(pub_id, {"preparado_en": ""})
        except Exception:  # noqa: BLE001 -- si ni esto entra, el log ya dejo rastro
            _log.exception("Pieza %r: no se pudo liberar la preparacion.", pub_id)
        return None

    id_post = resultado.id_post or ""
    estados_str = ", ".join(f"{r}={s}" for r, s in resultado.estados.items())
    _log.info(
        "Pieza %r publicada en Postproxy: id_post=%r redes=[%s] estados={%s}",
        pub_id, id_post, ", ".join(resultado.redes), estados_str,
    )
    return repos.actualizar_pieza(
        pub_id,
        {**campos_base, "estado": "publicado", "id_post_metricool": id_post},
    )


def _preparar(pub: dict[str, Any], ahora: datetime) -> dict[str, Any] | None:
    """Prepara UNA pieza vencida: estampa `preparado_en` y, si el gate esta activo,
    entrega el borrador a Metricool.

    Gate `KENI_PUBLICAR_REAL`:
      - OFF (default): solo estampa `preparado_en` en dry-run. La pieza SIGUE en
        `programado`. Comportamiento identico al anterior al enganche.
      - ON: construye el borrador, resuelve las creds de la marca y llama al
        adaptador con `dry_run=False`. Si Metricool acepta el post, la pieza pasa
        a `publicado` y se guarda `id_post_metricool`. Errores de CONFIGURACION
        (creds faltantes, red no soportada, borrador inviable) se loguean y la pieza
        SIGUE en `programado` con `preparado_en` estampado (no rompe el barrido;
        reintentar cada minuto no arregla una config rota). Un fallo de ENTREGA
        (excepcion de red/auth contra Metricool) LIMPIA `preparado_en` para que el
        siguiente barrido la reintente: antes quedaba estampada y `piezas_vencidas`
        la excluia PARA SIEMPRE (pieza programada que nunca salia, en silencio).
    """
    # Gate maestro + excepción por marca: el maestro global debe estar ON y la marca NO excluida.
    marca_id = pub.get("marca") or ""
    publicar_real_flag = config.publicar_real_para(marca_id)

    # Canon UTC sin offset (ver `tiempo.py`): antes `ahora.isoformat()` de un datetime aware
    # estampaba "+00:00", que rompia el orden lexicografico contra los timestamps naive.
    campos_base: dict[str, Any] = {"preparado_en": iso_utc(ahora)}

    if not publicar_real_flag:
        # DRY-RUN (maestro OFF o marca excluida): comportamiento original intacto.
        return repos.actualizar_pieza(pub["id"], campos_base)

    # --- camino REAL: DESPACHO por canal de publicación de la marca ----------
    # Default "metricool" (cero regresión): solo una marca con canal=postproxy se desvía.
    if config.canal_publicacion_para(marca_id) == _CANAL_POSTPROXY:
        return _preparar_postproxy(pub, ahora, campos_base, marca_id)

    # --- camino REAL Metricool (comportamiento histórico, INTACTO) ------------
    pub_id = pub["id"]

    creds = _creds_metricool(marca_id)
    if not creds:
        _log.warning(
            "Pieza %r (marca %r): sin credenciales Metricool; se prepara en dry-run "
            "y sigue en 'programado'. Configura [metricool.marcas.%s] con "
            "user_token + user_id + blog_id.",
            pub_id, marca_id, marcas.id_metricas_de(marca_id),
        )
        return repos.actualizar_pieza(pub_id, campos_base)

    borrador = _borrador_de_publicacion(pub)
    if borrador is None:
        # Motivo ya logueado en `_borrador_de_publicacion`.
        return repos.actualizar_pieza(pub_id, campos_base)

    try:
        from keni_metricas.pieza.metricool import AdaptadorPublicacionMetricool
    except ImportError:
        _log.warning("keni_metricas no disponible; pieza real imposible.")
        return repos.actualizar_pieza(pub_id, campos_base)

    try:
        adaptador = AdaptadorPublicacionMetricool(creds=creds)
        resultado = adaptador.programar(borrador, dry_run=False, ahora=ahora)  # type: ignore[arg-type]
    except httpx.TimeoutException:
        # TIMEOUT != fallo de entrega. La peticion (con su body) ya viajo entera; el post
        # casi seguro se ENTREGO en Metricool, solo no llego la respuesta. NO liberamos el
        # claim: hacerlo haria que el siguiente barrido REENVIE y duplique el post. Marcamos
        # `publicado` con id incierto (queda fuera de `piezas_vencidas` y nadie reintenta).
        # El humano verifica en redes; si no salio, re-publica a mano.
        _log.warning(
            "Pieza %r: TIMEOUT al enviar a Metricool; el post pudo entregarse. Se marca "
            "'publicado' (incierto) para NO reenviar y evitar doble-post. Verificar en redes.",
            pub_id,
        )
        return repos.actualizar_pieza(
            pub_id,
            {**campos_base, "estado": "publicado", "id_post_metricool": ID_POST_INCIERTO},
        )
    except Exception:  # noqa: BLE001 -- cualquier fallo de red/auth no mata el barrido
        # FALLO DE ENTREGA CLARO (no-timeout: red caida antes de enviar, 5xx, auth rota):
        # LIBERAR el claim limpiando `preparado_en`, para que el siguiente barrido (cada
        # ~60 s) la vuelva a intentar. Si quedara estampado, `piezas_vencidas` la excluiria
        # PARA SIEMPRE y la pieza moriria en `programado` sin publicarse ni avisar. El error
        # queda en el log de cada intento (visible); no se cuenta como preparada (return None).
        _log.exception(
            "Pieza %r: fallo al enviar a Metricool; se libera la preparacion y se "
            "reintentara en el proximo barrido.",
            pub_id,
        )
        try:
            repos.actualizar_pieza(pub_id, {"preparado_en": ""})
        except Exception:  # noqa: BLE001 -- si ni esto entra, el log ya dejo rastro
            _log.exception("Pieza %r: no se pudo liberar la preparacion.", pub_id)
        return None

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
    return repos.actualizar_pieza(pub_id, campos_publicado)


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
    marca_id = pub.get("marca") or ""
    # Mismo gate que el barrido: maestro global + excepción por marca (marca excluida -> dry-run).
    dry_run = not config.publicar_real_para(marca_id)

    # GUARDA DE RE-PIEZA (solo camino REAL): el barrido automatico evita el doble envio
    # via `preparado_en` (claim atomico), pero el boton manual no pasaba por ahi. Si la pieza
    # YA fue publicada (tiene `id_post_metricool` o estado `publicado`), no la re-enviamos a
    # Metricool. En dry-run NO bloqueamos: previsualizar el cuerpo de una pieza ya publicada
    # es inofensivo y util.
    if not dry_run and (pub.get("id_post_metricool") or pub.get("estado") == "publicado"):
        return {
            "ok": False,
            "dry_run": dry_run,
            "motivo": "Esta pieza ya fue publicada; no se vuelve a publicar.",
        }

    # DESPACHO por canal de la marca: default "metricool" (intacto). Solo una marca con
    # canal=postproxy se desvía al adaptador alternativo (misma forma de resultado).
    if config.canal_publicacion_para(marca_id) == _CANAL_POSTPROXY:
        return _programar_pieza_postproxy(pub, ahora, dry_run)

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

    # El botón manual es "publicar AHORA", no "agendar": fuerza la salida inmediata
    # ignorando la `fecha_programada` (que `_borrador_de_publicacion` había copiado a
    # `publicar_en`). Sin esto, una pieza programada al futuro se enviaba al scheduler de
    # Metricool con su hora futura + autoPublish y la consola la marcaba `publicado` antes
    # de que saliera de verdad: aparecía "publicada en el futuro". Con `publicar_en=ahora`,
    # Metricool publica ya y persistimos abajo `fecha_programada=ahora` (la hora real).
    borrador = borrador.model_copy(update={"publicar_en": ahora})

    try:
        from keni_metricas.pieza.metricool import AdaptadorPublicacionMetricool
    except ImportError:
        return {"ok": False, "dry_run": dry_run, "motivo": "keni_metricas no está disponible."}

    try:
        adaptador = AdaptadorPublicacionMetricool(creds=creds)
        resultado = adaptador.programar(borrador, dry_run=dry_run, ahora=ahora)  # type: ignore[arg-type]
    except httpx.TimeoutException:
        # TIMEOUT (solo camino real; el dry-run no toca red): el post casi seguro se
        # ENTREGO (la peticion viajo entera) pero no llego la respuesta. Marcamos
        # `publicado` con id incierto para NO permitir un re-click que duplique el post,
        # y avisamos al humano (`incierto`) para que verifique en redes. Mismo criterio
        # que el barrido automatico (ver `_preparar`).
        _log.warning(
            "Pieza %r: TIMEOUT al publicar en Metricool a demanda; se marca 'publicado' "
            "(incierto) para no duplicar. Verificar en redes.",
            pub.get("id"),
        )
        repos.actualizar_pieza(
            pub["id"],
            {
                "preparado_en": iso_utc(ahora),
                "estado": "publicado",
                # Hora real de publicación (ver nota al construir el borrador): salió ahora,
                # no a su `fecha_programada` original; reflejarlo para no mostrar futuro.
                "fecha_programada": iso_utc(ahora),
                "id_post_metricool": ID_POST_INCIERTO,
            },
        )
        return {
            "ok": True,
            "dry_run": False,
            "incierto": True,
            "motivo": (
                "La publicación se envió pero Metricool no respondió a tiempo (timeout). "
                "Se marcó como publicada para no duplicarla; verifica en redes que haya salido."
            ),
        }
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
    repos.actualizar_pieza(
        pub["id"],
        {
            # Canon UTC sin offset (ver `tiempo.py`): `ahora` es aware; isoformat directo
            # estamparia "+00:00" y romperia el orden lexicografico del TEXT.
            "preparado_en": iso_utc(ahora),
            "estado": "publicado",
            # Hora real de publicación (ver nota al construir el borrador): el botón publica
            # ahora, así que `fecha_programada` deja de ser la hora futura agendada.
            "fecha_programada": iso_utc(ahora),
            "id_post_metricool": id_post,
        },
    )
    return {**base, "id_post": id_post, "estados": dict(resultado.estados)}


def _programar_pieza_postproxy(
    pub: dict[str, Any], ahora: datetime, dry_run: bool
) -> dict[str, Any]:
    """Botón manual para una marca con canal=postproxy. Análogo a la rama Metricool.

    MISMA forma de resultado (`{ok, dry_run, motivo?, redes, cuerpo?, id_post?, estados?}`)
    y mismo trato de timeout/fallo. En dry-run NO toca red: usa el nombre de plataforma
    como destino para previsualizar el cuerpo exacto que se enviaría. En real resuelve el
    profile_id (best-effort) y persiste el id de Postproxy en `id_post_metricool`.
    """
    marca_id = pub.get("marca") or ""

    api_key, group_id = _creds_postproxy(marca_id)
    if not api_key or not group_id:
        return {
            "ok": False,
            "dry_run": dry_run,
            "motivo": (
                f"La marca {marca_id!r} no tiene Postproxy configurado (api_key global y "
                f"profile_group_id en [postproxy.marcas.{marcas.id_metricas_de(marca_id)}])."
            ),
        }

    borrador = _borrador_de_publicacion(pub)
    if borrador is None:
        return {
            "ok": False,
            "dry_run": dry_run,
            "motivo": "No se pudo construir el borrador (¿sin contenido o red no soportada?).",
        }

    # Botón = "publicar AHORA": fuerza la salida inmediata (mismo criterio que Metricool).
    borrador = borrador.model_copy(update={"publicar_en": ahora})

    try:
        from keni_metricas.pieza.postproxy import AdaptadorPublicacionPostproxy
    except ImportError:
        return {"ok": False, "dry_run": dry_run, "motivo": "keni_metricas no está disponible."}

    # En dry-run NO tocamos la red ni para resolver profile_ids: el nombre de plataforma
    # basta para previsualizar el cuerpo. En real, resolvemos el profile_id (best-effort).
    profiles = [_red_postproxy(pub)] if dry_run else _profiles_postproxy(pub, api_key, group_id)

    try:
        adaptador = AdaptadorPublicacionPostproxy(api_key=api_key)
        resultado = adaptador.programar(borrador, dry_run=dry_run, profiles=profiles)
    except httpx.TimeoutException:
        _log.warning(
            "Pieza %r: TIMEOUT al publicar en Postproxy a demanda; se marca 'publicado' "
            "(incierto) para no duplicar. Verificar en redes.",
            pub.get("id"),
        )
        repos.actualizar_pieza(
            pub["id"],
            {
                "preparado_en": iso_utc(ahora),
                "estado": "publicado",
                "fecha_programada": iso_utc(ahora),
                "id_post_metricool": ID_POST_INCIERTO,
            },
        )
        return {
            "ok": True,
            "dry_run": False,
            "incierto": True,
            "motivo": (
                "La publicación se envió pero Postproxy no respondió a tiempo (timeout). "
                "Se marcó como publicada para no duplicarla; verifica en redes que haya salido."
            ),
        }
    except Exception as e:  # noqa: BLE001 -- degrada con mensaje, no rompe el endpoint
        _log.exception("Pieza %r: fallo al programar en Postproxy a demanda.", pub.get("id"))
        return {"ok": False, "dry_run": dry_run, "motivo": f"Fallo al contactar Postproxy: {e}"}

    base = {
        "ok": True,
        "dry_run": resultado.dry_run,
        "redes": list(resultado.redes),
        "cuerpo": resultado.peticion.body,
    }
    if resultado.dry_run:
        return base  # Preview: NO se persiste nada.

    id_post = resultado.id_post or ""
    repos.actualizar_pieza(
        pub["id"],
        {
            "preparado_en": iso_utc(ahora),
            "estado": "publicado",
            "fecha_programada": iso_utc(ahora),
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
    # Canon UTC sin offset (ver `tiempo.py`): el claim `preparado_en` se compara como TEXT.
    ts = iso_utc(ahora)
    programadas = repos.listar_piezas(estado=ESTADO_PROGRAMADO)
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
        from . import latidos  # import tardio: solo lo paga el hilo del servidor real

        while True:
            t0 = time.monotonic()
            try:
                # RECUPERACIÓN de piezas con sus 2 likes sin hueco: la auto-programación síncrona
                # (al juntar el segundo like) se queda sin efecto si EN ESE MOMENTO no había franja
                # aplicable (p. ej. se configuró después). Sin este barrido no habría reintento: la
                # pieza se quedaría `en_revision` para siempre. Best-effort e idempotente (solo toca
                # piezas `en_revision` con sus likes que pasan los mismos gates que el encolado
                # manual); gateado por `KENI_AUTO_PROGRAMAR` dentro de `barrer_aprobadas`.
                # EVERGREEN DIARIO: si a una marca con línea evergreen le falta el green de hoy,
                # reemite uno aleatorio del banco (programado/publicado) y lo encola EN EL ACTO a su
                # hueco de las 8:00 (la reemisión se auto-programa sola, no depende del barrido).
                try:
                    from . import idear_diario

                    idear_diario.barrer()
                except Exception:  # noqa: BLE001 -- el evergreen nunca rompe el barrido principal
                    _log.exception("Fallo el barrido del evergreen diario.")
                try:
                    from . import auto_programar

                    auto_programar.barrer_aprobadas()
                except Exception:  # noqa: BLE001 -- la recuperación nunca rompe el barrido principal
                    _log.exception("Fallo el barrido de piezas aprobadas sin programar.")
                n = preparar_vencidas()
                if n:
                    _log.info(
                        "Programador: %d pieza(s) preparada(s) (KENI_PUBLICAR_REAL=%s).",
                        n, config.publicar_real(),
                    )
                modo = "real" if config.publicar_real() else "dry-run"
                resumen = f"{n} pieza(s) preparada(s) ({modo})" if n else "sin novedad"
                latidos.barrido(
                    "programador", ok=True, intervalo_seg=intervalo, tick_seg=intervalo,
                    duracion_ms=int((time.monotonic() - t0) * 1000), resumen=resumen,
                )
            except Exception as e:  # noqa: BLE001 -- un fallo de barrido no debe matar el hilo
                _log.exception("Fallo en el barrido del programador.")
                latidos.barrido(
                    "programador", ok=False, intervalo_seg=intervalo, tick_seg=intervalo,
                    duracion_ms=int((time.monotonic() - t0) * 1000), error=repr(e),
                )
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="programador-piezas", daemon=True)
    hilo.start()
    modo = "REAL (Metricool)" if config.publicar_real() else "DRY-RUN (sin publicar)"
    _log.info(
        "Programador de piezas activo cada %.0f s (modo: %s).",
        intervalo, modo,
    )
    return hilo
