"""Tests del dominio de aprobacion (#9): transiciones PURAS, sin HTTP ni persistencia.

`dominio.aprobacion` decide si una transicion de revision es valida y devuelve los
campos a aplicar (o un error). Estos tests fijan esa logica de forma aislada: estados
de partida invalidos, la regla de "otro par de ojos" y el caso admin/token.
"""

from __future__ import annotations

from keni_consola.dominio import aprobacion

_ANA = {"id": "ana1", "usuario": "ana"}
_BETO = {"id": "beto1", "usuario": "beto"}


def _pub(estado: str, autor_id: str = "ana1") -> dict:
    return {"id": "p1", "estado": estado, "autor_id": autor_id, "autor_nombre": "ana"}


# --- enviar_a_revision ----------------------------------------------------- #


def test_enviar_borrador_ok():
    campos, error = aprobacion.enviar_a_revision(_pub("borrador"), _ANA)
    assert error is None
    assert campos["estado"] == "en_revision"
    assert campos["enviado_a_revision_en"]
    # Arranca limpia de revisor previo.
    assert campos["revisor_id"] == "" and campos["revisado_en"] == ""


def test_enviar_no_borrador_error():
    for estado in ("en_revision", "aprobado", "programado", "publicado"):
        campos, error = aprobacion.enviar_a_revision(_pub(estado), _ANA)
        assert campos is None and error


# --- aprobar --------------------------------------------------------------- #


def test_aprobar_por_otro_ok():
    campos, error = aprobacion.aprobar(_pub("en_revision", autor_id="ana1"), _BETO, rol="editor")
    assert error is None
    assert campos["estado"] == "aprobado"
    assert campos["revisor_nombre"] == "beto"


def test_aprobar_estado_invalido_error():
    campos, error = aprobacion.aprobar(_pub("borrador"), _BETO, rol="editor")
    assert campos is None and error


def test_autor_no_aprueba_su_pieza():
    campos, error = aprobacion.aprobar(_pub("en_revision", autor_id="ana1"), _ANA, rol="editor")
    assert campos is None
    assert "propia pieza" in error.lower()


def test_admin_aprueba_su_pieza():
    campos, error = aprobacion.aprobar(_pub("en_revision", autor_id="ana1"), _ANA, rol="admin")
    assert error is None and campos["estado"] == "aprobado"


def test_token_de_mantenimiento_aprueba():
    # autor None = acceso por token (mantenimiento) => permitido aunque coincida.
    campos, error = aprobacion.aprobar(_pub("en_revision"), None, rol=None)
    assert error is None and campos["estado"] == "aprobado"


# --- rechazar -------------------------------------------------------------- #


def test_rechazar_por_otro_vuelve_a_borrador():
    campos, error = aprobacion.rechazar(_pub("en_revision", autor_id="ana1"), _BETO, rol="editor")
    assert error is None and campos["estado"] == "borrador"
    assert campos["revisor_nombre"] == "beto"


def test_autor_no_rechaza_su_pieza():
    campos, error = aprobacion.rechazar(_pub("en_revision", autor_id="ana1"), _ANA, rol="editor")
    assert campos is None and "propia pieza" in error.lower()
