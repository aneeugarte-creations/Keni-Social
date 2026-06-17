"""Etapa SUGERIR HASHTAGS (`dominio.sugerir_hashtags`): propone hashtags para un CONTENIDO que
aún no los lleva, sin tocar el copy. Los hashtags son GEMELOS en todas las redes: se calculan una
vez por contenido y se escriben idénticos en todas sus piezas.

Los helpers de parseo/armado son PUROS (sin BD); el gating y la persistencia usan Postgres
(fixture `entorno`). La lista final = FIJOS de la marca (firma) + temáticos de la IA (filtrados a
la biblioteca) + relleno por frecuencia hasta la cantidad típica.
"""

from __future__ import annotations

import json

from keni_consola import hashtags_biblioteca as hb
from keni_consola import repos
from keni_consola.dominio import sugerir_hashtags as dom_sh
from keni_consola.dominio.piezas import pieza_a_dict
from keni_consola.pipeline_contenido import contenidos_para_sugerir_hashtags

_MARCA = "unotv"


# --------------------------------------------------------------------------- #
# Parseo + armado — PURO                                                         #
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


def test_ensamblar_siempre_incluye_los_fijos_de_la_marca():
    # La IA NO propone la firma de la marca (no es temática); debe ir igual, al frente.
    out = dom_sh.ensamblar(["#internacional"], marca=_MARCA, cantidad=5)
    assert out[:2] == ["#unotv", "#portalunotv"]  # los fijos de unotv, primero
    assert "#internacional" in out


def test_ensamblar_llena_el_cupo_aunque_la_ia_no_de_nada_usable():
    # Bug papa León: copy sin hashtags y la IA solo propone tags fuera de la biblioteca.
    # Antes salía vacío; ahora se llena con fijos + relleno por frecuencia.
    out = dom_sh.ensamblar(["#papaleon", "#habemuspapa"], marca=_MARCA, cantidad=5)
    assert len(out) == 5
    assert out[:2] == ["#unotv", "#portalunotv"]
    assert all(t.lstrip("#") in set(hb.candidatos(_MARCA)) for t in out)


def test_ensamblar_descarta_inventados_y_dedup():
    out = dom_sh.ensamblar(["#Mexico", "#mexico", "#noexiste123"], marca=_MARCA, cantidad=5)
    cuerpos = [t.lstrip("#") for t in out]
    assert "mexico" in cuerpos and cuerpos.count("mexico") == 1
    assert "noexiste123" not in cuerpos


def test_ensamblar_cantidad_cero_es_vacia():
    assert dom_sh.ensamblar(["#mexico"], marca=_MARCA, cantidad=0) == []


def test_ensamblar_respeta_la_cantidad():
    out = dom_sh.ensamblar([f"#{c}" for c in hb.candidatos(_MARCA)[:10]], marca=_MARCA, cantidad=3)
    assert len(out) == 3


def test_cantidad_contenido_es_el_maximo_entre_redes():
    # X no está en `conteo_por_red` de unotv -> default 5; instagram 5 -> max 5.
    assert dom_sh.cantidad_contenido(_MARCA, ["x", "instagram"]) == 5
    # claro-sports: youtube 0, instagram 5 -> max 5 (gemelo en todas, gobernado por el máximo).
    assert dom_sh.cantidad_contenido("claro-sports", ["youtube"]) == 0
    assert dom_sh.cantidad_contenido("claro-sports", ["youtube", "instagram"]) == 5


def test_falta_hashtags():
    assert dom_sh.falta_hashtags({"contenido": "Sin etiquetas"}) is True
    assert dom_sh.falta_hashtags({"contenido": "Con #mundial"}) is False


# --------------------------------------------------------------------------- #
# Selección del barrido — PURA (agrupa por contenido)                            #
# --------------------------------------------------------------------------- #


def _twin(pid: str, red: str, contenido: str, sugeridos: list[str] | None = None) -> dict:
    return {
        "publicacion_id": pid, "red": red, "marca": _MARCA, "estado": "borrador",
        "contenido": contenido, "hashtags_sugeridos": sugeridos or [],
    }


def test_seleccion_agrupa_por_contenido_una_entrada_por_publicacion():
    pubs = [_twin("c1", "instagram", "sin hashtags"), _twin("c1", "x", "sin hashtags")]
    elegidos = contenidos_para_sugerir_hashtags(pubs)
    assert len(elegidos) == 1
    pid, twins = elegidos[0]
    assert pid == "c1" and {t["red"] for t in twins} == {"instagram", "x"}


def test_seleccion_salta_si_ya_tiene_hashtags_o_sugerencia():
    con_hashtag = [_twin("c1", "instagram", "lleva #mundial"), _twin("c1", "x", "lleva #mundial")]
    assert contenidos_para_sugerir_hashtags(con_hashtag) == []
    con_sugerencia = [_twin("c2", "instagram", "sin hashtags", sugeridos=["#mexico"])]
    assert contenidos_para_sugerir_hashtags(con_sugerencia) == []


# --------------------------------------------------------------------------- #
# Persistencia + gating — Postgres (fixture `entorno`)                           #
# --------------------------------------------------------------------------- #


def _crear_contenido(reds: list[str], copy: str) -> tuple[str, list[str]]:
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    ids = [repos.crear_pieza_fila(publicacion_id=tema["id"], red=r, copy=copy)["id"] for r in reds]
    return tema["id"], ids


def test_aplicar_sugerencia_escribe_identica_en_todas_las_gemelas(entorno):
    pid, ids = _crear_contenido(["instagram", "x"], "Cuerpo del post sin hashtags")
    guardados = dom_sh.aplicar_sugerencia(pid, ["#internacional", "#noexiste123", "#mexico"])
    # Firma de la marca al frente, temáticos válidos, cupo lleno (5), inventado descartado.
    assert guardados[:2] == ["#unotv", "#portalunotv"]
    assert "#internacional" in guardados and "#mexico" in guardados
    assert "#noexiste123" not in guardados and len(guardados) == 5
    # GEMELO: las dos piezas del contenido llevan EXACTAMENTE la misma lista.
    listas = [json.loads(repos.obtener_pieza(i)["hashtags_sugeridos"]) for i in ids]
    assert listas[0] == listas[1] == guardados


def test_no_sugiere_si_el_contenido_ya_tiene_hashtags(entorno):
    pid, ids = _crear_contenido(["instagram", "x"], "Cuerpo con #mundial ya puesto")
    twins = [pieza_a_dict(repos.obtener_pieza(i)) for i in ids]
    assert dom_sh.lanzar_para_contenido(pid, twins) is None


def test_no_sugiere_si_ya_hay_sugerencia(entorno):
    pid, ids = _crear_contenido(["instagram"], "Cuerpo sin hashtags")
    repos.actualizar_pieza(ids[0], {"hashtags_sugeridos": json.dumps(["#mexico"])})
    twins = [pieza_a_dict(repos.obtener_pieza(i)) for i in ids]
    assert dom_sh.lanzar_para_contenido(pid, twins) is None


def test_pieza_a_dict_serializa_hashtags_sugeridos_vacio_por_defecto(entorno):
    _pid, ids = _crear_contenido(["instagram"], "Cuerpo sin hashtags")
    d = pieza_a_dict(repos.obtener_pieza(ids[0]))
    assert d["hashtags_sugeridos"] == []
