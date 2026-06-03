"""Tests del Investigador (Fase 1): daemon + gate del snapshot del Radar. OFFLINE, sin red.

Cubre el contrato de CERO REGRESION (flag OFF) y la materializacion/lectura con el flag ON:

  - GATE OFF por defecto: `config.investigador_activo()` es False sin env; con el flag OFF
    `api.radar._temas_desde_snapshot` devuelve None (los endpoints siguen en VIVO -> los tests
    existentes de radar/parrilla NO se rompen).
  - GATE ON: `_temas_desde_snapshot` lee del snapshot (`repos.listar_radar_items`) y reconstruye
    Temas; `?refresh=1` lo SALTA (vuelve None -> golpea fuentes reales).
  - `materializar_snapshot`: consolida sobre COPIAS, puntua, marca el estado editorial y ESCRIBE
    via `repos.upsert_radar_items`. Best-effort: nunca lanza.

Las firmas de `repos.*`/`dedup.*` que implementa otro agente se MOCKEAN aqui (el test no depende
de su implementacion): `upsert_radar_items`, `listar_radar_items`, `listar_contenido`,
`dedup.url_canonica`. `dedup.clave` se usa real (ya existe).
"""

from __future__ import annotations

import pytest

from keni_consola import config, investigador, radar
from keni_consola import repos as repos_modulo
from keni_consola.api import radar as api_radar
from keni_consola.dominio import dedup


def _tema(titulo: str, *, senal: int = 1000, url: str = "https://example.com/a") -> radar.Tema:
    """Construye un Tema minimo con un enlace (para ejercitar `url_canonica`)."""
    enlace = radar.Enlace(titulo="nota", url=url, fuente="Medio")
    return radar.Tema(
        titulo=titulo,
        redes={"busquedas-mx"},
        fuentes={"Google Trends"},
        por_que="sube por X",
        senal=senal,
        senal_texto=f"{senal}+",
        enlaces=[enlace],
        _claves_enlace={url.lower()},
    )


# --------------------------------------------------------------------------- #
# GATE: OFF por defecto                                                         #
# --------------------------------------------------------------------------- #

def test_gate_off_por_defecto(monkeypatch):
    """Sin env, el Investigador esta OFF (conservador)."""
    monkeypatch.delenv("KENI_INVESTIGADOR", raising=False)
    assert config.investigador_activo() is False
    # Intervalo: def 6, min 1.
    monkeypatch.delenv("KENI_INVESTIGADOR_INTERVALO_HORAS", raising=False)
    assert config.investigador_intervalo_horas() == 6


def test_gate_on_con_flag(monkeypatch):
    monkeypatch.setenv("KENI_INVESTIGADOR", "1")
    assert config.investigador_activo() is True


def test_intervalo_min_1(monkeypatch):
    monkeypatch.setenv("KENI_INVESTIGADOR_INTERVALO_HORAS", "0")
    assert config.investigador_intervalo_horas() == 1


# --------------------------------------------------------------------------- #
# _temas_desde_snapshot: el gate de los endpoints                              #
# --------------------------------------------------------------------------- #

def test_snapshot_none_con_flag_off(monkeypatch):
    """Flag OFF: devuelve None en la PRIMERA linea -> los endpoints van en vivo (cero regresion)."""
    monkeypatch.delenv("KENI_INVESTIGADOR", raising=False)
    # Si tocara repos seria un error: con el flag OFF no debe ni intentarlo.
    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debe leer el snapshot con el flag OFF")
    monkeypatch.setattr(repos_modulo, "listar_radar_items", _boom, raising=False)
    assert api_radar._temas_desde_snapshot("claro-sports", "MX") is None


def test_snapshot_none_con_refresh(monkeypatch):
    """`?refresh=1` SIEMPRE salta el snapshot (golpea fuentes reales), aun con el flag ON."""
    monkeypatch.setenv("KENI_INVESTIGADOR", "1")
    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debe leer el snapshot cuando se refresca")
    monkeypatch.setattr(repos_modulo, "listar_radar_items", _boom, raising=False)
    assert api_radar._temas_desde_snapshot("claro-sports", "MX", refrescar=True) is None


def test_snapshot_lee_y_reconstruye(monkeypatch):
    """Flag ON + snapshot fresco: reconstruye Temas desde las filas del snapshot."""
    monkeypatch.setenv("KENI_INVESTIGADOR", "1")
    filas = [
        {
            "titulo": "Final de la Champions",
            "redes": ["busquedas-mx"],
            "fuentes": ["Google Trends"],
            "por_que": "se juega hoy",
            "senal": 90000,
            "senal_texto": "90K+",
            "curado": False,
            "enlaces": [{"titulo": "nota", "url": "https://example.com/c", "fuente": "Medio"}],
            "score": 0.8,
            "razon": "viralidad alta",
            "estado": "en_parrilla",
            "url_canonica": "https://example.com/c",
        }
    ]

    captura = {}

    def _listar(*, marca, geo, frescas_seg=None):  # noqa: ANN001, ANN003
        captura["marca"] = marca
        captura["geo"] = geo
        captura["frescas_seg"] = frescas_seg
        return filas

    monkeypatch.setattr(repos_modulo, "listar_radar_items", _listar, raising=False)
    temas = api_radar._temas_desde_snapshot("claro-sports", "MX")
    assert temas is not None
    assert [t.titulo for t in temas] == ["Final de la Champions"]
    # Lee la marca/geo pedidos y pasa un TTL > 0 (no el de la cache en vivo).
    assert captura["marca"] == "claro-sports"
    assert captura["geo"] == "MX"
    assert captura["frescas_seg"] and captura["frescas_seg"] > 0


def test_snapshot_vacio_es_none(monkeypatch):
    """Snapshot sin filas -> None (sin snapshot aun -> camino en vivo)."""
    monkeypatch.setenv("KENI_INVESTIGADOR", "1")
    monkeypatch.setattr(
        repos_modulo, "listar_radar_items", lambda **k: [], raising=False
    )
    assert api_radar._temas_desde_snapshot("claro-sports", "MX") is None


def test_snapshot_excepcion_es_none(monkeypatch):
    """Cualquier excepcion al leer -> None (degradacion al camino en vivo, sin propagar)."""
    monkeypatch.setenv("KENI_INVESTIGADOR", "1")
    def _boom(**k):  # noqa: ANN003
        raise RuntimeError("db caida")
    monkeypatch.setattr(repos_modulo, "listar_radar_items", _boom, raising=False)
    assert api_radar._temas_desde_snapshot("claro-sports", "MX") is None


def test_ttl_snapshot_distinto_del_de_cache(monkeypatch):
    """El TTL del snapshot NO es el de la cache en vivo (`_TTL_CACHE=180`)."""
    monkeypatch.setenv("KENI_INVESTIGADOR_INTERVALO_HORAS", "6")
    # ~2 intervalos = 12h = 43200s, muy distinto de 180.
    assert api_radar._ttl_snapshot() != api_radar._TTL_CACHE
    assert api_radar._ttl_snapshot() == 12 * 3600.0


# --------------------------------------------------------------------------- #
# materializar_snapshot: consolida, puntua, marca estado y escribe              #
# --------------------------------------------------------------------------- #

def test_materializar_escribe_items(monkeypatch):
    """Materializa: consolida sobre COPIAS, puntua y escribe via upsert_radar_items."""
    temas = [_tema("Gol de ultimo minuto", senal=70000), _tema("Lesion de la estrella", senal=5000)]
    grupos = [temas]

    monkeypatch.setattr(
        api_radar, "_radar_consolidado", lambda geo, **k: (grupos, []), raising=True
    )
    # url_canonica la implementa otro agente; la mockeamos a identidad para el test.
    monkeypatch.setattr(dedup, "url_canonica", lambda u: u, raising=False)
    # Sin estado editorial reciente.
    monkeypatch.setattr(repos_modulo, "listar_contenido", lambda **k: [], raising=False)

    escritos = {}

    def _upsert(marca, geo, items):  # noqa: ANN001
        escritos["marca"] = marca
        escritos["geo"] = geo
        escritos["items"] = items
        return len(items)

    monkeypatch.setattr(repos_modulo, "upsert_radar_items", _upsert, raising=False)

    n = investigador.materializar_snapshot("claro-sports", "MX")
    assert n == 2
    assert escritos["marca"] == "claro-sports"
    assert escritos["geo"] == "MX"
    items = escritos["items"]
    # Cada item lleva los campos del contrato (clave/score/razon/estado/url_canonica + a_dict).
    primero = items[0]
    for campo in ("titulo", "redes", "fuentes", "por_que", "senal", "enlaces",
                  "clave", "score", "razon", "estado", "url_canonica"):
        assert campo in primero
    assert isinstance(primero["score"], float)
    assert primero["clave"] == dedup.clave(primero["titulo"])
    # url_canonica del primer enlace.
    assert primero["url_canonica"] == "https://example.com/a"


def test_materializar_marca_estado(monkeypatch):
    """El estado editorial reciente de la marca se proyecta al snapshot (publicado gana)."""
    temas = [_tema("Tema publicado"), _tema("Tema en parrilla")]
    monkeypatch.setattr(
        api_radar, "_radar_consolidado", lambda geo, **k: ([temas], []), raising=True
    )
    monkeypatch.setattr(dedup, "url_canonica", lambda u: u, raising=False)

    contenido = [
        {"titulo": "Tema publicado", "estado": "publicado"},
        {"titulo": "Tema en parrilla", "estado": "borrador"},
    ]
    monkeypatch.setattr(
        repos_modulo, "listar_contenido", lambda **k: contenido, raising=False
    )

    capturado = {}
    monkeypatch.setattr(
        repos_modulo, "upsert_radar_items",
        lambda m, g, items: capturado.update(items=items) or len(items),
        raising=False,
    )

    investigador.materializar_snapshot("claro-sports", "MX")
    por_titulo = {it["titulo"]: it["estado"] for it in capturado["items"]}
    assert por_titulo["Tema publicado"] == "publicado"
    assert por_titulo["Tema en parrilla"] == "en_parrilla"


def test_materializar_nunca_lanza(monkeypatch):
    """Best-effort: un fallo (p.ej. consolidado revienta) devuelve 0, no propaga."""
    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("trends caido")
    monkeypatch.setattr(api_radar, "_radar_consolidado", _boom, raising=True)
    assert investigador.materializar_snapshot("claro-sports", "MX") == 0


def test_estado_por_clave_best_effort(monkeypatch):
    """`_estado_por_clave` devuelve {} si la lectura de contenido falla."""
    def _boom(**k):  # noqa: ANN003
        raise RuntimeError("db caida")
    monkeypatch.setattr(repos_modulo, "listar_contenido", _boom, raising=False)
    assert investigador._estado_por_clave("claro-sports") == {}


# --------------------------------------------------------------------------- #
# Daemon: arranca SIEMPRE; gateado en vivo                                      #
# --------------------------------------------------------------------------- #

def test_daemon_arranca_y_es_daemon(monkeypatch):
    """El hilo arranca SIEMPRE (aun con el flag OFF) y es daemon (no bloquea el cierre)."""
    monkeypatch.delenv("KENI_INVESTIGADOR", raising=False)
    hilo = investigador.iniciar_investigador(intervalo_segundos=3600.0)
    assert hilo.daemon is True
    assert hilo.is_alive()
