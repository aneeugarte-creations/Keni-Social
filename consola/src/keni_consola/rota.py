"""Logica de DOMINIO de la parrilla y rota de horarios del equipo.

Modulo PURO (sin I/O ni dependencias de persistencia): aqui viven las reglas y
predicados de rotacion, para poder probarlas a fondo sin tocar SQLite ni la red.
La capa de persistencia (`db.py`) y la API (`api/rota.py`) construyen sus entradas
y consumen estas funciones.

DECISION DE PRODUCTO: el coordinador de la rota (Claro Sports / UnoTV) asigna su rota A MANO por criterio
estrategico. La consola NO propone reparto automatico ni impone reglas de rotacion: solo
le muestra los huecos, la carga por persona y quien trabaja cada sabado; el coordinador
de la rota decide y APRUEBA antes de publicarla al equipo. Cualquiera puede cubrir
cualquier dia (incluidos sabados consecutivos) y un mismo turno admite a tantas personas
como haga falta. Aqui solo vive lo que respalda esa toma de decision.

FRANJAS POR SEMANA (ola "Mundial"): el feedback real del piloto descubrio semanas
con coberturas atipicas (Mundial, eventos grandes) que requieren MAS de 2 franjas y CON
SOLAPES (ej. semana 24: 09:00-17:00, 13:00-21:00, 17:00-01:00 cruzando medianoche). El
modelo viejo (`Franja = matutino|vespertino|descanso`, enum hardcoded) no lo soportaba.
Ahora cada SEMANA tiene sus propias franjas (`FranjaDef`), con `nombre` libre, rangos
`HH:MM` arbitrarios, solapes permitidos y soporte para franjas que cruzan medianoche
(`fin <= inicio`). La cobertura de un evento es la UNION de las personas con turno en
TODAS las franjas activas a la hora del evento.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TypedDict

SABADO = 5

FRANJAS_TRABAJO: tuple[str, ...] = ()

__all__ = ["FRANJAS_TRABAJO"]


# --------------------------------------------------------------------------- #
# Tipos del dominio                                                            #
# --------------------------------------------------------------------------- #


class FranjaDef(TypedDict):
    """Definicion de una franja de una semana (modelo "franjas por semana").

    - `id`: identificador estable (uuid corto), referencia desde `rota_turnos.franja_id`.
    - `lunes`: ISO (AAAA-MM-DD) del lunes de la semana a la que pertenece.
    - `nombre`: etiqueta legible (UNIQUE por semana). Ej. "Mañana", "Tarde",
      "Cobertura nocturna", "Descanso".
    - `inicio` / `fin`: rangos "HH:MM" (24h). El inicio es INCLUSIVO, el fin es
      EXCLUSIVO. Si `fin <= inicio`, la franja CRUZA MEDIANOCHE (ej. 17:00-01:00).
      En franjas con `es_descanso=true` el rango es decorativo (la UI lo muestra como
      "—"): `franjas_activas_en` IGNORA la hora y la franja nunca cubre eventos.
    - `orden`: entero ascendente para presentar las filas en la rejilla (estable). Por
      convencion la franja "Descanso" usa `orden=999` para quedar al final.
    - `es_descanso`: si True, marca la franja como "no laboral". `franjas_activas_en`
      la EXCLUYE: un turno asignado a esta franja NO cubre ningun evento. Existe para
      planificar EXPLICITAMENTE que una persona no trabaja ese dia (distinto de "olvido
      de asignacion": el descanso es una marca planificada del admin).
    """

    id: str
    lunes: str
    nombre: str
    inicio: str
    fin: str
    orden: int
    es_descanso: bool


@dataclass(frozen=True)
class Miembro:
    """Un miembro del equipo disponible para la rota (id estable + nombre legible)."""

    id: str
    nombre: str


@dataclass(frozen=True)
class Evento:
    """Un evento/transmision a cubrir: cuando es y QUE sacar de el.

    `fecha` es ISO (YYYY-MM-DD). `hora` es texto libre ("16:00", "16:00–18:00").
    `contenido` es "que sacar" de esa transmision (el campo clave del Excel del coordinador de la rota).
    """

    id: str
    titulo: str
    fecha: str
    hora: str = ""
    contenido: str = ""


@dataclass(frozen=True)
class Ausencia:
    """Un periodo en que un miembro NO esta disponible (vacaciones/descanso/baja/otro).

    `desde`/`hasta` son fechas ISO (YYYY-MM-DD), RANGO INCLUSIVO. `tipo` es informativo;
    la UI lo muestra como no disponible y la edicion de turnos lo respeta.
    """

    miembro_id: str
    desde: str
    hasta: str
    tipo: str = "otro"


# --------------------------------------------------------------------------- #
# Utilidades de fechas (semana lunes-domingo, deteccion de sabado)             #
# --------------------------------------------------------------------------- #


def _parsear_fecha(iso: str) -> date | None:
    """Parsea una fecha ISO (YYYY-MM-DD); None si no es valida (no rompe)."""
    try:
        return date.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


def lunes_de_semana(d: date) -> date:
    """Lunes de la semana ISO que contiene `d` (la semana va lunes->domingo)."""
    return d - timedelta(days=d.weekday())


def lunes_de_semana_iso(iso: str) -> str:
    """Lunes (ISO) de la semana que contiene la fecha `iso`; "" si la fecha no parsea."""
    d = _parsear_fecha(iso)
    return lunes_de_semana(d).isoformat() if d is not None else ""


def es_sabado(iso: str) -> bool:
    """True si la fecha ISO cae en sabado (el dia que rota)."""
    d = _parsear_fecha(iso)
    return d is not None and d.weekday() == SABADO


def rango_semana(lunes_iso: str) -> tuple[str, str]:
    """`(lunes, domingo)` ISO de la semana cuyo lunes es `lunes_iso`.

    Si `lunes_iso` no parsea, devuelve `("", "")`.
    """
    lunes = _parsear_fecha(lunes_iso)
    if lunes is None:
        return "", ""
    # Normalizamos por si nos dieran un dia que no es lunes.
    lunes = lunes_de_semana(lunes)
    return lunes.isoformat(), (lunes + timedelta(days=6)).isoformat()


def dias_de_semana(lunes_iso: str) -> list[str]:
    """Las 7 fechas ISO (lunes->domingo) de la semana cuyo lunes es `lunes_iso`.

    Lista vacia si `lunes_iso` no parsea. Normaliza por si dieran un dia que no es lunes.
    """
    inicio_iso, _ = rango_semana(lunes_iso)
    if not inicio_iso:
        return []
    inicio = date.fromisoformat(inicio_iso)
    return [(inicio + timedelta(days=i)).isoformat() for i in range(7)]


def _lunes_semanas_del_mes(anio: int, mes: int) -> list[date]:
    """Lunes (ancla lun->dom) de TODAS las semanas que solapan el mes `(anio, mes)`."""
    primero = date(anio, mes, 1)
    siguiente = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    ultimo = siguiente - timedelta(days=1)
    l_primero = lunes_de_semana(primero)
    l_ultimo = lunes_de_semana(ultimo)
    n = (l_ultimo - l_primero).days // 7
    return [l_primero + timedelta(weeks=i) for i in range(n + 1)]


def pares_semanas_copia_mes(
    mes_destino_iso: str, mes_origen_iso: str | None = None
) -> list[tuple[str, str]]:
    """Pares `(de_lunes, a_lunes)` para sembrar el mes `mes_destino_iso` ("YYYY-MM") con el rol de un
    mes origen, alineado por dia de semana (lunes<->lunes; el offset es multiplo de 7).

    `mes_origen_iso` (tambien "YYYY-MM") elige el mes que se copia; si es `None` se toma el MES
    ANTERIOR al destino (comportamiento por defecto). La primera semana del origen se alinea con la
    primera del destino y el resto sigue el mismo offset. Cada semana del origen se incluye solo si su
    equivalente sigue solapando el mes destino; las semanas del destino sin equivalente quedan FUERA.
    Lista vacia si algun mes no es un "YYYY-MM" valido. Pura (sin BD): la composicion con la copia
    real vive en `repos.copiar_mes_rota`.
    """
    try:
        partes = mes_destino_iso.split("-")
        if len(partes) != 2:
            return []
        anio, mes = int(partes[0]), int(partes[1])
        date(anio, mes, 1)  # valida que el mes sea 1..12
    except (ValueError, TypeError, AttributeError):
        return []
    if mes_origen_iso is None:
        anio_ori, mes_ori = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
    else:
        try:
            partes_ori = mes_origen_iso.split("-")
            if len(partes_ori) != 2:
                return []
            anio_ori, mes_ori = int(partes_ori[0]), int(partes_ori[1])
            date(anio_ori, mes_ori, 1)
        except (ValueError, TypeError, AttributeError):
            return []
    lunes_dest = _lunes_semanas_del_mes(anio, mes)
    lunes_ori = _lunes_semanas_del_mes(anio_ori, mes_ori)
    offset = (lunes_dest[0] - lunes_ori[0]).days  # multiplo de 7 (ambos extremos son lunes)
    dest = set(lunes_dest)
    return [
        (ls.isoformat(), (ls + timedelta(days=offset)).isoformat())
        for ls in lunes_ori
        if (ls + timedelta(days=offset)) in dest
    ]


# --------------------------------------------------------------------------- #
# Predicados de rotacion (usados por la edicion manual de turnos)               #
# --------------------------------------------------------------------------- #


def miembro_ausente(ausencias: list[Ausencia], miembro_id: str, fecha_iso: str) -> bool:
    """True si alguna ausencia de `miembro_id` cubre `fecha_iso` (rango inclusivo).

    Ausencias con fechas invalidas se ignoran (no se inventan exclusiones sobre fechas
    rotas). Predicado puro reutilizable por la serializacion de la UI (marcar el dia
    como "Ausente") y por la edicion manual de turnos.
    """
    d = _parsear_fecha(fecha_iso)
    if d is None:
        return False
    for a in ausencias:
        if a.miembro_id != miembro_id:
            continue
        desde = _parsear_fecha(a.desde)
        hasta = _parsear_fecha(a.hasta)
        if desde is None or hasta is None:
            continue
        if desde <= d <= hasta:
            return True
    return False


# --------------------------------------------------------------------------- #
# Franjas por semana: utilidades de hora y predicado de actividad               #
# --------------------------------------------------------------------------- #


FRANJA_MATUTINO_DEFAULT_INICIO = "08:00"
FRANJA_MATUTINO_DEFAULT_FIN = "16:00"
FRANJA_VESPERTINO_DEFAULT_INICIO = "16:00"
FRANJA_VESPERTINO_DEFAULT_FIN = "24:00"


def _parsear_hora_minutos(hora_iso: str) -> int:
    """Convierte `HH:MM` (o un rango `HH:MM-HH:MM` del Excel) a MINUTOS desde 00:00.

    Acepta sufijos del Excel real ("16:00-18:00", "16:00–18:00"): se queda con la hora de
    inicio. Vacio o malformado -> `ValueError`.
    """
    if not isinstance(hora_iso, str) or not hora_iso.strip():
        raise ValueError("La hora esta vacia.")
    crudo = hora_iso.strip().replace("–", "-").split("-", 1)[0].strip()
    partes = crudo.split(":")
    if len(partes) < 2:
        raise ValueError(f"Hora malformada: {hora_iso!r} (usa HH:MM).")
    try:
        h = int(partes[0])
        m = int(partes[1])
    except ValueError as exc:
        raise ValueError(f"Hora malformada: {hora_iso!r} (usa HH:MM).") from exc
    # Aceptamos h==24 SOLO como limite superior de una franja (00:00 del dia siguiente):
    # nunca como hora de un evento real.
    if not (0 <= h <= 24 and 0 <= m <= 59):
        raise ValueError(f"Hora fuera de rango: {hora_iso!r}.")
    if h == 24 and m != 0:
        raise ValueError(f"24:00 solo se usa como fin de franja: {hora_iso!r}.")
    return h * 60 + m


def _parsear_hora_minutos_o_none(hora_iso: str) -> int | None:
    """Variante TOLERANTE: devuelve None si la hora no parsea (sin lanzar)."""
    try:
        return _parsear_hora_minutos(hora_iso)
    except ValueError:
        return None


def hora_dentro_de(hora_min: int, inicio: str, fin: str) -> bool:
    """True si `hora_min` (minutos desde 00:00) cae en el rango `[inicio, fin)`.

    `inicio` INCLUSIVO, `fin` EXCLUSIVO. Si `fin <= inicio`, la franja CRUZA MEDIANOCHE
    (ej. 17:00-01:00 cubre 17:00..23:59 + 00:00..00:59). En ese caso `inicio == fin` se
    interpreta como "cobertura de las 24h" (defensa: nadie configura asi en la practica;
    si lo hace, la consola NO lo descarta, lo cubre todo).
    """
    ini = _parsear_hora_minutos_o_none(inicio)
    fn = _parsear_hora_minutos_o_none(fin)
    if ini is None or fn is None:
        return False
    if fn > ini:
        # Rango normal dentro del mismo dia.
        return ini <= hora_min < fn
    if fn == ini:
        # Caso degenerado (24h): cubre cualquier hora.
        return True
    # Cruza medianoche: cubre hora >= inicio O hora < fin.
    return hora_min >= ini or hora_min < fn


def franjas_activas_en(
    hora_iso: str, franjas: list[FranjaDef] | list[dict]
) -> list[FranjaDef]:
    """Lista de franjas de la semana cuyo rango `[inicio, fin)` contiene `hora_iso`.

    Pura. Soporta TODAS las particularidades del modelo nuevo:
      - SOLAPES: si una hora cae en N franjas, se devuelven las N (UNION en el llamante).
      - FRANJAS QUE CRUZAN MEDIANOCHE (`fin <= inicio`): cubren desde `inicio` hasta
        medianoche y de medianoche a `fin` (ej. 17:00-01:00 cubre 18:00 y 00:30, pero
        no 02:00).
      - HORA INVALIDA o vacia: devuelve `[]` (sin lanzar; la cobertura "no aplica").
      - FRANJAS DE DESCANSO (`es_descanso=true`): EXCLUIDAS. Una persona con turno en una
        franja descanso esta planificada para no trabajar; no cubre eventos.

    El orden de retorno respeta el `orden` ascendente de las franjas (mismo orden que se
    presenta en la rejilla).
    """
    minutos = _parsear_hora_minutos_o_none(hora_iso)
    if minutos is None:
        return []
    activas = [
        f
        for f in franjas
        if not bool(f.get("es_descanso", False))
        and hora_dentro_de(minutos, f.get("inicio", ""), f.get("fin", ""))
    ]
    activas.sort(key=lambda f: (f.get("orden", 0), f.get("nombre", "")))
    # `cast` informal: filtramos dicts compatibles con FranjaDef. El runtime no fuerza el TypedDict.
    return activas  # type: ignore[return-value]


def mapear_franja(  # noqa: PLR0913 -- kwargs explicitos para retrocompat
    hora_iso: str,
    *,
    matutino_inicio: str = FRANJA_MATUTINO_DEFAULT_INICIO,
    matutino_fin: str = FRANJA_MATUTINO_DEFAULT_FIN,
    vespertino_inicio: str = FRANJA_VESPERTINO_DEFAULT_INICIO,
    vespertino_fin: str = FRANJA_VESPERTINO_DEFAULT_FIN,
) -> str:
    """LEGACY: mapea una hora `HH:MM` a la franja "matutino"/"vespertino"/"descanso".

    Conservada SOLO para la migracion de turnos legados (`_migrar_modelo_franjas` en
    `db.py`) y para tests de retrocompatibilidad. La nueva cobertura usa
    `franjas_activas_en` con las franjas vivas de la semana.

    Los inicios son INCLUSIVOS, los finales EXCLUSIVOS. La franja `descanso` cubre lo que
    no entra en matutino ni vespertino. Vacio o malformado -> `ValueError`.
    """
    minutos_evento = _parsear_hora_minutos(hora_iso)
    m_inicio = _parsear_hora_minutos(matutino_inicio)
    m_fin = _parsear_hora_minutos(matutino_fin)
    v_inicio = _parsear_hora_minutos(vespertino_inicio)
    v_fin = _parsear_hora_minutos(vespertino_fin)
    if m_inicio <= minutos_evento < m_fin:
        return "matutino"
    if v_inicio <= minutos_evento < v_fin:
        return "vespertino"
    return "descanso"


# --------------------------------------------------------------------------- #
# Cobertura derivada: dado un evento, quien lo cubre (turnos en su franja+fecha) #
# --------------------------------------------------------------------------- #


def cobertura_de_evento(
    evento: dict,
    turnos: list[dict],
    franjas_semana: list[FranjaDef] | list[dict] | None = None,
) -> list[dict]:
    """Devuelve los TURNOS que cubren `evento` en su (fecha, franjas activas a esa hora).

    Pura. Recibe las `franjas_semana` (las definiciones vivas de la semana del evento) y
    calcula `franjas_activas_en(hora, franjas_semana)`. Devuelve la UNION: todos los
    turnos en la fecha del evento cuya `franja_id` este entre las franjas activas, sin
    duplicar.

    Si `hora` no parsea o no hay franja activa, no hay cobertura. Si la semana aun no tiene
    franjas (caso degenerado), no hay cobertura.
    """
    fecha = evento.get("fecha", "") or ""
    hora = evento.get("hora", "") or ""
    if not fecha or franjas_semana is None:
        return []
    activas = franjas_activas_en(hora, list(franjas_semana))
    if not activas:
        return []
    ids_activas = {f["id"] for f in activas}
    cubridores: list[dict] = []
    vistos: set[str] = set()
    for t in turnos:
        if (t.get("fecha", "") or "") != fecha:
            continue
        franja_id = t.get("franja_id", "") or ""
        if franja_id not in ids_activas:
            continue
        miembro_id = t.get("miembro_id", "") or ""
        if not miembro_id:
            continue
        # UNION por turno (no por persona): si una misma persona tiene 2 turnos en 2
        # franjas activas a la misma hora del evento, ambos cubren (la UI los chiparea
        # como 1 entrada por turno, no por persona).
        if t.get("id", "") in vistos:
            continue
        vistos.add(t.get("id", ""))
        cubridores.append(t)
    return cubridores


# --------------------------------------------------------------------------- #
# Asignacion flexible: carga por persona (panel "Carga del equipo")              #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CargaMiembro:
    """Cuanto trabajo lleva un miembro en una semana (panel de carga).

    Datos PUROS derivados de los turnos de la semana + la cobertura DERIVADA de los eventos.
    La UI los pinta como tabla: `eventos` = cuantos eventos cubre (derivado por franja+fecha),
    `dias_trabajados` = cuantos dias entra a trabajar (cualquier franja del nuevo modelo),
    `sabado` = si toca sabado, `descansos` = cuantos dias del rango lunes-domingo NO tiene
    ningun turno (descanso implicito: ausencia de turno).
    """

    miembro_id: str
    nombre: str
    eventos: int
    dias_trabajados: int
    sabado: bool
    descansos: int


def resumen_carga(
    equipo: list[Miembro],
    turnos: list[dict],
    eventos: list[dict],
    franjas_semana: list[FranjaDef] | list[dict] | None = None,
    *,
    lunes_iso: str = "",
) -> list[CargaMiembro]:
    """Resumen de carga por miembro a partir de los turnos + los eventos de la semana.

    `turnos` son los `rota_turnos` (horario: `fecha`, `franja_id`, `miembro_id`); `eventos`
    son los `rota_eventos` de la semana con `fecha`/`hora`/`tipo_cobertura`. La cobertura
    (cuantos eventos cubre cada miembro) es DERIVADA: para cada evento, sus cubridores son
    los miembros con un turno en alguna de las franjas activas a su hora (UNION). Pura: no
    toca IO.

    `franjas_semana` son las franjas vigentes de la semana (modelo nuevo). Si no se pasan
    o estan vacias, la cobertura de eventos se calcula como 0 (los call sites legados
    seguian funcionando con la firma antigua; la cobertura sin franjas no tiene sentido en
    el modelo nuevo y se reporta como 0 honestamente).

    `lunes_iso` se usa para contar `descansos` (dias del rango lunes-domingo sin turno).
    Si esta vacio, no se calculan descansos (queda en 0): es la salida correcta para el
    caso de tests que no pasan el lunes.

    Eventos con hora invalida o `tipo_cobertura=no_cubrir` se ignoran para el conteo.
    Devuelve un `CargaMiembro` por miembro del equipo, ordenado por `eventos` desc (con
    empate alfabetico para estabilidad).
    """
    franjas_list: list[dict] = list(franjas_semana or [])

    # Indexa turnos por (miembro_id, fecha, franja_id) para resolver cobertura O(eventos).
    turnos_por_clave: dict[tuple[str, str, str], dict] = {}
    dias_trabajo_por_miembro: dict[str, set[str]] = {}
    trabajo_sabado_por_miembro: dict[str, bool] = {}
    for t in turnos:
        mid = t.get("miembro_id", "") or ""
        fecha = t.get("fecha", "") or ""
        franja_id = t.get("franja_id", "") or ""
        if not mid or not fecha:
            continue
        turnos_por_clave[(mid, fecha, franja_id)] = t
        dias_trabajo_por_miembro.setdefault(mid, set()).add(fecha)
        if es_sabado(fecha):
            trabajo_sabado_por_miembro[mid] = True

    # Cobertura derivada: para cada evento, qué miembros tienen turno en alguna franja
    # activa a su hora. Iteramos cada combinacion (evento, miembro) usando la UNION de
    # franjas activas.
    eventos_por_miembro: dict[str, int] = {}
    sabado_cobertura_por_miembro: dict[str, bool] = {}
    for ev in eventos:
        if (ev.get("tipo_cobertura") or "transmision") == "no_cubrir":
            continue
        fecha = ev.get("fecha", "") or ""
        hora = ev.get("hora", "") or ""
        if not fecha or not franjas_list:
            continue
        activas = franjas_activas_en(hora, franjas_list)
        if not activas:
            continue
        for m in equipo:
            cubierto = any(
                (m.id, fecha, f["id"]) in turnos_por_clave for f in activas
            )
            if cubierto:
                eventos_por_miembro[m.id] = eventos_por_miembro.get(m.id, 0) + 1
                if es_sabado(fecha):
                    sabado_cobertura_por_miembro[m.id] = True

    # Descansos = dias del rango lunes-domingo SIN turno (descanso implicito).
    dias_semana = dias_de_semana(lunes_iso) if lunes_iso else []

    resultado: list[CargaMiembro] = []
    for m in equipo:
        dias_trab = dias_trabajo_por_miembro.get(m.id, set())
        descansos = len([d for d in dias_semana if d not in dias_trab]) if dias_semana else 0
        resultado.append(
            CargaMiembro(
                miembro_id=m.id,
                nombre=m.nombre,
                eventos=eventos_por_miembro.get(m.id, 0),
                dias_trabajados=len(dias_trab),
                sabado=bool(
                    trabajo_sabado_por_miembro.get(m.id, False)
                    or sabado_cobertura_por_miembro.get(m.id, False)
                ),
                descansos=descansos,
            )
        )
    resultado.sort(key=lambda c: (-c.eventos, c.nombre.lower()))
    return resultado


# --------------------------------------------------------------------------- #
# Auto-asignacion de responsable desde la rota (Fase 3 · auto-operativa)         #
# --------------------------------------------------------------------------- #
#
# El producto quiere que el equipo SOLO cree piezas: la operativa es automatica. Una
# pieza no debe quedar SIN RESPONSABLE. Si quien la crea no fija responsable, lo deriva la rota:
# de los miembros que entran a trabajar HOY (turno en una franja NO-descanso) y cubren la
# MARCA de la pieza, se elige uno de forma DETERMINISTA. Esta funcion es PURA y testeable
# (recibe los turnos, los miembros con sus marcas y el dia); la capa de API
# (`api/publicaciones.py`) construye sus entradas desde `repos`/`auth` y aplica el resultado.


def responsable_por_marca_hoy(
    marca: str,
    fecha_iso: str,
    turnos: list[dict],
    miembros_marcas: dict[str, list[str]],
    franjas_descanso: set[str] | None = None,
) -> str | None:
    """`miembro_id` que cubre `marca` el dia `fecha_iso` segun la rota, o None.

    PURA y DETERMINISTA. Un miembro "cubre la marca hoy" si:
      - tiene un turno con `fecha == fecha_iso`,
      - ese turno NO es de una franja de descanso (`franja_id` no en `franjas_descanso`),
      - y la `marca` esta entre sus `miembros_marcas[miembro_id]`.

    Si `marca` es vacia, no hay con que filtrar por vertical y se devuelve None (no se
    inventa un responsable). Si varios miembros la cubren, se elige el de id menor
    (orden estable) para que el resultado sea reproducible. None si nadie la cubre hoy.
    """
    if not marca or not fecha_iso:
        return None
    descanso = franjas_descanso or set()
    candidatos: set[str] = set()
    for t in turnos:
        if (t.get("fecha", "") or "") != fecha_iso:
            continue
        if (t.get("franja_id", "") or "") in descanso:
            continue
        mid = t.get("miembro_id", "") or ""
        if not mid:
            continue
        if marca in (miembros_marcas.get(mid) or []):
            candidatos.add(mid)
    if not candidatos:
        return None
    return sorted(candidatos)[0]
