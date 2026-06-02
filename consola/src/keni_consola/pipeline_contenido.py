"""Pipeline de contenido CI→CD→QA por marca (fase3 auto-produccion, Flujo "tubería").

PROBLEMA QUE RESUELVE
=====================
Los daemons existentes (`autogen_copy`, `autogen_arte`, `radar_auto`) automatizan PASOS
sueltos del tablero, pero no hay un flujo que, por MARCA, lea sus fuentes RSS frescas y las
lleve de extremo a extremo —ingesta → creación de copy+arte de marca → validación
automática— dejando BORRADORES listos para la aprobación humana, y que REGISTRE cada ETAPA
como un pipeline de CI/CD (visible en "Actividad IA"). Este daemon (espejo de `autogen_copy`/
`radar_auto`) hace exactamente eso, cada N horas y por marca con feeds activos:

  - CI — INGESTA DE FUENTES: lee items frescos (no usados) de los feeds activos de la marca,
    elige hasta un CAP. Para feeds de MARCA PROPIA (`propia`) resuelve la `og:image` del
    artículo (la foto real); para feeds de no-propia / tendencia, sin imagen (el pipeline de
    copy ya compone una placa de marca con hueco de foto). Registra UNA entrada de actividad
    etapa="CI".
  - CD — CREACIÓN DE CONTENIDO: por cada item, lanza la generación de copy por el camino
    PROBADO (`dominio.generar.lanzar_copy`), con `imagen_fuente` puesta para marca propia.
    Marca el item del feed como USADO (dedup) para no re-ingerirlo. Registra una entrada de
    actividad etapa="CD" por item.
  - QA — VALIDACIÓN AUTOMÁTICA: una pasada aparte que, para los BORRADORES recientes del
    pipeline (origen `pipeline`) COMPLETADOS y SIN veredicto, corre una validación léxica
    mínima (longitud por red vs `redes`, copy vacío) y persiste un veredicto. Registra una
    entrada de actividad etapa="QA" por borrador. (El gancho al QA editorial real —la skill
    `qa-editorial`— queda como TODO: encolar un `claude -p` por pieza es pesado/asíncrono;
    aquí basta una verificación determinista que deje la señal y la etapa en la actividad.)

El borrador queda `borrador` para el paso de APROBACIÓN HUMANA en la parrilla. Nada se
publica; NUNCA se llama a Metricool.

SEGURO POR DISEÑO (CONSERVADOR)
===============================
  - GATEADO: el daemon solo barre con `KENI_PIPELINE=1` (def OFF). Sin el flag, el
    comportamiento existente NO cambia (este modulo es ADITIVO: nadie lo invoca con el flag
    ausente). El hilo arranca SIEMPRE y comprueba el flag en cada ciclo (apagar/encender en
    runtime sin reiniciar).
  - SOLO LECTURA DE FUENTES: la ingesta solo LEE feeds RSS y resuelve `og:image`; el guard
    SSRF de los feeds sigue aplicando aguas arriba (`http_feed`).
  - CAP por barrido y por marca (`KENI_PIPELINE_MAX`, def 3): cada item lanza un `claude -p`;
    el cap evita avalanchas. El cap del worker (`KENI_MAX_JOBS`) sigue aplicando aguas abajo.
  - DEDUP: tras lanzar, el item del feed se marca USADO (`repos.marcar_item`); el siguiente
    barrido lo salta. La ingesta lee `claves_vistas` para no re-elegir lo ya usado.
  - NO PUBLICA: el borrador nace `borrador` y pasa por la MISMA revisión/aprobación humana;
    la publicación real (Metricool) sigue gated por `KENI_PUBLICAR_REAL` (no se toca aquí).

La SELECCIÓN de items (`items_ingeribles`) y el VEREDICTO léxico (`qa_lexico`) son PUROS y
testeables. El LANZAMIENTO reutiliza `lanzar_copy` sin tocar su contrato: bajo riesgo.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from . import biblioteca, config, daemon_util, generaciones, marcas, redes, repos
from .dominio import generar as gen_dom
from .dominio import jobspec
from .dominio import qa_editorial as dom_qa

_log = logging.getLogger("keni_consola.pipeline_contenido")

# Origen reservado de los BORRADORES producidos por el pipeline (en el `contenido` padre que
# los NIDA). La dedup de la pasada QA y la UI distinguen lo del pipeline de lo manual/otro auto.
ORIGEN_PIPELINE = "pipeline"

# `tipo` con el que se sellan los MARCADORES de etapa (CI/CD/QA): registros `generaciones`
# ligeros SIN coste (no llaman a `claude`). Llevan tipo PROPIO `pipeline_etapa` para que la
# vista "Actividad IA" los EXCLUYA (no son trabajo con tokens/coste; serían ruido a 0). El
# trabajo REAL con coste es la generación de copy, que se sella `tipo='pipeline'` (TIPO_COPY)
# y SÍ aparece en Actividad con sus tokens/coste/tiempo. La vista Pipelines lee estos
# marcadores por `contenido_id`. La ETAPA viaja en la `etiqueta` ("CI · ..."/"CD · ..."/"QA · ...").
TIPO_ACTIVIDAD = "pipeline_etapa"
# `tipo` de la GENERACIÓN de copy que lanza el pipeline: la pieza real de trabajo (claude -p)
# con tokens/coste/tiempo. Etiquetarla `pipeline` la hace identificable y medible en Actividad.
TIPO_COPY = "pipeline"

ETAPA_CI = "CI"
ETAPA_CD = "CD"
ETAPA_QA = "QA"

# Cuantos borradores recientes (origen pipeline) revisa la pasada QA por barrido. Cota de
# seguridad: la QA léxica es barata, pero acotamos para no recorrer un histórico enorme.
_QA_REVISAR_MAX = 50

# Redes objetivo por defecto del pipeline: subconjunto sensato de las canónicas (las que el
# piloto AMX usa a diario), intersecado con `redes.ids()` por si el catálogo cambiara.
_REDES_DEFECTO_PIPELINE = ("instagram", "x", "facebook")

# --- QA editorial por DOCUMENTO de Biblioteca (no skills) ---------------------------------
# El equipo NO usa skills: el QA editorial se hace adjuntando un DOCUMENTO de la Biblioteca con
# los criterios de revisión. Regla del dueño: "si el documento existe, adjúntalo; si no existe,
# créalo y adjúntalo." Este es el id (prompt) de ese documento de criterios.
PROMPT_QA_ID = "prompt/qa-editorial"
_TITULO_QA = "QA editorial"

# Veredicto SENTINEL que se persiste en la pieza mientras su QA editorial (claude -p) está en
# vuelo: la pasada QA NO la re-lanza (deja de estar "sin veredicto") y la vista Pipelines pinta
# la etapa QA como "en curso". Al completar, el sweep lo sustituye por el veredicto real.
QA_EN_CURSO = "en_curso"

# Criterios por defecto del documento QA editorial que se CREA si aún no existe (idempotente).
# Cubre lo que pidió el dueño: voz de marca, veracidad/factualidad, límites por red, coherencia
# editorial y no clickbait. SEÑALA (no publica ni reescribe): abre con un veredicto claro.
_DEFAULT_QA_CRITERIOS = """\
Eres el revisor editorial de AMX Contenido. Recibes en el bloque CONTEXTO un copy ya
redactado para una red social y haces una revisión de CALIDAD antes de que un humano lo
apruebe. NO reescribes la pieza: la AUDITAS y devuelves un informe accionable. Aplica la
LÍNEA EDITORIAL adjunta (voz de marca, plataformas, tropicalización, reglas).

Modo dry-run: no publicas ni haces peticiones de red. SEÑALAS; el equipo decide.

## Veredicto (ANTES del detalle)

Empieza, arriba del todo, por una sola línea de veredicto:

LISTO PARA APROBAR · REVISAR ANTES DE PUBLICAR · NO PUBLICAR

Y en una frase, lo más importante a corregir si no está listo.

## Qué revisas

1. Voz de marca: ¿suena a la marca y a su tono? ¿quedó algún giro de España sin tropicalizar a México?
2. Veracidad / factualidad: ¿todo dato, fecha y cifra tiene respaldo? Señala lo no verificable o
   lo que parezca inventado. No des por buenos números sin fuente.
3. Límites por red: ¿la pieza cabe en el límite de caracteres de su plataforma? ¿el gancho va al
   principio? ¿el CTA es claro?
4. Coherencia editorial: ¿es coherente con la línea editorial y con la nota de origen? Sin
   contradicciones internas.
5. No clickbait: nada de titulares engañosos, sensacionalismo ni promesas que el cuerpo no cumple.

## Salida

Tras el veredicto, un informe breve por cada punto (lo que está bien y lo que hay que corregir) y
cierra con una lista numerada de correcciones priorizadas. Sin emojis.
"""


# --------------------------------------------------------------------------- #
# og:image (best-effort, INYECTABLE)                                           #
# --------------------------------------------------------------------------- #

# Regex tolerante para `<meta property="og:image" content="...">` (en cualquier orden de
# atributos). Solo se usa sobre el HTML de marca PROPIA; un fallo devuelve "" (la placa de
# marca con hueco de foto es aceptable). NUNCA lanza fuera del barrido.
_RE_OG_IMAGE = re.compile(
    r"""<meta[^>]+?(?:property|name)\s*=\s*["']og:image["'][^>]*?>""",
    re.IGNORECASE,
)
_RE_CONTENT = re.compile(r"""content\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# Tope de bytes que leemos del artículo para buscar la og:image (suele estar en el <head>).
_OG_MAX_BYTES = 512 * 1024
_OG_TIMEOUT_S = 8.0


def _fetch_og_image_real(enlace: str) -> str:
    """Resuelve la `og:image` de un artículo. "" si falla / no hay. NUNCA lanza.

    Best-effort: GET con redirects (los enlaces de Google News redirigen al editor),
    timeout corto, lee solo el principio del HTML y parsea la meta og:image con regex. Es el
    punto INYECTABLE: los tests lo parchean para no tocar la red (`monkeypatch.setattr`).
    """
    if not isinstance(enlace, str) or not enlace.strip().startswith(("http://", "https://")):
        return ""
    try:
        import httpx
    except ImportError:  # pragma: no cover -- httpx es dependencia
        return ""
    try:
        cabeceras = {"User-Agent": "keni-social/pipeline (+https://social.kenitech.io)"}
        with httpx.Client(
            timeout=_OG_TIMEOUT_S, follow_redirects=True, headers=cabeceras
        ) as cliente:
            with cliente.stream("GET", enlace.strip()) as respuesta:
                respuesta.raise_for_status()
                trozos: list[bytes] = []
                total = 0
                for trozo in respuesta.iter_bytes():
                    trozos.append(trozo)
                    total += len(trozo)
                    if total >= _OG_MAX_BYTES:
                        break
        html = b"".join(trozos).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 -- la og:image es un extra; nunca rompe el barrido
        return ""
    return _extraer_og_image(html)


def _extraer_og_image(html: str) -> str:
    """Extrae la URL `og:image` del HTML (PURA, testeable). "" si no la encuentra."""
    if not html:
        return ""
    for meta in _RE_OG_IMAGE.finditer(html):
        m = _RE_CONTENT.search(meta.group(0))
        if m:
            url = (m.group(1) or "").strip()
            if url.startswith(("http://", "https://")):
                return url
    return ""


# Seam inyectable (los tests lo parchean): NO se llama a la red en tests.
_FETCH_OG_IMAGE = _fetch_og_image_real


# --------------------------------------------------------------------------- #
# Actividad (etapas CI/CD/QA como generaciones-marcador)                       #
# --------------------------------------------------------------------------- #


def registrar_etapa(
    etapa: str, marca: str, detalle: str, contenido_id: str = "", gen_id: str = ""
) -> dict[str, Any] | None:
    """Sella una entrada de ACTIVIDAD de una etapa del pipeline (CI/CD/QA). Best-effort.

    Crea una generación-marcador `completado` (sin `claude`): `tipo='pipeline'` y la etapa +
    detalle en la `etiqueta` ("CI · Ingesta...", etc.). La vista "Actividad IA" la muestra
    junto al resto de la actividad de IA. Un fallo al sellar NUNCA aborta el barrido (devuelve
    None y se loguea): la actividad es trazabilidad, no parte crítica del flujo.

    `contenido_id` (opcional, def "") CORRELACIONA la etapa con la RUN (el `contenido` padre
    del pipeline) para la vista Pipelines (`/api/pipelines/{id}`). CD/QA lo pasan (la etapa va
    sobre un tema concreto); CI es brand-level y lo deja vacío. Es ADITIVO: vacío no engorda el
    registro (lo filtra `generaciones._cuerpo`) y los registros previos lo traen como "".

    `gen_id` (opcional, def "") apunta a la GENERACIÓN REAL de `claude -p` que ejecutó esa
    etapa (CD = copy, QA = revisión editorial). La vista Pipelines lo resuelve para mostrar el
    STREAM del agente (su proceso de pensamiento). CI no lanza `claude`, así que lo deja vacío.
    """
    etiqueta = f"{etapa} · {detalle}".strip()
    try:
        gen = generaciones.crear({
            "tipo": TIPO_ACTIVIDAD,
            "marca": marca or "",
            "contenido_id": contenido_id or "",
            "gen_id": gen_id or "",
            "etiqueta": etiqueta[:200],
            "estado": generaciones.ESTADO_COMPLETADO,
            "fecha_fin": generaciones.ahora_iso(),
        })
        return gen
    except Exception:  # noqa: BLE001 -- la traza de actividad no debe romper el pipeline
        _log.warning("pipeline: no se pudo registrar la etapa %s (%s)", etapa, marca, exc_info=True)
        return None


# --------------------------------------------------------------------------- #
# CI — ingesta de fuentes (SELECCIÓN pura + lectura de feeds)                  #
# --------------------------------------------------------------------------- #


def items_ingeribles(
    items: list[dict[str, Any]],
    *,
    vistas: set[str],
    maximo: int,
) -> list[dict[str, Any]]:
    """Subconjunto de items de un feed que se debe ingerir (PURA, testeable).

    Reglas, en orden:
      - con `clave` no vacía (necesaria para dedup/marcado),
      - con `titulo` no vacío,
      - no ya usados (`clave` en `vistas`),
      - sin claves duplicadas dentro del propio barrido,
      - se RECORTA a `maximo` (cap de seguridad por barrido y por marca).

    Determinista: depende solo de sus argumentos (conserva el orden de entrada, que el feed
    ya trae cronológico).
    """
    elegidos: list[dict[str, Any]] = []
    vistos = set(vistas)
    for item in items:
        if len(elegidos) >= maximo:
            break
        clave = (item.get("clave") or "").strip()
        if not clave:
            continue
        if not (item.get("titulo") or "").strip():
            continue
        if clave in vistos:
            continue
        vistos.add(clave)
        elegidos.append(item)
    return elegidos


def _leer_items_fuente(fuente: dict[str, Any]) -> list[dict[str, Any]]:
    """Lee los items crudos de un feed (via `api.rss`). Best-effort: [] si falla.

    Import diferido de `api.rss` (no acoplar el daemon a la capa API en carga); reutiliza su
    `leer_items_fuente` (con el `_DESCARGADOR` mockeable de los tests).
    """
    try:
        from .api import rss as api_rss

        return api_rss.leer_items_fuente(fuente)
    except Exception:  # noqa: BLE001 -- un feed que falla no debe abortar el barrido
        _log.warning("pipeline: no se pudo leer el feed %s", fuente.get("id", ""), exc_info=True)
        return []


def fuentes_activas_de_marca(marca: str) -> list[dict[str, Any]]:
    """Feeds RSS ACTIVOS de una marca. Best-effort: [] si la lectura falla."""
    try:
        fuentes = repos.listar_fuentes_rss()
    except Exception:  # noqa: BLE001 -- sin feeds legibles, esta marca no produce nada
        return []
    return [
        f
        for f in fuentes
        if (f.get("marca") or "") == marca and f.get("activo", True)
    ]


def _redes_de_fuente(fuente: dict[str, Any]) -> list[str]:
    """Redes objetivo de un item: las `redes_def` del feed si las tiene; si no, el defecto."""
    crudo = fuente.get("redes_def", "")
    pedidas = {r for r in (crudo if isinstance(crudo, list) else []) if redes.es_red(r)}
    if not pedidas and isinstance(crudo, str) and crudo:
        import json

        try:
            datos = json.loads(crudo)
        except (json.JSONDecodeError, ValueError):
            datos = []
        pedidas = {r for r in datos if isinstance(r, str) and redes.es_red(r)}
    if pedidas:
        return [r for r in redes.ids() if r in pedidas]
    return [r for r in _REDES_DEFECTO_PIPELINE if redes.es_red(r)]


def _autor_pipeline() -> dict[str, str] | None:
    """Autor (brand-agnóstico) al que se atribuyen los lanzamientos del pipeline.

    Usa el usuario configurado del MCP (`config.mcp_usuario()`) si existe y resuelve a un
    usuario real; si no, el primer admin. None si no hay usuarios (best-effort: la generación
    seguirá funcionando con autor anónimo).
    """
    try:
        from . import auth

        usuarios = auth.listar_usuarios()
    except Exception:  # noqa: BLE001 -- sin usuarios legibles, autor anónimo (no rompe)
        return None
    if not usuarios:
        return None
    preferido = (config.mcp_usuario() or "").strip().lower()

    def _u(u: dict[str, Any]) -> dict[str, str]:
        return {"id": str(u.get("id", "") or ""), "usuario": str(u.get("usuario", "") or "")}

    if preferido:
        for u in usuarios:
            if str(u.get("usuario", "") or "").strip().lower() == preferido:
                return _u(u)
    for u in usuarios:
        if (u.get("rol") or "") == "admin":
            return _u(u)
    return _u(usuarios[0])


def _crear_tema_pipeline(marca: str, titulo: str) -> str:
    """Crea el `contenido` padre que NIDA los borradores del pipeline. "" si falla.

    El tema nace con `origen=ORIGEN_PIPELINE` para que sus borradores (que cuelgan de él, via
    `lanzar_copy(contenido_id=...)`) hereden ese origen y la pasada QA pueda encontrarlos.
    """
    try:
        from datetime import date

        tema = repos.crear_contenido(
            clase="contenido",
            titulo=titulo[:300],
            marca=marca,
            origen=ORIGEN_PIPELINE,
            fecha_objetivo=date.today().isoformat(),
        )
        return tema.get("id", "") or ""
    except Exception:  # noqa: BLE001 -- sin tema padre, caemos a borrador suelto (no rompe)
        _log.warning("pipeline: no se pudo crear el tema padre (%s)", marca, exc_info=True)
        return ""


def _nota_de_item(item: dict[str, Any]) -> str:
    """Nota de partida del copy: titulo + resumen + enlace (los vacíos se omiten)."""
    partes = [
        (item.get("titulo") or "").strip(),
        (item.get("resumen") or "").strip(),
        (item.get("enlace") or "").strip(),
    ]
    return "\n\n".join(p for p in partes if p)


def ingerir_marca(marca: str, *, maximo: int) -> list[dict[str, Any]]:
    """CI — lee los feeds activos de una marca y elige items frescos. Registra la etapa CI.

    Devuelve una lista de "trabajos" `{item, fuente, propia, imagen}` listos para la fase CD.
    Para feeds de marca PROPIA resuelve la `og:image` del artículo (best-effort). Registra UNA
    entrada de actividad CI con el resumen (n temas / m fuentes / k con foto).
    """
    fuentes = fuentes_activas_de_marca(marca)
    trabajos: list[dict[str, Any]] = []
    con_foto = 0
    for fuente in fuentes:
        if len(trabajos) >= maximo:
            break
        try:
            vistas = repos.claves_vistas(fuente["id"])
        except Exception:  # noqa: BLE001 -- sin dedup legible, mejor no ingerir este feed
            continue
        crudos = _leer_items_fuente(fuente)
        restante = maximo - len(trabajos)
        elegidos = items_ingeribles(crudos, vistas=vistas, maximo=restante)
        propia = bool(fuente.get("propia"))
        for item in elegidos:
            imagen = ""
            if propia:
                try:
                    imagen = _FETCH_OG_IMAGE(item.get("enlace", "") or "")
                except Exception:  # noqa: BLE001 -- og:image best-effort; nunca rompe
                    imagen = ""
                if imagen:
                    con_foto += 1
            trabajos.append(
                {"item": item, "fuente": fuente, "propia": propia, "imagen": imagen}
            )
    registrar_etapa(
        ETAPA_CI,
        marca,
        f"Ingesta de fuentes — {marcas.etiqueta_de(marca)}: {len(trabajos)} temas "
        f"seleccionados de {len(fuentes)} fuentes ({con_foto} con foto)",
    )
    return trabajos


# --------------------------------------------------------------------------- #
# CD — creación de contenido (lanza copy + marca el item usado)               #
# --------------------------------------------------------------------------- #


def crear_contenido_de(trabajo: dict[str, Any], *, autor: dict[str, str] | None) -> dict[str, Any] | None:
    """CD — lanza la generación de copy para UN trabajo de ingesta y marca el item usado.

    Reutiliza el lanzador PROBADO `dominio.generar.lanzar_copy` (mismo camino que `api/rss`):
    compone el prompt copy-desde-nota, encola un `claude -p` y el borrador cae en la cola de
    revisión, NIDADO bajo el tema padre del pipeline (`contenido_id`). Para marca PROPIA con
    `og:image`, la pieza nace con esa imagen (`tipo_contenido='fuente'`). Marca el item del
    feed como USADO (dedup) tras lanzar. Registra la etapa CD. None si se omite.
    """
    item = trabajo["item"]
    fuente = trabajo["fuente"]
    imagen = trabajo.get("imagen") or ""
    titulo = (item.get("titulo") or "").strip()
    if not titulo:
        return None
    marca = (fuente.get("marca") or "").strip()
    if not marca or not marcas.es_marca(marca):
        return None
    clave = (item.get("clave") or "").strip()
    nota = _nota_de_item(item)[: gen_dom.MAX_TEXTO]
    redes_ids = _redes_de_fuente(fuente)

    tema_id = _crear_tema_pipeline(marca, titulo)
    tipo_contenido = "fuente" if imagen else ""
    gen = gen_dom.lanzar_copy(
        # `pipeline`: la generación REAL (claude -p) queda etiquetada como pipeline y reporta
        # sus tokens/coste/tiempo en Actividad IA (el resto del flujo —CI/QA— no cuesta).
        tipo=TIPO_COPY,
        marca=marca,
        contexto=nota,
        redes_ids=redes_ids,
        titulo=titulo,
        titulo_dado=titulo,
        texto_base=nota,
        autor=autor,
        fuente_id=fuente.get("id") or None,
        clave=clave or None,
        contenido_id=tema_id,
        imagen_fuente=imagen,
        tipo_contenido=tipo_contenido,
    )
    # Dedup: marca el item del feed como usado (el post-procesado de copy también lo marca al
    # completar con éxito, pero lo hacemos AQUÍ ya para que un re-barrido inmediato —antes de
    # que el job complete— no lo vuelva a elegir). Best-effort.
    if clave:
        try:
            repos.marcar_item(fuente["id"], clave, True)
        except Exception:  # noqa: BLE001 -- el marcado es dedup; un fallo no debe romper el barrido
            _log.warning("pipeline: no se pudo marcar el item usado (%s)", clave, exc_info=True)
    registrar_etapa(
        ETAPA_CD,
        marca,
        f"Generación de copy+arte de marca — '{titulo[:120]}'",
        contenido_id=tema_id,
        # Ata el marcador CD a la generación REAL de copy: su STREAM (proceso del agente)
        # se muestra en el detalle del pipeline.
        gen_id=gen.get("id", "") if isinstance(gen, dict) else "",
    )
    return gen


# --------------------------------------------------------------------------- #
# QA — validación automática (léxica mínima; gancho editorial = TODO)         #
# --------------------------------------------------------------------------- #


def qa_lexico(publicacion: dict[str, Any]) -> dict[str, Any]:
    """Veredicto léxico de UN borrador (PURO, testeable): `{verdicto, observaciones:[..]}`.

    Comprobaciones DETERMINISTAS y baratas (no editorial; el gancho a la skill `qa-editorial`
    real es un TODO):
      - copy no vacío,
      - longitud del copy <= límite duro de la red (`redes`), cuando la red tiene tope.

    Verdicto: "listo" sin observaciones; "revisar" si hay alguna. NUNCA "no_publicar" (la QA
    léxica solo SEÑALA; el humano decide). Determinista.
    """
    observaciones: list[str] = []
    copy = (publicacion.get("contenido") or "").strip()
    red = (publicacion.get("red") or "").strip()
    if not copy:
        observaciones.append("El copy está vacío.")
    limite = None
    for r in redes.REDES:
        if r.id == red:
            limite = r.limite
            break
    if limite is not None and len(copy) > limite:
        observaciones.append(
            f"El copy supera el límite de {redes.nombre_por_id(red)} ({len(copy)}/{limite})."
        )
    verdicto = "listo" if not observaciones else "revisar"
    return {"verdicto": verdicto, "observaciones": observaciones}


def _es_del_pipeline(publicacion: dict[str, Any]) -> bool:
    """True si un borrador procede del pipeline (origen `pipeline`), directo o heredado.

    Acepta dos formas (robusto a cómo se propague el `origen` aguas abajo del copy):
      - la PROPIA publicación trae `origen == 'pipeline'`, o
      - su `contenido` PADRE (el tema que creó el pipeline con `origen='pipeline'`) lo trae.
    Así la pasada QA encuentra los borradores reales aunque el post-procesado de copy no
    copie el `origen` del tema a la publicación. Best-effort: si no se puede leer el padre,
    cae a la comprobación directa.
    """
    if (publicacion.get("origen") or "") == ORIGEN_PIPELINE:
        return True
    cid = (publicacion.get("contenido_id") or "").strip()
    if not cid:
        return False
    try:
        padre = repos.obtener_contenido(cid)
    except Exception:  # noqa: BLE001 -- sin padre legible, nos quedamos con la directa
        return False
    return bool(padre) and (padre.get("origen") or "") == ORIGEN_PIPELINE


def borradores_pipeline_sin_qa(marca: str | None = None) -> list[dict[str, Any]]:
    """Borradores recientes del pipeline COMPLETADOS y SIN veredicto.

    Best-effort: [] si la lectura falla. Recorta a `_QA_REVISAR_MAX` (la pasada QA es barata
    pero acotamos para no recorrer un histórico enorme). El "del pipeline" lo decide
    `_es_del_pipeline` (origen propio o heredado del tema padre).
    """
    try:
        pubs = repos.listar_publicaciones(
            marca=marca, estado="borrador", limite=_QA_REVISAR_MAX
        )
    except Exception:  # noqa: BLE001 -- sin borradores legibles, la QA no hace nada
        return []
    return [
        p
        for p in pubs
        if _es_del_pipeline(p)
        and not (p.get("veredicto") or "").strip()
        and (p.get("contenido") or "").strip()
    ]


def asegurar_documento_qa() -> str:
    """Garantiza que el DOCUMENTO de criterios de QA editorial existe en la Biblioteca.

    Regla del dueño: "si el documento existe, adjúntalo; si no existe, créalo y adjúntalo." El
    equipo NO usa skills: el QA editorial se hace con un documento adjunto. Aquí:
      - si el documento (`PROMPT_QA_ID`) ya está en el STORE de la Biblioteca, lo respeta;
      - si no, lo CREA con `_DEFAULT_QA_CRITERIOS` (voz de marca, veracidad, límites por red,
        coherencia editorial, no clickbait). IDEMPOTENTE (no duplica).
    Devuelve `PROMPT_QA_ID` si el documento queda disponible (creado o ya presente), o "" si no
    se pudo asegurar (best-effort: el QA editorial caerá entonces al léxico).

    Nota: la semilla del paquete ya trae un `prompt/qa-editorial`; `cuerpo_efectivo` lo resuelve
    aunque no esté materializado en el store. Materializarlo aquí garantiza un documento EDITABLE
    por el equipo (la regla pide un documento real, adjuntable y versionado).
    """
    try:
        if biblioteca.obtener(PROMPT_QA_ID) is not None:
            return PROMPT_QA_ID
        # No está en el store: si la semilla lo trae, ya hay cuerpo efectivo; aun así CREAMOS el
        # documento del store para que sea editable/adjuntable (la regla pide un doc real).
        cuerpo_semilla = biblioteca.cuerpo_efectivo(PROMPT_QA_ID)
        cuerpo = cuerpo_semilla if cuerpo_semilla else _DEFAULT_QA_CRITERIOS
        doc = biblioteca.crear(_TITULO_QA, tipo="prompt", cuerpo=cuerpo)
        # `crear` deriva el id del slug del título: "QA editorial" -> "prompt/qa-editorial".
        return doc.id if doc.id == PROMPT_QA_ID else (PROMPT_QA_ID if biblioteca.obtener(PROMPT_QA_ID) else doc.id)
    except Exception:  # noqa: BLE001 -- asegurar el doc es best-effort; el léxico es el fallback
        _log.warning("pipeline: no se pudo asegurar el documento de QA editorial", exc_info=True)
        return ""


def _pieza_principal(publicacion: dict[str, Any]) -> tuple[str, str, str]:
    """Datos de la pieza para el QA editorial: (plataforma_id, copy, red). "" si faltan."""
    pid = (publicacion.get("id") or "").strip()
    copy = (publicacion.get("contenido") or "").strip()
    red = (publicacion.get("red") or "").strip()
    return pid, copy, red


def lanzar_qa_editorial(
    publicacion: dict[str, Any], *, autor: dict[str, str] | None
) -> dict[str, Any] | None:
    """QA editorial REAL via `claude -p`: evalúa el copy contra el DOCUMENTO de Biblioteca.

    Reutiliza el camino PROBADO de generaciones (`gen_dom.lanzar`) con el mismo post-procesado
    de QA editorial (`dominio.qa_editorial`) que el endpoint manual: parsea el informe, deriva
    el veredicto (listo/revisar/no_publicar) y lo PERSISTE atado a la pieza
    (`registrar_veredicto_qa`, con `copy_hash` para invalidarlo si el copy cambia). El stream
    (proceso del agente) queda en la generación; el marcador QA la enlaza por `gen_id` (Feature
    1), así su proceso se ve en el detalle del pipeline.

    ASÍNCRONO (como CD): encola y devuelve la generación; marca la pieza `veredicto='en_curso'`
    para que la pasada QA no la re-lance y la etapa QA se vea "en curso" hasta que complete. El
    sweep `reconciliar_qa_en_curso` recoge el veredicto real al terminar. None si no se pudo
    lanzar (sin doc / sin marca / cola llena): el llamante cae al QA léxico.
    """
    pid, copy, red = _pieza_principal(publicacion)
    if not pid or not copy:
        return None
    marca = (publicacion.get("marca") or "").strip()
    if not marca or not marcas.es_marca(marca):
        return None
    contenido_id = (publicacion.get("contenido_id") or "").strip()

    # Regla del dueño: asegura (crea si falta) el documento de criterios y adjúntalo.
    doc_id = asegurar_documento_qa()
    cuerpo = biblioteca.cuerpo_efectivo(doc_id) if doc_id else None
    if not cuerpo:
        return None  # sin documento de QA no hay QA editorial: el llamante cae al léxico.

    titulo = dom_qa_titulo(copy)
    copy_hash = dom_qa.hash_copy(copy)
    plataforma_label = redes.nombre_por_id(red) if red and redes.es_red(red) else ""
    prompt = gen_dom.componer(
        cuerpo,
        biblioteca.editoriales_de_marca(marca),
        _contexto_qa_pipeline(copy, plataforma_label),
    )
    try:
        gen = gen_dom.lanzar(
            tipo="qa-editorial",
            titulo=_TITULO_QA,
            marca=marca,
            prompt=prompt,
            procesar=dom_qa.construir_procesar_qa(
                marca, titulo, autor,
                plataforma_id=pid, contenido_id=contenido_id, copy_hash=copy_hash,
            ),
            procesar_spec=jobspec.construir_qa(
                marca=marca, titulo=titulo, autor=autor,
                plataforma_id=pid, contenido_id=contenido_id, copy_hash=copy_hash,
            ),
            autor=autor,
        )
    except generaciones.ColaLlenaError:
        # Cola llena: NO marcamos en_curso (que el siguiente barrido reintente) y dejamos que el
        # llamante caiga al léxico para no quedarnos sin señal de QA en esta pieza.
        raise
    # Marca la pieza en curso para que la pasada QA no la re-lance (deja de estar "sin veredicto").
    try:
        repos.actualizar_publicacion(pid, {"veredicto": QA_EN_CURSO})
    except Exception:  # noqa: BLE001 -- best-effort; sin esto el doble-lanzamiento se evita en el sweep
        _log.warning("pipeline: no se pudo marcar la pieza en_curso para QA (%s)", pid, exc_info=True)
    registrar_etapa(
        ETAPA_QA,
        marca,
        f"Revisión editorial (claude) — '{titulo[:120]}'",
        contenido_id=contenido_id,
        gen_id=gen.get("id", "") if isinstance(gen, dict) else "",
    )
    return gen


def dom_qa_titulo(copy: str) -> str:
    """Título corto del QA (deriva del copy, como el endpoint manual). Best-effort."""
    try:
        from .dominio import stream

        return stream.derivar_titulo(copy)
    except Exception:  # noqa: BLE001 -- el título es cosmético; nunca rompe el QA
        return (copy or "").strip().splitlines()[0][:80] if copy.strip() else "Copy"


def _contexto_qa_pipeline(copy: str, plataforma_label: str) -> str:
    """Bloque de contexto del QA del pipeline: plataforma + el copy a revisar."""
    partes: list[str] = []
    if plataforma_label:
        partes.append(f"Plataforma de destino: {plataforma_label}")
    partes.append("Copy a revisar:\n\n" + copy)
    return "\n\n".join(partes)


def reconciliar_qa_en_curso(marca: str | None = None) -> list[dict[str, Any]]:
    """Recoge el veredicto de las piezas con QA editorial EN CURSO ya resuelto.

    Espeja cómo `ejecutar_qa` corría sobre borradores completados: aquí barremos los borradores
    del pipeline marcados `veredicto='en_curso'` (su QA editorial se lanzó en un barrido previo)
    y, si su veredicto editorial ya está persistido (`repos.ultimo_veredicto_qa`), lo MAPEAMOS al
    veredicto de la pieza (listo / revisar; nunca 'no_publicar' en la pieza —el humano decide—,
    pero el veredicto editorial completo queda en `contenido_qa_veredictos`). Best-effort por
    item. Devuelve los que reconcilió.
    """
    reconciliados: list[dict[str, Any]] = []
    try:
        pubs = repos.listar_publicaciones(marca=marca, estado="borrador", limite=_QA_REVISAR_MAX)
    except Exception:  # noqa: BLE001 -- sin borradores legibles, nada que reconciliar
        return reconciliados
    for pub in pubs:
        if (pub.get("veredicto") or "").strip() != QA_EN_CURSO:
            continue
        if not _es_del_pipeline(pub):
            continue
        pid = (pub.get("id") or "").strip()
        if not pid:
            continue
        try:
            veredicto_qa = repos.ultimo_veredicto_qa(pid, pub.get("contenido_id", "") or "")
        except Exception:  # noqa: BLE001 -- una pieza ilegible no debe romper la pasada
            continue
        if not veredicto_qa:
            continue  # aún sin resolver (QA en vuelo) o copy cambió: lo deja en_curso.
        crudo = (veredicto_qa.get("verdicto") or "").strip()
        # Mapeo conservador al veredicto de la PIEZA: 'listo' si listo; cualquier otro -> 'revisar'
        # (incluido 'no_publicar': la pieza solo SEÑALA "revisar"; el detalle vive en el informe).
        verdicto_pieza = "listo" if crudo == "listo" else "revisar"
        try:
            repos.actualizar_publicacion(pid, {"veredicto": verdicto_pieza})
        except Exception:  # noqa: BLE001 -- un fallo al persistir no aborta la pasada
            _log.warning("pipeline: no se pudo persistir el veredicto QA (%s)", pid, exc_info=True)
            continue
        reconciliados.append({"id": pid, "verdicto": verdicto_pieza})
    return reconciliados


def validar_borrador(publicacion: dict[str, Any]) -> dict[str, Any] | None:
    """QA — valida UN borrador del pipeline. Prefiere el QA EDITORIAL real; cae al léxico.

    1) Intenta el QA EDITORIAL via `claude -p` contra el DOCUMENTO de Biblioteca de criterios
       (`lanzar_qa_editorial`): asíncrono, deja la pieza `en_curso` y enlaza su stream; el
       `reconciliar_qa_en_curso` recoge el veredicto al completar. Si arranca, NO corremos el
       léxico (la señal editorial es superior).
    2) FALLBACK (sin documento / sin worker / cola llena): la QA LÉXICA determinista de antes
       (longitud por red, copy vacío), que persiste un veredicto inmediato y registra la etapa.

    None si no se puede (best-effort por item).
    """
    pid = (publicacion.get("id") or "").strip()
    if not pid:
        return None
    # 1) QA editorial real (preferente). Best-effort: cualquier fallo cae al léxico.
    try:
        gen = lanzar_qa_editorial(publicacion, autor=_autor_pipeline())
    except generaciones.ColaLlenaError:
        gen = None  # cola llena: caemos al léxico para no dejar la pieza sin ninguna señal.
    except Exception:  # noqa: BLE001 -- el QA editorial nunca debe romper la pasada
        _log.warning("pipeline: fallo el QA editorial (%s); caigo al léxico", pid, exc_info=True)
        gen = None
    if gen is not None:
        return {"id": pid, "verdicto": QA_EN_CURSO, "modo": "editorial", "gen_id": gen.get("id", "")}

    # 2) Fallback léxico (determinista, inmediato).
    resultado = qa_lexico(publicacion)
    verdicto = resultado["verdicto"]
    try:
        repos.actualizar_publicacion(pid, {"veredicto": verdicto})
    except Exception:  # noqa: BLE001 -- un fallo al persistir no debe abortar la pasada QA
        _log.warning("pipeline: no se pudo persistir el veredicto QA (%s)", pid, exc_info=True)
        return None
    obs = resultado["observaciones"]
    detalle_ok = "ok" if not obs else f"{len(obs)} observaciones"
    titulo = (publicacion.get("titulo") or publicacion.get("contenido") or "").strip()[:120]
    registrar_etapa(
        ETAPA_QA,
        (publicacion.get("marca") or "") or "",
        f"Validación léxica (fallback) — '{titulo}': {detalle_ok}",
        contenido_id=(publicacion.get("contenido_id") or ""),
    )
    return {"id": pid, "verdicto": verdicto, "modo": "lexico", "observaciones": obs}


# --------------------------------------------------------------------------- #
# Barrido (CI→CD por marca + pasada QA)                                       #
# --------------------------------------------------------------------------- #


def ejecutar_barrido() -> dict[str, Any]:
    """Un barrido del pipeline: CI→CD por cada marca con feeds activos, luego pasada QA.

    Best-effort: un fallo por marca/item se loguea y se sigue; si la cola de generación está
    llena, se corta la fase CD de esa marca (reintenta el siguiente barrido). Devuelve un
    resumen `{lanzados, validados}` (para el endpoint/los tests).
    """
    autor = _autor_pipeline()
    maximo = config.pipeline_max()
    lanzados: list[dict[str, Any]] = []
    for marca in marcas.ids():
        try:
            trabajos = ingerir_marca(marca, maximo=maximo)
        except Exception:  # noqa: BLE001 -- un fallo de ingesta de una marca no rompe el barrido
            _log.exception("pipeline: fallo la ingesta (CI) de la marca %s", marca)
            continue
        for trabajo in trabajos:
            try:
                gen = crear_contenido_de(trabajo, autor=autor)
            except generaciones.ColaLlenaError:
                _log.info("pipeline: cola llena; el resto entra en el próximo barrido.")
                break
            except Exception:  # noqa: BLE001 -- un fallo por item no debe matar el barrido
                _log.exception("pipeline: fallo la creación de contenido (CD) de un item.")
                continue
            if gen:
                lanzados.append(gen)
    validados = ejecutar_qa()
    if lanzados or validados:
        _log.info(
            "pipeline: %d borrador(es) encolado(s) (CD), %d validado(s) (QA).",
            len(lanzados), len(validados),
        )
    return {"lanzados": lanzados, "validados": validados}


def ejecutar_qa() -> list[dict[str, Any]]:
    """Pasada QA: reconcilia el QA editorial en vuelo y valida los borradores sin veredicto.

    Separada de la fase CD a propósito (el enunciado): un borrador encolado en CD aún no está
    COMPLETADO en el mismo barrido, así que la QA recoge los borradores que YA completaron en
    barridos anteriores. Dos pasos, en orden:
      1) RECONCILIA las piezas con QA editorial `en_curso` cuyo veredicto ya está resuelto
         (`reconciliar_qa_en_curso`): persiste el veredicto real y cierra la etapa.
      2) VALIDA los borradores SIN veredicto: lanza el QA editorial (claude) o cae al léxico.
    Best-effort por item.
    """
    validados: list[dict[str, Any]] = []
    # 1) Cierra los QA editoriales que ya completaron en barridos anteriores.
    try:
        validados.extend(reconciliar_qa_en_curso())
    except Exception:  # noqa: BLE001 -- un fallo de reconciliación no debe matar la pasada
        _log.exception("pipeline: fallo la reconciliación de QA editorial en curso.")
    # 2) Lanza/valida los borradores aún sin veredicto.
    for pub in borradores_pipeline_sin_qa():
        try:
            r = validar_borrador(pub)
        except Exception:  # noqa: BLE001 -- un fallo por item no debe matar la pasada QA
            _log.exception("pipeline: fallo la validación (QA) de un borrador.")
            continue
        if r:
            validados.append(r)
    return validados


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (a partir de `KENI_PIPELINE_INTERVALO_HORAS`)."""
    return config.pipeline_intervalo_horas() * 3600.0


def iniciar_pipeline(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio del pipeline de contenido (GATEADO EN VIVO).

    Pensado para el servidor real (`daemons`/`__main__`), NO para `crear_app` (los tests no lo
    arrancan, igual que el resto de daemons). El hilo arranca SIEMPRE y comprueba
    `KENI_PIPELINE` en cada ciclo: apagar/encender en runtime aplica sin reiniciar (apagar en
    <= ~1 min; encender tras estar apagado dispara un barrido de inmediato). El hilo es daemon;
    un fallo de barrido se loguea y NO lo mata.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.pipeline_activo,
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="pipeline-contenido-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.pipeline_activo() else "EN ESPERA (KENI_PIPELINE off)"
    _log.info(
        "Pipeline de contenido %s, cada %.0f h (max/barrido=%d).",
        estado, intervalo / 3600.0, config.pipeline_max(),
    )
    return hilo
