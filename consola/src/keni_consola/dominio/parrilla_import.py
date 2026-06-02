"""Dominio PURO de la importacion de documentos a la PARRILLA/ROTA (turnos + eventos).

PROBLEMA QUE RESUELVE
=====================
El equipo de redes de AMX recibe la rota/parrilla de la semana en cualquier formato (un PDF,
una captura de pantalla, un Excel raro, un Word, un texto pegado). Hoy hay que teclear evento
a evento y turno a turno en la rejilla. Aqui vive la logica que convierte la salida de un
`claude -p` (que LEYO el documento) en una PROPUESTA de operaciones estructuradas y la VALIDA
estrictamente contra el estado real de la semana, SIN tocar la base de datos.

DOS CAPAS (como `importador_calendario`):
  - PARSEO + VALIDACION (este modulo) es PURO y testeable: texto de claude -> lista de
    `Operacion` validadas contra un `Contexto` (semana, franjas, roster, turnos/eventos
    actuales) + lista de errores honesta. NO escribe nada.
  - APLICACION (los side-effects) vive en `db.aplicar_propuesta_parrilla` y en
    `api/parrilla_import.py`: re-valida contra la BD viva y aplica el diff en UNA transaccion.

Claude NUNCA escribe en el calendario: solo emite JSON. El JSON es CONTENIDO NO CONFIABLE
(viene de un documento subido), por eso la validacion es ESTRICTA: fechas que parsean, dentro
de la semana objetivo, `franja_id` que existe ESA semana, `miembro_id` que existe en el
roster, `turno_id` que existe, y enums (`tipo_cobertura`/`prioridad`/`estado`) validos. Un
miembro o franja inventados se RECHAZAN, no se crean al vuelo.

CONFLICTOS (vista, no error de validacion): un `crear_turno` sobre una celda (fecha,
franja_id) ya ocupada por ESE miembro, o un `modificar_turno` cuyo turno cambio o desaparecio,
se marcan con `conflicto=True` para que el frontend pinte la superposicion (nuevo/cambio/
conflicto) sin re-derivarlo. El conflicto NO descarta la operacion en la fase de propuesta;
solo el `/aplicar` decide (re-valida y, si hay conflicto, devuelve 409 sin aplicar).
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from ..estados import (
    ESTADOS_ROTA,
    PRIORIDADES_EVENTO,
    TIPOS_COBERTURA,
)

# Origen reservado de las filas creadas/editadas por este flujo (provenance / dedup).
ORIGEN = "import-doc"

# Topes defensivos: una rota semanal real no tiene cientos de operaciones.
MAX_OPERACIONES = 500
MAX_TEXTO = 4000


# --------------------------------------------------------------------------- #
# Esquema de operaciones (Pydantic; union discriminada por `tipo`)            #
# --------------------------------------------------------------------------- #


class CrearEvento(BaseModel):
    """Alta de un evento/transmision a cubrir (no atado a miembro)."""

    model_config = {"extra": "forbid"}

    tipo: Literal["crear_evento"]
    fecha: str
    hora: str | None = None
    titulo: str
    contenido: str | None = None
    nota: str | None = None
    tipo_cobertura: str | None = None
    prioridad: str | None = None


class CrearTurno(BaseModel):
    """Alta de un turno (horario `(fecha, franja_id)` para un miembro existente)."""

    model_config = {"extra": "forbid"}

    tipo: Literal["crear_turno"]
    fecha: str
    franja_id: str
    miembro_id: str
    miembro_nombre: str | None = None
    nota_relevo: str | None = None
    motivo: str | None = None


class CambiosTurno(BaseModel):
    """Campos editables de un turno en una modificacion (todos opcionales)."""

    model_config = {"extra": "forbid"}

    miembro_id: str | None = None
    miembro_nombre: str | None = None
    estado: str | None = None
    override: bool | None = None
    motivo: str | None = None
    nota_relevo: str | None = None


class ModificarTurno(BaseModel):
    """Modificacion de un turno existente (referenciado por `turno_id`)."""

    model_config = {"extra": "forbid"}

    tipo: Literal["modificar_turno"]
    turno_id: str
    cambios: CambiosTurno


Operacion = Annotated[
    Union[CrearEvento, CrearTurno, ModificarTurno],
    Field(discriminator="tipo"),
]

# Adaptador para validar UNA operacion de un dict crudo (discrimina por `tipo`).
_ADAPTADOR_OP: TypeAdapter[Operacion] = TypeAdapter(Operacion)


# --------------------------------------------------------------------------- #
# Contexto de validacion (estado real de la semana objetivo)                  #
# --------------------------------------------------------------------------- #


class Contexto:
    """Estado real de la semana objetivo contra el que se valida una propuesta.

    PURO: lo construye la capa de API/DB (desde `repos`) y se lo pasa al validador. No abre
    conexiones ni lee disco; es un snapshot inmutable de lo necesario para validar/conflictos.

    - `semana`: lunes ISO (AAAA-MM-DD) de la semana objetivo.
    - `dias`: las 7 fechas ISO (lunes->domingo) de la semana.
    - `franjas_ids`: ids de `rota_franjas` de ESA semana (las unicas asignables).
    - `miembros`: id -> nombre del roster valido (equipo completo asignable).
    - `turnos_por_id`: id -> dict del turno (para `modificar_turno` y valores actuales).
    - `turnos_por_celda`: (fecha, franja_id) -> miembro_id ocupante (deteccion de choque).
    """

    def __init__(
        self,
        *,
        semana: str,
        dias: list[str],
        franjas_ids: set[str],
        miembros: dict[str, str],
        turnos: list[dict[str, Any]],
    ) -> None:
        self.semana = semana
        self.dias = list(dias)
        self.franjas_ids = set(franjas_ids)
        self.miembros = dict(miembros)
        self.turnos_por_id: dict[str, dict[str, Any]] = {
            str(t.get("id", "")): t for t in turnos if t.get("id")
        }
        # (fecha, franja_id) -> miembro_id que ya la ocupa (para detectar celda ocupada).
        self.turnos_por_celda: dict[tuple[str, str], str] = {}
        for t in turnos:
            clave = (str(t.get("fecha", "") or ""), str(t.get("franja_id", "") or ""))
            mid = str(t.get("miembro_id", "") or "")
            if clave[0] and clave[1] and mid:
                self.turnos_por_celda[clave] = mid

    def fecha_en_semana(self, fecha_iso: str) -> bool:
        """True si `fecha_iso` cae en la semana objetivo (dentro del rango lunes-domingo)."""
        return fecha_iso in self.dias


# --------------------------------------------------------------------------- #
# Parseo del bloque JSON de la salida de claude                               #
# --------------------------------------------------------------------------- #


def _fecha_iso_valida(valor: str) -> bool:
    """True si `valor` es una fecha ISO AAAA-MM-DD real."""
    try:
        date.fromisoformat(valor)
        return True
    except (ValueError, TypeError):
        return False


_RE_HORA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _hora_valida(valor: str) -> bool:
    """True si `valor` es 'HH:MM' (24h, sin segundos). 24:00 NO es hora de evento."""
    return bool(_RE_HORA.match(valor.strip())) if isinstance(valor, str) else False


def extraer_bloque_json(texto: str) -> list[Any] | None:
    """Saca la lista de operaciones del texto de claude. Tolera ```json fences y dict envoltorio.

    Acepta tres formas: una lista JSON cruda, un objeto `{"operaciones": [...]}` (o `ops`/
    `operations`), todo opcionalmente dentro de un bloque cercado ```json ... ```. Devuelve la
    lista de operaciones (sin validar) o None si no hay JSON legible. PURO.
    """
    if not isinstance(texto, str) or not texto.strip():
        return None
    s = texto.strip()
    # Preferimos el ULTIMO bloque cercado (el modelo a veces razona antes y cierra con el JSON).
    cercados = re.findall(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    candidatos = [c.strip() for c in cercados if c.strip()] or [s]
    for crudo in reversed(candidatos):
        data = _cargar_json_tolerante(crudo)
        if data is None:
            continue
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for clave in ("operaciones", "ops", "operations"):
                if isinstance(data.get(clave), list):
                    return data[clave]
    return None


def _cargar_json_tolerante(s: str) -> Any | None:
    """`json.loads` tolerante: si el texto trae prefijo/sufijo, intenta desde el 1er `[`/`{`."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        inicio = next((i for i, c in enumerate(s) if c in "[{"), -1)
        if inicio < 0:
            return None
        try:
            return json.loads(s[inicio:])
        except (json.JSONDecodeError, ValueError):
            return None


# --------------------------------------------------------------------------- #
# Validacion estricta contra el contexto                                      #
# --------------------------------------------------------------------------- #


def _normalizar_op_validada(op: Operacion) -> dict[str, Any]:
    """Serializa una operacion Pydantic ya validada a un dict JSON limpio (sin None sueltos)."""
    return op.model_dump(exclude_none=False)


def _validar_semantica(op: Operacion, ctx: Contexto) -> str | None:
    """Valida una operacion YA tipada contra el contexto. Devuelve un mensaje de error o None.

    Reglas (estrictas): fechas parsean y caen en la semana objetivo; `franja_id` existe ESA
    semana; `miembro_id` existe en el roster; `turno_id` existe; enums validos. NO decide
    conflictos (eso es vista, ver `calcular_conflicto`).
    """
    if isinstance(op, CrearEvento):
        if not op.titulo.strip():
            return "El evento necesita un título."
        if not _fecha_iso_valida(op.fecha):
            return f"Fecha inválida: {op.fecha!r} (usa AAAA-MM-DD)."
        if not ctx.fecha_en_semana(op.fecha):
            return f"La fecha {op.fecha} cae fuera de la semana objetivo ({ctx.semana})."
        if op.hora not in (None, "") and not _hora_valida(op.hora or ""):
            return f"Hora inválida: {op.hora!r} (usa HH:MM)."
        if op.tipo_cobertura not in (None, "") and op.tipo_cobertura not in TIPOS_COBERTURA:
            return f"Tipo de cobertura inválido: {op.tipo_cobertura!r}."
        if op.prioridad not in (None, "") and op.prioridad not in PRIORIDADES_EVENTO:
            return f"Prioridad inválida: {op.prioridad!r}."
        return None

    if isinstance(op, CrearTurno):
        if not _fecha_iso_valida(op.fecha):
            return f"Fecha inválida: {op.fecha!r} (usa AAAA-MM-DD)."
        if not ctx.fecha_en_semana(op.fecha):
            return f"La fecha {op.fecha} cae fuera de la semana objetivo ({ctx.semana})."
        if op.franja_id not in ctx.franjas_ids:
            return f"La franja {op.franja_id!r} no existe en la semana objetivo."
        if op.miembro_id not in ctx.miembros:
            return f"El miembro {op.miembro_id!r} no existe en el equipo."
        return None

    if isinstance(op, ModificarTurno):
        actual = ctx.turnos_por_id.get(op.turno_id)
        if actual is None:
            return f"El turno {op.turno_id!r} ya no existe en la semana objetivo."
        c = op.cambios
        if c.miembro_id not in (None, "") and c.miembro_id not in ctx.miembros:
            return f"El miembro {c.miembro_id!r} no existe en el equipo."
        if c.estado not in (None, "") and c.estado not in ESTADOS_ROTA:
            return f"Estado inválido: {c.estado!r}."
        if (
            c.miembro_id is None
            and c.miembro_nombre is None
            and c.estado is None
            and c.override is None
            and c.motivo is None
            and c.nota_relevo is None
        ):
            return "La modificación no especifica ningún cambio."
        return None

    return "Operación de tipo desconocido."


def calcular_conflicto(op_dict: dict[str, Any], ctx: Contexto) -> dict[str, Any]:
    """Calcula el `conflicto` (bool) + datos de overlay de UNA operacion ya validada.

    PURO. Lo usa el GET de detalle para que el frontend pinte la superposicion sin re-derivar:
      - `crear_evento`: nunca conflictua (un evento no ocupa celda de turno).
      - `crear_turno`: conflicto si la celda (fecha, franja_id) ya está ocupada por OTRO/EL
        MISMO miembro (una celda persona×fecha×franja no se duplica). `ocupada_por` lleva el
        miembro_id ocupante actual.
      - `modificar_turno`: conflicto si el turno desapareció; ademas devuelve `actual` con los
        valores vivos de la fila referenciada (miembro_id/estado/override/...).

    Devuelve `{conflicto: bool, ...}`; la forma extra depende del tipo (la consume el front).
    """
    tipo = op_dict.get("tipo")
    if tipo == "crear_turno":
        clave = (str(op_dict.get("fecha", "")), str(op_dict.get("franja_id", "")))
        ocupante = ctx.turnos_por_celda.get(clave)
        return {
            "conflicto": ocupante is not None,
            "ocupada_por": ocupante or "",
        }
    if tipo == "modificar_turno":
        actual = ctx.turnos_por_id.get(str(op_dict.get("turno_id", "")))
        if actual is None:
            return {"conflicto": True, "actual": None}
        return {
            "conflicto": False,
            "actual": {
                "miembro_id": actual.get("miembro_id", ""),
                "miembro_nombre": actual.get("miembro_nombre", ""),
                "franja_id": actual.get("franja_id", ""),
                "fecha": actual.get("fecha", ""),
                "estado": actual.get("estado", ""),
                "override": bool(actual.get("override", False)),
                "motivo": actual.get("motivo", ""),
                "nota_relevo": actual.get("nota_relevo", ""),
            },
        }
    # crear_evento u otros: sin concepto de celda ocupada.
    return {"conflicto": False}


# --------------------------------------------------------------------------- #
# Entrada publica: parseo + validacion                                        #
# --------------------------------------------------------------------------- #


def parsear_y_validar(
    texto: str, ctx: Contexto
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Salida de claude (texto) + contexto -> `(operaciones_validas, errores)`. PURO.

    Cada operacion valida se devuelve como dict JSON normalizado (apto para guardar en la
    columna `operaciones`). Una operacion que no parsea el esquema o falla la validacion
    semantica se reporta como error (con su indice y motivo) SIN abortar el resto. Si el texto
    no trae JSON legible, devuelve `([], [{indice:0, error:...}])`.
    """
    crudas = extraer_bloque_json(texto)
    if crudas is None:
        return [], [
            {"indice": 0, "error": "El asistente no devolvió un bloque JSON legible con las operaciones."}
        ]
    if len(crudas) > MAX_OPERACIONES:
        crudas = crudas[:MAX_OPERACIONES]

    validas: list[dict[str, Any]] = []
    errores: list[dict[str, Any]] = []
    for i, cruda in enumerate(crudas):
        if not isinstance(cruda, dict):
            errores.append({"indice": i, "error": "La operación no es un objeto JSON."})
            continue
        try:
            op = _ADAPTADOR_OP.validate_python(cruda)
        except ValidationError as exc:
            errores.append({"indice": i, "error": _mensaje_validacion(exc)})
            continue
        problema = _validar_semantica(op, ctx)
        if problema is not None:
            errores.append({"indice": i, "error": problema})
            continue
        validas.append(_normalizar_op_validada(op))
    return validas, errores


def validar_operaciones(
    operaciones: list[Any], ctx: Contexto
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Re-valida una lista de operaciones YA parseadas (dicts) contra el contexto. PURO.

    Lo usa el `/aplicar` para re-validar contra la BD viva (las filas pudieron cambiar desde
    que se generó la propuesta). Mismas reglas que `parsear_y_validar`, pero sin extraer JSON.
    Devuelve `(validas, errores)` con los mismos campos.
    """
    validas: list[dict[str, Any]] = []
    errores: list[dict[str, Any]] = []
    for i, cruda in enumerate(operaciones or []):
        if not isinstance(cruda, dict):
            errores.append({"indice": i, "error": "La operación no es un objeto JSON."})
            continue
        try:
            op = _ADAPTADOR_OP.validate_python(cruda)
        except ValidationError as exc:
            errores.append({"indice": i, "error": _mensaje_validacion(exc)})
            continue
        problema = _validar_semantica(op, ctx)
        if problema is not None:
            errores.append({"indice": i, "error": problema})
            continue
        validas.append(_normalizar_op_validada(op))
    return validas, errores


def _mensaje_validacion(exc: ValidationError) -> str:
    """Resumen legible (es) del 1er error de validacion de Pydantic, sin volcar el traceback."""
    try:
        err = exc.errors()[0]
        campo = ".".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "valor inválido")
        return f"Campo «{campo}»: {msg}." if campo else f"{msg}."
    except Exception:  # noqa: BLE001 -- nunca propagar al parseo por un error al formatear
        return "La operación no cumple el esquema requerido."


# --------------------------------------------------------------------------- #
# Estados de la propuesta (fuente unica, compartida con db/api)               #
# --------------------------------------------------------------------------- #

ESTADO_GENERANDO = "generando"
ESTADO_PENDIENTE = "pendiente"
ESTADO_APLICADA = "aplicada"
ESTADO_DESCARTADA = "descartada"
ESTADO_ERROR = "error"

ESTADOS_PROPUESTA: tuple[str, ...] = (
    ESTADO_GENERANDO,
    ESTADO_PENDIENTE,
    ESTADO_APLICADA,
    ESTADO_DESCARTADA,
    ESTADO_ERROR,
)
