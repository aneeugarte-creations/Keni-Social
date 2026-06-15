"""Etapa de REVISAR del copy del pipeline: criba ADVISORY antes del avance. OFFLINE + DB tmp.

Cubre:
  - COHERENCIA (pura): avisa sólo cuando el copy no comparte NINGÚN término de contenido con su
    nota y ambos son sustanciales; calla si comparten algo o si son cortos.
  - VOZ (pura, perfil sembrado): reusa `patrones_marca.verificar_pieza` con `copy_unico=False`
    (el borrador ya lleva sus hashtags), avisa fuera de patrón.
  - `verificar_calidad_pieza` (DB): ADVISORY — degrada `listo`→`revisar` y anota el tema, sin
    bloquear; un copy limpio no se toca.
  - Integración en `ejecutar_avance`: gateada por `KENI_PIPELINE_REVISAR`. Con el toggle ON una
    pieza marcada AVANZA igual (no bloquea) pero sale degradada; con el toggle OFF, intacta.
"""

from __future__ import annotations

import json

from keni_consola import app as app_modulo
from keni_consola import auth, patrones_marca, repos
from keni_consola.pipeline_contenido import _avance, _calidad
from starlette.testclient import TestClient

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba-123"
_MARCA = "unotv"

# Copy con 14 términos de contenido (tokens >= 4 chars) sobre tecnología.
_COPY_TECH = (
    "tecnologia robotica industrial avanzada sensores autonomos modernos fabricas "
    "automatizacion eficiente produccion europea innovacion ingenieria"
)
# Nota con 22 términos de contenido sobre fútbol: CERO solapamiento con el copy de tecnología.
_NOTA_FUTBOL = (
    "partido futbol seleccion mexicana goles estadio aficion mundial entrenador jugadores "
    "lesiones convocatoria torneo continental rivales tabla posiciones clasificacion "
    "eliminatoria delantero portero defensa"
)


# --------------------------------------------------------------------------- #
# COHERENCIA (pura)                                                           #
# --------------------------------------------------------------------------- #


def test_coherencia_avisa_si_no_comparte_terminos():
    avisos = _calidad.avisos_coherencia(_COPY_TECH, _NOTA_FUTBOL)
    assert len(avisos) == 1 and "no comparte" in avisos[0]


def test_coherencia_calla_si_comparte_algun_termino():
    # El copy ahora menciona "futbol" (presente en la nota): hay solapamiento -> sin aviso.
    assert _calidad.avisos_coherencia(_COPY_TECH + " futbol", _NOTA_FUTBOL) == []


def test_coherencia_calla_con_textos_cortos():
    # Copy corto (pocos términos de contenido): el contraste no significa nada -> sin aviso.
    assert _calidad.avisos_coherencia("gol en el noventa", _NOTA_FUTBOL) == []
    assert _calidad.avisos_coherencia(_COPY_TECH, "nota breve sin sustancia") == []


def test_coherencia_calla_sin_nota():
    assert _calidad.avisos_coherencia(_COPY_TECH, "") == []


# --------------------------------------------------------------------------- #
# VOZ (pura, perfil de patrones sembrado en disco)                            #
# --------------------------------------------------------------------------- #


def _sembrar_perfil(monkeypatch, tmp_path, *, red: str = "x") -> None:
    """Perfil mínimo de patrones para `_MARCA`/`red` con `emojis_max=0` (la marca va sin emojis)."""
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path / "patrones"))
    base = patrones_marca.dir_perfiles_data()
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{_MARCA}.json").write_text(
        json.dumps({
            "version": 1, "marca": _MARCA,
            "redes": {red: {"lint": {
                "longitud_max": None, "longitud_min": None, "emojis_max": 0,
                "hashtags_max": 3, "gancho_mayusculas": None, "pregunta": None,
            }}},
        }),
        encoding="utf-8",
    )


def test_voz_avisa_emoji_fuera_de_patron(monkeypatch, tmp_path):
    _sembrar_perfil(monkeypatch, tmp_path)
    avisos = _calidad.avisos_voz(_MARCA, "x", "Un copy con un emoji 🔥 al final")
    assert avisos and "emoji" in avisos[0]


def test_voz_calla_copy_en_patron(monkeypatch, tmp_path):
    _sembrar_perfil(monkeypatch, tmp_path)
    assert _calidad.avisos_voz(_MARCA, "x", "Un copy sobrio sin emojis ni adornos") == []


def test_voz_sin_perfil_no_inventa(monkeypatch, tmp_path):
    # Sin perfil para la marca, el lint no se pronuncia (degradación honesta).
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path / "vacio"))
    assert _calidad.avisos_voz(_MARCA, "x", "Lo que sea con emoji 🔥") == []


# --------------------------------------------------------------------------- #
# verificar_calidad_pieza (DB): ADVISORY, degrada + anota, NO bloquea          #
# --------------------------------------------------------------------------- #


def _cli(usuario: str = "ana") -> TestClient:
    auth.crear_usuario(usuario, _CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _borrador(cli: TestClient, *, contenido: str, veredicto: str = "listo", con_foto: bool = True) -> dict:
    r = cli.post(
        "/api/publicaciones",
        json={"marca": _MARCA, "red": "x", "titulo": "T", "contenido": contenido},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    pub = r.json()["publicacion"]
    cambios = {"veredicto": veredicto}
    if con_foto:
        cambios["foto"] = "fotos/prueba.jpg"
    repos.actualizar_publicacion(pub["id"], cambios)
    return repos.obtener_publicacion(pub["id"])


def test_verificar_calidad_degrada_listo_y_anota(entorno, monkeypatch, tmp_path):
    _sembrar_perfil(monkeypatch, tmp_path)
    pub = _borrador(_cli(), contenido="Copy con emoji 🔥 fuera de patrón")

    avisos = _calidad.verificar_calidad_pieza(pub)

    assert avisos  # encontró algo (voz)
    actual = repos.obtener_publicacion(pub["id"])
    assert actual["veredicto"] == "revisar"  # degradado (advisory), no bloqueado
    tema = repos.obtener_contenido(pub["contenido_id"])
    assert "Validación de copy" in (tema.get("notas") or "")


def test_verificar_calidad_no_toca_copy_limpio(entorno, monkeypatch, tmp_path):
    _sembrar_perfil(monkeypatch, tmp_path)
    pub = _borrador(_cli(), contenido="Copy sobrio dentro de patrón, sin emojis")

    assert _calidad.verificar_calidad_pieza(pub) == []
    assert repos.obtener_publicacion(pub["id"])["veredicto"] == "listo"  # intacto


# --------------------------------------------------------------------------- #
# Integración en ejecutar_avance: gateada, ADVISORY (marca pero NO bloquea)    #
# --------------------------------------------------------------------------- #


def _encender_maquina(monkeypatch) -> None:
    monkeypatch.setenv("KENI_MAQUINA", "1")
    monkeypatch.setattr(_avance, "_REPOSO_MINUTOS", 0)


def test_avance_con_calidad_on_marca_pero_no_bloquea(entorno, monkeypatch, tmp_path):
    _sembrar_perfil(monkeypatch, tmp_path)
    _encender_maquina(monkeypatch)
    monkeypatch.setenv("KENI_PIPELINE_REVISAR", "1")
    pub = _borrador(_cli(), contenido="Copy con emoji 🔥 que se sale del patrón")

    enviadas = _avance.ejecutar_avance()

    assert [p["id"] for p in enviadas] == [pub["id"]]  # AVANZA igual (no bloquea)
    actual = repos.obtener_publicacion(pub["id"])
    assert actual["estado"] == "en_revision"
    assert actual["veredicto"] == "revisar"  # ...pero marcada para que el humano decida


def test_avance_con_calidad_off_no_marca(entorno, monkeypatch, tmp_path):
    _sembrar_perfil(monkeypatch, tmp_path)
    _encender_maquina(monkeypatch)
    monkeypatch.delenv("KENI_PIPELINE_REVISAR", raising=False)
    pub = _borrador(_cli(), contenido="Copy con emoji 🔥 que se sale del patrón")

    enviadas = _avance.ejecutar_avance()

    assert [p["id"] for p in enviadas] == [pub["id"]]
    actual = repos.obtener_publicacion(pub["id"])
    assert actual["estado"] == "en_revision"
    assert actual["veredicto"] == "listo"  # sin criba, no se toca el veredicto
