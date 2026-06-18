"""La ausencia avisa del HUECO de cobertura que deja (turnos ya asignados en su rango).

Cara que faltaba del cruce ausencia<->turno: al REGISTRAR/editar una ausencia sobre alguien
que YA tiene turnos asignados, la respuesta trae `conflictos` (aviso, NO bloqueo). Excluye
los descansos. Usa el cliente del token (la frontera de permisos se cubre aparte).
"""

from __future__ import annotations

from keni_consola import auth, repos

from .test_api_rota import CLAVE, _crear_equipo

LUNES = "2026-05-25"  # es lunes
MARTES = "2026-05-26"


def _id_admin() -> str:
    """Id de la admin sembrada (la que recibe el aviso del descubierto en la campana)."""
    return next(u["id"] for u in auth.listar_usuarios() if u["usuario"] == "jefa")


def test_crear_ausencia_avisa_de_turnos_en_el_rango(cliente):
    miembro = _crear_equipo(1)[0]
    # El miembro tiene un turno (Mañana) el martes, DENTRO del rango de la ausencia.
    repos.crear_turno_rota(
        LUNES,
        MARTES,
        miembro_id=miembro["id"],
        miembro_nombre=miembro["usuario"],
        franja="matutino",
    )
    r = cliente.post(
        "/api/rota/ausencias",
        json={
            "miembro_id": miembro["id"],
            "desde": LUNES,
            "hasta": "2026-05-31",
            "tipo": "vacaciones",
        },
    )
    assert r.status_code == 201, r.text
    conflictos = r.json()["conflictos"]
    assert [c["fecha"] for c in conflictos] == [MARTES]
    assert conflictos[0]["franja"]  # nombre legible de la franja, no el uuid


def test_crear_ausencia_sin_turnos_no_tiene_conflictos(cliente):
    miembro = _crear_equipo(1)[0]
    r = cliente.post(
        "/api/rota/ausencias",
        json={
            "miembro_id": miembro["id"],
            "desde": "2026-06-08",
            "hasta": "2026-06-10",
            "tipo": "descanso",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["conflictos"] == []


def test_ausencia_con_huecos_avisa_al_admin_en_la_campana(cliente):
    # Una ausencia que deja turnos sin cubrir no se queda en un toast efímero: persiste un
    # aviso in-app a los admin para que el coordinador resuelva el hueco.
    auth.crear_usuario("jefa", CLAVE, "admin")
    miembro = _crear_equipo(1)[0]
    repos.crear_turno_rota(
        LUNES,
        MARTES,
        miembro_id=miembro["id"],
        miembro_nombre=miembro["usuario"],
        franja="matutino",
    )
    r = cliente.post(
        "/api/rota/ausencias",
        json={
            "miembro_id": miembro["id"],
            "desde": LUNES,
            "hasta": "2026-05-31",
            "tipo": "vacaciones",
        },
    )
    assert r.status_code == 201, r.text
    avisos = [
        n
        for n in repos.listar_notificaciones(_id_admin())
        if n["tipo"] == "ausencia_descubierto"
    ]
    assert len(avisos) == 1
    assert "sin cubrir" in avisos[0]["resumen"]
    assert avisos[0]["enlace"]  # deep-link al calendario para reasignar el turno


def test_ausencia_sin_huecos_no_avisa_al_admin(cliente):
    auth.crear_usuario("jefa", CLAVE, "admin")
    miembro = _crear_equipo(1)[0]
    r = cliente.post(
        "/api/rota/ausencias",
        json={
            "miembro_id": miembro["id"],
            "desde": "2026-06-08",
            "hasta": "2026-06-10",
            "tipo": "descanso",
        },
    )
    assert r.status_code == 201, r.text
    assert repos.listar_notificaciones(_id_admin()) == []
