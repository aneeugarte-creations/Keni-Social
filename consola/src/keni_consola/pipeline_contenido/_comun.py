"""Constantes, seams y helpers COMPARTIDOS del pipeline de contenido (CI→QA→CD).

Núcleo común a las distintas etapas (ingesta, QA, copy, barrido): constantes del flujo,
los seams inyectables de `og:image`, el sello de ACTIVIDAD por etapa (`registrar_etapa`), el
autor de los lanzamientos y los lectores de temas/copy que más de una etapa comparte. Vive
aparte para que los módulos de etapa no se importen entre sí (evita ciclos): todos dependen
de `_comun`, no al revés.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .. import config, generaciones, marcas, redes, repos
from ..dominio import qa_editorial as dom_qa

__all__ = [
    # módulos/seams reexportados que algún consumidor referencia vía el paquete
    "Any",
    "logging",
    "re",
    "config",
    "generaciones",
    "marcas",
    "repos",
    "redes",
    "dom_qa",
    "_log",
    # constantes de flujo
    "ORIGEN_PIPELINE",
    "TIPO_ACTIVIDAD",
    "TIPO_COPY",
    "ETAPA_CI",
    "ETAPA_CD",
    "ETAPA_QA",
    "_DIAS_DEDUP",
    "_FORMATO_PIPELINE",
    "PROMPT_QA_ID",
    "_TITULO_QA",
    "QA_EN_CURSO",
    "QA_SALTADA",
    "VERDICTO_NO_VERIFICADO",
    "VERDICTO_PROBLEMA",
    "_DEFAULT_QA_CRITERIOS",
    # og:image
    "_RE_OG_IMAGE",
    "_RE_CONTENT",
    "_OG_MAX_BYTES",
    "_OG_TIMEOUT_S",
    "_FETCH_OG_IMAGE",
    "_fetch_og_image_real",
    "_extraer_og_image",
    # actividad / autor / lecturas compartidas
    "registrar_etapa",
    "_autor_pipeline",
    "_copy_pendiente_leido",
    "_tiene_copy",
    "_MAX_INTENTOS_ETAPA",
    "intentos_de",
    "anotar_intento",
    "marcar_fallo_etapa",
    "temas_pipeline",
]

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
ETAPA_ARTE = "ARTE"

# FLUJO CONTINUO: el pipeline NO tiene topes por etapa (cribas QA/copies/autogen/revisados). El
# volumen lo regula la ADMISIÓN (`config.pipeline_max()` + el gate serial WIP
# `config.pipeline_en_vuelo_max()`, editables en el Monitor) y el backpressure de la cola.

# DEDUP de contenido: ventana (días) hacia atrás para considerar que una noticia "ya está" en la
# marca. Un tema nuevo cuyo título coincide (normalizado) con otro contenido de la MISMA marca
# creado en esta ventana NO se crea: cubre el duplicado en la cola (misma noticia por dos fuentes)
# y el republicado de lo ya salido hace poco. Fuera de la ventana, una noticia recurrente sí entra.
_DIAS_DEDUP = 60

# El pipeline no sabe de antemano si un ítem será FOTO o VIDEO, así que crea piezas de FOTO
# (regla del dueño: foto -> 3 redes IG/X/FB). El mapeo formato->redes vive en
# `redes.redes_de_formato` (fuente única); video -> las 5 queda definido para flujos futuros.
_FORMATO_PIPELINE = redes.FORMATO_FOTO

# --- QA de la FUENTE por DOCUMENTO de Texto (no skills) ------------------------------
# El equipo NO usa skills: la criba pre-copy de la FUENTE se hace adjuntando un DOCUMENTO de la
# Texto con los criterios. Regla del dueño: "si el documento existe, adjúntalo; si no existe,
# créalo y adjúntalo." Apunta al prompt EDITABLE `prompt/qa-fuente` (pestaña «Prompts»), cuyo
# cuerpo base viaja en la semilla. El título DEBE sluggear al id (`crear` deriva el id del
# slug del título): "QA fuente" -> "prompt/qa-fuente". DISTINTO del QA de COPY (`prompt/qa-editorial`).
PROMPT_QA_ID = "prompt/qa-fuente"
_TITULO_QA = "QA fuente"

# Veredicto SENTINEL que se persiste en el TEMA mientras su QA de la fuente (claude -p) está en
# vuelo: la fase QA NO lo re-lanza (deja de estar "sin veredicto") y la vista Pipelines pinta la
# etapa QA como "en curso". Al completar, el `procesar` lo sustituye por el veredicto real.
QA_EN_CURSO = "en_curso"

# Veredicto SENTINEL que se persiste cuando la etapa QA está DESACTIVADA para la marca (toggle
# `KENI_PIPELINE_VALIDACION` off): no se lanza la criba, pero el tema NO queda bloqueado: `temas_para_copy` lo acepta
# igual que un `no_verificado`, así el copy se genera sin criba. La vista Pipelines pinta QA como
# "saltada". Distinto de "sin veredicto" (que significaría "QA pendiente, aún por cribar").
QA_SALTADA = "saltada"

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


def _autor_pipeline() -> dict[str, str] | None:
    """Autor (brand-agnóstico) al que se atribuyen los lanzamientos del pipeline.

    Usa el usuario configurado del MCP (`config.mcp_usuario()`) si existe y resuelve a un
    usuario real; si no, el primer admin. None si no hay usuarios (best-effort: la generación
    seguirá funcionando con autor anónimo).
    """
    try:
        from .. import auth

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


# --------------------------------------------------------------------------- #
# Lecturas de temas compartidas entre etapas (QA y CD)                         #
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


# REINTENTOS ACOTADOS por etapa (flujo continuo): con el tick corto, una etapa que falla se
# relanzaría cada pocos segundos para siempre (bucle de tokens). Cada lanzamiento de QA/Copy
# anota su intento en `copy_pendiente` (JSON, sin migración de esquema); al agotarlos, el tema
# se marca `problema` con un hallazgo de sistema: SALE del cupo en vuelo (in=out se sostiene)
# y queda visible en Pipelines/tablero como fallo, para que un humano decida.
_MAX_INTENTOS_ETAPA = 3


def intentos_de(tema: dict[str, Any], campo: str) -> int:
    """Intentos ya consumidos de una etapa (`campo` = 'qa_intentos'/'cd_intentos'). 0 si no hay."""
    try:
        return int(_copy_pendiente_leido(tema).get(campo) or 0)
    except (TypeError, ValueError):
        return 0


def anotar_intento(tema: dict[str, Any], campo: str) -> None:
    """Suma 1 al contador de intentos de la etapa en `copy_pendiente` (best-effort, persiste).

    RE-LEE el tema de BD antes de escribir: con el lanzador SÍNCRONO de los tests, el `procesar`
    del copy puede haber LIMPIADO `copy_pendiente` (éxito) durante el propio lanzamiento; anotar
    sobre el dict viejo lo resucitaría. Si ya no hay pendiente, no hay nada que contar.
    """
    import json

    tema_id = (tema.get("id") or "").strip()
    if not tema_id:
        return
    try:
        fresco = repos.obtener_contenido(tema_id)
    except Exception:  # noqa: BLE001 -- sin lectura no anotamos (el tope simplemente no avanza)
        return
    if fresco is None or not (fresco.get("copy_pendiente") or "").strip():
        return  # éxito ya limpió el pendiente (o el tema desapareció): nada que anotar
    pend = _copy_pendiente_leido(fresco)
    pend[campo] = int(pend.get(campo) or 0) + 1
    try:
        repos.actualizar_contenido(tema_id, {"copy_pendiente": json.dumps(pend, ensure_ascii=False)})
    except Exception:  # noqa: BLE001 -- sin contador, el tope no aplica; el reintento sigue
        _log.warning("pipeline: no se pudo anotar el intento %s del tema %s", campo, tema_id, exc_info=True)


def marcar_fallo_etapa(tema_id: str, etapa: str, motivo: str) -> None:
    """Marca el tema con veredicto `problema` por fallo REPETIDO de una etapa (salida terminal).

    El tema sale del cupo en vuelo (deja de reintentarse y de bloquear la admisión de su marca)
    y el fallo queda visible (❗) con un hallazgo de sistema. Mismo formato que la criba QA.
    """
    import json

    hallazgos = [{
        "tipo": "sistema", "gravedad": "error", "fragmento": etapa,
        "explicacion": motivo, "sugerencia": "Revisa la generación o relanza a mano.",
    }]
    try:
        repos.actualizar_contenido(tema_id, {
            "qa_veredicto": VERDICTO_PROBLEMA,
            "qa_hallazgos": json.dumps(hallazgos, ensure_ascii=False),
        })
        _log.warning("pipeline: tema %s marcado problema por fallo repetido de %s", tema_id, etapa)
    except Exception:  # noqa: BLE001 -- best-effort; el tema seguirá reintentando si no persiste
        _log.warning("pipeline: no se pudo marcar el fallo terminal del tema %s", tema_id, exc_info=True)


def _tiene_copy(tema_id: str) -> bool:
    """True si el tema ya tiene al menos una pieza por plataforma (copy en marcha). Best-effort."""
    if not tema_id:
        return False
    try:
        return bool(repos.listar_contenido_plataforma(tema_id))
    except Exception:  # noqa: BLE001 -- sin lectura, conservador: asumimos que NO para reintentar
        return False


def temas_pipeline(marca: str | None = None) -> list[dict[str, Any]]:
    """TODOS los temas del pipeline (origen `pipeline`), en orden FIFO. [] si la lectura falla.

    NO recorta: el volumen lo acota la ADMISIÓN (gate serial en vuelo por marca), así que aquí
    solo puede haber, como mucho, lo admitido. `listar_contenido` ya ordena por prioridad y
    `fecha_objetivo/creado ASC`, así que el más antiguo PENDIENTE se atiende primero (justo).
    """
    try:
        items = repos.listar_contenido(marca=marca)
    except Exception:  # noqa: BLE001 -- sin temas legibles, el barrido no hace nada
        return []
    return [it for it in items if (it.get("origen") or "") == ORIGEN_PIPELINE]
