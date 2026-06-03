"""Auto-programación: una pieza APROBADA se encola SOLA a su próximo hueco.

OFFLINE (Postgres de pruebas vía fixture `cliente`). Igual que los tests de `encolar`,
inyectamos un "ahora" fijo parcheando el `datetime` del módulo de publicaciones (de donde
`calcular_hueco_para` lee `now()`), de modo que el hueco calculado sea determinista.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from keni_consola import auto_programar, repos
from keni_consola.api import publicaciones as ap

# Miércoles 2026-05-20 10:00 (weekday()==2).
_AHORA = datetime(2026, 5, 20, 10, 0)


class _AhoraFijo(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ANN001
        return _AHORA


@pytest.fixture
def ahora_fijo(monkeypatch):
    """Ancla `datetime.now()` del módulo de publicaciones (lo usa el cálculo de hueco)."""
    monkeypatch.setattr(ap, "datetime", _AhoraFijo)
    return _AHORA


def _crear_aprobada(cliente, **campos) -> str:
    """Crea una publicación directamente en `aprobado` (sin cadena) y devuelve su id."""
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C", "estado": "aprobado"}
    base.update(campos)
    r = cliente.post("/api/publicaciones", json=base)
    assert r.status_code == 200, r.text
    return r.json()["publicacion"]["id"]


def test_aprobada_sin_franja_se_queda_aprobada(cliente, ahora_fijo):
    # Sin franja aplicable NO se inventa fecha: la pieza se queda aprobada.
    pid = _crear_aprobada(cliente)
    assert auto_programar.programar_si_aprobada(pid) is None
    assert repos.obtener_publicacion(pid)["estado"] == "aprobado"


def test_aprobada_se_programa_en_proximo_hueco(cliente, ahora_fijo):
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})  # mié 15:00
    pid = _crear_aprobada(cliente)
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["estado"] == "programado"
    assert actualizada["fecha_programada"] == "2026-05-20T15:00"


def test_no_programa_si_no_esta_aprobada(cliente, ahora_fijo):
    # Solo actúa sobre `aprobado`: un borrador con franja disponible NO se toca.
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    pid = _crear_aprobada(cliente, estado="borrador")
    assert auto_programar.programar_si_aprobada(pid) is None
    assert repos.obtener_publicacion(pid)["estado"] == "borrador"


def test_flag_off_no_programa(cliente, ahora_fijo, monkeypatch):
    # Kill switch: con KENI_AUTO_PROGRAMAR falsy, ni la síncrona ni el barrido programan.
    monkeypatch.setenv("KENI_AUTO_PROGRAMAR", "0")
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    pid = _crear_aprobada(cliente)
    assert auto_programar.programar_si_aprobada(pid) is None
    assert auto_programar.barrer_aprobadas() == 0
    assert repos.obtener_publicacion(pid)["estado"] == "aprobado"


def test_barrer_aprobadas_programa_las_existentes(cliente, ahora_fijo):
    # El barrido coge las que YA están aprobadas (las que la síncrona no vio).
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "16:00"})
    p1 = _crear_aprobada(cliente)
    p2 = _crear_aprobada(cliente)
    assert auto_programar.barrer_aprobadas() == 2
    assert repos.obtener_publicacion(p1)["estado"] == "programado"
    assert repos.obtener_publicacion(p2)["estado"] == "programado"
