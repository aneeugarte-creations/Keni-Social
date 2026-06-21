"""Validacion anti-escape del slug de un agente (`agentes._rutas`). OFFLINE.

El slug de un agente generico SOLO puede vivir dentro de la raiz de agentes. Aqui se
prueba que entradas maliciosas (`..`, rutas absolutas, separadores, comodines,
caracteres de control) se rechazan, y que un slug limpio resuelve dentro de la raiz.
Sin disco real: la raiz es un `tmp_path`.
"""

from __future__ import annotations

import pytest

from keni_consola.agentes._rutas import NombreAgenteInvalido, resolver_slug_agente


def test_slug_limpio_resuelve_dentro_de_la_raiz(tmp_path):
    raiz = tmp_path / "datos"
    raiz.mkdir()
    destino = resolver_slug_agente("ok", raiz)
    assert destino.is_relative_to(raiz)
    assert destino.name == "ok"


def test_dotdot_rechazado_con_mensaje_de_escape(tmp_path):
    with pytest.raises(NombreAgenteInvalido) as exc:
        resolver_slug_agente("../fuera", tmp_path)
    assert "salir de la carpeta base" in str(exc.value).lower()


def test_ruta_absoluta_rechazada(tmp_path):
    for malo in ("/abs", "~/x", str(tmp_path / "intruso")):
        with pytest.raises(NombreAgenteInvalido):
            resolver_slug_agente(malo, tmp_path)


def test_separadores_comodines_y_control_rechazados(tmp_path):
    for malo in ("a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b"):
        with pytest.raises(NombreAgenteInvalido):
            resolver_slug_agente(malo, tmp_path)
    # Caracter de control (tab) en medio del nombre.
    with pytest.raises(NombreAgenteInvalido):
        resolver_slug_agente("a\tb", tmp_path)


def test_vacio_rechazado(tmp_path):
    for malo in ("", "   "):
        with pytest.raises(NombreAgenteInvalido):
            resolver_slug_agente(malo, tmp_path)


def test_escape_compuesto_rechazado(tmp_path):
    for malo in ("..", "../x", "a/../../b"):
        with pytest.raises(NombreAgenteInvalido):
            resolver_slug_agente(malo, tmp_path)
