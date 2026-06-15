"""Auto-asignacion de responsable desde la rota (Fase 3 · auto-operativa).

Resuelve QUIEN debe ser el responsable por defecto de una pieza nueva cuando quien la
crea no fija uno: lo deriva de la ROTA del dia. Asi una pieza nunca queda HUERFANA y el
equipo solo tiene que CREAR el contenido; el reparto operativo lo hace la consola.

Este modulo es la CAPA DE I/O (lee `repos`/`auth`) sobre la funcion PURA del dominio
`rota.responsable_por_marca_hoy`: arma los turnos del dia, las marcas de cada miembro y
las franjas de descanso de la semana, y delega la decision (determinista) en el dominio.

Degradacion honesta: si no hay rota cargada, nadie cubre la marca hoy, o la pieza no
tiene marca, devuelve None (sin lanzar): la pieza se crea sin responsable, igual que
antes de esta automatizacion. NO inventa un responsable que no este de turno.

Lo consume `api/contenido.py` (creacion de contenido) con UNA sola llamada, para
mantener el cambio en ese fichero minimo y localizado (coordinacion de fase 3).
"""

from __future__ import annotations

import logging

from . import auth, repos
from . import rota as dominio
from .tiempo import hoy_utc

_log = logging.getLogger("keni_consola.auto_responsable")

# Marcas con reparto PULL ("la lista"): la gente COGE las tareas, nadie nace asignado.
# En el piloto de ClaroSports una pieza nacida ya asignada jamás aparece en «Por coger»
# y el 409 de coger/PATCH mentiría («Ya la cogió X» cuando fue la rota). Para estas
# marcas `responsable_automatico` devuelve None SIEMPRE; las demás siguen con la rota.
MARCAS_REPARTO_PULL = frozenset({"claro-sports"})


def responsable_automatico(marca: str, fecha_iso: str | None = None) -> dict[str, str] | None:
    """`{"id","usuario"}` del responsable que la rota asigna a `marca` HOY, o None.

    `fecha_iso` (def hoy) permite testear sin tocar el reloj. Lee:
      - los turnos del dia (de la semana que contiene `fecha_iso`),
      - las franjas de descanso de esa semana (para excluir turnos no laborales),
      - las marcas de cada miembro del equipo (organigrama del cliente).
    y delega la eleccion determinista en `rota.responsable_por_marca_hoy`. Devuelve la
    forma `{"id","usuario"}` lista para `repos.crear_contenido(responsable=...)`, o None
    si la pieza no tiene marca, la marca es de reparto PULL (`MARCAS_REPARTO_PULL`),
    no hay rota, o nadie cubre la marca hoy.

    NUNCA lanza: cualquier fallo de lectura se degrada a None (la pieza se crea sin
    responsable, como antes), para no romper la creacion de contenido.
    """
    if not marca:
        return None
    # Reparto PULL: en estas marcas las piezas nacen LIBRES y el equipo las coge de
    # «la lista» (claim atómico vía coger/soltar). No se consulta la rota.
    if marca in MARCAS_REPARTO_PULL:
        return None
    dia = (fecha_iso or hoy_utc().isoformat()).strip()
    if not dia:
        return None
    try:
        lunes = dominio.lunes_de_semana_iso(dia)
        if not lunes:
            return None
        turnos = repos.listar_turnos_rota(semana=lunes)
        if not turnos:
            return None
        franjas = repos.listar_franjas_semana(lunes)
        franjas_descanso = {f["id"] for f in franjas if f.get("es_descanso")}
        # Marcas por miembro: solo los usuarios con cobertura entran en la rota, pero
        # filtrar por marca ya es suficiente (un usuario sin la marca no es candidato).
        miembros_marcas = {
            u["id"]: list(u.get("marcas") or [])
            for u in auth.listar_usuarios()
            if u.get("cobertura")
        }
    except Exception:  # noqa: BLE001 -- una pieza sin responsable es preferible a romper el alta
        _log.exception("auto_responsable: fallo al resolver la rota para marca=%s; sin asignar.", marca)
        return None

    miembro_id = dominio.responsable_por_marca_hoy(
        marca, dia, turnos, miembros_marcas, franjas_descanso
    )
    if not miembro_id:
        return None
    usuario = auth.obtener_usuario_por_id(miembro_id)
    if usuario is None:
        return None
    return {"id": usuario["id"], "usuario": usuario["usuario"]}
