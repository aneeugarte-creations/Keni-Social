"""Tests de `db.existe_publicado_similar` (dedup contra contenido YA publicado).

Verifica que la marca no republique lo que ya salió: dado un titulo, devuelve True si la
MISMA marca tiene contenido con alguna plataforma en estado 'publicado' cuyo titulo casa
(exacto o fuzzy >= umbral) con el dado. Aislamiento por marca y best-effort (no rompe).
Usa Postgres de pruebas via `entorno` (se SALTA si no hay).
"""

from __future__ import annotations

from keni_consola import db, repos


def _publicar(marca: str, titulo: str) -> str:
    """Crea un contenido de `marca` con una plataforma en estado 'publicado'. Devuelve id."""
    c = db.crear_contenido(titulo=titulo, marca=marca)
    db.crear_contenido_plataforma(contenido_id=c["id"], red="x", estado="publicado")
    return c["id"]


def test_match_exacto_por_titulo(entorno):
    _publicar("unotv", "El América gana el clásico")
    # Mismo titulo con acentos/mayusculas distintas: casa por `clave(...)`.
    assert db.existe_publicado_similar("unotv", "el america GANA el clasico") is True


def test_match_fuzzy_sobre_umbral(entorno):
    _publicar("unotv", "El América gana el clásico ante Chivas en el Estadio Azteca")
    # Casi identico -> ratio alto -> casa con el umbral por defecto (0.85).
    assert (
        db.existe_publicado_similar(
            "unotv", "El America gana el clasico ante Chivas en Estadio Azteca"
        )
        is True
    )


def test_no_match_titulo_distinto(entorno):
    _publicar("unotv", "Resultados de la jornada 10 de la Liga MX")
    assert (
        db.existe_publicado_similar("unotv", "Pronóstico del clima en CDMX mañana") is False
    )


def test_aislamiento_por_marca(entorno):
    """Lo publicado por OTRA marca no cuenta para la marca consultada."""
    _publicar("clarosports", "Final de la Champions League")
    assert db.existe_publicado_similar("unotv", "Final de la Champions League") is False
    assert db.existe_publicado_similar("clarosports", "Final de la Champions League") is True


def test_no_publicado_no_cuenta(entorno):
    """Contenido sin plataforma 'publicado' no dispara el dedup."""
    c = db.crear_contenido(titulo="Borrador del América", marca="unotv")
    db.crear_contenido_plataforma(contenido_id=c["id"], red="x", estado="pendiente")
    assert db.existe_publicado_similar("unotv", "Borrador del América") is False


def test_sin_contenido_devuelve_false(entorno):
    assert db.existe_publicado_similar("unotv", "Cualquier cosa") is False


def test_delegado_repos(entorno):
    _publicar("unotv", "Gol de último minuto del Cruz Azul")
    assert repos.existe_publicado_similar("unotv", "gol de ultimo minuto del cruz azul") is True
