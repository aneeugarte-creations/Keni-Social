"""Etapa de AVANCE del pipeline: borradores COMPLETOS pasan solos a revisión. OFFLINE, DB tmp.

Cubre la selección (completas sí; incompletas, devueltas y recién editadas no), la transición
real (en_revision + cadena simple, idéntica al envío humano) y el gateado (SOLO el interruptor
general `KENI_MAQUINA`: el avance ya no tiene toggle propio ni exclusión por marca). Reusa el
aislamiento de `entorno` y el patrón de login real de `test_api_aprobacion` (la pieza se crea
por el API, como en producción).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, config, repos
from keni_consola.pipeline_contenido import _avance

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba-123"
_MARCA = "unotv"


def _cli_usuario(usuario: str = "ana") -> TestClient:
    auth.crear_usuario(usuario, _CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _crear_borrador(cli: TestClient, *, con_foto: bool = True, **campos) -> dict:
    # Copy COMPLETO = con hashtag: los hashtags gatean el avance igual que copy/foto.
    base = {"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C #keni"}
    base.update(campos)
    r = cli.post("/api/piezas", json=base, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    pub = r.json()["pieza"]
    if con_foto:
        # La foto REAL es lo que completa la pieza (la placa/plantilla no cuenta).
        repos.actualizar_pieza(pub["id"], {"foto": "fotos/prueba.jpg"})
    return repos.obtener_pieza(pub["id"])


def _encender(monkeypatch, *, reposo_cero: bool = True):
    """Máquina ON (único gate del avance). Reposo a 0 para no esperar."""
    monkeypatch.setenv("KENI_MAQUINA", "1")
    if reposo_cero:
        monkeypatch.setattr(_avance, "_REPOSO_MINUTOS", 0)


def test_avance_envia_borrador_completo_y_monta_cadena(entorno, monkeypatch):
    """Un borrador completo (copy + foto) pasa solo a en_revision con su cadena, una sola vez."""
    _encender(monkeypatch)
    pub = _crear_borrador(_cli_usuario())

    enviadas = _avance.ejecutar_avance()
    assert [p["id"] for p in enviadas] == [pub["id"]]

    actual = repos.obtener_pieza(pub["id"])
    assert actual["estado"] == "en_revision"
    assert actual["enviado_a_revision_en"]
    assert repos.listar_aprobaciones(pub["id"])  # cadena montada (los OK siguen siendo humanos)

    # Idempotente: el siguiente barrido no la vuelve a tocar (ya no está en borrador).
    assert _avance.ejecutar_avance() == []


def test_avance_revierte_si_falla_el_montaje_de_cadena(entorno, monkeypatch):
    """Todo-o-nada: si el montaje de la cadena lanza, la pieza vuelve a borrador sin cadena.

    Si quedara en en_revision sin cadena nunca se reintentaría (`piezas_para_avance` solo
    recoge borradores); revertirla la deja lista para un barrido futuro."""
    _encender(monkeypatch)
    pub = _crear_borrador(_cli_usuario())

    def _explota(*_a, **_k):
        raise RuntimeError("montaje caído")

    monkeypatch.setattr("keni_consola.api.colaboracion.montar_cadena_aprobacion", _explota)

    assert _avance.ejecutar_avance() == []  # el fallo no cuenta como enviada
    actual = repos.obtener_pieza(pub["id"])
    assert actual["estado"] == "borrador"  # revertida, lista para reintentar
    assert not actual["enviado_a_revision_en"]  # sello de envío limpio
    assert not repos.listar_aprobaciones(pub["id"])  # sin cadena huérfana


def test_avance_no_toca_incompletas(entorno, monkeypatch):
    """Sin foto real, sin copy o SIN HASHTAGS la pieza NO está completa: se queda en borrador."""
    _encender(monkeypatch)
    cli = _cli_usuario()
    sin_foto = _crear_borrador(cli, con_foto=False)
    sin_copy = _crear_borrador(cli, contenido="")
    sin_hashtags = _crear_borrador(cli, contenido="C sin tags")  # copy+foto pero sin #: gateada

    assert _avance.ejecutar_avance() == []
    assert repos.obtener_pieza(sin_foto["id"])["estado"] == "borrador"
    assert repos.obtener_pieza(sin_copy["id"])["estado"] == "borrador"
    assert repos.obtener_pieza(sin_hashtags["id"])["estado"] == "borrador"


def test_avance_reenvia_devueltas_tras_el_reposo(entorno, monkeypatch):
    """Una pieza DEVUELTA (dos dislikes) vuelve SOLA a la cola pasado el reposo.

    Decisión de producto (10-jun): "borrador" no es un estado donde vivir — una pieza con
    contenido completo pertenece a la cola de revisión. El reposo da margen a quien la
    devolvió para editarla antes de que reaparezca; la cadena se recrea fresca (mismo
    comportamiento que el re-envío humano)."""
    _encender(monkeypatch)
    pub = _crear_borrador(_cli_usuario())
    repos.actualizar_pieza(pub["id"], {"enviado_a_revision_en": "2026-06-01T00:00:00"})

    enviadas = _avance.ejecutar_avance()
    assert [p["id"] for p in enviadas] == [pub["id"]]
    actual = repos.obtener_pieza(pub["id"])
    assert actual["estado"] == "en_revision"
    assert actual["enviado_a_revision_en"] != "2026-06-01T00:00:00"  # sello re-estampado


def test_avance_respeta_reposo(entorno, monkeypatch):
    """Una pieza recién editada (fecha_actualizacion fresca) se deja en paz este barrido."""
    _encender(monkeypatch, reposo_cero=False)  # reposo real (10 min) y pieza recién creada
    pub = _crear_borrador(_cli_usuario())

    assert _avance.ejecutar_avance() == []
    assert repos.obtener_pieza(pub["id"])["estado"] == "borrador"


def test_avance_no_tiene_exclusion_por_marca(entorno, monkeypatch):
    """Ya NO hay opt-out por marca: el avance es incondicional. Un override legado en el store
    (cualquier `KENI_PIPELINE_AVANCE::<marca>`) se IGNORA y la pieza avanza igual."""
    _encender(monkeypatch)
    pub = _crear_borrador(_cli_usuario())
    legado = f"KENI_PIPELINE_AVANCE{config.SEP_MARCA}{_MARCA}"
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda c: "0" if c == legado else None)

    enviadas = _avance.ejecutar_avance()
    assert [p["id"] for p in enviadas] == [pub["id"]]
    assert repos.obtener_pieza(pub["id"])["estado"] == "en_revision"


def test_avance_gateado_solo_por_maquina(entorno, monkeypatch):
    """El único gate es el maestro general `KENI_MAQUINA`: con la máquina OFF no corre; ON sí."""
    pub = _crear_borrador(_cli_usuario())
    monkeypatch.setattr(_avance, "_REPOSO_MINUTOS", 0)

    # Máquina OFF: no avanza.
    monkeypatch.delenv("KENI_MAQUINA", raising=False)
    assert _avance.ejecutar_avance() == []
    assert repos.obtener_pieza(pub["id"])["estado"] == "borrador"

    # Máquina ON: avanza (sin ningún toggle de etapa de por medio).
    monkeypatch.setenv("KENI_MAQUINA", "1")
    enviadas = _avance.ejecutar_avance()
    assert [p["id"] for p in enviadas] == [pub["id"]]
    assert repos.obtener_pieza(pub["id"])["estado"] == "en_revision"
