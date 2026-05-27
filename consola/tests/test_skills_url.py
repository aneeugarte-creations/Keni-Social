"""Tests de F9 (#149): generar copy DESDE UNA URL.

Dos niveles, TODO OFFLINE (nunca se toca la red real):
  - `dominio.extraccion_url`: validacion de URL (esquema + SSRF mockeado), deteccion de
    hosts de video, extraccion de texto de HTML (parser stdlib) y composicion de la nota
    NO VERIFICADA. La descarga vive detras de `_DESCARGADOR`, que se parchea.
  - endpoint `POST /api/skills/ejecutar-url`: con el descargador y el lanzador de claude
    mockeados, comprueba que extrae el texto, lo pasa a `copy-desde-nota` (piezas +
    veredicto + borradores) y que el prompt incluye el AVISO de NO VERIFICADO. Y los
    caminos de degradacion honesta (video, 4xx, SSRF, skill que no es de URL).
"""

from __future__ import annotations

import yaml

from keni_consola import skills_catalogo
from keni_consola.dominio import extraccion_url

from .conftest import _cliente, lanzador_generacion_completa

# Salida canned de claude (igual forma que en test_skills_piezas): veredicto + json.
_SALIDA = """⚠️ Revisar antes de publicar: confirma nombres y cifras del enlace.

## X
Resumen al grano.

```json
{"piezas": [{"red": "x", "texto": "Resumen al grano."}]}
```
"""

# Pagina HTML de prueba con menus + un articulo (para verificar que extrae el cuerpo).
_HTML = """<!doctype html><html><head><title>Gol de último minuto</title>
<style>.x{color:red}</style><script>var a=1;</script></head>
<body>
  <nav>Inicio · Deportes · Más</nav>
  <article>
    <h1>Gol de último minuto</h1>
    <p>El equipo ganó 2-1 con un gol al 90+3.</p>
    <p>El técnico destacó el esfuerzo del grupo.</p>
  </article>
  <footer>Derechos reservados</footer>
</body></html>"""


# --------------------------------------------------------------------------- #
# dominio.extraccion_url — validacion de URL + SSRF                            #
# --------------------------------------------------------------------------- #


def test_validar_url_rechaza_esquema_no_http():
    url, error = extraccion_url.validar_url("ftp://example.com/x")
    assert url is None
    assert "http" in error


def test_validar_url_vacia_da_mensaje():
    url, error = extraccion_url.validar_url("   ")
    assert url is None and error


def test_validar_url_ssrf_localhost(monkeypatch):
    # 127.0.0.1 es loopback => rechazada sin tocar la red.
    url, error = extraccion_url.validar_url("http://127.0.0.1/admin")
    assert url is None
    assert "no permitida" in error


def test_validar_url_ok_con_host_publico(monkeypatch):
    # Forzamos que el host resuelva a una IP publica (sin DNS real).
    monkeypatch.setattr(extraccion_url, "_guard_ssrf", lambda host: None)
    url, error = extraccion_url.validar_url("https://www.unotv.com/nota")
    assert error is None
    assert url == "https://www.unotv.com/nota"


# --------------------------------------------------------------------------- #
# dominio.extraccion_url — deteccion de video + extraccion de texto            #
# --------------------------------------------------------------------------- #


def test_es_host_de_video_detecta_youtube_y_tiktok():
    assert extraccion_url.es_host_de_video("https://www.youtube.com/watch?v=abc")
    assert extraccion_url.es_host_de_video("https://youtu.be/abc")
    assert extraccion_url.es_host_de_video("https://www.tiktok.com/@x/video/1")
    assert not extraccion_url.es_host_de_video("https://www.unotv.com/nota")


def test_extraer_texto_de_html(monkeypatch):
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR", lambda url: _HTML)
    titulo, cuerpo = extraccion_url.extraer_texto("https://www.unotv.com/nota")
    assert titulo == "Gol de último minuto"
    assert "ganó 2-1" in cuerpo
    # El script/style y (al haber <article>) el nav/footer quedan fuera.
    assert "var a=1" not in cuerpo
    assert "Derechos reservados" not in cuerpo


def test_extraer_texto_video_degrada(monkeypatch):
    # Para un host de video NO se descarga nada: degrada con honestidad.
    llamado = {"n": 0}
    monkeypatch.setattr(
        extraccion_url, "_DESCARGADOR", lambda url: llamado.__setitem__("n", 1) or _HTML
    )
    try:
        extraccion_url.extraer_texto("https://www.youtube.com/watch?v=abc")
    except extraccion_url.ExtraccionError as e:
        assert "video" in str(e).lower() or "transmisión" in str(e)
    else:
        raise AssertionError("debía lanzar ExtraccionError para un host de video")
    assert llamado["n"] == 0  # nunca descargó


def test_extraer_texto_sin_texto_util(monkeypatch):
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR", lambda url: "<html><body></body></html>")
    try:
        extraccion_url.extraer_texto("https://www.unotv.com/vacia")
    except extraccion_url.ExtraccionError as e:
        assert "texto" in str(e).lower()
    else:
        raise AssertionError("debía lanzar ExtraccionError si no hay texto legible")


def test_componer_nota_marca_no_verificado():
    nota = extraccion_url.componer_nota_no_verificada(
        "https://x.com/n", "Titular", "Cuerpo de la nota."
    )
    assert "NO VERIFICADO" in nota
    assert "Cuerpo de la nota." in nota
    assert "https://x.com/n" in nota


# --------------------------------------------------------------------------- #
# Sembrado de la skill `url-a-copy` (ingesta=url) en el catalogo de prueba     #
# --------------------------------------------------------------------------- #


def _sembrar_url_a_copy() -> None:
    """Crea la skill `url-a-copy` en el catalogo aislado del test (KENI_SKILLS_DIR)."""
    carpeta = skills_catalogo.dir_skills() / "url-a-copy"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "SKILL.md").write_text("# url-a-copy\n\nCopy desde un enlace.\n", encoding="utf-8")
    meta = {
        "nombre": "Copy desde un enlace",
        "explicacion": "Pega el link de una nota y genera copy por red.",
        "grupo": "validadas",
        "aplica_redes": True,
        "salida": "piezas",
        "media": False,
        "ingesta": "url",
        "orden": 15,
        "campos": [
            {
                "id": "url",
                "etiqueta": "Enlace de la nota",
                "tipo": "texto",
                "requerido": True,
                "placeholder": "https://...",
                "ayuda": "",
                "opciones": [],
                "media_tipos": "",
            }
        ],
        "plantilla_invocacion": "usa copy-desde-nota con la nota del enlace {url}, marca {marca}.\n",
    }
    (carpeta / "keni.yaml").write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# skills_catalogo: `ingesta` round-trip                                        #
# --------------------------------------------------------------------------- #


def test_catalogo_lee_ingesta_url(entorno):
    _sembrar_url_a_copy()
    skill = skills_catalogo.obtener("url-a-copy")
    assert skill is not None
    assert skill.ingesta == "url"
    assert skill.a_dict()["ingesta"] == "url"


def test_opciones_expone_ingesta(entorno):
    _sembrar_url_a_copy()
    cuerpo = _cliente().get("/api/skills").json()
    por_id = {s["id"]: s for g in cuerpo["grupos"] for s in g["skills"]}
    assert por_id["url-a-copy"]["ingesta"] == "url"
    # Las skills normales siguen con ingesta vacia.
    assert por_id["copy-desde-nota"].get("ingesta", "") == ""


# --------------------------------------------------------------------------- #
# Endpoint POST /api/skills/ejecutar-url                                       #
# --------------------------------------------------------------------------- #


def _captura_prompt(salida: str):
    """Lanzador que COMPLETA la generacion y captura el prompt construido."""
    base = lanzador_generacion_completa(salida)
    capturado: dict[str, str] = {}

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        capturado["prompt"] = prompt
        base(gen_id, prompt=prompt, cwd=cwd, procesar=procesar, dir_temporal=dir_temporal)

    return lanzar, capturado


def test_ejecutar_url_genera_piezas_y_marca_no_verificado(entorno, monkeypatch):
    _sembrar_url_a_copy()
    monkeypatch.setattr(extraccion_url, "_guard_ssrf", lambda host: None)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR", lambda url: _HTML)
    lanzar, capturado = _captura_prompt(_SALIDA)
    r = _cliente(lanzar_generacion=lanzar).post(
        "/api/skills/ejecutar-url",
        json={
            "skill": "url-a-copy",
            "marca": "unotv",
            "url": "https://www.unotv.com/nota",
            "redes": ["x"],
        },
    )
    assert r.status_code == 200, r.text
    gen = r.json()["generacion"]
    assert gen["estado"] == "completado", gen
    res = gen["resultado"]
    assert [p["red"] for p in res["piezas"]] == ["x"]
    assert res["verdicto"] == "revisar"
    assert res["historial_id"]
    # El prompt incluye el AVISO de NO VERIFICADO + el texto extraido + la fuente.
    assert "NO VERIFICADO" in capturado["prompt"]
    assert "ganó 2-1" in capturado["prompt"]
    assert "https://www.unotv.com/nota" in capturado["prompt"]


def test_ejecutar_url_video_da_502(entorno, monkeypatch):
    _sembrar_url_a_copy()
    monkeypatch.setattr(extraccion_url, "_guard_ssrf", lambda host: None)
    r = _cliente().post(
        "/api/skills/ejecutar-url",
        json={"skill": "url-a-copy", "marca": "unotv", "url": "https://www.youtube.com/watch?v=x"},
    )
    assert r.status_code == 502
    assert "video" in r.json()["error"].lower() or "transmisión" in r.json()["error"]


def test_ejecutar_url_invalida_da_400(entorno):
    _sembrar_url_a_copy()
    r = _cliente().post(
        "/api/skills/ejecutar-url",
        json={"skill": "url-a-copy", "marca": "unotv", "url": "ftp://x/y"},
    )
    assert r.status_code == 400


def test_ejecutar_url_ssrf_da_400(entorno):
    _sembrar_url_a_copy()
    r = _cliente().post(
        "/api/skills/ejecutar-url",
        json={"skill": "url-a-copy", "marca": "unotv", "url": "http://127.0.0.1/x"},
    )
    assert r.status_code == 400
    assert "no permitida" in r.json()["error"]


def test_ejecutar_url_skill_no_es_de_url_da_400(entorno):
    # copy-desde-nota NO declara ingesta=url => el endpoint la rechaza.
    r = _cliente().post(
        "/api/skills/ejecutar-url",
        json={"skill": "copy-desde-nota", "marca": "unotv", "url": "https://x.com/n"},
    )
    assert r.status_code == 400


def test_ejecutar_url_marca_invalida_da_400(entorno, monkeypatch):
    _sembrar_url_a_copy()
    monkeypatch.setattr(extraccion_url, "_guard_ssrf", lambda host: None)
    r = _cliente().post(
        "/api/skills/ejecutar-url",
        json={"skill": "url-a-copy", "marca": "noexiste", "url": "https://x.com/n"},
    )
    assert r.status_code == 400
