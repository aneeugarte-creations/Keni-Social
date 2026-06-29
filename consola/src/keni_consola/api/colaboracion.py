"""API COLABORACION del tablero de contenido (inspirada en Planable):

  - Comentarios internos por pieza (hilo de discusion de redaccion).
  - Historial de versiones del copy de una plataforma (ver + revertir).
  - Aprobacion MULTINIVEL de una plataforma con roles y trazabilidad.

Todo cuelga del modelo `contenido`/`pieza` (api/publicaciones.py) SIN tocar
su esquema: tres familias de tablas apendidas (`publicacion_comentarios`,
`pieza_copy_versiones`, `pieza_aprobaciones`). Multiusuario via el middleware
(autoria/decisor desde `request.state.usuario`).

ENDPOINTS

  Comentarios (hilo por item de contenido; `pieza_id` opcional ata una red):
    GET    /api/publicaciones/{cid}/comentarios[?pieza_id=]
    POST   /api/publicaciones/{cid}/comentarios            {texto, pieza_id?}
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

import logging

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from keni_shared import marcas as _km

from .. import config, repos
from .._http_json import leer_json
from ..dominio import colaboracion, notificaciones
from ..estados import CADENA_APROBACION_DEFECTO, ROL_ADMIN
from ..seguridad import autor_de_peticion

_log = logging.getLogger("keni_consola.api.colaboracion")

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


def _puede_gestionar(autor: dict | None, rol: str | None, autor_id: str) -> bool:
    """True si quien pide es el autor del recurso, un admin, o entro por token (mantenimiento)."""
    if autor is None:  # token de bootstrap / sin sesion => mantenimiento
        return True
    if rol == ROL_ADMIN:
        return True
    return bool(autor_id) and autor.get("id") == autor_id


# --------------------------------------------------------------------------- #
# Comentarios internos                                                         #
# --------------------------------------------------------------------------- #


def _listar_comentarios(publicacion_id: str, pieza_id: str | None) -> tuple[int, dict]:
    if repos.obtener_publicacion(publicacion_id) is None:
        return 404, {"error": "Ese contenido ya no existe."}
    comentarios = repos.listar_comentarios(publicacion_id, pieza_id)
    return 200, {"comentarios": comentarios, "total": len(comentarios)}


async def listar_comentarios(request: Request) -> Response:
    """GET /api/publicaciones/{cid}/comentarios: hilo del item (filtro opcional por plataforma)."""
    publicacion_id = request.path_params["publicacion_id"]
    # `?pieza_id=` presente (aunque vacio) filtra esa red; ausente = todo el hilo.
    pieza_id = request.query_params.get("pieza_id")
    status, cuerpo = await run_in_threadpool(_listar_comentarios, publicacion_id, pieza_id)
    return JSONResponse(cuerpo, status_code=status)


def _crear_comentario(
    publicacion_id: str, datos: dict, autor: dict | None, menciones: list[str]
) -> tuple[int, dict]:
    contenido = repos.obtener_publicacion(publicacion_id)
    if contenido is None:
        return 404, {"error": "Ese contenido ya no existe."}
    texto = datos.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        return 400, {"error": "El comentario no puede estar vacío."}

    pieza_id = datos.get("pieza_id", "") or ""
    if not isinstance(pieza_id, str):
        pieza_id = ""
    pieza_id = pieza_id.strip()
    if pieza_id:
        plat = repos.obtener_pieza_fila(pieza_id)
        if plat is None or plat.get("publicacion_id") != publicacion_id:
            return 400, {"error": "Esa plataforma no es de este contenido."}

    comentario = repos.crear_comentario(
        publicacion_id=publicacion_id,
        pieza_id=pieza_id,
        texto=texto.strip()[:_MAX_TEXTO],
        autor=autor,
        menciones=menciones,
    )
    # Notificar (best-effort, ya envuelto en su propio try/except): nunca rompe el comentar.
    notificaciones.tras_comentario(contenido, comentario, autor)
    return 201, {"comentario": comentario}


async def crear_comentario(request: Request) -> Response:
    """POST /api/publicaciones/{cid}/comentarios: anade un comentario al hilo.

    `menciones` (opcional) es la lista de ids de usuarios etiquetados con @ en el texto: se
    guardan con el comentario y disparan una notificacion `mencion` a cada uno (y los dejan
    suscritos a la pieza). Tras crear el comentario notificamos tambien al resto de interesados.
    """
    publicacion_id = request.path_params["publicacion_id"]
    datos = await leer_json(request)
    # Menciones (@): ids de usuario unicos y no vacios (cap defensivo). El front los manda
    # resueltos por el autocompletado; aqui solo reparamos la forma.
    menciones_raw = datos.get("menciones")
    menciones = (
        list(dict.fromkeys(m for m in menciones_raw if isinstance(m, str) and m.strip()))[:20]
        if isinstance(menciones_raw, list)
        else []
    )
    autor = autor_de_peticion(request)
    status, cuerpo = await run_in_threadpool(
        _crear_comentario, publicacion_id, datos, autor, menciones
    )
    return JSONResponse(cuerpo, status_code=status)


def _actualizar_comentario(
    comentario_id: str, datos: dict, autor: dict | None, rol: str | None
) -> tuple[int, dict]:
    actual = repos.obtener_comentario(comentario_id)
    if actual is None:
        return 404, {"error": "Ese comentario ya no existe."}
    campos: dict[str, object] = {}

    if "texto" in datos:
        texto = datos.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            return 400, {"error": "El comentario no puede estar vacío."}
        if not _puede_gestionar(autor, rol, actual.get("autor_id", "")):
            return 403, {"error": "Solo el autor puede editar su comentario."}
        campos["texto"] = texto.strip()[:_MAX_TEXTO]
    # Marcar resuelto/reabrir lo puede hacer cualquiera del equipo (es un estado del hilo).
    if "resuelto" in datos:
        campos["resuelto"] = bool(datos["resuelto"])

    if not campos:
        return 400, {"error": "Indica algún campo a actualizar."}
    actualizado = repos.actualizar_comentario(comentario_id, campos)
    if actualizado is None:
        return 404, {"error": "Ese comentario ya no existe."}
    return 200, {"comentario": actualizado}


async def actualizar_comentario(request: Request) -> Response:
    """PATCH /api/comentarios/{id}: edita texto y/o resuelto (solo autor o admin para el texto)."""
    comentario_id = request.path_params["comentario_id"]
    datos = await leer_json(request)
    autor = autor_de_peticion(request)
    rol = _rol_de_peticion(request)
    status, cuerpo = await run_in_threadpool(
        _actualizar_comentario, comentario_id, datos, autor, rol
    )
    return JSONResponse(cuerpo, status_code=status)


def _borrar_comentario(
    comentario_id: str, autor: dict | None, rol: str | None
) -> tuple[int, dict]:
    actual = repos.obtener_comentario(comentario_id)
    if actual is None:
        return 404, {"error": "Ese comentario ya no existe."}
    if not _puede_gestionar(autor, rol, actual.get("autor_id", "")):
        return 403, {"error": "Solo el autor puede borrar su comentario."}
    repos.borrar_comentario(comentario_id)
    return 200, {"mensaje": "Comentario borrado."}


async def borrar_comentario(request: Request) -> Response:
    """DELETE /api/comentarios/{id}: borra un comentario (solo autor o admin)."""
    comentario_id = request.path_params["comentario_id"]
    autor = autor_de_peticion(request)
    rol = _rol_de_peticion(request)
    status, cuerpo = await run_in_threadpool(_borrar_comentario, comentario_id, autor, rol)
    return JSONResponse(cuerpo, status_code=status)


# --------------------------------------------------------------------------- #
# Historial de versiones del copy                                             #
# --------------------------------------------------------------------------- #


def _listar_copy_versiones(pieza_id: str) -> tuple[int, dict]:
    plat = repos.obtener_pieza_fila(pieza_id)
    if plat is None:
        return 404, {"error": "Esa plataforma ya no existe."}
    versiones = repos.listar_copy_versiones(pieza_id)
    return 200, {
        "versiones": versiones,
        "total": len(versiones),
        "copy_actual": plat.get("copy", ""),
    }


async def listar_copy_versiones(request: Request) -> Response:
    """GET /api/plataformas/{pid}/copy/versiones: historial (más reciente primero)."""
    pieza_id = request.path_params["pieza_id"]
    status, cuerpo = await run_in_threadpool(_listar_copy_versiones, pieza_id)
    return JSONResponse(cuerpo, status_code=status)


def _guardar_copy(pieza_id: str, datos: dict, autor: dict | None) -> tuple[int, dict]:
    plat = repos.obtener_pieza_fila(pieza_id)
    if plat is None:
        return 404, {"error": "Esa plataforma ya no existe."}
    nuevo = datos.get("copy")
    if not isinstance(nuevo, str):
        return 400, {"error": "El copy no es válido."}
    nuevo = nuevo[:_MAX_TEXTO]
    nota = datos.get("nota", "")
    nota = nota.strip()[:_MAX_TEXTO] if isinstance(nota, str) else ""

    anterior = plat.get("copy", "")
    if nuevo == anterior:
        return 200, {"plataforma": _plat_publica(plat), "version": None}

    # Snapshot del texto que se va a pisar (autoria = quien hace el cambio).
    version = repos.registrar_copy_version(
        pieza_id=pieza_id,
        publicacion_id=plat.get("publicacion_id", ""),
        copy=anterior,
        autor=autor,
        nota=nota,
    )
    actualizada = repos.actualizar_pieza_fila(
        pieza_id, {"copy": nuevo, "falta_copy": not bool(nuevo.strip())}
    )
    if actualizada is None:
        return 404, {"error": "Esa plataforma ya no existe."}
    return 200, {"plataforma": _plat_publica(actualizada), "version": version}


async def guardar_copy(request: Request) -> Response:
    """POST /api/plataformas/{pid}/copy: snapshotea el copy ACTUAL y escribe el nuevo.

    Antes de pisar el copy vivo guarda una version inmutable del texto anterior (con autor
    y nota), de modo que el cambio quede en el historial y sea reversible. Si el copy no
    cambia, no hace nada (evita versiones duplicadas).
    """
    pieza_id = request.path_params["pieza_id"]
    datos = await leer_json(request)
    autor = autor_de_peticion(request)
    status, cuerpo = await run_in_threadpool(_guardar_copy, pieza_id, datos, autor)
    return JSONResponse(cuerpo, status_code=status)


def _revertir_copy(pieza_id: str, datos: dict, autor: dict | None) -> tuple[int, dict]:
    plat = repos.obtener_pieza_fila(pieza_id)
    if plat is None:
        return 404, {"error": "Esa plataforma ya no existe."}
    version_id = datos.get("version_id")
    if not isinstance(version_id, str) or not version_id.strip():
        return 400, {"error": "Indica la versión a revertir."}
    version = repos.obtener_copy_version(version_id.strip())
    if version is None or version.get("pieza_id") != pieza_id:
        return 400, {"error": "Esa versión no es de esta plataforma."}

    objetivo = version.get("copy", "")
    actual = plat.get("copy", "")
    if objetivo != actual:
        repos.registrar_copy_version(
            pieza_id=pieza_id,
            publicacion_id=plat.get("publicacion_id", ""),
            copy=actual,
            autor=autor,
            nota=f"Antes de revertir a la versión {version.get('version', '')}",
        )
    actualizada = repos.actualizar_pieza_fila(
        pieza_id, {"copy": objetivo, "falta_copy": not bool(objetivo.strip())}
    )
    if actualizada is None:
        return 404, {"error": "Esa plataforma ya no existe."}
    return 200, {"plataforma": _plat_publica(actualizada)}


async def revertir_copy(request: Request) -> Response:
    """POST /api/plataformas/{pid}/copy/revertir {version_id}: aplica una versión vieja.

    Revertir snapshotea PRIMERO el copy vivo actual (para no perderlo) y luego escribe el
    texto de la versión elegida como copy actual. Así el historial crece sin huecos.
    """
    pieza_id = request.path_params["pieza_id"]
    datos = await leer_json(request)
    autor = autor_de_peticion(request)
    status, cuerpo = await run_in_threadpool(_revertir_copy, pieza_id, datos, autor)
    return JSONResponse(cuerpo, status_code=status)


# --------------------------------------------------------------------------- #
# Aprobacion multinivel                                                        #
# --------------------------------------------------------------------------- #


def _cadena_publica(pieza_id: str) -> dict[str, object]:
    """Cadena de aprobacion + su estado global resumido + gates de gobernanza (para la UI).

    Incluye `aprobados`/`minimo_aprobaciones` (gate A: cuantas firmas lleva vs cuantas exige
    programar) y `comentarios_sin_resolver` (gate B: objeciones abiertas que bloquean publicar),
    para que la UI muestre el contador y deshabilite el boton de programar cuando no cumple.
    """
    cadena = repos.listar_aprobaciones(pieza_id)
    plat = repos.obtener_pieza_fila(pieza_id)
    sin_resolver = repos.comentarios_sin_resolver(
        (plat or {}).get("publicacion_id", "") or "", pieza_id
    )
    likes = _km.likes_aprobacion_de(str((plat or {}).get("marca") or ""))
    # Umbral efectivo de la marca, acotado a los niveles humanos que la cadena tiene (una cadena
    # legada mas larga que el umbral no exige mas OK que pide la marca; ni mas que niveles hay).
    minimo = min(likes, colaboracion.niveles_humanos(cadena)) if cadena else likes
    return {
        "niveles": cadena,
        "estado": colaboracion.estado_cadena(cadena, minimo),
        "nivel_actual": (colaboracion.nivel_actual(cadena) or {}).get("id", ""),
        "aprobados": colaboracion.contar_aprobados(cadena),
        "minimo_aprobaciones": minimo,
        "comentarios_sin_resolver": sin_resolver,
    }


# Alias PUBLICO del armado de la cadena (la usa `api/piezas.cadenas_lote` para el
# endpoint batch del feed, sin importar un simbolo privado de este modulo).
def cadena_publica(pieza_id: str) -> dict[str, object]:
    """Cadena de aprobacion + estado global + gates, para UNA plataforma (ver `_cadena_publica`)."""
    return _cadena_publica(pieza_id)


def _obtener_aprobacion_cadena(pieza_id: str) -> tuple[int, dict]:
    if repos.obtener_pieza_fila(pieza_id) is None:
        return 404, {"error": "Esa plataforma ya no existe."}
    return 200, dict(_cadena_publica(pieza_id))


async def obtener_aprobacion_cadena(request: Request) -> Response:
    """GET /api/plataformas/{pid}/aprobacion: la cadena de niveles y su estado global."""
    pieza_id = request.path_params["pieza_id"]
    status, cuerpo = await run_in_threadpool(_obtener_aprobacion_cadena, pieza_id)
    return JSONResponse(cuerpo, status_code=status)


def _crear_aprobacion_cadena(pieza_id: str, datos: dict) -> tuple[int, dict]:
    plat = repos.obtener_pieza_fila(pieza_id)
    if plat is None:
        return 404, {"error": "Esa plataforma ya no existe."}
    etiquetas_raw = datos.get("etiquetas")
    if etiquetas_raw is None:
        etiquetas = list(CADENA_APROBACION_DEFECTO)
    elif isinstance(etiquetas_raw, list):
        etiquetas = [
            e.strip()[:_MAX_ETIQUETA] for e in etiquetas_raw if isinstance(e, str) and e.strip()
        ]
    else:
        return 400, {"error": "Las etiquetas no son válidas."}
    if not etiquetas:
        return 400, {"error": "La cadena necesita al menos un nivel."}
    if len(etiquetas) > _MAX_NIVELES:
        return 400, {"error": f"Demasiados niveles (máximo {_MAX_NIVELES})."}

    # Cadena del TABLERO (recrear a mano): respeta el cargo del organigrama por nivel
    # (item C: Coordinación→coordinador, Dirección→director).
    montar_cadena_aprobacion(pieza_id, plat, etiquetas, con_cargos=True)
    return 201, dict(_cadena_publica(pieza_id))


async def crear_aprobacion_cadena(request: Request) -> Response:
    """POST /api/plataformas/{pid}/aprobacion {etiquetas?}: crea o RECREA la cadena.

    `etiquetas` es la lista ordenada de niveles (1-based). Sin ella, usa la cadena por
    defecto del organigrama (Edición → Coordinación → Dirección). Recrear reinicia las
    decisiones (todos los niveles vuelven a `pendiente`).
    """
    pieza_id = request.path_params["pieza_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_crear_aprobacion_cadena, pieza_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def montar_cadena_aprobacion(
    pieza_id: str,
    plat: dict,
    etiquetas: list[str],
    *,
    con_cargos: bool,
    solo_si_ausente: bool = False,
) -> bool:
    """Crea (o RECREA) la cadena de aprobacion de una pieza, con todos sus automatismos.

    Punto unico compartido por `crear_aprobacion_cadena` (recrear la cadena del tablero) y
    por `api/aprobacion.enviar_a_revision` (mandar al flujo "dale el OK" del feed). Pasos:

      1. cargos por nivel: si `con_cargos`, se exige el cargo del organigrama derivado de la
         etiqueta (Coordinación→coordinador, etc.); si no, ningun nivel exige cargo (el flujo
         "dale el OK" del feed se abre a cualquiera del equipo, salvo el autor).
      2. crea la cadena (todos los niveles `pendiente`) via `repos.crear_cadena_aprobacion`.
      3. pre-aprobacion de piezas de bajo riesgo (gateada por su flag, def OFF).

    `solo_si_ausente` (idempotencia): si la pieza YA tiene cadena, NO la recrea (devuelve
    False). Lo usa `enviar_a_revision` para que dos envios a revision concurrentes no monten
    DOS cadenas: el segundo encuentra la del primero y no la pisa. Devuelve True si montó la
    cadena, False si la saltó por existir ya.
    """
    if solo_si_ausente and repos.existe_cadena_aprobacion(pieza_id):
        return False
    # Cargo por nivel: el organigrama si `con_cargos`; SIEMPRE el cargo reservado del nivel
    # "Crítica IA" (asi ninguna persona puede decidirlo por el feed, lo vota solo el critico).
    cargos = [colaboracion.cargo_de_nivel(e, con_cargos=con_cargos) for e in etiquetas]
    repos.crear_cadena_aprobacion(
        pieza_id=pieza_id,
        publicacion_id=plat.get("publicacion_id", "") or "",
        etiquetas=etiquetas,
        cargos=cargos,
    )
    # fase3 (auto-planificacion): pre-aprobacion de piezas de bajo riesgo (gateada, def OFF).
    # Auto-aprueba los niveles INFERIORES, dejando el ULTIMO a un humano (trazable, decisor
    # "auto"). Si todo lo demas queda aprobado, la cadena solo espera el OK final.
    _aplicar_preaprobacion_bajo_riesgo(pieza_id, plat)
    return True


def _aplicar_preaprobacion_bajo_riesgo(
    pieza_id: str, plat: dict[str, object]
) -> None:
    """Auto-aprueba los niveles inferiores si la pieza es de bajo riesgo y el flag esta ON.

    Best-effort y SIN tocar el contrato de aprobacion: reutiliza la MISMA escritura de nivel
    (`repos.actualizar_aprobacion`) que una decision manual, solo que con el decisor reservado
    AUTO. El ultimo nivel NUNCA se auto-aprueba (la logica pura lo garantiza), asi que la pieza
    jamas queda totalmente aprobada por la maquina: siempre espera al humano final.
    """
    if not config.auto_preaprobacion():
        return
    contenido = repos.obtener_publicacion(plat.get("publicacion_id", "") or "")
    if not colaboracion.es_pieza_bajo_riesgo(plat, contenido):
        return
    cadena = repos.listar_aprobaciones(pieza_id)
    for nivel_id, campos in colaboracion.autoaprobaciones_iniciales(
        cadena, activa=True, bajo_riesgo=True
    ):
        repos.actualizar_aprobacion(nivel_id, campos)


def _decidir_nivel(
    aprobacion_id: str,
    decision: str,
    comentario: str,
    autor: dict | None,
    rol: str | None,
    cargo: str,
) -> tuple[int, dict]:
    nivel = repos.obtener_aprobacion(aprobacion_id)
    if nivel is None:
        return 404, {"error": "Ese nivel de aprobación ya no existe."}
    pieza_id = nivel.get("pieza_id", "")
    cadena = repos.listar_aprobaciones(pieza_id)
    plat = repos.obtener_pieza_fila(pieza_id)

    campos, error = colaboracion.decidir(
        nivel,
        cadena,
        decision,
        autor,
        rol=rol,
        comentario=comentario,
        cargo_decisor=cargo,
    )
    if error is not None:
        return 409, {"error": error}
    actualizado = repos.actualizar_aprobacion(aprobacion_id, campos)
    if actualizado is None:
        return 404, {"error": "Ese nivel de aprobación ya no existe."}

    # Notificar la decision recien aplicada (OK -> interesados + coordinador; rechazo ->
    # interesados). Best-effort: nunca rompe el OK/rechazo ya registrado.
    if plat is not None:
        contenido_padre = repos.obtener_publicacion(plat.get("publicacion_id", "") or "") or {}
        notificaciones.tras_decision(
            plat, contenido_padre, actualizado.get("decision", ""), autor
        )

    # Reflejar el estado GLOBAL de la cadena en la pieza y, si juntó los 2 OK, auto-programar.
    # No hay estado de reposo `aprobado`: la cadena aprobada deja la pieza `en_revision` y es la
    # auto-programación quien la mueve a `programado` al hallar hueco.
    cadena = repos.listar_aprobaciones(pieza_id)
    # La aprobacion se COMPLETA al alcanzar el umbral de la marca (acotado a los niveles humanos),
    # no al llenar TODOS los niveles: una cadena legada mas larga que el umbral no exige mas OK.
    minimo = min(
        _km.likes_aprobacion_de(str((plat or {}).get("marca") or "")),
        colaboracion.niveles_humanos(cadena),
    )
    estado_global = colaboracion.estado_cadena(cadena, minimo)
    if plat is not None:
        estado_pieza = colaboracion.estado_publicacion_para(estado_global)
        if estado_pieza is not None:
            repos.actualizar_pieza_fila(pieza_id, {"estado": estado_pieza})
        if estado_global == "aprobado":
            # 2 OK => programado: la pieza se encola SOLA a su próximo hueco, respetando los
            # gates de la programación. Sin franja se queda en revisión. NO publica. Best-effort:
            # un fallo aquí no tumba la aprobación.
            from .. import auto_programar

            try:
                auto_programar.programar_si_aprobada(pieza_id)
            except Exception:  # noqa: BLE001 — encolar es secundario al OK ya registrado.
                _log.exception(
                    "Auto-programación falló para %s (queda en revisión).", pieza_id
                )
    return 200, {"nivel": actualizado, "estado": estado_global, "niveles": cadena}


async def decidir_nivel(request: Request) -> Response:
    """POST /api/aprobacion-nivel/{id}/decidir {decision, comentario?}: aprueba/rechaza un nivel.

    Se decide POR ORDEN (solo el nivel pendiente más bajo). Un `rechazado` para la cadena.
    Cuando todos los niveles quedan `aprobado` (los 2 OK), la pieza se auto-programa al próximo
    hueco; mientras tanto sigue `en_revision` (no hay estado de reposo `aprobado`).
    """
    aprobacion_id = request.path_params["aprobacion_id"]
    datos = await leer_json(request)
    decision = datos.get("decision")
    comentario = datos.get("comentario", "")
    comentario = comentario.strip()[:_MAX_TEXTO] if isinstance(comentario, str) else ""
    status, cuerpo = await run_in_threadpool(
        _decidir_nivel,
        aprobacion_id,
        decision if isinstance(decision, str) else "",
        comentario,
        autor_de_peticion(request),
        _rol_de_peticion(request),
        _cargo_de_peticion(request),
    )
    return JSONResponse(cuerpo, status_code=status)


def _plat_publica(plat: dict) -> dict:
    """Devuelve la fila de plataforma tal cual (sin enriquecer; la UI ya tiene `red_nombre`)."""
    return plat


RUTAS = [
    Route("/api/publicaciones/{publicacion_id}/comentarios", listar_comentarios, methods=["GET"]),
    Route("/api/publicaciones/{publicacion_id}/comentarios", crear_comentario, methods=["POST"]),
    Route("/api/comentarios/{comentario_id}", actualizar_comentario, methods=["PATCH"]),
    Route("/api/comentarios/{comentario_id}", borrar_comentario, methods=["DELETE"]),
    Route("/api/plataformas/{pieza_id}/copy/versiones", listar_copy_versiones, methods=["GET"]),
    Route("/api/plataformas/{pieza_id}/copy", guardar_copy, methods=["POST"]),
    Route("/api/plataformas/{pieza_id}/copy/revertir", revertir_copy, methods=["POST"]),
    Route("/api/plataformas/{pieza_id}/aprobacion", obtener_aprobacion_cadena, methods=["GET"]),
    Route("/api/plataformas/{pieza_id}/aprobacion", crear_aprobacion_cadena, methods=["POST"]),
    Route("/api/aprobacion-nivel/{aprobacion_id}/decidir", decidir_nivel, methods=["POST"]),
]
