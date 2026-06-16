"""verificación — verificación de la FUENTE (pre-copy) + helper léxico de vista/detalle.

Por cada TEMA nuevo sin verificación, lanza un `claude -p` que evalúa la NOTA DE ORIGEN (no el copy:
aún no existe) contra el DOCUMENTO de criterios de la Texto, y persiste un verificación ESTRUCTURADO
(`no_verificado`/`problema`) sobre el tema. El verificación léxico (`verificacion_lexica`) es PURO y testeable.
"""

from __future__ import annotations

from typing import Any

from .. import config, generaciones, libtexto, marcas, redes, repos
from ..dominio import generar as gen_dom
from ..dominio import jobspec
from ..dominio import verificar_fuente as dom_verificar
from . import _ref
from ._comun import (
    _DEFAULT_VERIFICACION_CRITERIOS,
    _TITULO_VERIFICACION,
    ETAPA_VERIFICAR,
    PROMPT_VERIFICACION_ID,
    VERIFICACION_EN_CURSO,
    TIPO_PIPELINE,
    _log,
    registrar_etapa,
)

__all__ = [
    "verificacion_lexica",
    "asegurar_documento_verificacion",
    "dom_verificacion_titulo",
    "_contexto_verificacion_fuente",
    "lanzar_verificar_cluster",
]


def verificacion_lexica(publicacion: dict[str, Any]) -> dict[str, Any]:
    """Verificación léxico de UN borrador (PURO, testeable): `{verificacion, observaciones:[..]}`.

    Comprobaciones DETERMINISTAS y baratas (no editorial; el gancho al prompt `revision`
    real es un TODO):
      - copy no vacío,
      - longitud del copy <= límite duro de la red (`redes`), cuando la red tiene tope.

    Verdicto: "listo" sin observaciones; "revisar" si hay alguna. NUNCA "no_publicar" (la verificación
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
    verificacion = "listo" if not observaciones else "revisar"
    return {"verificacion": verificacion, "observaciones": observaciones}


def asegurar_documento_verificacion() -> str:
    """Garantiza que el DOCUMENTO de criterios de verificación existe en la Texto.

    Regla del dueño: "si el documento existe, adjúntalo; si no existe, créalo y adjúntalo." El
    equipo NO usa skills: el verificación se hace con un documento adjunto. Aquí:
      - si el documento (`PROMPT_VERIFICACION_ID`) ya está en el STORE de la Texto, lo respeta;
      - si no, lo CREA con el cuerpo de la inicial `prompt/verificar` (verificación pre-copy). IDEMPOTENTE.
    Devuelve `PROMPT_VERIFICACION_ID` si el documento queda disponible (creado o ya presente), o "" si no
    se pudo asegurar (best-effort: sin documento, la verificación de la fuente no corre y el tema queda sin
    verificación, de modo que la fase CD no genera copy hasta que haya verificación).

    Nota: la inicial del paquete ya trae un `prompt/verificar`; `cuerpo_efectivo` lo resuelve
    aunque no esté materializado en el store. Materializarlo aquí garantiza un documento EDITABLE
    por el equipo (la regla pide un documento real, adjuntable y versionado).
    """
    try:
        if libtexto.obtener(PROMPT_VERIFICACION_ID) is not None:
            return PROMPT_VERIFICACION_ID
        # No está en el store: si la inicial lo trae, ya hay cuerpo efectivo; aun así CREAMOS el
        # documento del store para que sea editable/adjuntable (la regla pide un doc real).
        # `PROMPT_VERIFICACION_ID` = `prompt/verificar`: la verificación pre-copy vive como prompt EDITABLE en la
        # Biblioteca (inicial del paquete); la constante es el último recurso si faltara.
        cuerpo_inicial = libtexto.cuerpo_efectivo(PROMPT_VERIFICACION_ID)
        cuerpo = cuerpo_inicial or _DEFAULT_VERIFICACION_CRITERIOS
        doc = libtexto.crear(_TITULO_VERIFICACION, tipo="prompt", cuerpo=cuerpo)
        # `crear` deriva el id del slug del título: "Verificar" -> "prompt/verificar".
        return doc.id if doc.id == PROMPT_VERIFICACION_ID else (PROMPT_VERIFICACION_ID if libtexto.obtener(PROMPT_VERIFICACION_ID) else doc.id)
    except Exception:  # noqa: BLE001 -- asegurar el doc es best-effort
        _log.warning("pipeline: no se pudo asegurar el documento de verificación", exc_info=True)
        return ""


def dom_verificacion_titulo(texto: str) -> str:
    """Título corto del verificación (deriva del texto, como el endpoint manual). Best-effort."""
    try:
        from ..dominio import stream

        return stream.derivar_titulo(texto)
    except Exception:  # noqa: BLE001 -- el título es cosmético; nunca rompe el verificación
        return (texto or "").strip().splitlines()[0][:80] if texto.strip() else "Nota"


def _contexto_verificacion_fuente(nota: str) -> str:
    """Bloque de contexto de la verificación de la FUENTE: la nota de origen a verificar (titulo+resumen+enlace)."""
    return "Nota de origen a verificar (aún no hay copy):\n\n" + nota


def _endurecer_verificacion_fuente() -> dict[str, Any] | None:
    """Overrides `endurecer` de la verificación de la fuente: modelo rápido + esfuerzo bajo + timeout corto.

    Es una verificación PERMISIVA (no redacción): corre con Haiku + `low` + ~180 s (configurables:
    `KENI_VERIFICACION_FUENTE_MODELO`, `KENI_VERIFICACION_FUENTE_ESFUERZO`, `KENI_VERIFICACION_FUENTE_TIMEOUT`). Se omiten las
    claves vacías (cada una cae a su global). None si no hay ningún override.
    """
    overrides: dict[str, Any] = {}
    modelo = config.verificacion_fuente_modelo()
    if modelo:
        overrides["modelo"] = modelo
    esfuerzo = config.verificacion_fuente_esfuerzo()
    if esfuerzo:
        overrides["esfuerzo"] = esfuerzo
    timeout = config.verificacion_fuente_timeout()
    if timeout > 0:
        overrides["timeout"] = timeout
    return overrides or None


def lanzar_verificar_cluster(
    cluster: dict[str, Any], *, autor: dict[str, str] | None
) -> dict[str, Any] | None:
    """verificación de la FUENTE sobre una HISTORIA (cluster) via `claude -p`, ANTES de materializar
    contenido de producción (ADR 0011 F3).

    Verificación la nota de origen del cluster (título + resumen + bloques de sus fuentes; usa los
    cuerpos ARCHIVADOS del feed, sin fetch HTTP — la verificación es permisiva) y sella el verificación en
    `noticias_clusters.verificacion_fuente` (no en `contenido`: la pieza aún no existe). El barrido de
    investigación admite luego solo las `no_verificado` (hereda el verificación al contenido) y deja
    fuera las `problema`. ASÍNCRONO: marca el cluster `en_curso` y devuelve la generación; None si
    no se pudo lanzar (sin doc / sin marca / sin nota). `ColaLlenaError` se PROPAGA (corta la fase
    verificación de esa marca). Runtime barato (Haiku/low/timeout corto, `_endurecer_verificacion_fuente`).
    """
    from . import _admitir

    cid = (cluster.get("id") or "").strip()
    if not cid:
        return None
    marca = (cluster.get("marca") or "").strip()
    if not marca or not marcas.es_marca(marca):
        return None
    titulo = (cluster.get("titulo_es") or cluster.get("titulo") or "").strip()
    resumen = (cluster.get("resumen_es") or cluster.get("resumen") or "").strip()
    try:
        items = repos.items_de_cluster(cid, limite=_admitir._MAX_ENLACES_CLUSTER)
    except Exception:  # noqa: BLE001 -- sin items legibles, verificamos con título+resumen igual
        items = []
    cuerpos = dict(repos.cuerpos_de_cluster(cid))  # archivados (gratis); sin fetch HTTP en verificación
    nota = _admitir._nota_de_cluster(titulo, resumen, items, cuerpos)[: gen_dom.MAX_TEXTO]
    if not nota.strip():
        return None

    doc_id = _ref.asegurar_documento_verificacion()
    cuerpo = libtexto.cuerpo_efectivo(doc_id) if doc_id else None
    if not cuerpo:
        return None  # sin documento de verificación no hay verificación: el cluster queda sin verificación.

    titulo = titulo or dom_verificacion_titulo(nota)
    prompt = gen_dom.componer(
        cuerpo,
        libtexto.editoriales_de_marca(marca, pipeline="verificar"),
        _contexto_verificacion_fuente(nota),
    )
    # Marca el cluster en curso ANTES de lanzar (la fase verificación no lo re-lanza). Con el lanzador
    # SÍNCRONO de los tests el `procesar` corre DURANTE `lanzar` y persiste el verificación real;
    # en prod (async) el orden es indiferente. El `procesar` lo sustituye por el real al fin.
    try:
        repos.marcar_cluster_verificacion(cid, VERIFICACION_EN_CURSO)
    except Exception:  # noqa: BLE001 -- best-effort; el doble-lanzamiento lo evita el sweep
        _log.warning("pipeline: no se pudo marcar el cluster en_curso para verificación (%s)", cid, exc_info=True)
    gen = gen_dom.lanzar(
        tipo=TIPO_PIPELINE,
        titulo=f"Verificar · {titulo}",
        marca=marca,
        prompt=prompt,
        # Sin contenido aún (verificación pre-admisión): se correla por cluster vía la spec/procesar.
        contenido_id="",
        clave_idem=generaciones.clave_idempotencia(
            (autor or {}).get("id", ""), TIPO_PIPELINE, marca, "verificación-cluster", cid
        ),
        procesar=dom_verificar.construir_procesar_verificacion_fuente(marca, titulo, autor, cluster_id=cid),
        procesar_spec=jobspec.construir_verificacion_fuente(
            marca=marca, titulo=titulo, autor=autor, cluster_id=cid,
        ),
        autor=autor,
        endurecer=_endurecer_verificacion_fuente(),
        # Frontera ADR 0011: la verificación/verificación de la fuente es INVESTIGACION (motor de noticias), no
        # produccion. Se sella en el registro para medir el coste de investigar por separado.
        proceso=generaciones.PROCESO_INVESTIGACION,
    )
    registrar_etapa(
        ETAPA_VERIFICAR,
        marca,
        f"Verificación de la fuente (claude) — '{titulo[:120]}'",
        gen_id=gen.get("id", "") if isinstance(gen, dict) else "",
    )
    return gen

