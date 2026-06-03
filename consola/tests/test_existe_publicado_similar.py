"""Tests de `db.existe_publicado_similar` (dedup contra contenido YA publicado).

Verifica que la marca no republique lo que ya salió: dado un titulo, devuelve True si la
MISMA marca tiene contenido con alguna plataforma en estado 'publicado' cuyo titulo casa
(exacto o fuzzy >= umbral) con el dado. Aislamiento por marca y best-effort (no rompe).
Usa Postgres de pruebas via `entorno` (se SALTA si no hay).
"""

from __future__ import annotations

from keni_consola import db, repos


def _publicar(marca: str, titulo: str, *, url_fuente: str = "") -> str:
    """Crea un contenido de `marca` con una plataforma en estado 'publicado'. Devuelve id."""
    c = db.crear_contenido(titulo=titulo, marca=marca, url_fuente=url_fuente)
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


# --------------------------------------------------------------------------- #
# Dedup por URL (F3): `url_fuente` persiste y cruza por URL canonica             #
# --------------------------------------------------------------------------- #

def test_crear_contenido_persiste_url_fuente(entorno):
    """`crear_contenido(url_fuente=...)` la guarda y se lee de vuelta."""
    c = db.crear_contenido(titulo="Algo", marca="unotv", url_fuente="https://medio.com/nota")
    assert c["url_fuente"] == "https://medio.com/nota"
    leido = db.obtener_contenido(c["id"])
    assert leido is not None and leido["url_fuente"] == "https://medio.com/nota"


def test_match_por_url_canonica(entorno):
    """Una pieza PUBLICADA con la misma url_fuente (canonica) dispara el dedup por URL.

    El titulo dado NO casa con el publicado (forzamos el match por la rama de URL): aun con
    parametros de tracking distintos, la url canonica coincide -> True.
    """
    _publicar("unotv", "Titular original publicado", url_fuente="https://medio.com/nota-x")
    # Misma URL con tracking + `www` + barra final: canoniza igual -> match por URL.
    assert (
        db.existe_publicado_similar(
            "unotv",
            "Un titular completamente distinto que no casaria por similitud",
            url="https://www.medio.com/nota-x/?utm_source=tw",
        )
        is True
    )


def test_no_match_por_url_cae_al_titulo(entorno):
    """Si la URL no casa con ninguna publicada, se evalua por TITULO (fallback)."""
    _publicar("unotv", "El América gana el clásico", url_fuente="https://medio.com/nota-a")
    # URL distinta (no casa por URL) pero titulo equivalente -> True por la rama de titulo.
    assert (
        db.existe_publicado_similar(
            "unotv",
            "el america GANA el clasico",
            url="https://otro.com/nota-distinta",
        )
        is True
    )
    # URL distinta Y titulo distinto -> False.
    assert (
        db.existe_publicado_similar(
            "unotv",
            "Pronóstico del clima en CDMX mañana",
            url="https://otro.com/nota-distinta",
        )
        is False
    )


def test_url_match_aislado_por_marca(entorno):
    """La url_fuente publicada por OTRA marca no cuenta para la marca consultada."""
    _publicar("clarosports", "Final", url_fuente="https://medio.com/final")
    assert (
        db.existe_publicado_similar("unotv", "x", url="https://medio.com/final") is False
    )
    assert (
        db.existe_publicado_similar("clarosports", "x", url="https://medio.com/final")
        is True
    )
