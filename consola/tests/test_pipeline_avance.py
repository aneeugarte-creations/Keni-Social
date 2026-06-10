"""Etapa de AVANCE del pipeline: borradores COMPLETOS pasan solos a revisión. OFFLINE, DB tmp.

Cubre la selección (completas sí; incompletas, devueltas, recién editadas y marcas excluidas
no), la transición real (en_revision + cadena simple, idéntica al envío humano) y el gateado
(toggle de etapa + interruptor general). Reusa el aislamiento de `entorno` y el patrón de
login real de `test_api_aprobacion` (la pieza se crea por el API, como en producción).
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
    base = {"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    r = cli.post("/api/publicaciones", json=base, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    pub = r.json()["publicacion"]
    if con_foto:
        # La foto REAL es lo que completa la pieza (la placa/plantilla no cuenta).
        repos.actualizar_publicacion(pub["id"], {"foto": "fotos/prueba.jpg"})
    return repos.obtener_publicacion(pub["id"])


def _encender(monkeypatch, *, reposo_cero: bool = True):
    """Máquina ON; el toggle de avance queda en su DEFECTO (ON). Reposo a 0 para no esperar."""
    monkeypatch.setenv("KENI_MAQUINA", "1")
    monkeypatch.delenv(config.ENV_PIPELINE_AVANCE, raising=False)
    if reposo_cero:
        monkeypatch.setattr(_avance, "_REPOSO_MINUTOS", 0)


def test_avance_envia_borrador_completo_y_monta_cadena(entorno, monkeypatch):
    """Un borrador completo (copy + foto) pasa solo a en_revision con su cadena, una sola vez."""
    _encender(monkeypatch)
    pub = _crear_borrador(_cli_usuario())

    enviadas = _avance.ejecutar_avance()
    assert [p["id"] for p in enviadas] == [pub["id"]]

    actual = repos.obtener_publicacion(pub["id"])
    assert actual["estado"] == "en_revision"
    assert actual["enviado_a_revision_en"]
    assert repos.listar_aprobaciones(pub["id"])  # cadena montada (los OK siguen siendo humanos)

    # Idempotente: el siguiente barrido no la vuelve a tocar (ya no está en borrador).
    assert _avance.ejecutar_avance() == []


def test_avance_no_toca_incompletas(entorno, monkeypatch):
    """Sin foto real (o sin copy) la pieza NO está completa: se queda en borrador."""
    _encender(monkeypatch)
    cli = _cli_usuario()
    sin_foto = _crear_borrador(cli, con_foto=False)
    sin_copy = _crear_borrador(cli, contenido="")

    assert _avance.ejecutar_avance() == []
    assert repos.obtener_publicacion(sin_foto["id"])["estado"] == "borrador"
    assert repos.obtener_publicacion(sin_copy["id"])["estado"] == "borrador"


def test_avance_reenvia_devueltas_tras_el_reposo(entorno, monkeypatch):
    """Una pieza DEVUELTA (dos dislikes) vuelve SOLA a la cola pasado el reposo.

    Decisión de producto (10-jun): "borrador" no es un estado donde vivir — una pieza con
    contenido completo pertenece a la cola de revisión. El reposo da margen a quien la
    devolvió para editarla antes de que reaparezca; la cadena se recrea fresca (mismo
    comportamiento que el re-envío humano)."""
    _encender(monkeypatch)
    pub = _crear_borrador(_cli_usuario())
    repos.actualizar_publicacion(pub["id"], {"enviado_a_revision_en": "2026-06-01T00:00:00"})

    enviadas = _avance.ejecutar_avance()
    assert [p["id"] for p in enviadas] == [pub["id"]]
    actual = repos.obtener_publicacion(pub["id"])
    assert actual["estado"] == "en_revision"
    assert actual["enviado_a_revision_en"] != "2026-06-01T00:00:00"  # sello re-estampado


def test_avance_respeta_reposo(entorno, monkeypatch):
    """Una pieza recién editada (fecha_actualizacion fresca) se deja en paz este barrido."""
    _encender(monkeypatch, reposo_cero=False)  # reposo real (10 min) y pieza recién creada
    pub = _crear_borrador(_cli_usuario())

    assert _avance.ejecutar_avance() == []
    assert repos.obtener_publicacion(pub["id"])["estado"] == "borrador"


def test_avance_respeta_marca_apagada(entorno, monkeypatch):
    """El override por-marca (`KENI_PIPELINE_AVANCE::<marca>` falsy) excluye esa marca."""
    _encender(monkeypatch)
    pub = _crear_borrador(_cli_usuario())
    clave = config.clave_por_marca(config.ENV_PIPELINE_AVANCE, _MARCA)
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda c: "0" if c == clave else None)

    assert _avance.ejecutar_avance() == []
    assert repos.obtener_publicacion(pub["id"])["estado"] == "borrador"


def test_avance_gateado_por_toggle_y_maquina(entorno, monkeypatch):
    """`KENI_PIPELINE_AVANCE=0` apaga la etapa; sin `KENI_MAQUINA` tampoco corre (def ON solo
    del toggle: el maestro general sigue mandando)."""
    pub = _crear_borrador(_cli_usuario())
    monkeypatch.setattr(_avance, "_REPOSO_MINUTOS", 0)

    # Máquina ON pero toggle explícitamente OFF.
    monkeypatch.setenv("KENI_MAQUINA", "1")
    monkeypatch.setenv(config.ENV_PIPELINE_AVANCE, "0")
    assert _avance.ejecutar_avance() == []

    # Toggle ON (defecto) pero máquina OFF.
    monkeypatch.delenv(config.ENV_PIPELINE_AVANCE, raising=False)
    monkeypatch.delenv("KENI_MAQUINA", raising=False)
    assert _avance.ejecutar_avance() == []

    assert repos.obtener_publicacion(pub["id"])["estado"] == "borrador"
