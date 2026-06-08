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
    elige hasta un CAP, y CREA un `contenido` (tema) por item SIN generar copy todavía. Para
    feeds de MARCA PROPIA (`propia`) resuelve la `og:image` del artículo (la foto real); para
    feeds de no-propia / tendencia, sin imagen. Guarda en el tema (`copy_pendiente`, JSON) los
    parámetros que la fase CD necesitará para lanzar el copy. Marca el item del feed como USADO
    (dedup). Registra UNA entrada de actividad etapa="CI".
  - QA — CRIBA DE LA FUENTE (pre-copy): por cada TEMA nuevo sin veredicto, lanza un `claude -p`
    que evalúa la NOTA DE ORIGEN (no el copy: aún no existe) contra el DOCUMENTO de Texto
    de criterios. Es PERMISIVO y devuelve un veredicto ESTRUCTURADO con dos salidas:
    `no_verificado` (nada de peso en contra: seguir; la pieza llevará ⚠️ "no verificado") o
    `problema` (algo de peso: NO se genera copy; el tema se marca ❗ con los hallazgos). Por
    defecto `no_verificado` cuando hay duda (permisivo). El veredicto + hallazgos se PERSISTEN
    sobre el tema (`qa_veredicto`/`qa_hallazgos`). Cota de lanzamientos por barrido
    (`_QA_LANZAR_MAX`). Registra etapa="QA" por tema, enlazada a la generación (stream).
  - CD — CREACIÓN DE CONTENIDO: por cada tema cuya QA salió `no_verificado` y que aún no tiene
    copy, lanza la generación de copy por el camino PROBADO (`dominio.generar.lanzar_copy`) con
    los parámetros guardados (`imagen_fuente` para marca propia). NUNCA genera copy de un tema
    `problema` (ahorra tokens). Registra etapa="CD" por tema y limpia `copy_pendiente`.

ORDEN Y ASINCRONÍA (DOS FASES ENTRE BARRIDOS)
=============================================
La QA es asíncrona (`claude -p`): un tema cribado en un barrido NO tiene veredicto en ESE mismo
barrido. Por eso el flujo es de DOS FASES entre barridos: la fase QA marca el tema; la fase CD
de un barrido POSTERIOR actúa sobre los temas `no_verificado` sin copy. Se eligió esta vía
(no encadenar la QA→copy dentro del worker) por ser la más limpia y reusar el mismo patrón
async que ya tenía el QA editorial: el estado vive en el TEMA, es idempotente y auto-curativo.

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
  - DEDUP: al crear el tema (CI), el item del feed se marca USADO (`repos.marcar_item`); el
    siguiente barrido lo salta. La ingesta lee `claves_vistas` para no re-elegir lo ya usado.
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

from . import libtexto, config, daemon_util, generaciones, marcas, redes, repos
from .dominio import dedup
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

# Cuantos temas recientes (origen pipeline) revisa cada fase por barrido. Cota de seguridad
# para no recorrer un histórico enorme.
_QA_REVISAR_MAX = 50

# CAP de LANZAMIENTOS de QA de la FUENTE (`claude -p`) por barrido. Cada uno es un job del worker
# (KENI_MAX_JOBS); sin tope, una pasada que encuentra muchos temas sin veredicto dispara una
# RÁFAGA que satura el worker e inunda Actividad de QA "ejecutando". Con el tope, cada barrido
# lanza pocos y el resto se criba en el siguiente; el sweep es horario, así drena gradualmente.
_QA_LANZAR_MAX = 4

# CAP de LANZAMIENTOS de COPY (CD) por barrido: la fase CD también encola `claude -p` (uno por
# tema `no_verificado`); mismo motivo de anti-ráfaga que la QA. El resto entra en el siguiente.
_CD_LANZAR_MAX = 4

# DEDUP de contenido: ventana (días) hacia atrás para considerar que una noticia "ya está" en la
# marca. Un tema nuevo cuyo título coincide (normalizado) con otro contenido de la MISMA marca
# creado en esta ventana NO se crea: cubre el duplicado en la cola (misma noticia por dos fuentes)
# y el republicado de lo ya salido hace poco. Fuera de la ventana, una noticia recurrente sí entra.
_DIAS_DEDUP = 60

# El pipeline no sabe de antemano si un ítem será FOTO o VIDEO, así que crea piezas de FOTO
# (regla del dueño: foto -> 3 redes IG/X/FB). El mapeo formato->redes vive en
# `redes.redes_de_formato` (fuente única); video -> las 5 queda definido para flujos futuros.
_FORMATO_PIPELINE = redes.FORMATO_FOTO

# --- QA editorial por DOCUMENTO de Texto (no skills) ---------------------------------
# El equipo NO usa skills: el QA editorial se hace adjuntando un DOCUMENTO de la Texto con
# los criterios de revisión. Regla del dueño: "si el documento existe, adjúntalo; si no existe,
# créalo y adjúntalo." Este es el id (prompt) de ese documento de criterios.
PROMPT_QA_ID = "prompt/qa-editorial"
_TITULO_QA = "QA editorial"

# Veredicto SENTINEL que se persiste en el TEMA mientras su QA de la fuente (claude -p) está en
# vuelo: la fase QA NO lo re-lanza (deja de estar "sin veredicto") y la vista Pipelines pinta la
# etapa QA como "en curso". Al completar, el `procesar` lo sustituye por el veredicto real.
QA_EN_CURSO = "en_curso"

# Veredictos ESTRUCTURADOS de la QA de la FUENTE (rediseño QPC), reexportados del dominio para
# que el sweep, la API y los tests compartan los literales sin acoplarse al módulo de dominio.
VERDICTO_NO_VERIFICADO = dom_qa.VERDICTO_NO_VERIFICADO  # ⚠️ OK para seguir (no verificado a fondo)
VERDICTO_PROBLEMA = dom_qa.VERDICTO_PROBLEMA  # ❗ algo de peso en contra: NO se genera copy

# Criterios por defecto del documento QA que se CREA si aún no existe (idempotente). REDISEÑO:
# la QA es PRE-COPY y criba la NOTA DE ORIGEN (no el copy, que aún no existe). Es PERMISIVA: solo
# levanta `problema` ante algo de PESO (dato falso evidente, problema legal/ético claro); ante la
# duda, `no_verificado`. SEÑALA (no publica ni reescribe).
_DEFAULT_QA_CRITERIOS = """\
Eres el revisor editorial de AMX Contenido. Recibes en el bloque CONTEXTO la NOTA DE ORIGEN
(título + resumen + enlace) de la que se generará copy para redes. Haces una CRIBA PREVIA,
ANTES de que se redacte el copy: decides si la fuente es apta para producir contenido. NO
redactas copy ni reescribes nada. Aplica la LÍNEA EDITORIAL adjunta (voz de marca, reglas).

Modo dry-run: no publicas ni haces peticiones de red. SEÑALAS; el equipo decide.

SÉ PERMISIVO: esta criba es un primer filtro barato, NO una verificación a fondo. Solo levanta
un PROBLEMA cuando hay algo de PESO en contra (un dato claramente falso, un asunto legal o ético
serio, una fuente no fiable o sensacionalista que no debería amplificarse). Ante la duda, DEJA
PASAR: el copy generado llevará un aviso de "no verificado" y un humano lo revisará después.

## Veredicto (ANTES del detalle)

Empieza, arriba del todo, por una sola línea de semáforo:

🟢 (apta, seguir) · 🔴 (problema de peso, NO generar copy)

No uses el amarillo: o es apta (🟢) o tiene un problema de peso (🔴).

## Qué miras (a alto nivel, sin verificar a fondo)

1. Veracidad evidente: ¿la nota afirma algo claramente falso o inventado? No verifiques datos uno
   a uno; solo señala lo que salte a la vista como falso.
2. Legal / ético: ¿hay algo serio (difamación, contenido sensible, desinformación) que desaconseje
   amplificar esta fuente?
3. Fuente: ¿es una fuente fiable o un clickbait/sensacionalismo que no deberíamos amplificar?

## Salida

Tras el semáforo, cierra con un bloque ```json con la forma:
{"veredicto": "🟢", "resumen": "una frase",
 "hallazgos": [{"tipo": "dato|legal|voz", "gravedad": "error|aviso",
                "fragmento": "...", "explicacion": "...", "sugerencia": "..."}]}
Usa gravedad "error" SOLO para lo de peso (lo que hace 🔴). Sin emojis en el cuerpo.
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
    return list(redes.redes_de_formato(_FORMATO_PIPELINE))


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


def _copy_pendiente_de(trabajo: dict[str, Any], nota: str, redes_ids: list[str]) -> str:
    """JSON con los parámetros que la fase CD necesitará para lanzar el copy de un tema.

    Se guarda en `contenido.copy_pendiente` al crear el tema (CI). La fase CD lo lee y lanza
    `lanzar_copy` SOLO si la QA de la fuente salió `no_verificado`, sin re-leer el feed ni
    re-resolver la og:image (ya resuelta en CI). "" si no se puede serializar (best-effort).
    """
    import json

    fuente = trabajo.get("fuente") or {}
    item = trabajo.get("item") or {}
    imagen = trabajo.get("imagen") or ""
    try:
        return json.dumps({
            "nota": nota,
            "redes_ids": list(redes_ids),
            "fuente_id": fuente.get("id") or "",
            "clave": (item.get("clave") or "").strip(),
            "imagen": imagen,
            "tipo_contenido": "fuente" if imagen else "",
        }, ensure_ascii=False)
    except (TypeError, ValueError):  # pragma: no cover -- entrada simple, no debería fallar
        return ""


def _fecha_fuente_iso(item: dict[str, Any]) -> str:
    """ISO UTC de la fecha de la FUENTE (pubDate/updated del item); "" si falta o no parsea.

    Reutiliza el parser tolerante del feed (`http_feed.fecha_a_orden`, que cubre RFC 822 e
    ISO 8601 y asume UTC para naive). Un crudo ausente/ilegible cae a la fecha mínima
    (epoch); lo tratamos como "" (la pieza no conserva fecha de fuente). Best-effort: nunca
    rompe la ingesta.
    """
    crudo = (item.get("fecha") or "").strip()
    if not crudo:
        return ""
    try:
        from datetime import UTC

        from .dominio import http_feed

        dt = http_feed.fecha_a_orden(crudo)
        if dt.year <= 1970:  # epoch = no se pudo parsear
            return ""
        return dt.astimezone(UTC).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001 -- el dato es informativo; un fallo no debe romper la ingesta
        return ""


_AVISO_SIN_LINEA = "⚠ Sin línea: clasifícala a una línea o deséchala."


def _auto_etiquetar_linea(tema: dict[str, Any], titulo: str, resumen: str) -> None:
    """Auto-etiqueta la pieza con su LÍNEA (vertical) y ORIGEN si `KENI_PIPELINE_LINEAS`.

    Sin el flag no hace nada (comportamiento previo). Sin línea → deja un aviso en `notas`
    (la pieza NO se descarta). Best-effort: un fallo no rompe la ingesta.
    """
    if not config.pipeline_lineas_activo():
        return
    try:
        from .dominio import clasificador_lineas

        res = clasificador_lineas.clasificar_pieza(titulo, resumen, tema.get("marca", ""))
        if res.get("vertical"):
            repos.asignar_etiqueta(tema["id"], str(res["vertical"]))
        else:
            repos.actualizar_contenido(tema["id"], {"notas": _AVISO_SIN_LINEA})
        if res.get("origen"):
            repos.asignar_etiqueta(tema["id"], str(res["origen"]))
    except Exception:  # noqa: BLE001 -- el etiquetado es best-effort; nunca rompe el barrido
        _log.warning(
            "pipeline: auto-etiquetado de línea falló (%s)", tema.get("id"), exc_info=True
        )


def crear_tema_de(
    trabajo: dict[str, Any], *, claves_vistas: set[str] | None = None
) -> dict[str, Any] | None:
    """CI — crea el `contenido` (tema) de UN trabajo de ingesta SIN generar copy, y marca el item.

    Rediseño QPC: el copy se genera DESPUÉS, en la fase CD, y SOLO si la QA de la fuente pasa.
    El tema nace con `origen=ORIGEN_PIPELINE` (para que la vista Pipelines y las fases QA/CD lo
    encuentren), la nota en `descripcion` y los parámetros de copy pendiente en `copy_pendiente`
    (JSON). Marca el item del feed como USADO (dedup) para no re-ingerirlo. None si se omite.

    `claves_vistas` (opcional): claves de dedup (`dominio.dedup.clave`) del contenido reciente de
    la marca. Si el título de este trabajo ya está ahí (misma noticia en cola o publicada hace
    poco), NO se crea el tema (se marca el item usado y se devuelve None). Tras crear, la clave
    nueva se añade al conjunto para dedup también dentro del mismo barrido. Sin él, no hay dedup.
    """
    item = trabajo["item"]
    fuente = trabajo["fuente"]
    titulo = (item.get("titulo") or "").strip()
    if not titulo:
        return None
    marca = (fuente.get("marca") or "").strip()
    if not marca or not marcas.es_marca(marca):
        return None
    clave = (item.get("clave") or "").strip()
    # Dedup de contenido: misma noticia (título normalizado) ya en la cola o publicada hace poco
    # para esta marca -> no se crea otro tema. Se marca el item usado para no re-evaluarlo.
    if claves_vistas is not None and dedup.es_duplicado(titulo, claves_vistas):
        if clave:
            try:
                repos.marcar_item(fuente["id"], clave, True)
            except Exception:  # noqa: BLE001 -- best-effort
                _log.warning("pipeline: no se pudo marcar item dup usado (%s)", clave, exc_info=True)
        _log.info("pipeline: omito duplicado «%s» (%s)", titulo[:60], marca)
        return None
    nota = _nota_de_item(item)[: gen_dom.MAX_TEXTO]
    redes_ids = _redes_de_fuente(fuente)
    try:
        from datetime import date

        tema = repos.crear_contenido(
            clase="contenido",
            titulo=titulo[:300],
            descripcion=nota[:5000],
            marca=marca,
            origen=ORIGEN_PIPELINE,
            fecha_objetivo=date.today().isoformat(),
            # FOTO explícito: el pipeline no sabe si el ítem será foto o video, así que crea
            # un post de FOTO (3 redes IG/X/FB). El humano puede pasarlo a video más adelante.
            formato=_FORMATO_PIPELINE,
            copy_pendiente=_copy_pendiente_de(trabajo, nota, redes_ids),
            # Fecha de la FUENTE (pubDate del item), para mostrar en la Consola "Fuente del …"
            # junto a "Generado el …" (`creado`). "" si la fuente no traía fecha.
            fecha_fuente=_fecha_fuente_iso(item),
            # URL CANÓNICA de la nota de origen (trazabilidad + dedup por URL). El enlace ya va
            # como texto en la nota; aquí se persiste estructurado. "" si no es http(s) válido.
            url_fuente=_url_fuente_de(item),
        )
    except Exception:  # noqa: BLE001 -- sin tema, este item no produce nada (no rompe el barrido)
        _log.warning("pipeline: no se pudo crear el tema (%s)", marca, exc_info=True)
        return None
    # Auto-etiquetado de línea (vertical) y origen — gated por KENI_PIPELINE_LINEAS.
    _auto_etiquetar_linea(tema, titulo, (item.get("resumen") or "").strip())
    # Dedup intra-barrido: registra el título recién creado para que otro item con el mismo
    # título (otra fuente) en este MISMO barrido no cree un segundo tema.
    if claves_vistas is not None:
        claves_vistas.add(dedup.clave(titulo))
    # Dedup: marca el item del feed como usado tras crear el tema, para que un re-barrido
    # inmediato no lo vuelva a elegir. Best-effort.
    if clave:
        try:
            repos.marcar_item(fuente["id"], clave, True)
        except Exception:  # noqa: BLE001 -- el marcado es dedup; un fallo no debe romper el barrido
            _log.warning("pipeline: no se pudo marcar el item usado (%s)", clave, exc_info=True)
    return tema


def _claves_dedup_marca(marca: str) -> set[str]:
    """Claves de dedup (títulos normalizados) del contenido reciente de `marca` (`_DIAS_DEDUP`).

    Best-effort: si la lectura falla, devuelve un set vacío (no se deduplica, no se rompe el
    barrido). Cubre el duplicado en cola y el republicado: todo contenido de la marca creado en
    la ventana entra (esté en borrador, en revisión o ya publicado).
    """
    from datetime import date, timedelta

    desde = (date.today() - timedelta(days=_DIAS_DEDUP)).isoformat()
    try:
        titulos = repos.titulos_recientes_marca(marca, desde)
    except Exception:  # noqa: BLE001 -- sin títulos legibles, no dedup (no rompe el barrido)
        _log.warning("pipeline: no se pudieron leer títulos para dedup (%s)", marca, exc_info=True)
        return set()
    return {k for t in titulos if (k := dedup.clave(t))}


def _url_fuente_de(item: dict[str, Any]) -> str:
    """URL CANÓNICA del enlace de origen del item, para `contenido.url_fuente` (trazabilidad/dedup).

    Solo canoniza http/https (la canonización ya descarta lo demás devolviendo ""). El enlace
    sigue viajando como texto en la nota; esto lo persiste estructurado. "" si no hay enlace
    válido. Best-effort y puro (delega en `dedup.url_canonica`).
    """
    enlace = (item.get("enlace") or "").strip()
    if not enlace.startswith(("http://", "https://")):
        return ""
    return dedup.url_canonica(enlace)


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
# CD — creación de contenido (lanza copy de temas con QA `no_verificado`)      #
# --------------------------------------------------------------------------- #


def _copy_pendiente_leido(tema: dict[str, Any]) -> dict[str, Any]:
    """Lee y parsea `copy_pendiente` (JSON) de un tema. {} si vacío o ilegible (best-effort)."""
    import json

    crudo = (tema.get("copy_pendiente") or "").strip()
    if not crudo:
        return {}
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def lanzar_copy_de_tema(tema: dict[str, Any], *, autor: dict[str, str] | None) -> dict[str, Any] | None:
    """CD — lanza la generación de copy de UN tema cuya QA de la fuente salió `no_verificado`.

    Reutiliza el lanzador PROBADO `dominio.generar.lanzar_copy` con los parámetros que CI guardó
    en `copy_pendiente` (nota, redes, imagen ya resuelta, fuente, clave). El borrador resultante
    cuelga del tema (`contenido_id`) y hereda su origen. Para marca PROPIA con `og:image`, la
    pieza nace con esa imagen (`tipo_contenido='fuente'`). Registra la etapa CD y limpia
    `copy_pendiente` (evita relanzar). None si se omite (sin parámetros / marca inválida).
    """
    tema_id = (tema.get("id") or "").strip()
    marca = (tema.get("marca") or "").strip()
    if not tema_id or not marca or not marcas.es_marca(marca):
        return None
    pend = _copy_pendiente_leido(tema)
    nota = (pend.get("nota") or tema.get("descripcion") or "").strip()
    if not nota:
        return None
    titulo = (tema.get("titulo") or "").strip()
    redes_ids = [r for r in (pend.get("redes_ids") or []) if redes.es_red(r)] or list(
        redes.redes_de_formato(_FORMATO_PIPELINE)
    )
    imagen = (pend.get("imagen") or "").strip()
    tipo_contenido = "fuente" if imagen else ""
    fuente_id = (pend.get("fuente_id") or "").strip() or None
    clave = (pend.get("clave") or "").strip() or None
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
        fuente_id=fuente_id,
        clave=clave,
        contenido_id=tema_id,
        imagen_fuente=imagen,
        tipo_contenido=tipo_contenido,
        # La fuente pasó como `no_verificado` (criba permisiva, sin verificación a fondo): las
        # piezas heredan ese aviso (⚠️) en su veredicto, para que la parrilla y Pipelines lo
        # muestren. Si el copy trajera un veredicto propio, ese manda; aquí da el por defecto.
        veredicto_inicial=VERDICTO_NO_VERIFICADO,
    )
    # Limpia `copy_pendiente`: el copy ya se lanzó; la fase CD no debe relanzarlo (idempotencia).
    try:
        repos.actualizar_contenido(tema_id, {"copy_pendiente": ""})
    except Exception:  # noqa: BLE001 -- best-effort; sin esto, la guarda "sin copy" lo evita igual
        _log.warning("pipeline: no se pudo limpiar copy_pendiente (%s)", tema_id, exc_info=True)
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


def _tiene_copy(tema_id: str) -> bool:
    """True si el tema ya tiene al menos una pieza por plataforma (copy en marcha). Best-effort."""
    if not tema_id:
        return False
    try:
        return bool(repos.listar_contenido_plataforma(tema_id))
    except Exception:  # noqa: BLE001 -- sin lectura, conservador: asumimos que NO para reintentar
        return False


def temas_pipeline(marca: str | None = None) -> list[dict[str, Any]]:
    """Temas del pipeline (origen `pipeline`), recientes acotados. [] si la lectura falla."""
    try:
        items = repos.listar_contenido(marca=marca)
    except Exception:  # noqa: BLE001 -- sin temas legibles, el barrido no hace nada
        return []
    pipeline = [it for it in items if (it.get("origen") or "") == ORIGEN_PIPELINE]
    return pipeline[:_QA_REVISAR_MAX]


def temas_para_copy(marca: str | None = None) -> list[dict[str, Any]]:
    """Temas listos para CD: QA `no_verificado`, con `copy_pendiente` y SIN copy aún.

    La guarda de DOS niveles (copy_pendiente no vacío + sin piezas) hace la fase CD idempotente
    y auto-curativa: un tema cuyo copy ya se lanzó no se relanza aunque su `copy_pendiente` no se
    hubiera limpiado (p. ej. tras un fallo). Best-effort.
    """
    listos: list[dict[str, Any]] = []
    for tema in temas_pipeline(marca):
        if (tema.get("qa_veredicto") or "") != VERDICTO_NO_VERIFICADO:
            continue
        if not (tema.get("copy_pendiente") or "").strip():
            continue
        if _tiene_copy(tema.get("id", "") or ""):
            continue
        listos.append(tema)
    return listos


# --------------------------------------------------------------------------- #
# QA — criba de la FUENTE (pre-copy) + helper léxico (vista/detalle)           #
# --------------------------------------------------------------------------- #


def qa_lexico(publicacion: dict[str, Any]) -> dict[str, Any]:
    """Veredicto léxico de UN borrador (PURO, testeable): `{verdicto, observaciones:[..]}`.

    Comprobaciones DETERMINISTAS y baratas (no editorial; el gancho al prompt `qa-editorial`
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


def asegurar_documento_qa() -> str:
    """Garantiza que el DOCUMENTO de criterios de QA existe en la Texto.

    Regla del dueño: "si el documento existe, adjúntalo; si no existe, créalo y adjúntalo." El
    equipo NO usa skills: el QA se hace con un documento adjunto. Aquí:
      - si el documento (`PROMPT_QA_ID`) ya está en el STORE de la Texto, lo respeta;
      - si no, lo CREA con `_DEFAULT_QA_CRITERIOS` (criba pre-copy de la fuente). IDEMPOTENTE.
    Devuelve `PROMPT_QA_ID` si el documento queda disponible (creado o ya presente), o "" si no
    se pudo asegurar (best-effort: sin documento, la QA de la fuente no corre y el tema queda sin
    veredicto, de modo que la fase CD no genera copy hasta que haya criba).

    Nota: la semilla del paquete ya trae un `prompt/qa-editorial`; `cuerpo_efectivo` lo resuelve
    aunque no esté materializado en el store. Materializarlo aquí garantiza un documento EDITABLE
    por el equipo (la regla pide un documento real, adjuntable y versionado).
    """
    try:
        if libtexto.obtener(PROMPT_QA_ID) is not None:
            return PROMPT_QA_ID
        # No está en el store: si la semilla lo trae, ya hay cuerpo efectivo; aun así CREAMOS el
        # documento del store para que sea editable/adjuntable (la regla pide un doc real).
        cuerpo_semilla = libtexto.cuerpo_efectivo(PROMPT_QA_ID)
        cuerpo = cuerpo_semilla if cuerpo_semilla else _DEFAULT_QA_CRITERIOS
        doc = libtexto.crear(_TITULO_QA, tipo="prompt", cuerpo=cuerpo)
        # `crear` deriva el id del slug del título: "QA editorial" -> "prompt/qa-editorial".
        return doc.id if doc.id == PROMPT_QA_ID else (PROMPT_QA_ID if libtexto.obtener(PROMPT_QA_ID) else doc.id)
    except Exception:  # noqa: BLE001 -- asegurar el doc es best-effort
        _log.warning("pipeline: no se pudo asegurar el documento de QA", exc_info=True)
        return ""


def dom_qa_titulo(texto: str) -> str:
    """Título corto del QA (deriva del texto, como el endpoint manual). Best-effort."""
    try:
        from .dominio import stream

        return stream.derivar_titulo(texto)
    except Exception:  # noqa: BLE001 -- el título es cosmético; nunca rompe el QA
        return (texto or "").strip().splitlines()[0][:80] if texto.strip() else "Nota"


def _contexto_qa_fuente(nota: str) -> str:
    """Bloque de contexto de la QA de la FUENTE: la nota de origen a cribar (titulo+resumen+enlace)."""
    return "Nota de origen a cribar (aún no hay copy):\n\n" + nota


def lanzar_qa_fuente(
    tema: dict[str, Any], *, autor: dict[str, str] | None
) -> dict[str, Any] | None:
    """QA de la FUENTE via `claude -p`: criba la NOTA de origen de un TEMA contra el doc de Texto.

    Rediseño QPC (pre-copy, por TEMA): evalúa el material de origen (no el copy: aún no existe) y
    persiste un veredicto ESTRUCTURADO (`no_verificado`/`problema`) + hallazgos sobre el TEMA
    (`construir_procesar_qa_fuente`). Reutiliza el camino PROBADO de generaciones (`gen_dom.lanzar`).
    El stream queda en la generación; el marcador QA la enlaza por `gen_id` (su proceso se ve en
    el detalle del pipeline).

    ASÍNCRONO: encola y devuelve la generación; marca el tema `qa_veredicto='en_curso'` para que
    la fase QA no lo re-lance y la etapa QA se vea "en curso" hasta que el `procesar` persista el
    veredicto real al completar. None si no se pudo lanzar (sin doc / sin marca / sin nota). La
    `ColaLlenaError` se PROPAGA (el barrido corta la fase QA de esa marca).
    """
    tema_id = (tema.get("id") or "").strip()
    if not tema_id:
        return None
    marca = (tema.get("marca") or "").strip()
    if not marca or not marcas.es_marca(marca):
        return None
    pend = _copy_pendiente_leido(tema)
    nota = (pend.get("nota") or tema.get("descripcion") or "").strip()
    if not nota:
        return None

    # Regla del dueño: asegura (crea si falta) el documento de criterios y adjúntalo.
    doc_id = asegurar_documento_qa()
    cuerpo = libtexto.cuerpo_efectivo(doc_id) if doc_id else None
    if not cuerpo:
        return None  # sin documento de QA no hay criba: el tema queda sin veredicto (sin copy).

    titulo = (tema.get("titulo") or "").strip() or dom_qa_titulo(nota)
    prompt = gen_dom.componer(
        cuerpo,
        libtexto.editoriales_de_marca(marca, pipeline="qa"),
        _contexto_qa_fuente(nota),
    )
    # Marca el tema en curso ANTES de lanzar (para que la fase QA no lo re-lance). CLAVE con el
    # lanzador SÍNCRONO de los tests: el `procesar` corre DURANTE `lanzar` y persiste el veredicto
    # real; si marcáramos en_curso DESPUÉS, sobrescribiría ese veredicto. En prod (async) el orden
    # es indiferente; así queda correcto en ambos. El `procesar` lo sustituye por el real al fin.
    try:
        repos.actualizar_contenido(tema_id, {"qa_veredicto": QA_EN_CURSO})
    except Exception:  # noqa: BLE001 -- best-effort; sin esto el doble-lanzamiento lo evita el sweep
        _log.warning("pipeline: no se pudo marcar el tema en_curso para QA (%s)", tema_id, exc_info=True)
    gen = gen_dom.lanzar(
        tipo="qa-fuente",
        titulo=_TITULO_QA,
        marca=marca,
        prompt=prompt,
        procesar=dom_qa.construir_procesar_qa_fuente(
            marca, titulo, autor, contenido_id=tema_id,
        ),
        procesar_spec=jobspec.construir_qa_fuente(
            marca=marca, titulo=titulo, autor=autor, contenido_id=tema_id,
        ),
        autor=autor,
        # Criba QA de la FUENTE = VERIFICACIÓN con SALIDA ESTRUCTURADA (veredicto
        # `no_verificado`/`problema` + hallazgos, parseados; el usuario no ve la salida cruda).
        # Corroborar el material puede requerir LEER la fuente: NO se le veta la web. Queda la
        # veta global `Bash Write Edit`.
    )
    registrar_etapa(
        ETAPA_QA,
        marca,
        f"Criba de la fuente (claude) — '{titulo[:120]}'",
        contenido_id=tema_id,
        gen_id=gen.get("id", "") if isinstance(gen, dict) else "",
    )
    return gen


def temas_sin_qa(marca: str | None = None) -> list[dict[str, Any]]:
    """Temas del pipeline SIN veredicto de QA todavía (criba pendiente). Best-effort.

    Excluye los `en_curso` (su QA está en vuelo) y los ya cribados (`no_verificado`/`problema`).
    """
    return [t for t in temas_pipeline(marca) if not (t.get("qa_veredicto") or "").strip()]


# --------------------------------------------------------------------------- #
# Barrido (CI → QA de la fuente → CD por marca)                               #
# --------------------------------------------------------------------------- #


def ejecutar_barrido() -> dict[str, Any]:
    """Un barrido del pipeline: CI (crea temas) → QA de la fuente → CD (copy de los OK).

    Tres fases EN ORDEN (rediseño QPC):
      1) CI: por cada marca con feeds activos, crea temas SIN copy (`crear_tema_de`) y marca los
         items usados (dedup).
      2) QA: lanza la criba de la FUENTE (`claude -p`) de los temas nuevos sin veredicto, con tope
         `_QA_LANZAR_MAX`. ASÍNCRONA: marca el tema `en_curso` y el `procesar` persiste el veredicto
         (`no_verificado`/`problema`) al completar (normalmente en un barrido posterior).
      3) CD: genera copy SOLO de los temas cuya QA salió `no_verificado` y que aún no tienen copy
         (`temas_para_copy`), con tope `_CD_LANZAR_MAX`. Los `problema` NO generan copy (ahorro).

    Best-effort: un fallo por marca/tema se loguea y se sigue; si la cola de generación está
    llena, se corta la fase en curso (reintenta el siguiente barrido). Devuelve un resumen
    `{temas, cribados, lanzados}` (para el endpoint/los tests).

    SINGLE-FLIGHT cross-proceso (advisory lock de Postgres): el daemon y el endpoint a demanda
    comparten este barrido; su dedup (`_claves_dedup_marca`) es leer-luego-escribir en Python,
    así que dos barridos solapados podrían ingerir/cribar/generar el MISMO tema dos veces. El
    lock hace que un segundo barrido concurrente salga de inmediato con un resumen vacío.
    """
    from . import db

    with db.lock_barrido("pipeline_contenido") as ok:
        if not ok:
            _log.debug("pipeline: otro barrido en curso; se omite este.")
            return {"temas": [], "cribados": [], "lanzados": []}
        return _ejecutar_barrido()


def _ejecutar_barrido() -> dict[str, Any]:
    """Cuerpo del barrido del pipeline (ya bajo el single-flight de `ejecutar_barrido`)."""
    autor = _autor_pipeline()
    maximo = config.pipeline_max()
    # --- Fase CI: crea los temas (sin copy) por marca. ---------------------------------------
    temas_nuevos: list[dict[str, Any]] = []
    for marca in marcas.ids():
        # Exclusión por marca: si la auto-producción de ESTA marca se apagó a mano, no se ingiere
        # nada suyo (no entran temas nuevos). Sin override, sigue al daemon (global).
        if config.marca_apagada(config.ENV_PIPELINE, marca):
            continue
        try:
            trabajos = ingerir_marca(marca, maximo=maximo)
        except Exception:  # noqa: BLE001 -- un fallo de ingesta de una marca no rompe el barrido
            _log.exception("pipeline: fallo la ingesta (CI) de la marca %s", marca)
            continue
        # Dedup: claves de los títulos del contenido reciente de la marca (ventana `_DIAS_DEDUP`).
        # `crear_tema_de` salta los trabajos cuyo título ya esté aquí (duplicado en cola o
        # republicado) y va añadiendo los nuevos, para dedup también DENTRO de este barrido.
        claves_vistas = _claves_dedup_marca(marca)
        for trabajo in trabajos:
            try:
                tema = crear_tema_de(trabajo, claves_vistas=claves_vistas)
            except Exception:  # noqa: BLE001 -- un fallo por item no debe matar el barrido
                _log.exception("pipeline: fallo la creación del tema (CI) de un item.")
                continue
            if tema:
                temas_nuevos.append(tema)
    # --- Fase QA (criba de la fuente) + Fase CD (copy de los OK). ----------------------------
    cribados = ejecutar_qa(autor=autor)
    lanzados = ejecutar_cd(autor=autor)
    if temas_nuevos or cribados or lanzados:
        _log.info(
            "pipeline: %d tema(s) ingerido(s) (CI), %d cribado(s) (QA), %d copy encolado(s) (CD).",
            len(temas_nuevos), len(cribados), len(lanzados),
        )
    return {"temas": temas_nuevos, "cribados": cribados, "lanzados": lanzados}


def ejecutar_qa(*, autor: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Fase QA del barrido: lanza la CRIBA de la fuente (`claude -p`) de los temas sin veredicto.

    Con TOPE de lanzamientos por barrido (`_QA_LANZAR_MAX`): evita la ráfaga de `claude -p` que
    satura el worker e inunda Actividad de QA "en curso". Los temas restantes se criban en el
    siguiente barrido (drenaje gradual). Si la cola se llena, corta la fase (reintenta luego).
    Best-effort por tema. Devuelve los temas cuya QA se lanzó.
    """
    if autor is None:
        autor = _autor_pipeline()
    cribados: list[dict[str, Any]] = []
    lanzados = 0
    for tema in temas_sin_qa():
        if lanzados >= _QA_LANZAR_MAX:
            break
        try:
            gen = lanzar_qa_fuente(tema, autor=autor)
        except generaciones.ColaLlenaError:
            _log.info("pipeline: cola llena en QA; el resto entra en el próximo barrido.")
            break
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la fase QA
            _log.exception("pipeline: fallo la criba de la fuente (QA) de un tema.")
            continue
        if gen is not None:
            cribados.append({"id": tema.get("id", ""), "gen_id": gen.get("id", ""), "verdicto": QA_EN_CURSO})
            lanzados += 1
    return cribados


def ejecutar_cd(*, autor: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Fase CD del barrido: genera copy SOLO de los temas con QA `no_verificado` y sin copy aún.

    Con TOPE por barrido (`_CD_LANZAR_MAX`): mismo motivo anti-ráfaga que la QA. Un tema cuyo
    copy ya se lanzó (o `problema`) no entra (lo decide `temas_para_copy`). Si la cola se llena,
    corta la fase (reintenta luego). Best-effort por tema. Devuelve las generaciones de copy.
    """
    if autor is None:
        autor = _autor_pipeline()
    lanzados: list[dict[str, Any]] = []
    contador = 0
    for tema in temas_para_copy():
        if contador >= _CD_LANZAR_MAX:
            break
        # Exclusión por marca: no generamos copy de temas de una marca apagada a mano (aunque
        # ya estuvieran ingeridos antes de apagarla).
        if config.marca_apagada(config.ENV_PIPELINE, tema.get("marca") or ""):
            continue
        try:
            gen = lanzar_copy_de_tema(tema, autor=autor)
        except generaciones.ColaLlenaError:
            _log.info("pipeline: cola llena en CD; el resto entra en el próximo barrido.")
            break
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la fase CD
            _log.exception("pipeline: fallo la generación de copy (CD) de un tema.")
            continue
        if gen:
            lanzados.append(gen)
            contador += 1
    return lanzados


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
            activo_fn=config.gate_maquina(config.pipeline_activo),
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
