"""API Aprobacion de PIEZAS (#9): cola de revision, decision y programacion.

  - GET  /api/aprobacion/cola                  -> piezas en revision (sin cambios; lectura).
  - POST /api/aprobacion/{id}/enviar-a-revision -> crea una cadena SIMPLE (1 nivel) y deja
        la pieza `en_revision`.
  - POST /api/aprobacion/{id}/aprobar           -> DECIDE el nivel actual de la cadena como
        aprobado; si la cadena queda completa, la pieza pasa a `aprobado`.
  - POST /api/aprobacion/{id}/rechazar          -> DECIDE el nivel actual como rechazado;
        la pieza vuelve a `borrador`.
  - POST /api/aprobacion/{id}/programar {fecha} -> aprobado -> programado (NO es aprobacion;
        es programacion: deja la pieza `programado`, que es lo que la pagina feed muestra).

La logica PURA (orden, "otro par de ojos", estado global) vive en `dominio.colaboracion`;
la traduccion estado-cadena -> estado-pieza en `colaboracion.estado_publicacion_para`.

GATING (frontera del producto): programar NO publica en ninguna plataforma. Deja la pieza
en `programado` con su `fecha_programada` y aterriza en el feed para su aprobacion final; la
salida a redes la dispara una persona desde ahi. "El humano aprueba; el sistema no publica solo."
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import config, db, permisos, repos
from .._http_json import leer_json
from ..dominio import colaboracion
from ..dominio.piezas import pieza_a_dict
from ..estados import (
    DECISION_APROBADO,
    DECISION_PENDIENTE,
    DECISION_RECHAZADO,
    ESTADO_EN_REVISION,
    ESTADO_PROGRAMADO,
    ROL_ADMIN,
)
from ..motor_db import IntegrityError
from ..seguridad import autor_de_peticion
from ..tiempo import ahora_iso
from .colaboracion import montar_cadena_aprobacion

_log = logging.getLogger("keni_consola.api.aprobacion")

# Tope de seguridad de la cola de revisión: `en_revision` es un estado transitorio (el equipo lo
# vacía revisando), así que la cola real es pequeña; el cap solo acota un estado patológico para
# que la serialización nunca recorra el histórico entero. No trunca en operación normal.
_CAP_COLA = 500


def _rol_de_peticion(request: Request) -> str | None:
    """Rol del usuario de la sesion (None si entro por token de bootstrap / sin sesion)."""
    usuario = getattr(request.state, "usuario", None)
    if isinstance(usuario, dict):
        return usuario.get("rol")
    return None


def _reflejar_estado_pieza(
    pieza_id: str, nivel_decidido: dict[str, Any]
) -> dict[str, Any] | None:
    """Aplica el estado GLOBAL de la cadena al `estado` editorial de la pieza.

    Lee la cadena de la pieza, la resume con `dominio.colaboracion` y traduce ese estado
    global al estado editorial que el resto del flujo entiende. Ademas,
    propaga al registro publico de la pieza los campos de revision legados
    (`revisor_*`/`revisado_en`) tomados de la ULTIMA decision, para que la cola/UI sigan
    mostrando quien revisó y cuándo. Devuelve la pieza actualizada.
    """
    cadena = repos.listar_aprobaciones(pieza_id)
    estado_global = colaboracion.estado_cadena(cadena)
    estado_pieza = colaboracion.estado_publicacion_para(estado_global)
    campos: dict[str, Any] = {
        "revisor_id": nivel_decidido.get("decisor_id", "") or "",
        "revisor_nombre": nivel_decidido.get("decisor_nombre", "") or "",
        "revisado_en": nivel_decidido.get("decidido_en", "") or "",
    }
    if estado_pieza is not None:  # None == "sin_cadena": no se toca el estado editorial.
        campos["estado"] = estado_pieza
    return repos.actualizar_pieza(pieza_id, campos)


async def _decidir(request: Request, decision: str) -> Response:
    """Forwardea aprobar/rechazar al nivel ACTUAL de la cadena de la pieza.

    Centraliza el patron: 404 si la pieza no existe; 409 si no hay nivel pendiente que
    decidir (no se mando a revision o la cadena esta parada); delega la regla de "otro par
    de ojos" y de orden en `dominio.colaboracion.decidir`; refleja el estado resultante en
    la pieza.
    """
    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    # Pre-flight (solo para un mensaje claro): si no hay nivel pendiente, la pieza no está en
    # revisión. La validación REAL (orden, "otro par de ojos", estado) se re-hace bajo bloqueo
    # dentro de la transacción para no decidir sobre un snapshot obsoleto.
    cadena = repos.listar_aprobaciones(pieza_id)
    nivel = colaboracion.nivel_actual(cadena)
    if nivel is None:
        return JSONResponse(
            {"error": "Esta publicación no está en revisión."}, status_code=409
        )
    # El nivel "Crítica IA" lo vota SOLO el critico automatico: nadie lo decide a mano por el feed
    # (un coordinador que quiera saltarse el critico usa `forzar`). Mensaje claro en vez del 409
    # generico de cargo. Pasa la decision humana al SIGUIENTE par de ojos, no a la maquina.
    if colaboracion.es_nivel_critica_ia(nivel):
        return JSONResponse(
            {"error": "La crítica IA decide este paso automáticamente; espera su decisión."},
            status_code=409,
        )

    decisor = autor_de_peticion(request)
    rol = _rol_de_peticion(request)

    def _validar(nivel_fresco: dict[str, Any], cadena_fresca: list[dict[str, Any]]):
        # Re-aplica la regla PURA del dominio sobre la cadena YA bloqueada/consistente: cierra
        # la carrera del invariante cruzado (mismo decisor en dos niveles, orden) que el CAS
        # por-fila no ve.
        return colaboracion.decidir(
            nivel_fresco,
            cadena_fresca,
            decision,
            decisor,
            rol=rol,
        )

    # ATÓMICO: bloquea la cadena, re-valida con `_validar` y aplica el CAS, todo en una sola
    # transacción (db.decidir_nivel_aprobacion_tx). Un `error` = 409 (estado cambió / regla);
    # un `None` sin error sólo ocurriría si la fila desapareció (carrera de borrado) -> 404.
    nivel_decidido, error = db.decidir_nivel_aprobacion_tx(
        pieza_id, nivel["id"], _validar
    )
    if error is not None:
        return JSONResponse({"error": error}, status_code=409)
    if nivel_decidido is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    actualizada = _reflejar_estado_pieza(pieza_id, nivel_decidido)
    if actualizada is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    # Si esta decision cerro la parte HUMANA y queda el nivel IA pendiente, encola al critico
    # (best-effort). La pieza queda `en_revision` hasta que el critico vote; no se programa aun.
    _encolar_critica_si_corresponde(pieza_id)
    return _responder_aprobada(pieza_id, actualizada)


def _responder_aprobada(pieza_id: str, actualizada: dict[str, Any]) -> Response:
    """Auto-programa si la cadena juntó sus 2 likes y devuelve la pieza (estado final) como JSON.

    2 likes => programado: si la cadena quedó aprobada, encola SOLA al próximo hueco (mismos
    gates que `programar`; def ON `KENI_AUTO_PROGRAMAR`). Best-effort; no publica. Lo comparten la
    decisión normal (`_decidir`) y el override (`forzar`). COLAPSO 2026-06: ya no hay estado de
    reposo `aprobado`; se mira el estado de la CADENA, no el `estado` de la pieza (que sigue
    `en_revision` hasta que la auto-programación encuentre hueco).
    """
    cadena = repos.listar_aprobaciones(pieza_id)
    if colaboracion.estado_cadena(cadena) == DECISION_APROBADO:
        # Evento público `pieza.aprobada`: el momento REAL de la aprobación es juntar los 2 OK
        # (ya no hay estado de reposo `aprobado` que dispare el evento). Se emite ANTES de la
        # auto-programación. Best-effort: nunca rompe el OK ya registrado.
        _emitir_pieza_aprobada(actualizada)
        from .. import auto_programar

        try:
            programada = auto_programar.programar_si_aprobada(pieza_id)
            if programada is not None:
                actualizada = programada
        except Exception:  # noqa: BLE001 — encolar es secundario al OK ya registrado.
            _log.exception("Auto-programación falló para %s (queda en revisión).", pieza_id)
    return JSONResponse({"pieza": pieza_a_dict(actualizada)})


def _emitir_pieza_aprobada(pub: dict[str, Any]) -> None:
    """Emite el evento público `pieza.aprobada` (best-effort) al juntarse los 2 OK de la cadena.

    COLAPSO 2026-06: el evento ya no se dispara al ENTRAR en un estado `aprobado` (no existe);
    se emite aquí, en el momento real de la aprobación, antes de que la auto-programación mueva
    la pieza a `programado`. Un fallo de notificación nunca tumba la aprobación ya registrada.
    """
    try:
        from .. import marcas, redes
        from ..dominio import eventos

        marca = pub.get("marca", "") or ""
        red = pub.get("red", "") or ""
        padre = repos.obtener_publicacion(pub.get("publicacion_id", "") or "") or {}
        eventos.emitir(
            "pieza.aprobada",
            {
                "publicacion_id": pub.get("publicacion_id", "") or "",
                "pieza_id": pub.get("id", "") or "",
                "red": red,
                "red_nombre": redes.nombre_por_id(red) if red else "",
                "titulo": padre.get("titulo", "") or "",
                "marca": marca,
                "marca_nombre": marcas.etiqueta_de(marca) if marca else "",
                "estado": pub.get("estado", "") or "",
            },
            publicacion_id=pub.get("publicacion_id", "") or "",
            pieza_id=pub.get("id", "") or "",
        )
    except Exception:  # noqa: BLE001 — notificar es secundario al OK ya registrado.
        _log.exception("No se pudo emitir pieza.aprobada para %s.", pub.get("id"))


async def cola(request: Request) -> Response:
    """Cola de aprobacion: piezas EN REVISION, mas antiguas primero (FIFO de revision).

    Devuelve `{cola: [...], total: N}`. Cada item incluye `autor_nombre`/`autor_id`
    (quien envio) y `enviado_a_revision_en` (cuando), para que el equipo vea que espera
    revision y desde cuando. Lectura: sin cambios respecto al flujo legado.
    """
    pendientes = repos.listar_piezas(estado=ESTADO_EN_REVISION, limite=_CAP_COLA)
    # FOCO POR DEFECTO (no es restriccion): la cola se ENFOCA en las marcas preferentes de la
    # sesion para reducir la mezcla de contexto. No bloquea: cualquiera puede revisar piezas de
    # cualquier marca (las verá filtrando por esa marca). Sin preferencia (admin/token/sin
    # marcas) ve todo. Post-filtro en memoria (la cola es pequeña).
    preferentes = permisos.marcas_preferentes(request)
    if preferentes is not None:
        pendientes = [
            p for p in pendientes if not p.get("marca") or p.get("marca") in preferentes
        ]
    # Mas antiguas primero por `enviado_a_revision_en` (lo que lleva mas esperando, arriba).
    pendientes.sort(key=lambda p: p.get("enviado_a_revision_en") or "")
    items = [pieza_a_dict(p) for p in pendientes]
    return JSONResponse({"cola": items, "total": len(items)})


async def enviar_a_revision(request: Request) -> Response:
    """POST /api/aprobacion/{id}/enviar-a-revision: crea la cadena SIMPLE y deja en revision.

    Equivale a la vieja transicion borrador->en_revision, pero montando una cadena de un
    solo nivel ("otro par de ojos") sobre la pieza. Solo desde `borrador`. 409 si no lo esta.
    """
    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    if pub.get("estado") != "borrador":
        return JSONResponse(
            {"error": "Solo se puede enviar a revisión una pieza en borrador."},
            status_code=409,
        )

    # CAS de la transicion borrador->en_revision: cierra el TOCTOU (dos envios a revision
    # concurrentes leian el mismo snapshot `borrador` y pasaban ambos). El estado se mueve EN
    # EL MISMO UPDATE que sella autoria/sello de envio y limpia los `revisor_*`, condicionado a
    # que la pieza SIGA en `borrador`. El perdedor de la carrera ve None -> 409 (recarga).
    # Nota: `revisor_*`/`revisado_en` se sellan en la fila por plataforma; `autor_*` viven en el
    # `contenido` PADRE (no son columnas por plataforma), asi que el CAS NO los puede tocar: el
    # autor ya quedo fijado al crear la pieza, y la cola muestra ese autor (no se re-escribe aqui).
    actualizada = repos.transicionar_estado_pieza(
        pieza_id,
        "borrador",
        ESTADO_EN_REVISION,
        {
            "enviado_a_revision_en": ahora_iso(),
            "revisor_id": "",
            "revisor_nombre": "",
            "revisado_en": "",
        },
    )
    if actualizada is None:
        return JSONResponse(
            {"error": "El estado de la pieza cambió; recarga e inténtalo de nuevo."},
            status_code=409,
        )

    # `publicacion_id` no viaja en el dict publico de la pieza; se lee de la fila
    # plataforma (la pieza ES esa fila: su id es el `pieza_id`).
    plat = repos.obtener_pieza_fila(pieza_id)
    # Monta la cadena por defecto del flujo "dale el OK": dos niveles humanos (Edición +
    # Coordinación = los dos OK) y, si el flag lo activa, el nivel automatico "verificación Editorial"
    # (la aprobacion de IA) delante. SIN exigir cargo (`con_cargos=False`): cualquiera del
    # equipo da su OK, salvo el autor. La RECREA (cadena fresca toda `pendiente`) a proposito:
    # re-enviar a revision tras un rechazo debe arrancar limpio, no heredar decisiones viejas.
    # La carrera "dos cadenas" la cierra el CAS de arriba (solo UN envio gana la transicion
    # borrador->en_revision y llega aqui); el `solo_si_ausente` queda para otros llamantes.
    # Cadena por defecto del feed: los dos OK humanos y, si `KENI_CRITICA_IA` esta on, el nivel
    # automatico "Crítica IA" AL FINAL (lo vota el critico con vision tras cerrar los humanos).
    etiquetas = colaboracion.cadena_simple()
    if config.critica_ia_activa():
        etiquetas = [*etiquetas, colaboracion.ETIQUETA_CRITICA_IA]
    montar_cadena_aprobacion(pieza_id, plat or {}, etiquetas, con_cargos=False)
    return JSONResponse({"pieza": pieza_a_dict(actualizada)})


def _encolar_critica_si_corresponde(pieza_id: str) -> None:
    """Tras una decision humana, encola la Crítica IA si toca (humanos OK, nivel IA pendiente).

    Best-effort y idempotente: solo dispara cuando todos los niveles humanos estan aprobados y el
    nivel "Crítica IA" sigue pendiente (`humanos_aprobados_ia_pendiente`). El lanzador
    (`dominio.critica_ia`) usa la idempotencia de `generar.lanzar` para no encolar dos veces si la
    ruta se reintenta. Nunca rompe la respuesta de aprobacion: la decision humana ya quedo escrita.
    """
    if not config.critica_ia_activa():
        return
    cadena = repos.listar_aprobaciones(pieza_id)
    if not colaboracion.humanos_aprobados_ia_pendiente(cadena):
        return
    try:
        from ..dominio import critica_ia

        critica_ia.lanzar_para_publicacion(pieza_id)
    except Exception:  # noqa: BLE001 — encolar la critica es secundario al OK ya registrado.
        _log.exception("No se pudo encolar la crítica IA para %s.", pieza_id)


def _resolver_comentarios_critica_ia(pieza_id: str) -> None:
    """Resuelve los comentarios SIN resolver que dejó la Crítica IA (override de coordinación).

    Best-effort: cierra la objeción del crítico para que el gate B no siga frenando la
    programación cuando un coordinador FUERZA la pieza a pesar del dislike de IA.
    """
    plat = repos.obtener_pieza_fila(pieza_id)
    publicacion_id = (plat or {}).get("publicacion_id", "") or ""
    if not publicacion_id:
        return
    for c in repos.listar_comentarios(publicacion_id):
        if c.get("resuelto"):
            continue
        if (c.get("autor_id") or "") == colaboracion.DECISOR_CRITICA_ID:
            try:
                repos.actualizar_comentario(c["id"], {"resuelto": True})
            except Exception:  # noqa: BLE001 — resolver es best-effort; el override ya se aplicó
                _log.exception("No se pudo resolver el comentario IA %s.", c.get("id"))


async def aprobar(request: Request) -> Response:
    """POST /api/aprobacion/{id}/aprobar: decide el nivel actual como aprobado (revisor != autor)."""
    return await _decidir(request, DECISION_APROBADO)


async def rechazar(request: Request) -> Response:
    """POST /api/aprobacion/{id}/rechazar: decide el nivel actual como rechazado ("dislike").

    Un solo dislike NO devuelve a borrador: marca un nivel `rechazado` y deja el siguiente
    disponible. La pieza vuelve a borrador cuando acumula dos dislikes de dos personas
    distintas (espejo de los dos OK); lo decide `dominio.colaboracion.estado_cadena`.
    """
    return await _decidir(request, DECISION_RECHAZADO)


async def deshacer(request: Request) -> Response:
    """POST /api/aprobacion/{id}/deshacer: el revisor RETIRA su decisión (su OK o su dislike).

    Devuelve el nivel que decidió esta sesión a `pendiente` (sin decisor ni sello) y refleja
    el estado resultante en la pieza. Es lo que da el toggle del feed: un dislike tras un like
    quita el like (deshacer) y el siguiente dislike lo marca (rechazar). 404 si la pieza no
    existe; 409 si no tienes ninguna decisión propia que deshacer (o hay una decisión posterior).
    """
    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    cadena = repos.listar_aprobaciones(pieza_id)
    decisor_id = (autor_de_peticion(request) or {}).get("id", "") or ""
    nivel_id, error = colaboracion.deshacer_decision(cadena, decisor_id)
    if error is not None:
        return JSONResponse({"error": error}, status_code=409)

    if repos.actualizar_aprobacion(nivel_id, dict(colaboracion.CAMPOS_NIVEL_PENDIENTE)) is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    # Tras retirar la decisión NO hay "último revisor" que mostrar: se limpia (la pieza vuelve
    # a su estado según el resto de la cadena, normalmente `en_revision`).
    actualizada = _reflejar_estado_pieza(
        pieza_id, {"decisor_id": "", "decisor_nombre": "", "decidido_en": ""}
    )
    if actualizada is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"pieza": pieza_a_dict(actualizada)})


def _puede_forzar(request: Request) -> bool:
    """¿Puede esta sesión FORZAR la aprobación (saltarse la cadena)? Admin o coordinador.

    El token de mantenimiento (sin sesión) cuenta como admin. Un usuario logueado puede forzar si
    su rol es admin o si su CARGO del organigrama es de coordinación (`coordinador`,
    `coordinador_redes`, `coordinador_youtube`…); todos empiezan por "coordinador".
    """
    usuario = getattr(request.state, "usuario", None)
    if not isinstance(usuario, dict):
        return True  # token de mantenimiento = admin
    if usuario.get("rol") == ROL_ADMIN:
        return True
    cargo = str(usuario.get("cargo") or "")
    return cargo.startswith("coordinador") or bool(usuario.get("puede_coordinar"))


async def forzar(request: Request) -> Response:
    """POST /api/aprobacion/{id}/forzar: admin/coordinador salta SOLO los OK humanos.

    Forzar bypassa el "doble par de ojos" humano (sella los niveles humanos pendientes como
    override, con traza de quién forzó), pero NO sustituye a la Crítica IA: esa sigue siendo
    automática. Por eso, sobre el nivel "Crítica IA":
      - PENDIENTE (aún no corrió): se deja pendiente y se ENCOLA al crítico (debe correr igual).
        La pieza queda `en_revision` hasta que la IA vote; forzar no la da por publicable.
      - RECHAZADA (la IA ya vetó): override CONSCIENTE de coordinación ("publicar a pesar de la
        IA") — se voltea a aprobado y se cierra su objeción.
    403 si la sesión no puede forzar; 404 si la pieza no existe; 409 si no está en revisión.
    """
    if not _puede_forzar(request):
        return JSONResponse(
            {"error": "Solo un admin o coordinador puede forzar la aprobación."},
            status_code=403,
        )
    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    if pub.get("estado") != ESTADO_EN_REVISION:
        return JSONResponse(
            {"error": "Solo se puede forzar la aprobación de una pieza en revisión."},
            status_code=409,
        )

    autor = autor_de_peticion(request) or {}
    decisor_id = autor.get("id", "") or "forzado"
    decisor_nombre = autor.get("usuario", "") or "Override"
    ahora = ahora_iso()

    def _sello_override() -> dict[str, Any]:
        return {
            "decision": DECISION_APROBADO,
            "decisor_id": decisor_id,
            "decisor_nombre": decisor_nombre,
            "comentario": "Aprobación forzada (override de la cadena)",
            "decidido_en": ahora,
        }

    nivel_decidido: dict[str, Any] | None = None
    # ¿quedó la Crítica IA por correr? -> encolar al crítico (no se sella a mano).
    ia_por_correr = False
    # ¿se sobreescribió un VETO de la IA? -> hay que cerrar su comentario (gate B).
    override_veto_ia = False
    for nivel in repos.listar_aprobaciones(pieza_id):
        if colaboracion.es_nivel_critica_ia(nivel):
            # La Crítica IA NO la decide el override: forzar salta los OK HUMANOS, no la IA.
            if nivel.get("decision") == DECISION_PENDIENTE:
                # Aún no corrió: se deja pendiente y se encola al crítico (abajo). La pieza no
                # queda publicable hasta que la IA vote.
                ia_por_correr = True
                continue
            if nivel.get("decision") == DECISION_RECHAZADO:
                # OVERRIDE de un VETO de IA = transición rechazado→aprobado, pero el CAS de
                # `actualizar_aprobacion` solo deja pendiente→terminal (anti-carrera). Reseteamos
                # a pendiente PRIMERO (sin guardia) para que el OK forzado prospere; sin esto el
                # flip se perdía en silencio y la pieza quedaba `en_revision`.
                repos.actualizar_aprobacion(nivel["id"], {"decision": DECISION_PENDIENTE})
                nivel_decidido = repos.actualizar_aprobacion(nivel["id"], _sello_override())
                override_veto_ia = True
            # Ya aprobada: nada que forzar.
            continue
        # Niveles HUMANOS: el override sella los PENDIENTES (salta el "doble par de ojos"). Los
        # dislikes HUMANOS se respetan (no se voltean): el override salta la cadena, no borra la
        # objeción de una persona.
        if nivel.get("decision") != DECISION_PENDIENTE:
            continue
        nivel_decidido = repos.actualizar_aprobacion(nivel["id"], _sello_override())
    # Solo el override de un VETO de IA cierra su objeción (resuelve el comentario que frena el
    # gate B). Si la IA aún no corrió, NO hay nada que resolver: la dejamos votar.
    if override_veto_ia:
        _resolver_comentarios_critica_ia(pieza_id)
    # Si la Crítica IA quedó pendiente, se encola al crítico (best-effort, idempotente): forzar
    # cierra la parte humana, la IA decide después. Mismo gate que el flujo normal de aprobación.
    if ia_por_correr:
        _encolar_critica_si_corresponde(pieza_id)
    sello = nivel_decidido or {
        "decisor_id": decisor_id,
        "decisor_nombre": decisor_nombre,
        "decidido_en": ahora,
    }
    actualizada = _reflejar_estado_pieza(pieza_id, sello)
    if actualizada is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return _responder_aprobada(pieza_id, actualizada)


def _validar_fecha_programada(valor: Any) -> tuple[str | None, str | None]:
    """Valida `fecha` como datetime ISO FUTURO; devuelve `(iso_normalizada, None)` o `(None, error)`.

    Acepta 'YYYY-MM-DDTHH:MM' (o con segundos), con o sin zona ('...Z'/'+00:00'). Una
    cadena SIN zona se interpreta como UTC (convención del sistema). Debe ser estrictamente
    futura: no tiene sentido programar para un instante ya pasado. Se normaliza a minutos en
    UTC ('YYYY-MM-DDTHH:MM', hora de pared UTC).
    """
    if not isinstance(valor, str) or not valor.strip():
        return None, "Indica la fecha y hora de publicación (formato YYYY-MM-DDTHH:MM)."
    try:
        fecha = datetime.fromisoformat(valor.strip())
    except ValueError:
        return None, "La fecha no es válida (usa el formato YYYY-MM-DDTHH:MM)."
    # Normaliza a UTC consciente (naive → se asume UTC) y compara aware-vs-aware.
    fecha = fecha.replace(tzinfo=UTC) if fecha.tzinfo is None else fecha.astimezone(UTC)
    if fecha <= datetime.now(UTC):
        return None, "La fecha debe ser futura."
    return fecha.strftime("%Y-%m-%dT%H:%M"), None


async def programar(request: Request) -> Response:
    """POST /api/aprobacion/{id}/programar {fecha}: aprobado -> programado en esa fecha.

    NO es aprobacion: es programacion, y se conserva intacta. Solo se puede programar una
    pieza APROBADA (el humano ya la aprobó vía la cadena). NO publica: deja la pieza en
    `programado` con su `fecha_programada`, que es lo que la pagina feed muestra; la salida
    a redes la dispara una persona desde ahi. 404 si no existe; 409 si no está aprobada;
    400 si la fecha no es válida/futura.
    """
    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    if pub.get("estado") != ESTADO_EN_REVISION:
        return JSONResponse(
            {"error": "Solo se puede programar una pieza en revisión con sus likes."},
            status_code=409,
        )

    # GATE A (gobernanza): no se programa sin un MINIMO de aprobaciones acumuladas en la
    # cadena (def 2, "cuatro ojos" reales). El gate SOLO aplica si la pieza tiene una CADENA
    # de aprobacion configurada: una pieza marcada `aprobado` SIN cadena (atajo admin/legado)
    # ya paso por su propio control y no se le exige el minimo (no hay nada que contar). Una
    # cadena simple de 1 nivel SI queda sujeta al minimo (debe acumular las firmas exigidas).
    minimo = config.min_aprobaciones()
    cadena = repos.listar_aprobaciones(pieza_id)
    if cadena:
        cumple, aprobados = colaboracion.cumple_minimo_aprobaciones(cadena, minimo)
        if not cumple:
            return JSONResponse(
                {"error": f"Faltan aprobaciones: {aprobados} de {minimo}."}, status_code=409
            )

    # GATE B (revisión editorial): un comentario sin resolver es una objecion pendiente; bloquea
    # programar hasta que el equipo lo cierre. Se cuentan los del item entero + los de esta red.
    plat = repos.obtener_pieza_fila(pieza_id)
    pendientes = repos.comentarios_sin_resolver(
        (plat or {}).get("publicacion_id", "") or "", pieza_id
    )
    if pendientes:
        return JSONResponse(
            {
                "error": (
                    f"Hay {pendientes} comentario(s) sin resolver; "
                    "resuélvelos antes de programar."
                )
            },
            status_code=409,
        )

    datos = await leer_json(request)
    fecha, error = _validar_fecha_programada(datos.get("fecha"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    try:
        # CAS de la transicion en_revision->programado: cierra el TOCTOU (los gates de arriba se
        # evaluaron sobre un snapshot; entre la lectura y la escritura la pieza pudo dejar de
        # estar `en_revision` —p.ej. un deshacer concurrente—). El estado se mueve EN EL MISMO
        # UPDATE que fija `fecha_programada`/`preparado_en`, condicionado a que SIGA `en_revision`.
        actualizada = repos.transicionar_estado_pieza(
            pieza_id,
            ESTADO_EN_REVISION,
            ESTADO_PROGRAMADO,
            {"fecha_programada": fecha, "preparado_en": ""},
        )
    except IntegrityError:
        # Backstop de doble-reserva (índice parcial `idx_parrilla_slot_uniq`): ese (red, fecha)
        # ya está ocupado por otra pieza programada. El usuario eligió la fecha a mano, así que
        # no recalculamos; le pedimos otra ranura.
        return JSONResponse(
            {"error": "Ya hay una publicación programada en esa red y fecha; elige otra hora."},
            status_code=409,
        )
    if actualizada is None:
        # El CAS no aplicó: la pieza ya no está `en_revision` (transición concurrente) o se borró.
        return JSONResponse(
            {"error": "El estado de la pieza cambió; recarga e inténtalo de nuevo."},
            status_code=409,
        )
    return JSONResponse({"pieza": pieza_a_dict(actualizada)})


RUTAS = [
    Route("/api/aprobacion/cola", cola, methods=["GET"]),
    Route("/api/aprobacion/{pieza_id}/enviar-a-revision", enviar_a_revision, methods=["POST"]),
    Route("/api/aprobacion/{pieza_id}/aprobar", aprobar, methods=["POST"]),
    Route("/api/aprobacion/{pieza_id}/forzar", forzar, methods=["POST"]),
    Route("/api/aprobacion/{pieza_id}/rechazar", rechazar, methods=["POST"]),
    Route("/api/aprobacion/{pieza_id}/deshacer", deshacer, methods=["POST"]),
    Route("/api/aprobacion/{pieza_id}/programar", programar, methods=["POST"]),
]
