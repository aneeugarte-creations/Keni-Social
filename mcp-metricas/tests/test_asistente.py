"""Tests OFFLINE del asistente de onboarding.

Cubren la logica pura: construccion del dict, serializacion TOML (round-trip via
tomllib), merge no destructivo con config existente, enmascarado de tokens y
escritura atomica. NO hay red ni input() interactivo: se llaman las funciones
puras directamente. Los tokens son obviamente falsos (TOKEN_DE_EJEMPLO).
"""

from __future__ import annotations

import tomllib

import pytest

from keni_metricas import asistente as a

TOKEN_FALSO = "TOKEN_DE_EJEMPLO_meta_1234567890"
BEARER_FALSO = "BEARER_DE_EJEMPLO_x_abcdef9999"


# --- enmascarado -----------------------------------------------------------
def test_enmascarar_oculta_casi_todo():
    masc = a.enmascarar_token(TOKEN_FALSO)
    assert masc.endswith("7890")
    assert TOKEN_FALSO not in masc  # nunca el token completo
    assert set(masc[:-4]) == {"*"}


def test_enmascarar_vacio_y_placeholder():
    assert a.enmascarar_token("") == "(vacio)"
    assert a.enmascarar_token(None) == "(vacio)"
    assert a.enmascarar_token(a.PLACEHOLDER_TOKEN) == a.PLACEHOLDER_TOKEN


def test_enmascarar_token_corto_todo_oculto():
    assert a.enmascarar_token("abc") == "***"


# --- normalizacion ---------------------------------------------------------
def test_normalizar_id_marca():
    assert a.normalizar_id_marca("Claro Sports") == "claro_sports"
    assert a.normalizar_id_marca("  UnoTV!! ") == "unotv"
    assert a.normalizar_id_marca("a--b__c") == "a_b_c"


def test_normalizar_alcance_dedup_y_orden():
    assert a.normalizar_alcance("unotv, claro_sports, unotv") == ["unotv", "claro_sports"]
    assert a.normalizar_alcance(["x", "", "y", "x"]) == ["x", "y"]
    assert a.normalizar_alcance("") == []


def test_normalizar_alcance_filtra_a_ids_validos():
    out = a.normalizar_alcance("unotv, fantasma", ids_validos=["unotv", "claro_sports"])
    assert out == ["unotv"]


# --- construccion del dict -------------------------------------------------
def _plan_ejemplo() -> a.PlanConfig:
    return a.PlanConfig(
        fuente="real",
        marcas_cuenta=[
            a.MarcaEntrada(
                id="claro_sports",
                nombre="Claro Sports",
                plataformas={"facebook": "PAGE_ID", "instagram": "IG_ID", "tiktok": "IGNORADO"},
            ),
            a.MarcaEntrada(id="unotv", nombre="UnoTV", plataformas={"facebook": "PAGE2"}),
        ],
        alcance=["claro_sports"],
        credenciales={
            "meta": {"access_token": TOKEN_FALSO, "tipo_token": "system_user"},
            "x": {"bearer_token": BEARER_FALSO},
            "youtube": {},  # vacio: debe descartarse
        },
    )


def test_plan_a_dict_estructura():
    datos = a.plan_a_dict(_plan_ejemplo())
    assert datos["fuente"] == "real"
    assert datos["marcas"] == ["claro_sports"]
    # tiktok no lleva handle aunque se haya declarado uno
    cs = next(c for c in datos["cuenta"] if c["id"] == "claro_sports")
    assert "tiktok" not in cs["plataformas"]
    assert cs["plataformas"]["facebook"] == "PAGE_ID"
    # bloque vacio de youtube descartado; meta y x presentes
    assert set(datos["credenciales"]) == {"meta", "x"}
    assert datos["credenciales"]["meta"]["tipo_token"] == "system_user"


def test_plan_muestra_sin_marcas_ni_creds():
    datos = a.plan_a_dict(a.PlanConfig(fuente="muestra"))
    assert datos == {"fuente": "muestra"}
    assert "marcas" not in datos
    assert "credenciales" not in datos


# --- serializacion TOML (round-trip) ---------------------------------------
def test_serializar_round_trip():
    datos = a.plan_a_dict(_plan_ejemplo())
    texto = a.serializar_toml(datos)
    releido = tomllib.loads(texto)
    assert releido["fuente"] == "real"
    assert releido["marcas"] == ["claro_sports"]
    assert releido["credenciales"]["meta"]["access_token"] == TOKEN_FALSO
    assert releido["credenciales"]["meta"]["tipo_token"] == "system_user"
    assert releido["credenciales"]["x"]["bearer_token"] == BEARER_FALSO
    cuentas = {c["id"]: c for c in releido["cuenta"]}
    assert cuentas["claro_sports"]["plataformas"]["instagram"] == "IG_ID"
    assert cuentas["unotv"]["nombre"] == "UnoTV"


def test_serializar_escapa_comillas():
    datos = {"fuente": "real", "cuenta": [{"id": "x", "nombre": 'A "B" C'}]}
    releido = tomllib.loads(a.serializar_toml(datos))
    assert releido["cuenta"][0]["nombre"] == 'A "B" C'


def test_compatible_con_cargar_config(monkeypatch, tmp_path):
    """El TOML generado lo entiende config.cargar_config sin cambios."""
    from keni_metricas.config import cargar_config

    ruta = tmp_path / "config.toml"
    datos = a.plan_a_dict(_plan_ejemplo())
    a.escribir_config_atomico(ruta, datos)

    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    cfg = cargar_config()
    assert cfg.fuente == "real"
    assert cfg.marcas == ["claro_sports"]
    ids = {c.id for c in cfg.cuentas}
    assert ids == {"claro_sports", "unotv"}
    assert cfg.credenciales["meta"]["access_token"] == TOKEN_FALSO


# --- merge no destructivo --------------------------------------------------
def test_fusionar_preserva_seccion_ajena():
    existente = {
        "fuente": "muestra",
        "seccion_ajena": {"clave": "valor"},  # algo que el asistente no genera
        "credenciales": {"tiktok": {"access_token": "VIEJO_TIKTOK"}},
    }
    nuevo = {
        "fuente": "real",
        "credenciales": {"meta": {"access_token": TOKEN_FALSO}},
    }
    out = a.fusionar_config(existente, nuevo)
    assert out["fuente"] == "real"  # el nuevo gana
    assert out["seccion_ajena"] == {"clave": "valor"}  # preservada
    # bloque tiktok no tocado se mantiene; meta nuevo se anade
    assert out["credenciales"]["tiktok"]["access_token"] == "VIEJO_TIKTOK"
    assert out["credenciales"]["meta"]["access_token"] == TOKEN_FALSO


def test_fusionar_credenciales_por_clave_no_pierde_app_secret():
    existente = {"credenciales": {"meta": {"access_token": "VIEJO", "app_id": "APPID", "app_secret": "S"}}}
    nuevo = {"credenciales": {"meta": {"access_token": TOKEN_FALSO}}}
    out = a.fusionar_config(existente, nuevo)
    meta = out["credenciales"]["meta"]
    assert meta["access_token"] == TOKEN_FALSO  # actualizado
    assert meta["app_id"] == "APPID"  # conservado
    assert meta["app_secret"] == "S"


def test_construir_y_fusionar_lee_existente(tmp_path):
    ruta = tmp_path / "config.toml"
    a.escribir_config_atomico(
        ruta,
        {"fuente": "muestra", "seccion_ajena": {"k": "v"}},
    )
    plan = a.PlanConfig(fuente="real", credenciales={"x": {"bearer_token": BEARER_FALSO}})
    out = a.construir_y_fusionar(plan, ruta)
    assert out["fuente"] == "real"
    assert out["seccion_ajena"] == {"k": "v"}
    assert out["credenciales"]["x"]["bearer_token"] == BEARER_FALSO


# --- escritura atomica -----------------------------------------------------
def test_escribir_atomico_crea_dir_y_permisos(tmp_path):
    import os
    import stat

    ruta = tmp_path / "sub" / "dir" / "config.toml"
    a.escribir_config_atomico(ruta, {"fuente": "muestra"})
    assert ruta.exists()
    # solo el dueno puede leer/escribir (0600)
    modo = stat.S_IMODE(os.stat(ruta).st_mode)
    assert modo == 0o600
    # no quedan temporales
    assert list(ruta.parent.glob(".config-*.tmp")) == []


def test_escribir_incluye_cabecera_y_no_filtra_token_en_log(tmp_path):
    ruta = tmp_path / "config.toml"
    datos = a.plan_a_dict(_plan_ejemplo())
    a.escribir_config_atomico(ruta, datos)
    texto = ruta.read_text(encoding="utf-8")
    assert texto.startswith("#")  # cabecera de comentario
    # el token SI esta en el archivo (es su sitio), pero el resumen lo enmascara:
    resumen = a.resumen_plan(_plan_ejemplo())
    assert TOKEN_FALSO not in resumen
    assert BEARER_FALSO not in resumen
    assert "system_user" in resumen  # metadatos no secretos si se muestran


# --- guia por plataforma ---------------------------------------------------
def test_guia_plataforma_menciona_docs_y_system_user():
    g_meta = a.texto_guia_plataforma("facebook")
    assert "System User" in g_meta
    assert "docs/credenciales.md" in g_meta
    assert "docs/meta-app-review.md" in g_meta
    # facebook e instagram comparten el bloque meta
    assert a.guia_plataforma("instagram") is a.guia_plataforma("facebook")
    assert "docs/" in a.texto_guia_plataforma("youtube")
    assert "bearer" in a.texto_guia_plataforma("x").lower()


@pytest.mark.parametrize("plat", a.PLATAFORMAS)
def test_toda_plataforma_tiene_guia(plat):
    g = a.guia_plataforma(plat)
    assert g["titulo"] and g["que"] and g["docs"]
