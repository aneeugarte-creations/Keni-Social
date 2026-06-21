"""Dominio PURO de la importacion de documentos a la PARRILLA/ROTA (turnos + eventos).

PROBLEMA QUE RESUELVE
=====================
El equipo de redes recibe la rota/parrilla de la semana en cualquier formato (un PDF,
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
de una VENTANA temporal razonable (no atada a una sola semana: un documento puede traer un
AÑO entero de eventos/turnos), `franja` (nombre de franja) que es un slot VALIDO, `miembro_id`
que existe en el roster, `turno_id` que existe, y enums (`tipo_cobertura`/`prioridad`/`estado`)
validos. Un miembro o franja inventados se RECHAZAN, no se crean al vuelo.

RANGO, NO SEMANA UNICA: las franjas (`rota_franjas`) son filas POR SEMANA (keyed por su
`lunes`). Un documento anual referencia slots por NOMBRE ("Mañana", "Tarde", ...), no por el
`franja_id` de una semana concreta. Por eso `crear_turno` lleva `franja` (nombre del slot) y
el `Contexto` valida contra el CONJUNTO de nombres validos (union de los nombres distintos de
todas las semanas tocadas + la plantilla por defecto), normalizados case/space-insensitive. La
resolucion nombre->`franja_id` POR SEMANA ocurre al APLICAR (db.aplicar_propuesta_parrilla).

CONFLICTOS (vista, no error de validacion): un `crear_turno` sobre una celda
(fecha, nombre_de_franja) ya ocupada, o un `modificar_turno` cuyo turno cambio o desaparecio,
se marcan con `conflicto=True` para que el frontend pinte la superposicion (nuevo/cambio/
conflicto) sin re-derivarlo. El conflicto NO descarta la operacion en la fase de propuesta;
solo el `/aplicar` decide (re-valida y, si hay conflicto, devuelve 409 sin aplicar).
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from ..estados import (
    ESTADOS_ROTA,
    PRIORIDADES_EVENTO,
    TIPOS_COBERTURA,
)
from . import json_llm

# Origen reservado de las filas creadas/editadas por este flujo (provenance / dedup).
ORIGEN = "import-doc"

# SIN límite de rango ni de cantidad: un documento puede traer cualquier fecha (pasado o
# futuro) y todas las operaciones que el modelo extraiga. La cantidad ya está acotada de forma
# natural por el presupuesto/turnos de `claude -p`; no imponemos un tope artificial que recorte
# datos reales. `MAX_TEXTO` es solo higiene de longitud POR CAMPO (no un límite de rango).
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


class CrearTarea(BaseModel):
    """Alta de una TAREA suelta del equipo (encargo, `clase='tarea'`, sin evento ni calendario).

    La emite el modo `tareas` del import: a diferencia de `crear_evento` (unidad de cobertura
    con fecha/hora que cae en el calendario), una tarea es trabajo que alguien tiene que HACER
    (editar un clip, subir fotos, redactar un copy…). La fecha es OPCIONAL (un encargo puede no
    tener fecha límite); si viene es `fecha_objetivo` (deadline), no la clava al calendario.
    """

    model_config = {"extra": "forbid"}

    tipo: Literal["crear_tarea"]
    titulo: str
    detalle: str | None = None
    prioridad: str | None = None
    fecha_objetivo: str | None = None


class CrearTurno(BaseModel):
    """Alta de un turno (horario `(fecha, franja)` para un miembro existente).

    `franja` es el NOMBRE del slot (p.ej. "Mañana"), NO un `franja_id`: las franjas son filas
    por semana y un documento referencia el slot por nombre. NO se restringe a una plantilla
    fija: un día puede tener 3+ franjas y el documento puede traer nombres nuevos. La resolucion
    nombre->`franja_id` de la semana concreta ocurre al APLICAR, CREANDO la franja si no existe.
    `franja_inicio`/`franja_fin` (HH:MM, opcionales) son el horario del slot SI el documento lo
    indica; se usan al crear la franja (si no, horario por defecto).
    """

    model_config = {"extra": "forbid"}

    tipo: Literal["crear_turno"]
    fecha: str
    franja: str
    franja_inicio: str | None = None
    franja_fin: str | None = None
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
    Union[CrearEvento, CrearTarea, CrearTurno, ModificarTurno],
    Field(discriminator="tipo"),
]

# Adaptador para validar UNA operacion de un dict crudo (discrimina por `tipo`).
_ADAPTADOR_OP: TypeAdapter[Operacion] = TypeAdapter(Operacion)


# --------------------------------------------------------------------------- #
# Contexto de validacion (estado real, multi-semana / rango)                  #
# --------------------------------------------------------------------------- #


def normaliza_franja(nombre: str) -> str:
    """Normaliza un nombre de franja para comparar case/space-insensitive (lower+strip)."""
    return (nombre or "").strip().lower()


def _norm_titulo(titulo: str) -> str:
    """Normaliza un título para comparar «mismo nombre» de forma TOLERANTE a variaciones menores.

    Ignora mayúsculas/minúsculas, acentos/diacríticos, puntuación y espaciado, para que el mismo
    evento escrito de formas casi iguales NO se duplique:
        "España vs. Cabo Verde" == "espana vs cabo verde" == "ESPAÑA  VS CABO-VERDE".
    El día y la hora (que se comparan aparte y SÍ exactos) son la red que evita fundir dos
    eventos realmente distintos que solo compartan un título parecido.
    """
    # NFKD separa cada letra de su tilde; descartamos las marcas combinantes -> sin acentos.
    base = unicodedata.normalize("NFKD", titulo or "")
    sin_acentos = "".join(c for c in base if not unicodedata.combining(c)).casefold()
    # Solo letras/dígitos como separadores de palabra; la puntuación pasa a espacio y se colapsa.
    return " ".join(re.sub(r"[^0-9a-z]+", " ", sin_acentos).split())


def _norm_hora(hora: str | None) -> str:
    """Normaliza una hora para comparar (strip; "" para None/''): un evento sin hora casa con
    otro sin hora, y "09:00" casa con " 09:00 "."""
    return (hora or "").strip()


class Contexto:
    """Estado real (multi-semana) contra el que se valida una propuesta.

    PURO: lo construye la capa de API/DB (desde `repos`) y se lo pasa al validador. No abre
    conexiones ni lee disco; es un snapshot inmutable de lo necesario para validar/conflictos.
    A diferencia del modelo viejo (una sola semana), valida operaciones en CUALQUIER fecha,
    SIN límite de rango: un documento puede traer cualquier periodo (pasado o futuro).

    - `miembros`: id -> nombre del roster valido (equipo completo asignable).
    - `nombres_franja`: conjunto de NOMBRES de slot validos, ya normalizados
      (`normaliza_franja`): union de los nombres distintos de `rota_franjas` de todas las
      semanas tocadas + la plantilla por defecto.
    - `turnos_por_id`: id -> dict del turno (para `modificar_turno` y valores actuales). Para
      `modificar_turno` el `actual.franja` se expone como NOMBRE (resuelto via `franjas_nombre`).
    IDEMPOTENCIA («ya está en el calendario», sin tocar nada):
    - `turnos_existentes`: conjunto de (fecha, nombre_franja_norm, miembro_id) ya presentes. Un
      `crear_turno` que reproduce EXACTAMENTE una de estas claves es idempotente (la MISMA persona
      ya tiene ese turno): se omite, ni conflicto ni alta. Una franja de tiempo lleva VARIAS
      personas, así que dar de alta a OTRA persona en esa franja es alta normal, no choque.
    - `eventos_existentes`: conjunto de (fecha, hora_norm, titulo_norm) ya presentes. Un
      `crear_evento` con esa misma clave ya está; se omite al aplicar (no se duplica).

    `franjas_nombre` (id -> nombre) resuelve el `franja_id` de un turno existente a su nombre
    (para construir `turnos_existentes` y los `actual` de `modificar_turno`).
    `eventos` son los eventos VIVOS del rango (para `eventos_existentes`); opcional (vacío en el
    contexto del prompt, que no deduplica).
    """

    def __init__(
        self,
        *,
        miembros: dict[str, str],
        nombres_franja: set[str],
        turnos: list[dict[str, Any]],
        franjas_nombre: dict[str, str] | None = None,
        eventos: list[dict[str, Any]] | None = None,
    ) -> None:
        self.miembros = dict(miembros)
        # Nombres de franja validos, normalizados (case/space-insensitive).
        self.nombres_franja = {normaliza_franja(n) for n in nombres_franja if n}
        # id de franja -> NOMBRE (para resolver el slot de un turno existente).
        franjas_nombre = dict(franjas_nombre or {})
        self.turnos_por_id: dict[str, dict[str, Any]] = {
            str(t.get("id", "")): t for t in turnos if t.get("id")
        }
        # (fecha, nombre_franja_norm, miembro_id) ya presentes (idempotencia por PERSONA: una
        # franja de tiempo lleva varias personas, así que la clave incluye al miembro).
        self.turnos_existentes: set[tuple[str, str, str]] = set()
        for t in turnos:
            fecha = str(t.get("fecha", "") or "")
            franja_id = str(t.get("franja_id", "") or "")
            nombre = franjas_nombre.get(franja_id, "")
            mid = str(t.get("miembro_id", "") or "")
            if fecha and nombre and mid:
                self.turnos_existentes.add((fecha, normaliza_franja(nombre), mid))
        # (fecha, hora_norm, titulo_norm) de los eventos ya en el calendario (idempotencia).
        self.eventos_existentes: set[tuple[str, str, str]] = set()
        for e in eventos or []:
            fecha_e = str(e.get("fecha", "") or "")
            if fecha_e:
                self.eventos_existentes.add(
                    (fecha_e, _norm_hora(e.get("hora")), _norm_titulo(str(e.get("titulo", "") or "")))
                )
        # Guardamos el mapa id->nombre para exponer el nombre de franja del turno en `actual`.
        self._franjas_nombre = franjas_nombre

    def nombre_de_franja(self, franja_id: str) -> str:
        """NOMBRE de la franja `franja_id` de un turno existente ("" si no se conoce)."""
        return self._franjas_nombre.get(str(franja_id or ""), "")


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
    """Saca la lista de operaciones del texto de claude (extractor compartido `json_llm`).

    CONTRATO ESTRICTO: una lista JSON cruda o un objeto `{"operaciones": [...]}` (la ÚNICA
    clave que el prompt pide; ya no se aceptan los alias `ops`/`operations`), opcionalmente
    dentro de un bloque cercado ```json ... ``` (se prefiere el ÚLTIMO: el modelo a veces
    razona antes y cierra con el JSON). None si no hay JSON legible. PURO.
    """
    return json_llm.extraer_lista(texto, claves=("operaciones",))


# --------------------------------------------------------------------------- #
# Validacion estricta contra el contexto                                      #
# --------------------------------------------------------------------------- #


def _normalizar_op_validada(op: Operacion) -> dict[str, Any]:
    """Serializa una operacion Pydantic ya validada a un dict JSON limpio (sin None sueltos)."""
    return op.model_dump(exclude_none=False)


def _dedup_exactas(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Quita operaciones EXACTAMENTE iguales (mismo contenido), preservando el orden.

    Red de seguridad ante duplicados LITERALES (p.ej. una misma fila repetida en dos hojas
    del Excel). NO fusiona operaciones distintas: el caso "mismo evento para varias redes"
    (títulos distintos) lo resuelve el prompt agrupando por evento, no este dedup.
    """
    vistas: set[str] = set()
    unicas: list[dict[str, Any]] = []
    for op in ops:
        clave = json.dumps(op, sort_keys=True, ensure_ascii=False)
        if clave in vistas:
            continue
        vistas.add(clave)
        unicas.append(op)
    return unicas


def _nombre_casa(buscado: str, nombre_norm: str) -> bool:
    """True si `buscado` (ya normalizado) identifica a `nombre_norm` (ya normalizado): igual al
    nombre completo, o a una de sus palabras, o una palabra que empiece por lo buscado (apodos:
    «ale» -> «alejandra»). PURA."""
    if not buscado or not nombre_norm:
        return False
    if buscado == nombre_norm:
        return True
    return any(p == buscado or p.startswith(buscado) for p in nombre_norm.split())


def _resolver_miembro_id(miembro_id: str, miembro_nombre: str | None, ctx: Contexto) -> str:
    """Resuelve el `miembro_id` de un turno al id REAL del roster, tolerando que el modelo
    transcriba mal el id opaco o ponga el NOMBRE en su lugar.

    Si `miembro_id` ya es válido, se respeta. Si no, intenta casar por NOMBRE (el `miembro_nombre`
    que leyó el modelo, o el propio `miembro_id` si trae un nombre) contra los nombres del roster,
    insensible a mayúsculas/acentos. Solo resuelve si la coincidencia es ÚNICA; si es ambigua o no
    hay ninguna, devuelve el id tal cual (la validación decidirá). Estrictamente aditivo: solo
    RESCATA turnos que se caerían, nunca toca uno con id ya válido. PURA.
    """
    if miembro_id in ctx.miembros:
        return miembro_id
    for buscado in (miembro_nombre, miembro_id):
        clave = _norm_titulo(str(buscado or ""))
        if not clave:
            continue
        coincidencias = {
            mid for mid, nombre in ctx.miembros.items() if _nombre_casa(clave, _norm_titulo(nombre))
        }
        if len(coincidencias) == 1:
            return next(iter(coincidencias))
    return miembro_id


def _validar_semantica(op: Operacion, ctx: Contexto) -> str | None:
    """Valida una operacion YA tipada contra el contexto. Devuelve un mensaje de error o None.

    Reglas (estrictas): fechas parsean y caen en la VENTANA temporal (no en una sola semana);
    `franja` (nombre de slot) es un slot valido; `miembro_id` existe en el roster; `turno_id`
    existe; enums validos. NO decide conflictos (eso es vista, ver `calcular_conflicto`).
    """
    if isinstance(op, CrearEvento):
        if not op.titulo.strip():
            return "El evento necesita un título."
        if not _fecha_iso_valida(op.fecha):
            return f"Fecha inválida: {op.fecha!r} (usa AAAA-MM-DD)."
        if op.hora not in (None, "") and not _hora_valida(op.hora or ""):
            return f"Hora inválida: {op.hora!r} (usa HH:MM)."
        if op.tipo_cobertura not in (None, "") and op.tipo_cobertura not in TIPOS_COBERTURA:
            return f"Tipo de cobertura inválido: {op.tipo_cobertura!r}."
        if op.prioridad not in (None, "") and op.prioridad not in PRIORIDADES_EVENTO:
            return f"Prioridad inválida: {op.prioridad!r}."
        return None

    if isinstance(op, CrearTarea):
        if not op.titulo.strip():
            return "La tarea necesita un título."
        # La fecha es OPCIONAL (un encargo puede no tener deadline); si viene, ISO válida.
        if op.fecha_objetivo not in (None, "") and not _fecha_iso_valida(op.fecha_objetivo or ""):
            return f"Fecha inválida: {op.fecha_objetivo!r} (usa AAAA-MM-DD)."
        if op.prioridad not in (None, "") and op.prioridad not in PRIORIDADES_EVENTO:
            return f"Prioridad inválida: {op.prioridad!r}."
        return None

    if isinstance(op, CrearTurno):
        if not _fecha_iso_valida(op.fecha):
            return f"Fecha inválida: {op.fecha!r} (usa AAAA-MM-DD)."
        if not op.franja.strip():
            return "El turno necesita el nombre de su franja."
        # NO restringimos la franja a una plantilla fija: cualquier nombre es válido y, si no
        # existe esa semana, se CREA al aplicar (un día puede tener 3+ franjas).
        if op.franja_inicio not in (None, "") and not _hora_valida(op.franja_inicio or ""):
            return f"Hora de inicio de franja inválida: {op.franja_inicio!r} (usa HH:MM)."
        if op.franja_fin not in (None, "") and not _hora_valida(op.franja_fin or ""):
            return f"Hora de fin de franja inválida: {op.franja_fin!r} (usa HH:MM)."
        # Rescata por NOMBRE si el modelo transcribió mal el id opaco (causa de turnos perdidos).
        op.miembro_id = _resolver_miembro_id(op.miembro_id, op.miembro_nombre, ctx)
        if op.miembro_id not in ctx.miembros:
            return f"El miembro {op.miembro_id!r} no existe en el equipo."
        return None

    if isinstance(op, ModificarTurno):
        actual = ctx.turnos_por_id.get(op.turno_id)
        if actual is None:
            return f"El turno {op.turno_id!r} ya no existe."
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
      - `crear_evento`: nunca conflictua; `ya_existe=True` si el MISMO (fecha, hora, título) ya
        está en el calendario (idempotente: se omite al aplicar, no se duplica).
      - `crear_turno`: `ya_existe=True` si la MISMA persona ya tiene ese (fecha, franja) —ni
        conflicto ni alta, ya está; `ocupada_por` lleva su miembro_id—. Si NO, es alta nueva: una
        franja de tiempo lleva VARIAS personas, así que OTRA persona en esa franja NUNCA choca.
      - `modificar_turno`: conflicto si el turno desapareció; ademas devuelve `actual` con los
        valores vivos de la fila referenciada (miembro_id/estado/override/... y `franja` como
        NOMBRE de slot).

    Devuelve `{conflicto: bool, ya_existe: bool, ...}`; la forma extra depende del tipo (la
    consume el front). `ya_existe` gana sobre `conflicto`: si ya está, no molesta al usuario.
    """
    tipo = op_dict.get("tipo")
    if tipo == "crear_turno":
        fecha = str(op_dict.get("fecha", ""))
        franja = normaliza_franja(str(op_dict.get("franja", "")))
        miembro = str(op_dict.get("miembro_id", ""))
        # La MISMA persona ya tiene ese turno -> idempotente, «ya está». En otro caso es alta
        # nueva: una franja de tiempo lleva VARIAS personas, así que OTRA persona no choca.
        ya = (fecha, franja, miembro) in ctx.turnos_existentes
        return {"conflicto": False, "ya_existe": ya, "ocupada_por": miembro if ya else ""}
    if tipo == "crear_evento":
        # Idempotente: mismo (fecha, hora, título) ya en el calendario -> «ya está», se omite.
        clave = (
            str(op_dict.get("fecha", "")),
            _norm_hora(op_dict.get("hora")),
            _norm_titulo(str(op_dict.get("titulo", "") or "")),
        )
        return {"conflicto": False, "ya_existe": clave in ctx.eventos_existentes}
    if tipo == "modificar_turno":
        actual = ctx.turnos_por_id.get(str(op_dict.get("turno_id", "")))
        if actual is None:
            return {"conflicto": True, "ya_existe": False, "actual": None}
        return {
            "conflicto": False,
            "ya_existe": False,
            "actual": {
                "miembro_id": actual.get("miembro_id", ""),
                "miembro_nombre": actual.get("miembro_nombre", ""),
                "franja": ctx.nombre_de_franja(actual.get("franja_id", "")),
                "fecha": actual.get("fecha", ""),
                "estado": actual.get("estado", ""),
                "override": bool(actual.get("override", False)),
                "motivo": actual.get("motivo", ""),
                "nota_relevo": actual.get("nota_relevo", ""),
            },
        }
    # crear_tarea u otros: no van al calendario, nada que deduplicar.
    return {"conflicto": False, "ya_existe": False}


# --------------------------------------------------------------------------- #
# Mapeo horario -> franja (modo `turnos`)                                      #
# --------------------------------------------------------------------------- #
# Una PARRILLA de trabajo es una MATRIZ (cabeceras = personas/roles, celdas = horario), no una
# lista de franjas con nombre. El equipo NO quiere una franja por persona: quiere a cada persona
# DENTRO de su franja de tiempo (Mañana/Tarde/Noche…). Aqui vive el mapeo PURO horario->franja
# que `parrilla_import_job` aplica en el post-procesado del modo `turnos`.


def _min_de_hhmm(hhmm: str) -> int | None:
    """`HH:MM` -> minutos desde medianoche (acepta `24:00` = 1440). None si malformado.

    Tolera un rango `HH:MM-HH:MM` quedandose con la hora de INICIO (el modelo a veces vuelca el
    rango entero en un solo campo). PURA.
    """
    if not isinstance(hhmm, str) or not hhmm.strip():
        return None
    parte = hhmm.strip().replace("–", "-").split("-", 1)[0].strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", parte)
    if not m:
        return None
    h, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 24 and 0 <= mm <= 59) or (h == 24 and mm != 0):
        return None
    return h * 60 + mm


def _intervalo_min(inicio: str, fin: str) -> tuple[int, int] | None:
    """`[inicio, fin)` en minutos. Si `fin <= inicio`, el turno cruza medianoche (+24h). None si
    alguna hora no parsea (p.ej. franja sin horario). PURA."""
    ini = _min_de_hhmm(inicio)
    fin_m = _min_de_hhmm(fin)
    if ini is None or fin_m is None:
        return None
    if fin_m <= ini:
        fin_m += 24 * 60
    return ini, fin_m


def _solape_min(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Minutos de solape de dos intervalos `[ini, fin)` (ya normalizados, pueden pasar de 1440)."""
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def mapear_franja_por_solape(
    candidatas: list[dict[str, str]], inicio: str, fin: str
) -> str | None:
    """NOMBRE de la franja candidata cuyo rango MAS solapa con `[inicio, fin)`. None si no hay
    horas validas o ninguna candidata solapa.

    `candidatas`: `[{nombre, inicio, fin}, ...]` (las franjas de tiempo del equipo). Soporta
    cruces de medianoche en AMBOS lados (un turno 16:00-00:00, una franja 16:00-24:00): el turno
    se prueba tambien desplazado -24h para alinear los husos. Empate -> la primera (orden de la
    plantilla). PURA: no toca BD.
    """
    turno = _intervalo_min(inicio, fin)
    if turno is None:
        return None
    mejor_nombre: str | None = None
    mejor_solape = 0
    for c in candidatas:
        rango = _intervalo_min(str(c.get("inicio", "")), str(c.get("fin", "")))
        if rango is None:
            continue
        s = max(
            _solape_min(turno, rango),
            _solape_min((turno[0] - 1440, turno[1] - 1440), rango),
        )
        if s > mejor_solape:
            mejor_solape = s
            mejor_nombre = str(c.get("nombre", "")) or None
    return mejor_nombre


def canonicalizar_franjas_turnos(
    operaciones: list[dict[str, Any]], plantilla: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Reescribe la `franja` de cada `crear_turno` al NOMBRE de una franja de la PLANTILLA del
    equipo, para que el import NUNCA cree una franja con nombre de persona/rango.

    El HORARIO MANDA: la franja se deriva del rango real trabajado (`franja_inicio`/`franja_fin`)
    eligiendo la franja de la plantilla que MÁS solapa, no de la etiqueta que puso el modelo —que
    a veces ancla a la persona a su franja habitual (p.ej. un 10:00-18:00 que es de Mañana pero el
    modelo etiqueta «Tarde»)—. Solo si no hay horario usable se cae en la etiqueta del modelo,
    corrigiendo su casing. El horario trabajado en `franja_inicio`/`franja_fin` se respeta tal
    cual (ya es HH:MM valido; no lo pisamos con el canonico para no introducir un `24:00` que la
    re-validacion del aplicar rechazaria). PURA.

    `plantilla`: `[{nombre,inicio,fin}, ...]` (franjas de tiempo del equipo). Si esta vacia, o un
    turno no es mapeable (sin horario y sin nombre conocido), ese turno se deja como vino.
    """
    if not plantilla:
        return operaciones
    por_nombre = {normaliza_franja(str(f.get("nombre", ""))): f for f in plantilla}
    for op in operaciones:
        if op.get("tipo") != "crear_turno":
            continue
        # El horario real manda sobre la etiqueta del modelo.
        nombre = mapear_franja_por_solape(
            plantilla,
            str(op.get("franja_inicio") or ""),
            str(op.get("franja_fin") or ""),
        )
        objetivo = por_nombre.get(normaliza_franja(nombre or "")) if nombre else None
        # Sin horario usable: cae en la etiqueta del modelo (corrige casing si es franja real).
        if objetivo is None:
            objetivo = por_nombre.get(normaliza_franja(str(op.get("franja", ""))))
        if objetivo is None:
            continue
        op["franja"] = str(objetivo.get("nombre", ""))
    return operaciones


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
    return _dedup_exactas(validas), errores


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
    return _dedup_exactas(validas), errores


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
