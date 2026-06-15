"""QA — verificación de la FUENTE (pre-copy) + helper léxico de vista/detalle.

Por cada TEMA nuevo sin veredicto, lanza un `claude -p` que evalúa la NOTA DE ORIGEN (no el copy:
aún no existe) contra el DOCUMENTO de criterios de la Texto, y persiste un veredicto ESTRUCTURADO
(`no_verificado`/`problema`) sobre el tema. El veredicto léxico (`qa_lexico`) es PURO y testeable.
"""

from __future__ import annotations

from typing import Any

from .. import config, generaciones, libtexto, marcas, redes, repos
from ..dominio import generar as gen_dom
from ..dominio import jobspec
from ..dominio import verificar_fuente as dom_verificar
from . import _ref
from ._comun import (
    _DEFAULT_QA_CRITERIOS,
    _TITULO_QA,
    ETAPA_VERIFICAR,
    PROMPT_QA_ID,
    QA_EN_CURSO,
    TIPO_PIPELINE,
    _copy_pendiente_leido,
    _log,
    registrar_etapa,
    temas_pipeline,
)

__all__ = [
    "qa_lexico",
    "asegurar_documento_qa",
    "dom_qa_titulo",
    "_contexto_qa_fuente",
    "lanzar_verificar_fuente",
    "lanzar_verificar_cluster",
    "temas_sin_verificar",
]


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
      - si no, lo CREA con el cuerpo de la inicial `prompt/verificar` (verificación pre-copy). IDEMPOTENTE.
    Devuelve `PROMPT_QA_ID` si el documento queda disponible (creado o ya presente), o "" si no
    se pudo asegurar (best-effort: sin documento, la QA de la fuente no corre y el tema queda sin
    veredicto, de modo que la fase CD no genera copy hasta que haya verificación).

    Nota: la inicial del paquete ya trae un `prompt/verificar`; `cuerpo_efectivo` lo resuelve
    aunque no esté materializado en el store. Materializarlo aquí garantiza un documento EDITABLE
    por el equipo (la regla pide un documento real, adjuntable y versionado).
    """
    try:
        if libtexto.obtener(PROMPT_QA_ID) is not None:
            return PROMPT_QA_ID
        # No está en el store: si la inicial lo trae, ya hay cuerpo efectivo; aun así CREAMOS el
        # documento del store para que sea editable/adjuntable (la regla pide un doc real).
        # `PROMPT_QA_ID` = `prompt/verificar`: la verificación pre-copy vive como prompt EDITABLE en la
        # Biblioteca (inicial del paquete); la constante es el último recurso si faltara.
        cuerpo_inicial = libtexto.cuerpo_efectivo(PROMPT_QA_ID)
        cuerpo = cuerpo_inicial or _DEFAULT_QA_CRITERIOS
        doc = libtexto.crear(_TITULO_QA, tipo="prompt", cuerpo=cuerpo)
        # `crear` deriva el id del slug del título: "Verificar" -> "prompt/verificar".
        return doc.id if doc.id == PROMPT_QA_ID else (PROMPT_QA_ID if libtexto.obtener(PROMPT_QA_ID) else doc.id)
    except Exception:  # noqa: BLE001 -- asegurar el doc es best-effort
        _log.warning("pipeline: no se pudo asegurar el documento de QA", exc_info=True)
        return ""


def dom_qa_titulo(texto: str) -> str:
    """Título corto del QA (deriva del texto, como el endpoint manual). Best-effort."""
    try:
        from ..dominio import stream

        return stream.derivar_titulo(texto)
    except Exception:  # noqa: BLE001 -- el título es cosmético; nunca rompe el QA
        return (texto or "").strip().splitlines()[0][:80] if texto.strip() else "Nota"


def _contexto_qa_fuente(nota: str) -> str:
    """Bloque de contexto de la QA de la FUENTE: la nota de origen a verificar (titulo+resumen+enlace)."""
    return "Nota de origen a verificar (aún no hay copy):\n\n" + nota


def _endurecer_qa_fuente() -> dict[str, Any] | None:
    """Overrides `endurecer` de la verificación de la fuente: modelo rápido + esfuerzo bajo + timeout corto.

    Es una verificación PERMISIVA (no redacción): corre con Haiku + `low` + ~180 s (configurables:
    `KENI_QA_FUENTE_MODELO`, `KENI_QA_FUENTE_ESFUERZO`, `KENI_QA_FUENTE_TIMEOUT`). Se omiten las
    claves vacías (cada una cae a su global). None si no hay ningún override.
    """
    overrides: dict[str, Any] = {}
    modelo = config.qa_fuente_modelo()
    if modelo:
        overrides["modelo"] = modelo
    esfuerzo = config.qa_fuente_esfuerzo()
    if esfuerzo:
        overrides["esfuerzo"] = esfuerzo
    timeout = config.qa_fuente_timeout()
    if timeout > 0:
        overrides["timeout"] = timeout
    return overrides or None


def lanzar_verificar_fuente(
    tema: dict[str, Any], *, autor: dict[str, str] | None
) -> dict[str, Any] | None:
    """QA de la FUENTE via `claude -p`: verifica la NOTA de origen de un TEMA contra el doc de Texto.

    Rediseño QPC (pre-copy, por TEMA): evalúa el material de origen (no el copy: aún no existe) y
    persiste un veredicto ESTRUCTURADO (`no_verificado`/`problema`) + hallazgos sobre el TEMA
    (`construir_procesar_qa_fuente`). Reutiliza el camino PROBADO de generaciones (`gen_dom.lanzar`).
    El stream queda en la generación; el marcador QA la enlaza por `gen_id` (su proceso se ve en
    el detalle del pipeline).

    ASÍNCRONO: encola y devuelve la generación; marca el tema `verificar_veredicto='en_curso'` para que
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
    doc_id = _ref.asegurar_documento_qa()
    cuerpo = libtexto.cuerpo_efectivo(doc_id) if doc_id else None
    if not cuerpo:
        return None  # sin documento de QA no hay verificación: el tema queda sin veredicto (sin copy).

    titulo = (tema.get("titulo") or "").strip() or dom_qa_titulo(nota)
    prompt = gen_dom.componer(
        cuerpo,
        libtexto.editoriales_de_marca(marca, pipeline="verificar"),
        _contexto_qa_fuente(nota),
    )
    # Marca el tema en curso ANTES de lanzar (para que la fase QA no lo re-lance). CLAVE con el
    # lanzador SÍNCRONO de los tests: el `procesar` corre DURANTE `lanzar` y persiste el veredicto
    # real; si marcáramos en_curso DESPUÉS, sobrescribiría ese veredicto. En prod (async) el orden
    # es indiferente; así queda correcto en ambos. El `procesar` lo sustituye por el real al fin.
    try:
        repos.actualizar_contenido(tema_id, {"verificar_veredicto": QA_EN_CURSO})
    except Exception:  # noqa: BLE001 -- best-effort; sin esto el doble-lanzamiento lo evita el sweep
        _log.warning("pipeline: no se pudo marcar el tema en_curso para QA (%s)", tema_id, exc_info=True)
    gen = gen_dom.lanzar(
        tipo=TIPO_PIPELINE,
        # Etiqueta HUMANA en Actividad: el nombre de la etapa ("Verificar", como en la vista
        # Pipelines) + el TEMA verificado. Sin el tema, N verificaciones simultáneas eran N filas idénticas
        # en el feed ("Verificar la fuente · UnoTV" ×16) imposibles de distinguir.
        titulo=f"Verificar · {titulo}",
        marca=marca,
        prompt=prompt,
        # Correlación con el TEMA: Producción suma las métricas de la verificación en su run.
        contenido_id=tema_id,
        # CLAVE ESTABLE por tema: el prompt lleva un nonce por llamada (anti-inyección) y la
        # clave por defecto (hash del prompt) nunca coincidiría. Con esta, un re-lanzamiento de
        # la verificación del MISMO tema mientras hay una en curso devuelve ese run (cinturón además
        # del marcador `en_curso`, que una reparación/reset puede limpiar a destiempo).
        clave_idem=generaciones.clave_idempotencia(
            (autor or {}).get("id", ""), TIPO_PIPELINE, marca, "qa-fuente", tema_id
        ),
        procesar=dom_verificar.construir_procesar_qa_fuente(
            marca, titulo, autor, contenido_id=tema_id,
        ),
        procesar_spec=jobspec.construir_qa_fuente(
            marca=marca, titulo=titulo, autor=autor, contenido_id=tema_id,
        ),
        autor=autor,
        # Verificación QA de la FUENTE = VERIFICACIÓN con SALIDA ESTRUCTURADA (veredicto
        # `no_verificado`/`problema` + hallazgos, parseados; el usuario no ve la salida cruda).
        # Corroborar el material puede requerir LEER la fuente: NO se le veta la web. Queda la
        # veta global `Bash Write Edit`.
        # VERIFICACIÓN BARATA: la QA de la fuente es un filtro permisivo, no redacción. Corre con un
        # modelo rápido (def Haiku), esfuerzo bajo y timeout corto (def 180 s), configurables
        # por env (`KENI_QA_FUENTE_MODELO`/`_ESFUERZO`/`_TIMEOUT`). Solo endurece; vacío = global.
        endurecer=_endurecer_qa_fuente(),
        # Frontera ADR 0011: la verificación/QA de la fuente es INVESTIGACION (motor de noticias), no
        # produccion. Se sella en el registro para medir el coste de investigar por separado.
        proceso=generaciones.PROCESO_INVESTIGACION,
    )
    registrar_etapa(
        ETAPA_VERIFICAR,
        marca,
        f"Verificación de la fuente (claude) — '{titulo[:120]}'",
        contenido_id=tema_id,
        gen_id=gen.get("id", "") if isinstance(gen, dict) else "",
    )
    return gen


def lanzar_verificar_cluster(
    cluster: dict[str, Any], *, autor: dict[str, str] | None
) -> dict[str, Any] | None:
    """QA de la FUENTE sobre una HISTORIA (cluster) via `claude -p`, ANTES de materializar
    contenido de producción (ADR 0011 F3).

    Verificación la nota de origen del cluster (título + resumen + bloques de sus fuentes; usa los
    cuerpos ARCHIVADOS del feed, sin fetch HTTP — la verificación es permisiva) y sella el veredicto en
    `noticias_clusters.verificar_veredicto` (no en `contenido`: la pieza aún no existe). El barrido de
    investigación admite luego solo las `no_verificado` (hereda el veredicto al contenido) y deja
    fuera las `problema`. ASÍNCRONO: marca el cluster `en_curso` y devuelve la generación; None si
    no se pudo lanzar (sin doc / sin marca / sin nota). `ColaLlenaError` se PROPAGA (corta la fase
    QA de esa marca). Mismo runtime barato (Haiku/low/timeout corto) que `lanzar_verificar_fuente`.
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
    cuerpos = dict(repos.cuerpos_de_cluster(cid))  # archivados (gratis); sin fetch HTTP en QA
    nota = _admitir._nota_de_cluster(titulo, resumen, items, cuerpos)[: gen_dom.MAX_TEXTO]
    if not nota.strip():
        return None

    doc_id = _ref.asegurar_documento_qa()
    cuerpo = libtexto.cuerpo_efectivo(doc_id) if doc_id else None
    if not cuerpo:
        return None  # sin documento de QA no hay verificación: el cluster queda sin veredicto.

    titulo = titulo or dom_qa_titulo(nota)
    prompt = gen_dom.componer(
        cuerpo,
        libtexto.editoriales_de_marca(marca, pipeline="verificar"),
        _contexto_qa_fuente(nota),
    )
    # Marca el cluster en curso ANTES de lanzar (la fase QA no lo re-lanza). Con el lanzador
    # SÍNCRONO de los tests el `procesar` corre DURANTE `lanzar` y persiste el veredicto real;
    # en prod (async) el orden es indiferente. El `procesar` lo sustituye por el real al fin.
    try:
        repos.marcar_cluster_qa(cid, QA_EN_CURSO)
    except Exception:  # noqa: BLE001 -- best-effort; el doble-lanzamiento lo evita el sweep
        _log.warning("pipeline: no se pudo marcar el cluster en_curso para QA (%s)", cid, exc_info=True)
    gen = gen_dom.lanzar(
        tipo=TIPO_PIPELINE,
        titulo=f"Verificar · {titulo}",
        marca=marca,
        prompt=prompt,
        # Sin contenido aún (QA pre-admisión): se correla por cluster vía la spec/procesar.
        contenido_id="",
        clave_idem=generaciones.clave_idempotencia(
            (autor or {}).get("id", ""), TIPO_PIPELINE, marca, "qa-cluster", cid
        ),
        procesar=dom_verificar.construir_procesar_qa_fuente(marca, titulo, autor, cluster_id=cid),
        procesar_spec=jobspec.construir_qa_fuente(
            marca=marca, titulo=titulo, autor=autor, cluster_id=cid,
        ),
        autor=autor,
        endurecer=_endurecer_qa_fuente(),
        # Frontera ADR 0011: la verificación/QA de la fuente es INVESTIGACION (motor de noticias), no
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


def temas_sin_verificar(marca: str | None = None) -> list[dict[str, Any]]:
    """Temas del pipeline SIN veredicto de QA todavía (verificación pendiente). Best-effort.

    Excluye los `en_curso` (su QA está en curso) y los ya verificados (`no_verificado`/`problema`).
    SIN recorte: el volumen lo acota la ADMISIÓN (el gate serial en curso por marca); aquí solo
    puede haber, como mucho, lo admitido. La cola de generación pone el backpressure real
    (`ColaLlenaError` corta la fase y el siguiente tick reintenta).
    """
    return [t for t in temas_pipeline(marca) if not (t.get("verificar_veredicto") or "").strip()]
