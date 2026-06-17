"""Publicacion a demanda de UNA pieza en Metricool/Postproxy (boton manual de la UI).

Una pieza APROBADA aterriza en el feed para su aprobacion final; desde ahi el humano
la publica en redes con el boton "publicar", que llama a `programar_pieza_metricool`.
Este modulo arma el borrador desde la fila de pieza y lo entrega al adaptador de la
marca (Metricool por defecto; Postproxy si la marca lo elige en `[postproxy.marcas.<id>]`).

GATING (frontera del producto, CRITICO):
  - `KENI_PUBLICAR_REAL` (por marca, `config.publicar_real_para`) decide si el boton
    publica de verdad o solo PREVISUALIZA el cuerpo que se enviaria (`dry_run`).
  - "El humano aprueba; el sistema no publica solo": no hay despacho automatico; la
    salida a redes la dispara una persona desde el feed.

FLOW: fila pieza -> BorradorMetricool -> AdaptadorPublicacion(Metricool|Postproxy) -> red
  1. `pub["red"]` (id canonico, p.ej. "x") -> `Plataforma` de keni_metricas.
  2. `pub["marca"]` (slug-guion, p.ej. "claro-sports") ->
     `marcas.id_metricas_de(...)` (guion_bajo, p.ej. "claro_sports") ->
     credenciales de MetricoolConfig.marcas_configuradas()[id_metricas].
  3. `pub["imagen"]` (nombre de archivo) + `KENI_CONSOLA_URL_PUBLICA` ->
     URL absoluta publica que Metricool puede ingerir. Sin URL publica, se omite
     la media y se loguea (el post va solo con texto, si la red lo permite).
  4. `pub["contenido"]` -> `BorradorMetricool.texto`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from . import config, marcas, repos
from .tiempo import iso_utc

_log = logging.getLogger("keni_consola.programador")

# Marcador de `id_post_metricool` cuando el POST de pieza se va por TIMEOUT.
# Un ReadTimeout salta DESPUES de enviar la peticion entera (body incluido): Metricool
# casi seguro recibio el post, pero la respuesta con el id real no llego. En ese caso
# marcamos la pieza `publicado` con ESTE marcador en vez de reintentar: reenviar a ciegas
# es lo que provoca el DOBLE-POST (el barrido y el boton reusan esta misma logica). No es
# un id real (no enlaza metricas); es deliberadamente legible para auditar y reconciliar.
ID_POST_INCIERTO = "incierto-timeout"

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
    cadenas SIN zona se interpretan como UTC, para que el `publicar_en` del borrador sea
    siempre un instante aware (nunca naive-vs-aware → TypeError)."""
    if not valor:
        return None
    try:
        return _a_utc(datetime.fromisoformat(valor))
    except ValueError:
        return None


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
    # Gate maestro global + excepción por marca (marca excluida -> dry-run).
    dry_run = not config.publicar_real_para(marca_id)

    # GUARDA DE RE-PIEZA (solo camino REAL): si la pieza YA fue publicada (tiene
    # `id_post_metricool` o estado `publicado`), no la re-enviamos a Metricool. En dry-run
    # NO bloqueamos: previsualizar el cuerpo de una pieza ya publicada es inofensivo y util.
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
        # y avisamos al humano (`incierto`) para que verifique en redes.
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
