"""Tests PUROS de la Fase 3 auto-operativa (sin DB ni red).

Cubren la lógica determinista de las tres automatizaciones, sin tocar Postgres:
  1. `rota.responsable_por_marca_hoy` — auto-asignación de responsable desde la rota.
  2. `metricas_pieza._es_reciente` — ventana del refresco proactivo por pieza.
  3. `dominio.eventos` — resumen humano de los nuevos eventos de alerta.

Los daemons y la capa de I/O (`auto_responsable`, `metricas_piezas_refresco`,
`alertas_rendimiento`) se ejercen con DB en los tests de integración; aquí queda
clavada la lógica pura, que es la que decide.
"""

from __future__ import annotations

from datetime import datetime

from keni_consola import metricas_pieza
from keni_consola import rota as r
from keni_consola.dominio import eventos

# --------------------------------------------------------------------------- #
# 1. Auto-asignación de responsable desde la rota                              #
# --------------------------------------------------------------------------- #

HOY = "2026-05-30"  # sábado real (irrelevante para esta función, pero estable)


def _turno(fecha: str, franja: str, miembro: str) -> dict:
    return {"fecha": fecha, "franja_id": franja, "miembro_id": miembro}


def test_responsable_elige_a_quien_cubre_la_marca_hoy():
    turnos = [_turno(HOY, "f1", "u2"), _turno("2026-05-29", "f1", "u1")]
    marcas = {"u1": ["claro-sports"], "u2": ["claro-sports"]}
    assert r.responsable_por_marca_hoy("claro-sports", HOY, turnos, marcas) == "u2"


def test_responsable_excluye_franja_de_descanso():
    turnos = [_turno(HOY, "fd", "u1")]
    marcas = {"u1": ["claro-sports"]}
    assert (
        r.responsable_por_marca_hoy("claro-sports", HOY, turnos, marcas, {"fd"}) is None
    )


def test_responsable_solo_de_la_marca_de_la_pieza():
    turnos = [_turno(HOY, "f1", "u1")]
    marcas = {"u1": ["unotv"]}
    assert r.responsable_por_marca_hoy("claro-sports", HOY, turnos, marcas) is None


def test_responsable_determinista_id_menor():
    turnos = [_turno(HOY, "f1", "u9"), _turno(HOY, "f1", "u3"), _turno(HOY, "f1", "u5")]
    marcas = {m: ["claro-sports"] for m in ("u3", "u5", "u9")}
    assert r.responsable_por_marca_hoy("claro-sports", HOY, turnos, marcas) == "u3"


def test_responsable_sin_marca_o_sin_turnos_es_none():
    turnos = [_turno(HOY, "f1", "u1")]
    marcas = {"u1": ["claro-sports"]}
    assert r.responsable_por_marca_hoy("", HOY, turnos, marcas) is None
    assert r.responsable_por_marca_hoy("claro-sports", HOY, [], marcas) is None
    # Nadie de turno hoy (turno de otro día).
    assert (
        r.responsable_por_marca_hoy(
            "claro-sports", HOY, [_turno("2026-05-29", "f1", "u1")], marcas
        )
        is None
    )


# --------------------------------------------------------------------------- #
# 2. Ventana del refresco proactivo por pieza                                  #
# --------------------------------------------------------------------------- #

AHORA = datetime(2026, 5, 30, 12, 0, 0)


def test_es_reciente_dentro_de_la_ventana():
    assert metricas_pieza._es_reciente("2026-05-20T10:00:00", AHORA, 30) is True


def test_no_es_reciente_fuera_de_la_ventana():
    assert metricas_pieza._es_reciente("2026-01-01T10:00:00", AHORA, 30) is False


def test_es_reciente_tolerante_con_fecha_vacia_o_invalida():
    # Sin fecha o con fecha basura: no excluimos (mejor refrescar de más).
    assert metricas_pieza._es_reciente("", AHORA, 30) is True
    assert metricas_pieza._es_reciente("no-es-fecha", AHORA, 30) is True


# --------------------------------------------------------------------------- #
# 3. Resumen humano de los nuevos eventos de alerta                            #
# --------------------------------------------------------------------------- #


def test_evento_reciclaje_en_catalogo_y_resumen():
    assert "pieza.reciclaje_sugerida" in eventos.TIPOS_EVENTO
    payload = eventos.construir_payload(
        "pieza.reciclaje_sugerida",
        {"titulo": "Gol histórico", "marca_nombre": "Claro Sports", "motivo_detalle": "Rindió muy bien"},
    )
    assert "Gol histórico" in payload["resumen"]
    assert "Claro Sports" in payload["resumen"]


def test_evento_bajo_rendimiento_en_catalogo_y_resumen():
    assert "pieza.bajo_rendimiento" in eventos.TIPOS_EVENTO
    payload = eventos.construir_payload(
        "pieza.bajo_rendimiento",
        {"titulo": "Resumen del día", "red_nombre": "Instagram", "engagement_pct": 0.4},
    )
    assert "Resumen del día" in payload["resumen"]
    assert "0.4%" in payload["resumen"]
    assert "Instagram" in payload["resumen"]
