"""Etapa SUGERIR HASHTAGS (`dominio.sugerir_hashtags`): propone hashtags para una pieza que
aún no los lleva, sin tocar el copy.

Los helpers de parseo/filtrado son PUROS (sin BD); el gating y la persistencia usan Postgres
(fixture `entorno`). La sugerencia se filtra SIEMPRE contra la biblioteca de la marca: un
hashtag inventado por la IA se descarta.
"""

from __future__ import annotations

import json

from keni_consola import repos
from keni_consola.dominio import sugerir_hashtags as dom_sh
from keni_consola.dominio.piezas import pieza_a_dict

_MARCA = "unotv"


# --------------------------------------------------------------------------- #
# Parseo + filtrado — PURO                                                       #
# --------------------------------------------------------------------------- #


def test_parsea_json_con_valla():
    salida = 'Aquí van:\n```json\n{"hashtags": ["#mexico", "#cdmx"]}\n```\n'
    assert dom_sh._parsear_hashtags(salida) == ["#mexico", "#cdmx"]


def test_parsea_json_desnudo():
    assert dom_sh._parsear_hashtags('{"hashtags": ["#unotv"]}') == ["#unotv"]


def test_parseo_basura_devuelve_vacio():
    assert dom_sh._parsear_hashtags("no hay json aquí") == []
    assert dom_sh._parsear_hashtags("") == []


def test_normaliza_un_solo_almohadilla_y_minuscula():
    assert dom_sh._normalizar("##Mexico") == "#mexico"
    assert dom_sh._normalizar("CDMX") == "#cdmx"
    assert dom_sh._normalizar("  ") == ""


def test_depurar_filtra_a_la_biblioteca_dedup_y_cap():
    # 'mexico'/'cdmx' están en la biblioteca de unotv; 'noexiste123' no -> se descarta.
    propuestos = ["#Mexico", "#mexico", "#noexiste123", "#CDMX"]
    out = dom_sh.depurar(propuestos, marca=_MARCA, cantidad=5)
    assert out == ["#mexico", "#cdmx"]  # dedup case-insensitive, solo los de la biblioteca


def test_depurar_respeta_la_cantidad():
    from keni_consola import hashtags_biblioteca as hb

    propuestos = [f"#{c}" for c in hb.candidatos(_MARCA)[:10]]
    out = dom_sh.depurar(propuestos, marca=_MARCA, cantidad=3)
    assert len(out) == 3


def test_falta_hashtags():
    assert dom_sh.falta_hashtags({"contenido": "Sin etiquetas"}) is True
    assert dom_sh.falta_hashtags({"contenido": "Con #mundial"}) is False


# --------------------------------------------------------------------------- #
# Persistencia + gating — Postgres (fixture `entorno`)                           #
# --------------------------------------------------------------------------- #


def _crear_pieza_borrador(copy: str) -> str:
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    pieza = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy=copy)
    return pieza["id"]


def test_aplicar_sugerencia_persiste_filtrada(entorno):
    pid = _crear_pieza_borrador("Cuerpo del post sin hashtags")
    guardados = dom_sh.aplicar_sugerencia(pid, ["#Mexico", "#noexiste123", "#cdmx"])
    assert guardados == ["#mexico", "#cdmx"]
    # Persistida como JSON en la pieza y expuesta como lista por `pieza_a_dict`.
    pub = repos.obtener_pieza(pid)
    assert json.loads(pub["hashtags_sugeridos"]) == ["#mexico", "#cdmx"]
    d = pieza_a_dict(pub)
    assert d["hashtags_sugeridos"] == ["#mexico", "#cdmx"]
    assert d["falta_hashtags"] is True  # el copy sigue sin hashtags hasta que un humano acepte


def test_no_sugiere_si_la_pieza_ya_tiene_hashtags(entorno):
    pid = _crear_pieza_borrador("Cuerpo con #mundial ya puesto")
    assert dom_sh.lanzar_para_publicacion(pid) is None


def test_no_sugiere_si_ya_hay_sugerencia(entorno):
    pid = _crear_pieza_borrador("Cuerpo sin hashtags")
    repos.actualizar_pieza(pid, {"hashtags_sugeridos": json.dumps(["#mexico"])})
    assert dom_sh.lanzar_para_publicacion(pid) is None


def test_pieza_a_dict_serializa_hashtags_sugeridos_vacio_por_defecto(entorno):
    pid = _crear_pieza_borrador("Cuerpo sin hashtags")
    d = pieza_a_dict(repos.obtener_pieza(pid))
    assert d["hashtags_sugeridos"] == []
