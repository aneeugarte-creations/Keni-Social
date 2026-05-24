"""Tests de la feature Configuracion (cambiar fuente/alcance desde la UI). OFFLINE.

La feature lee `cargar_config()` y escribe el config.toml reutilizando la logica
del asistente (merge no destructivo + escritura atomica 0600). Estos tests aislan
el config en `tmp_path` via `KENI_METRICAS_CONFIG` y limpian las env vars que
sobreescriben fuente/marcas, para que el archivo sea la unica fuente de verdad.
Nada de red, nada de tokens reales.
"""

from __future__ import annotations

import tomllib

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo

# Un config de prueba con un bloque de credenciales (token real falso) que NUNCA
# debe perderse al guardar fuente/marcas ni aparecer en el HTML de la pagina.
_TOKEN_FALSO = "ABC123secretoquenodebeaparecer"
_CONFIG_CON_CREDENCIALES = f"""\
fuente = "muestra"
marcas = ["unotv"]

[[cuenta]]
id = "unotv"
nombre = "UnoTV"

[cuenta.plataformas]
facebook = "unotv.oficial"

[credenciales.meta]
access_token = "{_TOKEN_FALSO}"
tipo_token = "system_user"
"""


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Aisla el config de metricas en tmp; sin env vars que pisen fuente/marcas."""
    ruta = tmp_path / "config.toml"
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    return ruta


def _cliente() -> TestClient:
    # `abrir` de proyectos: mock inofensivo (esta feature no lo usa).
    return TestClient(app_modulo.crear_app(abrir=lambda _r: "ok-mock"))


def _escribir(ruta, contenido: str) -> None:
    ruta.write_text(contenido, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Pagina y nav                                                                 #
# --------------------------------------------------------------------------- #


def test_config_devuelve_html_200(entorno):
    r = _cliente().get("/config")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Configuraci" in r.text  # "Configuracion"/"Configuración"


def test_config_aparece_en_la_nav(entorno):
    html = _cliente().get("/proyectos").text
    assert 'href="/config"' in html
    # orden=70 => Config va al final (despues de Estado=60).
    assert html.index('href="/estado"') < html.index('href="/config"')


def test_config_carga_su_css_y_js(entorno):
    html = _cliente().get("/config").text
    assert 'href="/estaticos/config.css"' in html
    assert 'src="/estaticos/config.js"' in html
    c = _cliente()
    assert c.get("/estaticos/config.css").status_code == 200
    assert c.get("/estaticos/config.js").status_code == 200


# --------------------------------------------------------------------------- #
# GET /config muestra fuente / marcas / alcance                               #
# --------------------------------------------------------------------------- #


def test_get_muestra_fuente_activa(entorno):
    _escribir(entorno, _CONFIG_CON_CREDENCIALES)
    html = _cliente().get("/config").text
    # Fuente activa es muestra y el radio muestra queda marcado.
    assert "Fuente activa" in html
    assert 'value="muestra" checked' in html


def test_get_muestra_marcas_disponibles_y_alcance(entorno):
    _escribir(entorno, _CONFIG_CON_CREDENCIALES)
    html = _cliente().get("/config").text
    # Las marcas de la fuente muestra estan como checkboxes.
    assert 'name="marca" value="unotv"' in html
    assert 'name="marca" value="claro_sports"' in html
    # El alcance actual (unotv) sale en el resumen y unotv queda marcado.
    assert 'value="unotv" checked' in html


def test_get_alcance_vacio_dice_todas(entorno):
    _escribir(entorno, 'fuente = "muestra"\n')
    html = _cliente().get("/config").text
    assert "todas las marcas" in html


# --------------------------------------------------------------------------- #
# POST /api/config/guardar cambia fuente y alcance                            #
# --------------------------------------------------------------------------- #


def test_guardar_cambia_fuente_y_alcance_y_se_relee(entorno):
    _escribir(entorno, 'fuente = "muestra"\n')
    c = _cliente()
    r = c.post("/api/config/guardar", json={"fuente": "real", "marcas": ["unotv", "claro_sports"]})
    assert r.status_code == 200
    assert "guardada" in r.json()["mensaje"].lower()

    # Releemos el TOML escrito: fuente y marcas reflejan el cambio.
    datos = tomllib.loads(entorno.read_text(encoding="utf-8"))
    assert datos["fuente"] == "real"
    assert datos["marcas"] == ["unotv", "claro_sports"]

    # Y la pagina recargada lo muestra.
    html = c.get("/config").text
    assert 'value="real" checked' in html


def test_guardar_alcance_vacio_borra_marcas(entorno):
    _escribir(entorno, 'fuente = "muestra"\nmarcas = ["unotv"]\n')
    c = _cliente()
    r = c.post("/api/config/guardar", json={"fuente": "muestra", "marcas": []})
    assert r.status_code == 200
    datos = tomllib.loads(entorno.read_text(encoding="utf-8"))
    # Sin marcas => "todas" => no debe quedar una lista vacia en el TOML.
    assert "marcas" not in datos


# --------------------------------------------------------------------------- #
# Preservacion de credenciales y cuentas                                       #
# --------------------------------------------------------------------------- #


def test_guardar_preserva_credenciales_existentes(entorno):
    _escribir(entorno, _CONFIG_CON_CREDENCIALES)
    c = _cliente()
    r = c.post("/api/config/guardar", json={"fuente": "real", "marcas": ["unotv"]})
    assert r.status_code == 200

    datos = tomllib.loads(entorno.read_text(encoding="utf-8"))
    # Las credenciales y la cuenta declarada siguen intactas tras guardar.
    assert datos["credenciales"]["meta"]["access_token"] == _TOKEN_FALSO
    assert datos["credenciales"]["meta"]["tipo_token"] == "system_user"
    assert datos["cuenta"][0]["id"] == "unotv"
    assert datos["cuenta"][0]["plataformas"]["facebook"] == "unotv.oficial"
    # Y lo que pedimos cambiar, cambio.
    assert datos["fuente"] == "real"


def test_archivo_tiene_permisos_0600(entorno):
    _escribir(entorno, _CONFIG_CON_CREDENCIALES)
    c = _cliente()
    c.post("/api/config/guardar", json={"fuente": "real", "marcas": ["unotv"]})
    modo = entorno.stat().st_mode & 0o777
    assert modo == 0o600


# --------------------------------------------------------------------------- #
# Validacion                                                                   #
# --------------------------------------------------------------------------- #


def test_fuente_invalida_400(entorno):
    _escribir(entorno, 'fuente = "muestra"\n')
    r = _cliente().post("/api/config/guardar", json={"fuente": "inventada", "marcas": []})
    assert r.status_code == 400
    assert "fuente" in r.json()["error"].lower()


def test_marca_desconocida_400(entorno):
    _escribir(entorno, 'fuente = "muestra"\n')
    r = _cliente().post(
        "/api/config/guardar", json={"fuente": "muestra", "marcas": ["marca_que_no_existe"]}
    )
    assert r.status_code == 400
    assert "desconocida" in r.json()["error"].lower()


def test_body_invalido_400(entorno):
    r = _cliente().post(
        "/api/config/guardar", content=b"no-json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400


def test_marcas_no_lista_400(entorno):
    _escribir(entorno, 'fuente = "muestra"\n')
    r = _cliente().post("/api/config/guardar", json={"fuente": "muestra", "marcas": "unotv"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Credenciales: solo presencia, nunca el valor                                 #
# --------------------------------------------------------------------------- #


def test_no_aparece_ningun_token_en_el_html(entorno):
    _escribir(entorno, _CONFIG_CON_CREDENCIALES)
    html = _cliente().get("/config").text
    assert _TOKEN_FALSO not in html
    # Si muestra presencia: meta aparece como conectada.
    assert "conectada" in html


def test_credencial_ausente_se_marca_sin_conectar(entorno):
    _escribir(entorno, 'fuente = "muestra"\n')
    html = _cliente().get("/config").text
    # Sin credenciales declaradas, todos los bloques salen "sin conectar".
    assert "sin conectar" in html
    # Y aparece la nota guia al asistente.
    assert "keni_metricas.asistente" in html


def test_placeholder_no_cuenta_como_conectada(entorno):
    # Un token placeholder NO debe contar como credencial presente.
    contenido = (
        'fuente = "real"\n\n'
        "[credenciales.meta]\n"
        'access_token = "PENDIENTE_PON_TU_TOKEN_AQUI"\n'
    )
    _escribir(entorno, contenido)
    html = _cliente().get("/config").text
    assert "sin conectar" in html


# --------------------------------------------------------------------------- #
# H2: marcas con etiqueta humana (con acentos), nunca ids crudos en la UI      #
# --------------------------------------------------------------------------- #


def test_marcas_se_muestran_con_etiqueta_humana_no_id_crudo(entorno):
    """La marca 'nacion_gamer' se muestra como 'Nación Gamer' (acentos), nunca como
    'nacion_gamer' visible ni '(nacion_gamer)' entre parentesis."""
    contenido = (
        'fuente = "muestra"\n\n'
        "[[cuenta]]\n"
        'id = "nacion_gamer"\n'
        'nombre = "Nacion Gamer"\n'  # nombre sin acento en el config...
    )
    _escribir(entorno, contenido)
    html = _cliente().get("/config").text
    # ...pero en la UI sale la etiqueta canonica de marcas, con acento.
    assert "Nación Gamer" in html
    # El id crudo NUNCA aparece entre parentesis como texto visible.
    assert "(nacion_gamer)" not in html


def test_id_de_marca_viaja_en_title_no_como_texto(entorno):
    """El id tecnico de la marca solo aparece en title= (para quien lo necesite)."""
    contenido = (
        'fuente = "muestra"\n\n'
        "[[cuenta]]\n"
        'id = "unotv"\n'
        'nombre = "UnoTV"\n'
    )
    _escribir(entorno, contenido)
    html = _cliente().get("/config").text
    # El id sigue siendo el value del checkbox y el title de la etiqueta.
    assert 'name="marca" value="unotv"' in html
    assert 'title="unotv"' in html


def test_alcance_en_resumen_usa_etiqueta_humana(entorno):
    """El resumen de alcance muestra etiquetas humanas, no ids con guion_bajo."""
    _escribir(entorno, 'fuente = "muestra"\nmarcas = ["claro_sports"]\n')
    html = _cliente().get("/config").text
    assert "Claro Sports" in html
    # El id con guion_bajo no debe salir como texto del alcance.
    assert ">claro_sports<" not in html


def test_comando_del_asistente_no_esta_en_texto_principal_sino_en_details(entorno):
    """Des-jerga: el comando CLI y la ruta del config no estan en el texto principal,
    sino escondidos en un <details> para personas tecnicas."""
    _escribir(entorno, 'fuente = "muestra"\n')
    html = _cliente().get("/config").text
    # Hay un <details> con el detalle tecnico.
    assert "<details" in html
    assert "Detalles técnicos" in html
    # El comando sigue disponible (dentro del details), pero la nota principal es amable.
    assert "keni_metricas.asistente" in html
    assert "asistente de configuración" in html
    # La ruta del config aparece tras el summary del details (no en el cuerpo principal).
    pos_details = html.index("<details")
    pos_ruta = html.index("Tu configuración se guarda en")
    assert pos_ruta > pos_details
