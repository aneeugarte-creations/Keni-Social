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


def _vincular_cluster(pid: str, *, categoria: str = "mx", breaking: int = 0) -> None:
    """Vincula la pieza a una HISTORIA del pool (cluster→contenido), como al promoverla."""
    plat = repos.obtener_contenido_plataforma(pid)
    assert plat and plat.get("contenido_id")
    repos.upsert_noticia_cluster({
        "id": f"cl-{pid[:8]}", "titulo": "Historia origen", "resumen": "", "marca": "unotv",
        "categoria": categoria, "geo": "MX", "clave": f"t:{pid[:8]}", "n_items": 1,
        "n_fuentes": 2, "idiomas": ["es"], "senal": 0, "score": 0.7, "breaking": breaking,
        "primer_visto": "2026-05-19T00:00:00", "ultimo_visto": "2026-05-19T00:00:00",
        "estado": "usado", "verificacion": "corroborada",
    })
    repos.actualizar_noticia_cluster(f"cl-{pid[:8]}", contenido_id=plat["contenido_id"])


def test_breaking_se_programa_al_instante(cliente, ahora_fijo):
    """Una pieza BREAKING no espera franja: se programa a ahora+margen (minuto libre)."""
    pid = _crear_aprobada(cliente)
    _vincular_cluster(pid, breaking=1)
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["fecha_programada"] == "2026-05-20T10:02"  # _AHORA + 2 min


def test_categoria_usa_sus_horarios_del_plan(cliente, ahora_fijo):
    """Una pieza de una categoría se programa en las franjas de SU categoría, no en las genéricas."""
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "12:00"})  # genérica mié 12:00
    cliente.post(
        "/api/franjas",
        json={"dia_semana": 2, "hora": "14:45", "marca": "unotv", "categoria": "internacional"},
    )
    pid = _crear_aprobada(cliente)
    _vincular_cluster(pid, categoria="internacional")
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["fecha_programada"] == "2026-05-20T14:45"


def test_redes_de_un_tema_comparten_hora(cliente, ahora_fijo):
    """El hueco se ocupa POR (marca, red): piezas del mismo tema en redes distintas salen a
    la MISMA hora (espejo del índice de unicidad de slot por marca+red+fecha)."""
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00", "marca": "unotv"})
    pid_x = _crear_aprobada(cliente, red="x")
    pid_ig = _crear_aprobada(cliente, red="instagram")
    a = auto_programar.programar_si_aprobada(pid_x)
    b = auto_programar.programar_si_aprobada(pid_ig)
    assert a is not None and b is not None
    assert a["fecha_programada"] == b["fecha_programada"] == "2026-05-20T15:00"


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
