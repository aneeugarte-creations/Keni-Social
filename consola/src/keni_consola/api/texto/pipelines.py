"""Pipelines: registro/atribución, preview del prompt ensamblado, catálogo de variables,
la "máquina" (flujo de pipelines) y la estrategia editorial por marca.

OJO: nada que ver con `api/pipelines.py` (módulo aparte). Aquí vive el catálogo de procesos
de generación tal como lo consume el rediseño de la Biblioteca.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import libtexto
from ._comun import _MAX_TEXTO

# --------------------------------------------------------------------------- #
# Pipelines: registro, atribucion y preview del prompt ensamblado              #
# --------------------------------------------------------------------------- #


async def pipelines_listar(request: Request) -> Response:
    """`GET /api/texto/pipelines` -> `{pipelines: [{id, titulo, descripcion, rol, prompt_base_id}]}`.

    Es el catalogo de procesos de generacion: para cada uno, su prompt base EFECTIVO (resuelto
    por el registro, considerando rebindeos en la Texto). Sostiene la vista de atribucion.
    """
    items = []
    for pid, spec in libtexto.PIPELINES.items():
        try:
            base = libtexto.prompt_base_de(pid)
        except libtexto.TextoError:
            base = spec.get("prompt_defecto", "")
        items.append({
            "id": pid,
            "titulo": spec.get("titulo", pid),
            "descripcion": spec.get("descripcion", ""),
            "rol": spec.get("rol", ""),
            "prompt_base_id": base,
        })
    return JSONResponse({"pipelines": items})


async def pipeline_preview(request: Request) -> Response:
    """`GET /api/texto/pipelines/{pid}/preview?marca=&contexto=` -> prompt ENSAMBLADO.

    "Lo que inyectas es lo que ves": muestra el prompt final (base + editoriales + contexto)
    que recibiria `claude -p`, SIN lanzar nada. Resuelve de raiz "no se que se inyecta donde".
    """
    pid = request.path_params["pid"]
    if pid not in libtexto.PIPELINES:
        return JSONResponse({"error": "Pipeline desconocido."}, status_code=404)
    marca = request.query_params.get("marca") or ""
    contexto = request.query_params.get("contexto") or ""
    return JSONResponse(libtexto.previsualizar_pipeline(pid, marca, contexto[:_MAX_TEXTO]))


# --------------------------------------------------------------------------- #
# Catálogo de variables {{VAR}} + la "máquina" (flujo de pipelines)             #
# --------------------------------------------------------------------------- #


async def variables(request: Request) -> Response:
    """`GET /api/texto/variables` -> `{variables: [{nombre, descripcion, ejemplo, origen}]}`.

    Catálogo (en código, fuente única) de los marcadores `{{VAR}}` que la Consola sustituye
    al inyectar prompts: transparencia para el editor de la Biblioteca.
    """
    return JSONResponse({"variables": libtexto.catalogo_variables()})


# Las TRES MÁQUINAS del flujo (ADR 0011): Investigación (el motor de noticias), Producción
# (la máquina de contenido) y las Herramientas de importación. Cada etapa es:
#   - `mecanica`: paso del proceso SIN prompt de la Biblioteca (código puro, p. ej. Agrupar
#     léxico o Admitir). Da contexto: el flujo cuenta la historia completa
#     del proceso, no solo los prompts editables.
#   - `prompt` : etapa cuyo prompt vive en la Biblioteca. `doc_id=None` => se resuelve por el
#     REGISTRO (`prompt_base_de`, ver `_ETAPA_PIPELINE`): respeta rebindeos sin tocar código.
#
# El ORDEN sigue el modelo conceptual del ADR 0011 (frontera: Verificar la fuente es
# Investigación; Redactar/Ilustrar son Producción), apoyado en el orden real de los daemons
# (`recolectar_daemon.ejecutar_barrido`, `pipeline_contenido._barrido`). Donde difieren hoy
# manda el ADR: la marca se clasifica DENTRO de Agrupar y Verificar corre
# tras Admitir del lado `contenido` (hasta F3), pero el flujo los presenta como etapas del
# proceso de Investigación. Fusionar son DOS prompts: la verificación previa
# (`prompt/fusionar-verificar`) corre por grupo propuesto ANTES de fusionar.
#
# TERMINOLOGÍA (ADR 0011 §5 + páginas de proceso de F2): los títulos e ids de las etapas
# compartidas casan 1:1 con el flujo de la página Investigación (`/datos/investigacion`:
# Recolectar · Fusionar · Clasificar · Priorizar · Verificar) y con las etapas que muestra el
# hub Producción (`/datos/produccion`: Redactar · Ilustrar · Aprobar). Las etapas intermedias que
# esas páginas NO muestran (Agrupar, Traducir, Admitir…) se mantienen solo como
# contexto del proceso, en el vocabulario nuevo (verbos C).
# Tupla de etapa: (tipo, id, titulo, doc_id | None, seccion | None).
# Iconos en la UI: `mecanica` => ⚙ (determinista) · `prompt` => 🤖 (LLM).
_Etapa = tuple[str, str, str, str | None, str | None]
_MAQUINAS: tuple[tuple[str, str, str, tuple[_Etapa, ...]], ...] = (
    ("investigacion", "Investigación", "El motor de noticias", (
        ("mecanica", "recolectar", "Recolectar", None, None),
        ("mecanica", "agrupar", "Agrupar", None, None),
        ("prompt", "fusionar-verificar", "Fusionar · verificar", "prompt/fusionar-verificar", None),
        ("prompt", "fusionar", "Fusionar", "prompt/fusionar", None),
        ("prompt", "traducir", "Traducir", "prompt/traducir", None),
        ("prompt", "clasificar", "Clasificar", "prompt/clasificar-marca", None),
        ("prompt", "priorizar", "Priorizar", "prompt/priorizar", None),
        ("mecanica", "admitir", "Admitir", None, None),
        ("prompt", "verificar", "Verificar", None, None),  # prompt_base_de("verificar")
    )),
    ("produccion", "Producción", "La máquina de contenido", (
        ("prompt", "redactar", "Redactar", None, None),          # prompt_base_de("redactar")
        ("mecanica", "revisar", "Revisar", None, None),
        ("prompt", "ilustrar", "Ilustrar", "prompt/ilustrar", None),
        ("mecanica", "aprobar", "Aprobar", None, None),
        ("mecanica", "publicar", "Publicar", None, None),
        ("prompt", "idear", "Idear", None, "taller"),            # prompt_base_de("idear")
    )),
    ("importacion", "Herramientas de importación", "Material recibido del equipo", (
        ("prompt", "recibir-portal", "Recibir · Portal/SMS", "prompt/recibir/portal", None),
        ("prompt", "recibir-corresponsales", "Recibir · Corresponsales", "prompt/recibir/corresponsales", None),
        ("prompt", "recibir-reporteros", "Recibir · Reporteros", "prompt/recibir/reporteros", None),
        ("prompt", "recibir-eventos-claro", "Recibir · Eventos Claro Sports", "prompt/recibir/eventos-claro", None),
        ("prompt", "importar-calendario", "Importar calendario", "prompt/importar/calendario", None),
        ("prompt", "importar-parrilla", "Importar rota/parrilla", "prompt/importar/parrilla", None),
    )),
)

# id de etapa -> pipeline del registro cuyo prompt base efectivo la alimenta (rebindeable).
# Los valores son las CLAVES del registro `libtexto.PIPELINES` (verificar/redactar/idear), estables.
_ETAPA_PIPELINE = {"verificar": "verificar", "redactar": "redactar", "idear": "idear"}


def _doc_id_de_etapa(eid: str, doc_id: str | None) -> str:
    """Resuelve el doc de una etapa `prompt`: fijo, o el prompt base EFECTIVO del registro."""
    if doc_id is not None:
        return doc_id
    pipeline = _ETAPA_PIPELINE[eid]
    try:
        return libtexto.prompt_base_de(pipeline)
    except libtexto.TextoError:
        return libtexto.PIPELINES.get(pipeline, {}).get("prompt_defecto", "")


async def maquina(request: Request) -> Response:
    """`GET /api/texto/maquina?marca=` -> `{maquinas}`: las TRES máquinas del ADR 0011.

    Forma (CONTRATO con el frontend del rediseño): `maquinas` es la lista
    Investigación -> Producción -> Importación; cada una `{id, titulo, subtitulo, etapas}`
    con sus etapas en el orden del proceso (ver `_MAQUINAS`):
      - etapa `mecanica`: `{tipo, id, titulo}` (sin prompt de la Biblioteca; contexto).
      - etapa `prompt`  : `{tipo, id, titulo, doc_id, produccion, sha_actual, sin_publicar}`
        (+ `seccion` opcional, p. ej. `"taller"` para Idear) con el estado de
        publicación del documento que se inyecta en esa etapa.

    Las CAPAS editoriales ya no salen aquí: el ensamblaje por marca vive en
    `GET /api/texto/estrategia?marca=` (`orden_inyeccion` + pilares). `marca` se acepta
    por compatibilidad pero el flujo es global (no depende de la marca).
    """
    punteros = libtexto.producciones()
    shas = libtexto.shas_actuales()

    def estado(doc_id: str) -> dict[str, object]:
        return libtexto.estado_publicacion(doc_id, punteros=punteros, shas=shas)

    maquinas = []
    for mid, titulo, subtitulo, etapas in _MAQUINAS:
        filas: list[dict[str, object]] = []
        for tipo, eid, etitulo, doc_id, seccion in etapas:
            if tipo == "mecanica":
                filas.append({"tipo": "mecanica", "id": eid, "titulo": etitulo})
                continue
            efectivo = _doc_id_de_etapa(eid, doc_id)
            fila: dict[str, object] = {
                "tipo": "prompt", "id": eid, "titulo": etitulo,
                "doc_id": efectivo, **estado(efectivo),
            }
            if seccion:
                fila["seccion"] = seccion
            filas.append(fila)
        maquinas.append({"id": mid, "titulo": titulo, "subtitulo": subtitulo, "etapas": filas})
    return JSONResponse({"maquinas": maquinas})


# Los 4+1 pilares de la estrategia de marca, SIEMPRE presentes y en orden fijo: los 4
# obligatorios (`PILARES_EDITORIALES`) + `reglas` (auxiliar). El bool es el `global` que se
# etiqueta cuando NO hay documento (con doc manda `es_editorial_global`, el mismo criterio
# que usa el auto-adjunto).
_PILARES_ESTRATEGIA: tuple[tuple[str, str, bool], ...] = (
    ("marca", "Identidad de marca", False),
    ("voz", "Voz y tono", False),
    ("tropicalizacion", "Tropicalización MX", True),
    ("plataforma", "Convenciones de plataforma", True),
    ("reglas", "Reglas globales", True),
)


async def estrategia(request: Request) -> Response:
    """`GET /api/texto/estrategia?marca=` -> la estrategia editorial de la marca.

    Forma (CONTRATO con el frontend del rediseño de "Estrategia de marca"):
      - `marca`: la pedida (puede ser "").
      - `completitud`: `{completa, faltan, recomendacion}` (misma lógica que `/validacion`).
      - `pilares`: SIEMPRE los 4+1 en orden fijo (marca, voz, tropicalizacion, plataforma,
        reglas); cada uno `{clase, titulo, doc_id|null, vacio, global, produccion,
        sha_actual, sin_publicar, actualizado}`. Sin documento: `doc_id` null y `vacio`
        true. `vacio` = cuerpo en blanco (mismo criterio que `/validacion`).
      - `extras`: documentos editoriales del auto-adjunto SIN clase-pilar (p. ej. los
        patrones medidos), con la misma forma (titulo = el del documento).
      - `orden_inyeccion`: ids en el ORDEN real de `adjuntos_copy()` para esa marca (lo
        que se adjunta al copy, capa a capa).
    """
    from ...dominio import generar  # perezoso: generar importa libtexto

    marca = request.query_params.get("marca") or ""
    punteros = libtexto.producciones()
    shas = libtexto.shas_actuales()

    def fila_doc(d: libtexto.Documento) -> dict[str, object]:
        return {
            "doc_id": d.id,
            "vacio": not d.cuerpo.strip(),
            "global": libtexto.es_editorial_global(d),
            **libtexto.estado_publicacion(d.id, punteros=punteros, shas=shas),
            "actualizado": d.actualizado,
        }

    docs = libtexto.editoriales_de_marca(marca)
    # Primer doc por clase en el orden del auto-adjunto: el que representa al pilar.
    por_clase: dict[str, libtexto.Documento] = {}
    for d in docs:
        por_clase.setdefault(d.clase, d)

    pilares: list[dict[str, object]] = []
    for clase, titulo, global_defecto in _PILARES_ESTRATEGIA:
        d = por_clase.get(clase)
        if d is None:
            pilares.append({
                "clase": clase, "titulo": titulo, "doc_id": None, "vacio": True,
                "global": global_defecto, "produccion": None, "sha_actual": None,
                "sin_publicar": False, "actualizado": None,
            })
        else:
            pilares.append({"clase": clase, "titulo": titulo, **fila_doc(d)})

    clases_pilar = {clase for clase, _, _ in _PILARES_ESTRATEGIA}
    extras = [
        {"clase": d.clase, "titulo": d.titulo, **fila_doc(d)}
        for d in docs
        if d.clase not in clases_pilar
    ]

    completitud = {
        k: v
        for k, v in libtexto.validacion_editorial(marca).items()
        if k in ("completa", "faltan", "recomendacion")
    }
    return JSONResponse({
        "marca": marca,
        "completitud": completitud,
        "pilares": pilares,
        "extras": extras,
        "orden_inyeccion": [d.id for d in generar.adjuntos_copy(marca)],
    })
