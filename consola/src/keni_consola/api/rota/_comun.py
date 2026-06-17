"""Helpers compartidos del paquete `api.rota` (identidad/equipo, marca, serializacion).

NO exporta `RUTAS` (nombre con `_`): el descubridor de `api/__init__.py` lo ignora.
Las funciones aqui las usa mas de un area de la rota (eventos, turnos, cobertura, etc.)."""
from __future__ import annotations

import re
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import auth, marcas, permisos, repos
from ... import rota as dominio

# Patron HH:MM con 00:00..24:00 (24:00 valido como FIN exclusivo de franja).
_PATRON_HHMM = re.compile(r"^([01]?\d|2[0-4]):([0-5]\d)$")


def _equipo(solo_cobertura: bool = True) -> list[dominio.Miembro]:
    """Equipo asignable a la rota: usuarios con `cobertura=True` por defecto.

    El frontend solo deberia ofrecer estos como opciones al asignar turnos. Pasar
    `solo_cobertura=False` devuelve el equipo COMPLETO (todos los usuarios), util para
    resolver nombres legibles de turnos historicos asignados antes de marcar a alguien
    como `cobertura=False` (no perder el nombre en la UI).
    """
    usuarios = auth.listar_usuarios()
    if solo_cobertura:
        usuarios = [u for u in usuarios if u.get("cobertura")]
    return [dominio.Miembro(id=u["id"], nombre=u["usuario"]) for u in usuarios]


def _equipo_dict(solo_cobertura: bool = True) -> list[dict[str, Any]]:
    """Como `_equipo`, pero con marcas N:M, `cargo` y `cobertura` para que el frontend
    pueda filtrar por vertical y por funcion en el organigrama.

    Hoy la rota solo cubre Claro Sports; con `marcas` el front puede limitar el equipo a
    los que pertenecen a esa marca (la creativa de Fundación ya sale por `cobertura=False`, pero el creativo de vertical
    cubre nacion-gamer y NO debe aparecer en la rota de ClaroSports). `cargo` permite
    ademas restringir la rejilla de Turnos a community managers (los coordinadores
    siguen en el equipo, pero no aparecen en la grilla de asignacion por franja).
    """
    usuarios = auth.listar_usuarios()
    if solo_cobertura:
        usuarios = [u for u in usuarios if u.get("cobertura")]
    return [
        {
            "id": u["id"],
            "nombre": u["usuario"],
            "marcas": list(u.get("marcas") or []),
            "cargo": u.get("cargo") or "",
            "cobertura": bool(u.get("cobertura")),
            "puede_coordinar": bool(u.get("puede_coordinar")),
        }
        for u in usuarios
    ]


def _nombres_equipo() -> dict[str, str]:
    """Mapa id->nombre del equipo COMPLETO (todos los usuarios).

    No filtra por cobertura: un turno asignado a alguien que despues queda fuera de la
    rota sigue mostrando su nombre, no un id suelto.
    """
    return {m.id: m.nombre for m in _equipo(solo_cobertura=False)}


def _usuario_actual(request: Request) -> dict[str, Any] | None:
    """Usuario de la sesion (None si se entro por el token de mantenimiento)."""
    usuario = getattr(request.state, "usuario", None)
    return usuario if isinstance(usuario, dict) else None


def _es_admin(request: Request) -> bool:
    """True si la peticion la hace un admin o entro por el token de bootstrap.

    Delega en el helper unico de rol (`keni_consola.permisos.es_admin`), compartido
    con `/api/conexiones` y `/api/usuarios` (#153). Mismo contrato que antes.
    """
    return permisos.es_admin(request)


def _lunes_param(request: Request) -> str:
    """Lunes (ISO) de la semana pedida (`?lunes=`); normaliza a lunes. "" si falta/invalido."""
    crudo = (request.query_params.get("lunes") or "").strip()
    return dominio.lunes_de_semana_iso(crudo) if crudo else ""


def _marca_param(request: Request) -> tuple[str | None, Response | None]:
    """Filtro de marca (`?marca=`) del calendario de turnos (multi-tenant por marca).

    Devuelve `(marca, None)` con el id canonico, o `(None, None)` si no se pidio
    (vista "Todas" agregada). Si la marca no existe, devuelve `(None, respuesta_400)`
    para que el handler la propague tal cual. La rota de turnos cruza eventos por marca
    (`rota_eventos.marca`); el resto (turnos, franjas, equipo) es compartido por el equipo.
    """
    marca = (request.query_params.get("marca") or "").strip() or None
    if marca and not marcas.es_marca(marca):
        return None, JSONResponse({"error": "Marca no reconocida."}, status_code=400)
    return marca, None


def _marca_cuerpo(datos: dict[str, Any]) -> tuple[str, Response | None]:
    """Marca OBLIGATORIA del cuerpo de una escritura del grid (aprobar/copiar/lote).

    GRID POR MARCA: las operaciones que MUTAN una rejilla exigen una marca concreta — no
    tienen sentido en "Todas". Devuelve `(marca, None)` con el id canonico, o `("", 400)` si
    falta o no existe (el handler propaga la respuesta tal cual).
    """
    marca = str(datos.get("marca") or "").strip()
    if not marca:
        return "", JSONResponse(
            {"error": "Elige una marca concreta (no «Todas») para esta operación."},
            status_code=400,
        )
    if not marcas.es_marca(marca):
        return "", JSONResponse({"error": "Marca no reconocida."}, status_code=400)
    return marca, None


def _evento_a_dict(evento: dict[str, Any]) -> dict[str, Any]:
    marca_id = evento.get("marca") or ""
    return {
        "id": evento["id"],
        "titulo": evento["titulo"],
        "fecha": evento["fecha"],
        "hora": evento["hora"],
        "contenido": evento["contenido"],
        "nota": evento["nota"],
        # Ola B (#144): cobertura, prioridad y seguimiento de reprogramaciones.
        "tipo_cobertura": evento.get("tipo_cobertura", "transmision"),
        "prioridad": evento.get("prioridad", "media"),
        "cambiado": bool(evento.get("cambiado")),
        "actualizado": evento.get("actualizado", ""),
        "es_sabado": dominio.es_sabado(evento["fecha"]),
        # Multi-tenant por marca.
        "marca": marca_id,
        "marca_nombre": marcas.etiqueta_de(marca_id) if marca_id else "",
    }


def _turno_a_dict(
    turno: dict[str, Any],
    nombres: dict[str, str],
    franjas_por_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Serializa un turno (horario `(fecha, franja_id)` para `miembro_id`).

    Si se pasa `franjas_por_id`, anade `franja_nombre` resuelto (para que el front no
    tenga que cruzarlo con la lista de franjas). Sin el mapa, `franja_nombre` queda "".

    Retrocompat: `franja` (literal 'matutino'/'vespertino'/'descanso') se calcula a partir
    del NOMBRE de la franja para tests legados y clientes pre-"franjas por semana". Es
    derivado: codigo nuevo debe leer `franja_id`/`franja_nombre`.
    """
    franja_def = (franjas_por_id or {}).get(turno.get("franja_id", "") or "")
    nombre = franja_def["nombre"] if franja_def else ""
    es_descanso = bool(franja_def.get("es_descanso", False)) if franja_def else False
    # Horario EFECTIVO del turno: si lleva horas a medida (inicio/fin propios) mandan; si no,
    # hereda las de su franja. `horario_propio` deja que la UI marque la celda como "cambiada".
    inicio_propio = (turno.get("inicio", "") or "").strip()
    fin_propio = (turno.get("fin", "") or "").strip()
    inicio_efec = inicio_propio or (franja_def["inicio"] if franja_def else "")
    fin_efec = fin_propio or (franja_def["fin"] if franja_def else "")
    if es_descanso:
        franja_legacy = "descanso"
    elif nombre == "Mañana":
        franja_legacy = "matutino"
    elif nombre == "Tarde":
        franja_legacy = "vespertino"
    else:
        franja_legacy = nombre.lower() if nombre else ""
    return {
        "id": turno["id"],
        "semana": turno["semana"],
        "fecha": turno["fecha"],
        "miembro_id": turno["miembro_id"],
        # El nombre vivo del equipo manda sobre el snapshot guardado (renombres).
        "miembro_nombre": nombres.get(
            turno["miembro_id"], turno.get("miembro_nombre", "")
        ),
        "franja_id": turno.get("franja_id", "") or "",
        "franja_nombre": nombre,
        "franja": franja_legacy,  # retrocompat: derivado del nombre de la franja.
        # Horario efectivo (override del turno o, en su defecto, el de la franja).
        "inicio": inicio_efec,
        "fin": fin_efec,
        "horario_propio": bool(inicio_propio or fin_propio),
        "estado": turno["estado"],
        "override": bool(turno["override"]),
        "motivo": turno["motivo"],
        "nota_relevo": turno["nota_relevo"],
        "es_sabado": dominio.es_sabado(turno["fecha"]),
        # GRID POR MARCA: la rejilla a la que pertenece el turno (la UI etiqueta en "Todas").
        "marca": turno.get("marca", "") or "",
        "marca_nombre": marcas.etiqueta_de(turno["marca"]) if turno.get("marca") else "",
    }


def _franja_semana_a_dict(franja: dict[str, Any]) -> dict[str, Any]:
    """Serializa una `FranjaDef` al contrato HTTP."""
    marca_id = franja.get("marca", "") or ""
    return {
        "id": franja["id"],
        "lunes": franja["lunes"],
        "nombre": franja["nombre"],
        "inicio": franja["inicio"],
        "fin": franja["fin"],
        "orden": int(franja.get("orden", 0)),
        "es_descanso": bool(franja.get("es_descanso", False)),
        # GRID POR MARCA: la rejilla (marca) a la que pertenece esta columna.
        "marca": marca_id,
        "marca_nombre": marcas.etiqueta_de(marca_id) if marca_id else "",
    }


def _hhmm_valido(valor: Any) -> bool:
    """True si `valor` es 'HH:MM' (24h, con 24:00 permitido como fin exclusivo)."""
    if not isinstance(valor, str):
        return False
    m = _PATRON_HHMM.match(valor.strip())
    if not m:
        return False
    h, mm = int(m.group(1)), int(m.group(2))
    if h == 24 and mm != 0:
        return False
    return True


def _franjas_de_semana(
    lunes_iso: str, marca: str | None = None
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Devuelve `(franjas_lista, franjas_por_id)` de la semana, acotadas a la rejilla `marca`.

    GRID POR MARCA: con `marca` concreta lista (y SIEMBRA por defecto si vacio) la rejilla de
    esa marca. En "Todas" (`marca` None) lista las franjas de TODAS las marcas (union, columnas
    etiquetadas) y NO siembra (sin una marca concreta no hay rejilla que inicializar).
    """
    franjas = repos.listar_franjas_semana(lunes_iso, marca) if lunes_iso else []
    if not franjas and lunes_iso and marca:
        franjas = repos.inicializar_franjas_por_defecto(lunes_iso, marca)
    return franjas, {f["id"]: f for f in franjas}


def _fecha_valida(iso: str) -> bool:
    """True si `iso` es una fecha AAAA-MM-DD valida (reutiliza el parser del dominio)."""
    return bool(iso) and dominio.lunes_de_semana_iso(iso) != ""
