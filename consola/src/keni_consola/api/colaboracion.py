"""API COLABORACION del tablero de contenido (inspirada en Planable):

  - Comentarios internos por pieza (hilo de discusion de redaccion).
  - Historial de versiones del copy de una plataforma (ver + revertir).
  - Aprobacion MULTINIVEL de una plataforma con roles y trazabilidad.

Todo cuelga del modelo `contenido`/`contenido_plataforma` (api/contenido.py) SIN tocar
su esquema: tres familias de tablas apendidas (`contenido_comentarios`,
`contenido_copy_versiones`, `contenido_aprobaciones`). Multiusuario via el middleware
(autoria/decisor desde `request.state.usuario`).

ENDPOINTS

  Comentarios (hilo por item de contenido; `plataforma_id` opcional ata una red):
    GET    /api/contenido/{cid}/comentarios[?plataforma_id=]
    POST   /api/contenido/{cid}/comentarios            {texto, plataforma_id?}
    PATCH  /api/comentarios/{id}                        {texto?, resuelto?}  (autor o admin)
    DELETE /api/comentarios/{id}                        (autor o admin)

  Versiones de copy (snapshot inmutable; revertir reescribe el copy vivo):
    GET    /api/plataformas/{pid}/copy/versiones
    POST   /api/plataformas/{pid}/copy                 {copy, nota?}  (guarda + snapshot previo)
    POST   /api/plataformas/{pid}/copy/revertir        {version_id}

  Aprobacion multinivel (cadena de niveles por pieza):
    GET    /api/plataformas/{pid}/aprobacion
    POST   /api/plataformas/{pid}/aprobacion            {etiquetas?}  (crea/recrea la cadena)
    POST   /api/aprobacion-nivel/{id}/decidir           {decision, comentario?}

SEPARACION DE FUNCIONES: en la cadena multinivel, quien decide un nivel no puede ser el
autor de la pieza (salvo admin), igual que el flujo legado (#9). Se decide POR ORDEN.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import config, repos
from .._http_json import leer_json
from ..dominio import colaboracion
from ..estados import CADENA_APROBACION_DEFECTO, ROL_ADMIN
from ..seguridad import autor_de_peticion

_MAX_TEXTO = 8000
_MAX_NIVELES = 6
_MAX_ETIQUETA = 60


def _rol_de_peticion(request: Request) -> str | None:
    """Rol del usuario de la sesion (None si entro por token de bootstrap / sin sesion)."""
    usuario = getattr(request.state, "usuario", None)
    if isinstance(usuario, dict):
        return usuario.get("rol")
    return None


def _cargo_de_peticion(request: Request) -> str:
    """Cargo del organigrama del usuario de la sesion ("" si por token / sin cargo). Item C."""
    usuario = getattr(request.state, "usuario", None)
    if isinstance(usuario, dict):
        return usuario.get("cargo", "") or ""
    return ""


def _puede_gestionar(request: Request, autor_id: str) -> bool:
    """True si quien pide es el autor del recurso, un admin, o entro por token (mantenimiento)."""
    autor = autor_de_peticion(request)
    if autor is None:  # token de bootstrap / sin sesion => mantenimiento
        return True
    if _rol_de_peticion(request) == ROL_ADMIN:
        return True
    return bool(autor_id) and autor.get("id") == autor_id


# --------------------------------------------------------------------------- #
# Comentarios internos                                                         #
# --------------------------------------------------------------------------- #


async def listar_comentarios(request: Request) -> Response:
    """GET /api/contenido/{cid}/comentarios: hilo del item (filtro opcional por plataforma)."""
    contenido_id = request.path_params["contenido_id"]
    if repos.obtener_contenido(contenido_id) is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    # `?plataforma_id=` presente (aunque vacio) filtra esa red; ausente = todo el hilo.
    plataforma_id = request.query_params.get("plataforma_id")
    comentarios = repos.listar_comentarios(contenido_id, plataforma_id)
    return JSONResponse({"comentarios": comentarios, "total": len(comentarios)})


async def crear_comentario(request: Request) -> Response:
    """POST /api/contenido/{cid}/comentarios: anade un comentario al hilo."""
    contenido_id = request.path_params["contenido_id"]
    if repos.obtener_contenido(contenido_id) is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    texto = datos.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        return JSONResponse({"error": "El comentario no puede estar vacío."}, status_code=400)

    plataforma_id = datos.get("plataforma_id", "") or ""
    if not isinstance(plataforma_id, str):
        plataforma_id = ""
    plataforma_id = plataforma_id.strip()
    if plataforma_id:
        plat = repos.obtener_contenido_plataforma(plataforma_id)
        if plat is None or plat.get("contenido_id") != contenido_id:
            return JSONResponse({"error": "Esa plataforma no es de este contenido."}, status_code=400)

    comentario = repos.crear_comentario(
        contenido_id=contenido_id,
        plataforma_id=plataforma_id,
        texto=texto.strip()[:_MAX_TEXTO],
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"comentario": comentario}, status_code=201)


async def actualizar_comentario(request: Request) -> Response:
    """PATCH /api/comentarios/{id}: edita texto y/o resuelto (solo autor o admin para el texto)."""
    comentario_id = request.path_params["comentario_id"]
    actual = repos.obtener_comentario(comentario_id)
    if actual is None:
        return JSONResponse({"error": "Ese comentario ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "texto" in datos:
        texto = datos.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            return JSONResponse({"error": "El comentario no puede estar vacío."}, status_code=400)
        if not _puede_gestionar(request, actual.get("autor_id", "")):
            return JSONResponse({"error": "Solo el autor puede editar su comentario."}, status_code=403)
        campos["texto"] = texto.strip()[:_MAX_TEXTO]
    # Marcar resuelto/reabrir lo puede hacer cualquiera del equipo (es un estado del hilo).
    if "resuelto" in datos:
        campos["resuelto"] = bool(datos["resuelto"])

    if not campos:
        return JSONResponse({"error": "Indica algún campo a actualizar."}, status_code=400)
    actualizado = repos.actualizar_comentario(comentario_id, campos)
    if actualizado is None:
        return JSONResponse({"error": "Ese comentario ya no existe."}, status_code=404)
    return JSONResponse({"comentario": actualizado})


async def borrar_comentario(request: Request) -> Response:
    """DELETE /api/comentarios/{id}: borra un comentario (solo autor o admin)."""
    comentario_id = request.path_params["comentario_id"]
    actual = repos.obtener_comentario(comentario_id)
    if actual is None:
        return JSONResponse({"error": "Ese comentario ya no existe."}, status_code=404)
    if not _puede_gestionar(request, actual.get("autor_id", "")):
        return JSONResponse({"error": "Solo el autor puede borrar su comentario."}, status_code=403)
    repos.borrar_comentario(comentario_id)
    return JSONResponse({"mensaje": "Comentario borrado."})


# --------------------------------------------------------------------------- #
# Historial de versiones del copy                                             #
# --------------------------------------------------------------------------- #


async def listar_copy_versiones(request: Request) -> Response:
    """GET /api/plataformas/{pid}/copy/versiones: historial (más reciente primero)."""
    plataforma_id = request.path_params["plataforma_id"]
    plat = repos.obtener_contenido_plataforma(plataforma_id)
    if plat is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    versiones = repos.listar_copy_versiones(plataforma_id)
    return JSONResponse({"versiones": versiones, "total": len(versiones), "copy_actual": plat.get("copy", "")})


async def guardar_copy(request: Request) -> Response:
    """POST /api/plataformas/{pid}/copy: snapshotea el copy ACTUAL y escribe el nuevo.

    Antes de pisar el copy vivo guarda una version inmutable del texto anterior (con autor
    y nota), de modo que el cambio quede en el historial y sea reversible. Si el copy no
    cambia, no hace nada (evita versiones duplicadas).
    """
    plataforma_id = request.path_params["plataforma_id"]
    plat = repos.obtener_contenido_plataforma(plataforma_id)
    if plat is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    datos = await leer_json(request)
    nuevo = datos.get("copy")
    if not isinstance(nuevo, str):
        return JSONResponse({"error": "El copy no es válido."}, status_code=400)
    nuevo = nuevo[:_MAX_TEXTO]
    nota = datos.get("nota", "")
    nota = nota.strip()[:_MAX_TEXTO] if isinstance(nota, str) else ""

    anterior = plat.get("copy", "")
    if nuevo == anterior:
        return JSONResponse({"plataforma": _plat_publica(plat), "version": None})

    # Snapshot del texto que se va a pisar (autoria = quien hace el cambio).
    version = repos.registrar_copy_version(
        plataforma_id=plataforma_id,
        contenido_id=plat.get("contenido_id", ""),
        copy=anterior,
        autor=autor_de_peticion(request),
        nota=nota,
    )
    actualizada = repos.actualizar_contenido_plataforma(
        plataforma_id, {"copy": nuevo, "falta_copy": not bool(nuevo.strip())}
    )
    if actualizada is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    return JSONResponse({"plataforma": _plat_publica(actualizada), "version": version})


async def revertir_copy(request: Request) -> Response:
    """POST /api/plataformas/{pid}/copy/revertir {version_id}: aplica una versión vieja.

    Revertir snapshotea PRIMERO el copy vivo actual (para no perderlo) y luego escribe el
    texto de la versión elegida como copy actual. Así el historial crece sin huecos.
    """
    plataforma_id = request.path_params["plataforma_id"]
    plat = repos.obtener_contenido_plataforma(plataforma_id)
    if plat is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    datos = await leer_json(request)
    version_id = datos.get("version_id")
    if not isinstance(version_id, str) or not version_id.strip():
        return JSONResponse({"error": "Indica la versión a revertir."}, status_code=400)
    version = repos.obtener_copy_version(version_id.strip())
    if version is None or version.get("plataforma_id") != plataforma_id:
        return JSONResponse({"error": "Esa versión no es de esta plataforma."}, status_code=400)

    objetivo = version.get("copy", "")
    actual = plat.get("copy", "")
    if objetivo != actual:
        repos.registrar_copy_version(
            plataforma_id=plataforma_id,
            contenido_id=plat.get("contenido_id", ""),
            copy=actual,
            autor=autor_de_peticion(request),
            nota=f"Antes de revertir a la versión {version.get('version', '')}",
        )
    actualizada = repos.actualizar_contenido_plataforma(
        plataforma_id, {"copy": objetivo, "falta_copy": not bool(objetivo.strip())}
    )
    if actualizada is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    return JSONResponse({"plataforma": _plat_publica(actualizada)})


# --------------------------------------------------------------------------- #
# Aprobacion multinivel                                                        #
# --------------------------------------------------------------------------- #


def _cadena_publica(plataforma_id: str) -> dict[str, object]:
    """Cadena de aprobacion + su estado global resumido + gates de gobernanza (para la UI).

    Incluye `aprobados`/`minimo_aprobaciones` (gate A: cuantas firmas lleva vs cuantas exige
    programar) y `comentarios_sin_resolver` (gate B: objeciones abiertas que bloquean publicar),
    para que la UI muestre el contador y deshabilite el boton de programar cuando no cumple.
    """
    cadena = repos.listar_aprobaciones(plataforma_id)
    plat = repos.obtener_contenido_plataforma(plataforma_id)
    sin_resolver = repos.comentarios_sin_resolver(
        (plat or {}).get("contenido_id", "") or "", plataforma_id
    )
    return {
        "niveles": cadena,
        "estado": colaboracion.estado_cadena(cadena),
        "nivel_actual": (colaboracion.nivel_actual(cadena) or {}).get("id", ""),
        "aprobados": colaboracion.contar_aprobados(cadena),
        "minimo_aprobaciones": config.min_aprobaciones(),
        "comentarios_sin_resolver": sin_resolver,
    }


async def obtener_aprobacion_cadena(request: Request) -> Response:
    """GET /api/plataformas/{pid}/aprobacion: la cadena de niveles y su estado global."""
    plataforma_id = request.path_params["plataforma_id"]
    if repos.obtener_contenido_plataforma(plataforma_id) is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    return JSONResponse(_cadena_publica(plataforma_id))


async def crear_aprobacion_cadena(request: Request) -> Response:
    """POST /api/plataformas/{pid}/aprobacion {etiquetas?}: crea o RECREA la cadena.

    `etiquetas` es la lista ordenada de niveles (1-based). Sin ella, usa la cadena por
    defecto del organigrama (Edición → Coordinación → Dirección). Recrear reinicia las
    decisiones (todos los niveles vuelven a `pendiente`).
    """
    plataforma_id = request.path_params["plataforma_id"]
    plat = repos.obtener_contenido_plataforma(plataforma_id)
    if plat is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    datos = await leer_json(request)
    etiquetas_raw = datos.get("etiquetas")
    if etiquetas_raw is None:
        etiquetas = list(CADENA_APROBACION_DEFECTO)
    elif isinstance(etiquetas_raw, list):
        etiquetas = [
            e.strip()[:_MAX_ETIQUETA] for e in etiquetas_raw if isinstance(e, str) and e.strip()
        ]
    else:
        return JSONResponse({"error": "Las etiquetas no son válidas."}, status_code=400)
    if not etiquetas:
        return JSONResponse({"error": "La cadena necesita al menos un nivel."}, status_code=400)
    # El nivel "QA Editorial" (si el flag lo activa) se antepone DENTRO de `montar_cadena`,
    # asi que cuenta para el limite de niveles.
    if len(etiquetas) + (1 if config.auto_qa_editorial() else 0) > _MAX_NIVELES:
        return JSONResponse(
            {"error": f"Demasiados niveles (máximo {_MAX_NIVELES})."}, status_code=400
        )

    # Cadena del TABLERO (recrear a mano): respeta el cargo del organigrama por nivel
    # (item C: Coordinación→coordinador, Dirección→director).
    montar_cadena_aprobacion(plataforma_id, plat, etiquetas, con_cargos=True)
    return JSONResponse(_cadena_publica(plataforma_id), status_code=201)


def montar_cadena_aprobacion(
    plataforma_id: str,
    plat: dict,
    etiquetas: list[str],
    *,
    con_cargos: bool,
) -> None:
    """Crea (o RECREA) la cadena de aprobacion de una pieza, con todos sus automatismos.

    Punto unico compartido por `crear_aprobacion_cadena` (recrear la cadena del tablero) y
    por `api/aprobacion.enviar_a_revision` (mandar al flujo "dale el OK" del feed). Pasos:

      1. item D — QA Editorial como PRIMER nivel automatico, si `KENI_AUTO_QA_EDITORIAL` lo
         activa (la "aprobacion de IA"). El ultimo nivel queda SIEMPRE humano.
      2. cargos por nivel: si `con_cargos`, se exige el cargo del organigrama derivado de la
         etiqueta (Coordinación→coordinador, etc.); si no, ningun nivel exige cargo (el flujo
         "dale el OK" del feed se abre a cualquiera del equipo, salvo el autor).
      3. crea la cadena (todos los niveles `pendiente`) via `repos.crear_cadena_aprobacion`.
      4. aplica el veredicto de QA al nivel automatico (best-effort) y la pre-aprobacion de
         piezas de bajo riesgo (ambos gateados por sus flags, def OFF).
    """
    if config.auto_qa_editorial():
        etiquetas = colaboracion.cadena_con_qa(etiquetas)
    cargos = [colaboracion.cargo_requerido_para(e) for e in etiquetas] if con_cargos else None
    repos.crear_cadena_aprobacion(
        plataforma_id=plataforma_id,
        contenido_id=plat.get("contenido_id", "") or "",
        etiquetas=etiquetas,
        cargos=cargos,
    )
    if config.auto_qa_editorial():
        _aplicar_qa_automatico(plataforma_id, plat)
    # fase3 (auto-planificacion): pre-aprobacion de piezas de bajo riesgo (gateada, def OFF).
    # Auto-aprueba los niveles INFERIORES, dejando el ULTIMO a un humano (trazable, decisor
    # "auto"). Si todo lo demas queda aprobado, la cadena solo espera el OK final.
    _aplicar_preaprobacion_bajo_riesgo(plataforma_id, plat)


def _aplicar_preaprobacion_bajo_riesgo(
    plataforma_id: str, plat: dict[str, object]
) -> None:
    """Auto-aprueba los niveles inferiores si la pieza es de bajo riesgo y el flag esta ON.

    Best-effort y SIN tocar el contrato de aprobacion: reutiliza la MISMA escritura de nivel
    (`repos.actualizar_aprobacion`) que una decision manual, solo que con el decisor reservado
    AUTO. El ultimo nivel NUNCA se auto-aprueba (la logica pura lo garantiza), asi que la pieza
    jamas queda totalmente aprobada por la maquina: siempre espera al humano final.
    """
    if not config.auto_preaprobacion():
        return
    contenido = repos.obtener_contenido(plat.get("contenido_id", "") or "")
    if not colaboracion.es_pieza_bajo_riesgo(plat, contenido):
        return
    cadena = repos.listar_aprobaciones(plataforma_id)
    for nivel_id, campos in colaboracion.autoaprobaciones_iniciales(
        cadena, activa=True, bajo_riesgo=True
    ):
        repos.actualizar_aprobacion(nivel_id, campos)


def _aplicar_qa_automatico(plataforma_id: str, plat: dict[str, object]) -> None:
    """Aplica el veredicto del QA editorial al PRIMER nivel "QA Editorial" de la cadena (item D).

    Best-effort y gateado (el llamante ya verifico el flag). Busca el ULTIMO veredicto de QA
    de la pieza (`repos.ultimo_veredicto_qa`) y lo traduce a la decision del nivel automatico:
    🟢 aprueba, 🟡 lo deja pendiente (a un humano), 🔴 lo rechaza (para la cadena). Si no hay
    veredicto disponible, el nivel queda `pendiente` (CONSERVADOR: nada se auto-decide sin
    evidencia de QA). El ULTIMO nivel de la cadena es humano y este nunca se toca.
    """
    cadena = repos.listar_aprobaciones(plataforma_id)
    # El nivel QA es el PRIMERO (nivel 1) y nunca el ultimo (hay al menos un humano detras).
    primero = colaboracion.nivel_actual(cadena)
    if (
        primero is None
        or len(cadena) <= 1
        or (primero.get("etiqueta") or "").strip().lower() != colaboracion.ETIQUETA_QA.lower()
    ):
        return
    veredicto = repos.ultimo_veredicto_qa(
        plataforma_id, plat.get("contenido_id", "") or ""
    )
    if not veredicto:
        return  # sin veredicto de QA: el nivel sigue pendiente, lo decide un humano.
    campos = colaboracion.campos_nivel_qa(veredicto.get("verdicto", ""), resumen=veredicto.get("resumen", ""))
    repos.actualizar_aprobacion(primero["id"], campos)


async def decidir_nivel(request: Request) -> Response:
    """POST /api/aprobacion-nivel/{id}/decidir {decision, comentario?}: aprueba/rechaza un nivel.

    Se decide POR ORDEN (solo el nivel pendiente más bajo). Un `rechazado` para la cadena.
    Cuando todos los niveles quedan `aprobado`, la pieza pasa a estado `aprobado` (se refleja
    en `contenido_plataforma.estado` y se baja el check `falta_revision`).
    """
    aprobacion_id = request.path_params["aprobacion_id"]
    nivel = repos.obtener_aprobacion(aprobacion_id)
    if nivel is None:
        return JSONResponse({"error": "Ese nivel de aprobación ya no existe."}, status_code=404)
    plataforma_id = nivel.get("plataforma_id", "")
    cadena = repos.listar_aprobaciones(plataforma_id)
    plat = repos.obtener_contenido_plataforma(plataforma_id)

    datos = await leer_json(request)
    decision = datos.get("decision")
    comentario = datos.get("comentario", "")
    comentario = comentario.strip()[:_MAX_TEXTO] if isinstance(comentario, str) else ""

    autor_pieza_id = (plat or {}).get("revisor_id", "") or ""  # quien la mandó a revisión
    if not autor_pieza_id and plat is not None:
        # Fallback: autor del contenido padre (quien la creó).
        padre = repos.obtener_contenido(plat.get("contenido_id", ""))
        autor_pieza_id = (padre or {}).get("autor_id", "") or ""

    campos, error = colaboracion.decidir(
        nivel,
        cadena,
        decision if isinstance(decision, str) else "",
        autor_de_peticion(request),
        rol=_rol_de_peticion(request),
        comentario=comentario,
        autor_pieza_id=autor_pieza_id,
        cargo_decisor=_cargo_de_peticion(request),
    )
    if error is not None:
        return JSONResponse({"error": error}, status_code=409)
    actualizado = repos.actualizar_aprobacion(aprobacion_id, campos)
    if actualizado is None:
        return JSONResponse({"error": "Ese nivel de aprobación ya no existe."}, status_code=404)

    # Reflejar el estado GLOBAL de la cadena en la pieza (si quedó totalmente aprobada).
    cadena = repos.listar_aprobaciones(plataforma_id)
    estado_global = colaboracion.estado_cadena(cadena)
    if estado_global == "aprobado" and plat is not None:
        repos.actualizar_contenido_plataforma(
            plataforma_id, {"estado": "aprobado", "falta_revision": False}
        )
    return JSONResponse(
        {"nivel": actualizado, "estado": estado_global, "niveles": cadena}
    )


def _plat_publica(plat: dict) -> dict:
    """Devuelve la fila de plataforma tal cual (sin enriquecer; la UI ya tiene `red_nombre`)."""
    return plat


RUTAS = [
    Route("/api/contenido/{contenido_id}/comentarios", listar_comentarios, methods=["GET"]),
    Route("/api/contenido/{contenido_id}/comentarios", crear_comentario, methods=["POST"]),
    Route("/api/comentarios/{comentario_id}", actualizar_comentario, methods=["PATCH"]),
    Route("/api/comentarios/{comentario_id}", borrar_comentario, methods=["DELETE"]),
    Route("/api/plataformas/{plataforma_id}/copy/versiones", listar_copy_versiones, methods=["GET"]),
    Route("/api/plataformas/{plataforma_id}/copy", guardar_copy, methods=["POST"]),
    Route("/api/plataformas/{plataforma_id}/copy/revertir", revertir_copy, methods=["POST"]),
    Route("/api/plataformas/{plataforma_id}/aprobacion", obtener_aprobacion_cadena, methods=["GET"]),
    Route("/api/plataformas/{plataforma_id}/aprobacion", crear_aprobacion_cadena, methods=["POST"]),
    Route("/api/aprobacion-nivel/{aprobacion_id}/decidir", decidir_nivel, methods=["POST"]),
]
