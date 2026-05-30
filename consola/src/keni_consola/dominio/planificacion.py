"""Dominio PLANIFICACION: sugerir el MEJOR momento de publicacion (logica PURA).

Objetivo de producto ("el equipo solo crea piezas; la operativa es automatica"): que el
community manager no tenga que ADIVINAR a que hora publicar. Esta capa, dado:

  1. el HISTORICO de engagement de la marca/red (de `metricas_cache` -> Metricool, unica
     fuente: la serie diaria de interacciones del periodo), y
  2. las FRANJAS de publicacion configuradas (colas `(dia_semana, hora)` aplicables a esa
     marca/red) con sus HUECOS libres (los datetimes ya `programado` se evitan),

elige el hueco FUTURO libre cuyo DIA DE LA SEMANA rinde mejor historicamente.

POR QUE DIA-DE-SEMANA (y no hora exacta)
----------------------------------------
La fuente de metricas (Metricool, via `keni_metricas`) expone la fecha de publicacion de
cada pieza/serie con granularidad de DIA (`publicado: date` / serie diaria), no de hora.
Asi que la señal HONESTA que tenemos es "que dia de la semana interactua mas la audiencia".
La HORA la aportan las franjas (las define el equipo: 09:00, 13:00, ...). Combinamos ambas:
de los huecos libres de las franjas, preferimos el que cae en el mejor dia de la semana.
Sin inventar una "hora optima" que los datos no respaldan.

DEGRADACION HONESTA
-------------------
- Sin historico (serie vacia): no hay señal de dia; se cae al PROXIMO hueco libre (el mismo
  criterio que el encolado normal), marcando el motivo "sin historico".
- Sin franjas aplicables: no hay candidatos; se devuelve None (la UI lo dice).

Todo aqui es PURO y DETERMINISTA: recibe el historico, las franjas, los ocupados y `ahora`
inyectados. El handler (`api/sugerencias_hora.py`) trae esos datos de `metricas_cache`/
`repos` y consume estas funciones. Asi se testea sin red, sin reloj y sin BD.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

# Numero de candidatos (huecos libres de distintas franjas/dias) que evaluamos por
# delante de `ahora`. Con un horizonte de ~2 semanas cubrimos al menos un hueco por cada
# dia de la semana presente en las franjas, sin recorrer un anio entero.
_MAX_CANDIDATOS = 60
# Horizonte (dias) de busqueda de huecos candidatos.
_HORIZONTE_DIAS = 21

# Nombres de dia (0=lunes .. 6=domingo, igual que datetime.weekday()) para el motivo legible.
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


@dataclass(frozen=True)
class Sugerencia:
    """Una sugerencia de fecha-hora de publicacion (resultado PURO).

    `fecha` es ISO 'YYYY-MM-DDTHH:MM' (lo que entiende el programador). `score` es el peso
    historico del dia de la semana de esa fecha (mayor = mejor; 0.0 si no hay historico).
    `motivo` explica en español POR QUE se eligio (dia que mas rinde / proximo hueco libre).
    `con_historico` distingue una sugerencia respaldada por datos de una de mero "siguiente
    hueco" (sin señal). La UI muestra `motivo` junto al boton de 1 clic.
    """

    fecha: str
    score: float
    motivo: str
    con_historico: bool

    def a_dict(self) -> dict[str, Any]:
        return {
            "fecha": self.fecha,
            "score": round(self.score, 2),
            "motivo": self.motivo,
            "con_historico": self.con_historico,
        }


def perfil_por_dia_semana(puntos: list[dict[str, Any]]) -> dict[int, float]:
    """Engagement medio por DIA DE LA SEMANA a partir de la serie diaria de metricas.

    `puntos` son los `PuntoSerie` crudos de `construir_tendencia_diaria` (cacheado como
    TIPO_TENDENCIA): cada uno `{fecha: 'YYYY-MM-DD', interacciones: int, visualizaciones}`.
    Agrupamos las interacciones por dia de la semana (0=lunes..6=domingo) y devolvemos la
    MEDIA de interacciones de cada dia presente. Las interacciones son la magnitud
    comparable entre redes (ver `keni_metricas.schema`), por eso son la señal.

    Devuelve `{dia_semana: media_interacciones}` SOLO para los dias con datos (un dia sin
    ningun punto no aparece: su señal es desconocida, no cero). Dict vacio si no hay datos.
    """
    sumas: dict[int, float] = {}
    conteos: dict[int, int] = {}
    for p in puntos:
        fecha_iso = p.get("fecha")
        if not isinstance(fecha_iso, str) or not fecha_iso.strip():
            continue
        try:
            dia = datetime.fromisoformat(fecha_iso[:10]).weekday()
        except ValueError:
            continue
        inter = p.get("interacciones", 0)
        try:
            valor = float(inter)
        except (TypeError, ValueError):
            continue
        if valor < 0:
            continue
        sumas[dia] = sumas.get(dia, 0.0) + valor
        conteos[dia] = conteos.get(dia, 0) + 1
    return {dia: sumas[dia] / conteos[dia] for dia in sumas if conteos[dia] > 0}


def _candidatos_libres(
    franjas_aplican: list[dict[str, Any]],
    ahora: datetime,
    ocupados: set[str],
) -> list[datetime]:
    """Huecos FUTUROS libres de las franjas dadas dentro del horizonte, ordenados.

    Recorre cada franja `(dia_semana, hora)` repetidamente semana a semana (saltando los
    datetimes en `ocupados`) y junta los primeros huecos de cada una dentro del horizonte.
    Deduplica y ordena cronologicamente. PURO: depende solo de sus argumentos.
    """
    limite = ahora + timedelta(days=_HORIZONTE_DIAS)
    vistos: set[str] = set()
    candidatos: list[datetime] = []
    for franja in franjas_aplican:
        hora = franja.get("hora", "")
        try:
            hh, mm = (int(x) for x in str(hora).split(":"))
        except (ValueError, TypeError):
            continue
        dia_semana = franja.get("dia_semana")
        if not isinstance(dia_semana, int) or not (0 <= dia_semana <= 6):
            continue
        delta = (dia_semana - ahora.weekday()) % 7
        candidato = (ahora + timedelta(days=delta)).replace(
            hour=hh, minute=mm, second=0, microsecond=0
        )
        if candidato <= ahora:
            candidato += timedelta(days=7)
        # Avanza semana a semana mientras el hueco siga dentro del horizonte.
        while candidato <= limite:
            clave = candidato.strftime("%Y-%m-%dT%H:%M")
            if clave not in ocupados and clave not in vistos:
                vistos.add(clave)
                candidatos.append(candidato)
            candidato += timedelta(days=7)
    candidatos.sort()
    return candidatos[:_MAX_CANDIDATOS]


def sugerir_mejor_hora(
    *,
    franjas_aplican: list[dict[str, Any]],
    perfil_dia: dict[int, float],
    ahora: datetime,
    ocupados: set[str],
) -> Sugerencia | None:
    """Elige el mejor hueco FUTURO libre segun el historico por dia de la semana (PURA).

    Reglas:
      - Sin franjas aplicables -> None (no hay donde publicar; la UI lo dice).
      - Con historico (`perfil_dia` no vacio): de los huecos libres, gana el del dia de la
        semana con MAYOR engagement medio; a igualdad de dia, el mas temprano. Motivo:
        "El <dia> suele rendir mejor (~N interacciones de media)".
      - Sin historico: no hay señal de dia -> el PROXIMO hueco libre (mismo criterio que el
        encolado normal). Motivo: "sin historico, proximo hueco libre".

    Determinista: depende solo de sus argumentos. `ahora` y `ocupados` inyectados.
    """
    candidatos = _candidatos_libres(franjas_aplican, ahora, ocupados)
    if not candidatos:
        return None

    if not perfil_dia:
        primero = candidatos[0]
        return Sugerencia(
            fecha=primero.strftime("%Y-%m-%dT%H:%M"),
            score=0.0,
            motivo="Sin histórico de la marca/red todavía: se propone el próximo hueco libre.",
            con_historico=False,
        )

    # Con historico: maximizar el score del dia, y a igualdad, el hueco mas temprano. Los
    # candidatos ya vienen ordenados cronologicamente, asi que un `max` estable con clave
    # (score, -indice) elige el mejor dia y, dentro de el, el primero por orden.
    mejor_idx = max(
        range(len(candidatos)),
        key=lambda i: (perfil_dia.get(candidatos[i].weekday(), 0.0), -i),
    )
    elegido = candidatos[mejor_idx]
    score = perfil_dia.get(elegido.weekday(), 0.0)
    dia_nombre = _DIAS[elegido.weekday()]
    motivo = (
        f"El {dia_nombre} suele rendir mejor para esta marca/red "
        f"(~{score:.0f} interacciones de media en el periodo)."
    )
    return Sugerencia(
        fecha=elegido.strftime("%Y-%m-%dT%H:%M"),
        score=score,
        motivo=motivo,
        con_historico=True,
    )
