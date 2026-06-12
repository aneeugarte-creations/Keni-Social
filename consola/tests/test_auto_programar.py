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


def test_horario_de_linea_gana_a_la_cadencia(cliente, ahora_fijo):
    """Una pieza CON línea usa los horarios de su línea aunque exista una cadencia general.

    Regresión real: una cadencia «todas las redes» creada a mano (ventana en UTC) pisaba los
    horarios del plan y mandó una pieza nacional a las 3 a. m.
    """
    # Cadencia general de la marca (todas las redes), ventana amplia: SIN la precedencia de
    # línea, el hueco saldría de aquí (mié 10:00 -> 10:30 con margen 30).
    cliente.post(
        "/api/cadencias",
        json={"marca": "unotv", "margen_min": 30, "hora_inicio": "06:00",
              "hora_fin": "22:00", "dias": [0, 1, 2, 3, 4, 5, 6]},
    )
    # Horario de la línea mx: miércoles 15:45.
    cliente.post(
        "/api/franjas",
        json={"dia_semana": 2, "hora": "15:45", "marca": "unotv", "categoria": "mx"},
    )
    pid = _crear_aprobada(cliente)
    _vincular_cluster(pid, categoria="mx")
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["fecha_programada"] == "2026-05-20T15:45"  # la línea, no la cadencia


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


def test_no_resucita_si_dejo_de_estar_aprobada(cliente, ahora_fijo, monkeypatch):
    """CARRERA (CAS): entre que la auto-programación lee la pieza `aprobado` y escribe
    `programado`, otro flujo la movió (p. ej. una edición la resetea a `borrador`). El CAS sobre
    `estado` evita RESUCITARLA a `programado` pisando el estado/fecha que dejó el humano."""
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    pid = _crear_aprobada(cliente)

    real_hueco = ap.calcular_hueco_para

    def _hueco_con_carrera(pub, ahora=None):  # noqa: ANN001
        # Simula la carrera: la pieza deja de estar aprobada (vuelve a borrador) JUSTO antes de la
        # escritura, como si otro flujo la editara entre la lectura y el UPDATE condicional.
        repos.actualizar_publicacion(pid, {"estado": "borrador", "fecha_programada": ""})
        return real_hueco(pub, ahora)

    monkeypatch.setattr(ap, "calcular_hueco_para", _hueco_con_carrera)
    # No la programa (el CAS no aplica) y no lanza: best-effort.
    assert auto_programar.programar_si_aprobada(pid) is None
    despues = repos.obtener_publicacion(pid)
    assert despues["estado"] == "borrador"  # sigue en el estado nuevo, NO resucitada
    assert despues["fecha_programada"] == ""  # ni le pisó la fecha


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


# --------------------------------------------------------------------------- #
# Evergreen diario: reemision automatica del banco green (1 al dia, hueco 8h) #
# --------------------------------------------------------------------------- #


def _green_aprobado(titulo="Green del banco", creado="2026-05-01T00:00:00", estado="publicado"):
    """Siembra un contenido green del BANCO (creado hace tiempo: fuera de la ventana de
    24 h del plan). Por defecto su pieza ya está PUBLICADA (un green aprobado sale una
    primera vez por su propia franja; al banco de reemisión llega ya publicado)."""
    cont = repos.crear_contenido(
        clase="contenido", titulo=titulo, marca="unotv",
        flujo="evergreen", origen="evergreen", creado=creado,
    )
    repos.crear_contenido_plataforma(
        contenido_id=cont["id"], red="x", copy="Copy green", estado=estado,
        falta_revision=False,
    )
    return cont


def test_evergreen_diario_reemite_uno_del_banco(cliente, ahora_fijo, monkeypatch):
    from keni_consola import evergreen_diario

    monkeypatch.setenv("KENI_MAQUINA", "1")
    monkeypatch.setenv("KENI_PLAN_DIA::unotv", "evergreen:1")
    original = _green_aprobado()

    assert evergreen_diario.barrer() == 1

    reemisiones = [
        c for c in repos.listar_contenido(clase="contenido", marca="unotv")
        if c.get("origen") == evergreen_diario.ORIGEN_EVERGREEN_DIARIO
    ]
    assert len(reemisiones) == 1
    copia = reemisiones[0]
    assert copia["titulo"] == original["titulo"]
    assert copia["categoria"] == "evergreen"
    piezas = repos.listar_contenido_plataforma(copia["id"])
    assert len(piezas) == 1 and piezas[0]["estado"] == "aprobado"
    assert piezas[0]["copy"] == "Copy green"
    # IDEMPOTENTE en la ventana: la reemision cuenta como generado -> no se anade otra hoy.
    assert evergreen_diario.barrer() == 0


def test_evergreen_diario_no_reemite_si_hoy_ya_hay_green(cliente, ahora_fijo, monkeypatch):
    from keni_consola import evergreen_diario

    monkeypatch.setenv("KENI_MAQUINA", "1")
    monkeypatch.setenv("KENI_PLAN_DIA::unotv", "evergreen:1")
    _green_aprobado()
    # El equipo YA creo un green hoy (cuenta en la ventana): el automatismo no anade otro.
    # Es una publicacion real -> lleva su pieza por red (un tema sin piezas no contaria).
    green_hoy = repos.crear_contenido(
        clase="contenido", titulo="Green de hoy", marca="unotv", flujo="evergreen",
    )
    repos.crear_contenido_plataforma(
        contenido_id=green_hoy["id"], red="x", copy="Green de hoy", estado="aprobado",
        falta_revision=False,
    )
    assert evergreen_diario.barrer() == 0


def test_evergreen_diario_sin_banco_o_sin_plan_no_hace_nada(cliente, ahora_fijo, monkeypatch):
    from keni_consola import evergreen_diario

    monkeypatch.setenv("KENI_MAQUINA", "1")
    # Sin plan con linea evergreen: nada.
    monkeypatch.setenv("KENI_PLAN_DIA::unotv", "mx:4")
    _green_aprobado()
    assert evergreen_diario.barrer() == 0
    # Con plan pero sin banco aprobado: nada (no se inventa contenido).
    monkeypatch.setenv("KENI_PLAN_DIA::piso-15", "evergreen:1")
    assert evergreen_diario.barrer() == 0


def test_evergreen_diario_reemision_se_programa_al_hueco_de_su_categoria(
    cliente, ahora_fijo, monkeypatch
):
    """Cadena completa: reemision (aprobado) -> barrer_aprobadas -> franja evergreen."""
    from keni_consola import evergreen_diario

    monkeypatch.setenv("KENI_MAQUINA", "1")
    monkeypatch.setenv("KENI_PLAN_DIA::unotv", "evergreen:1")
    # Franja evergreen (mie 14:00 UTC = 8:00 MX del miercoles del reloj fijo).
    cliente.post(
        "/api/franjas",
        json={"dia_semana": 2, "hora": "14:00", "marca": "unotv", "categoria": "evergreen"},
    )
    _green_aprobado()

    assert evergreen_diario.barrer() == 1
    assert auto_programar.barrer_aprobadas() == 1

    programadas = repos.listar_publicaciones(estado="programado")
    assert len(programadas) == 1
    assert programadas[0]["fecha_programada"] == "2026-05-20T14:00"
