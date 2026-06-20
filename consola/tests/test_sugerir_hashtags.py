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
    assert out[0] == "#unotv"  # el fijo de unotv, primero
    assert "#portalunotv" not in out  # el tag máquina de ingesta web NUNCA se sugiere
    assert "#internacional" in out


def test_ensamblar_llena_el_cupo_aunque_la_ia_no_de_nada_usable():
    # Bug papa León: copy sin hashtags y la IA solo propone tags fuera de la biblioteca.
    # Antes salía vacío; ahora se llena con fijos + relleno por frecuencia.
    out = dom_sh.ensamblar(["#papaleon", "#habemuspapa"], marca=_MARCA, cantidad=5)
    assert len(out) == 5
    assert out[0] == "#unotv"
    assert "#portalunotv" not in out
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


def test_endurecer_va_con_haiku_por_defecto():
    # Elegir de la lista fija es tarea acotada: el run va con haiku (modelo barato), no el grande.
    assert dom_sh._endurecer()["modelo"] == "haiku"


def test_endurecer_respeta_el_modelo_configurado(monkeypatch):
    monkeypatch.setenv("KENI_HASHTAGS_MODELO", "sonnet")
    assert dom_sh._endurecer()["modelo"] == "sonnet"
    monkeypatch.setenv("KENI_HASHTAGS_MODELO", "")  # vacío explícito: sin --model (default de claude)
    assert dom_sh._endurecer()["modelo"] == ""


def test_componer_prompt_no_inyecta_contexto_editorial(entorno):
    # El pool de candidatos ya es de la marca; el prompt NO arrastra la voz/normas editoriales.
    out = dom_sh._componer_prompt(
        copy="Gana México el partido", marca=_MARCA, redes=["instagram"],
        candidatos=hb.candidatos(_MARCA), cantidad=5,
    )
    assert "Contexto editorial" not in out
    assert "Gana México el partido" in out


# --------------------------------------------------------------------------- #
# Persistencia + encadenado + gating — Postgres (fixture `entorno`)              #
# --------------------------------------------------------------------------- #


def _crear_contenido(reds: list[str], copy: str) -> tuple[str, list[str]]:
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    ids = [repos.crear_pieza_fila(publicacion_id=tema["id"], red=r, copy=copy)["id"] for r in reds]
    return tema["id"], ids


def test_aplicar_sugerencia_escribe_identica_en_todas_las_gemelas(entorno):
    pid, ids = _crear_contenido(["instagram", "x"], "Cuerpo del post sin hashtags")
    guardados = dom_sh.aplicar_sugerencia(pid, ["#internacional", "#noexiste123", "#mexico"])
    # Firma de la marca al frente, temáticos válidos, cupo lleno (5), inventado descartado.
    assert guardados[0] == "#unotv"
    assert "#portalunotv" not in guardados  # tag máquina de ingesta web, nunca
    assert "#internacional" in guardados and "#mexico" in guardados
    assert "#noexiste123" not in guardados and len(guardados) == 5
    # GEMELO: las dos piezas del contenido llevan EXACTAMENTE la misma lista.
    listas = [json.loads(repos.obtener_pieza(i)["hashtags_sugeridos"]) for i in ids]
    assert listas[0] == listas[1] == guardados


def test_aplicar_sugerencia_cubre_borrador_y_revision(entorno):
    # La sugerencia se encadena al copy (pieza en borrador), pero si una gemela ya avanzó a revisión
    # mientras el job esperaba en la cola, también la recibe (la lista es idéntica entre redes).
    pid, ids = _crear_contenido(["instagram", "x"], "Cuerpo del post sin hashtags")
    assert repos.transicionar_estado_pieza(ids[1], "borrador", "en_revision") is not None
    guardados = dom_sh.aplicar_sugerencia(pid, ["#internacional", "#mexico"])
    assert guardados  # ni borrador ni revisión bloquean la aplicación
    listas = [json.loads(repos.obtener_pieza(i)["hashtags_sugeridos"]) for i in ids]
    assert listas[0] == listas[1] == guardados


def test_aplicar_sugerencia_ignora_programado_y_publicado(entorno):
    # `falta_hashtags` se resuelve ANTES de programar: una pieza programada/publicada ya no se toca.
    pid, ids = _crear_contenido(["instagram"], "Cuerpo del post sin hashtags")
    repos.transicionar_estado_pieza(ids[0], "borrador", "en_revision")
    repos.transicionar_estado_pieza(ids[0], "en_revision", "programado")
    assert dom_sh.aplicar_sugerencia(pid, ["#mexico"]) == []


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


def test_copy_encadena_la_sugerencia_por_contenido(monkeypatch):
    # El post-proceso del copy dispara la sugerencia EN CUANTO crea los borradores (un disparo por
    # contenido, con sus gemelas como twins). Sustituye al barrido async. Piezas sin tema se ignoran.
    from keni_consola.dominio import copy as dom_copy

    llamadas: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        dom_sh, "lanzar_para_contenido",
        lambda pid, twins: llamadas.append((pid, sorted(t["red"] for t in twins))),
    )
    piezas = [
        {"publicacion_id": "c1", "red": "instagram", "contenido": "hola"},
        {"publicacion_id": "c1", "red": "x", "contenido": "hola"},
        {"publicacion_id": "c2", "red": "facebook", "contenido": "otro"},
        {"publicacion_id": "", "red": "x", "contenido": "suelto"},  # sin tema: se ignora
    ]
    dom_copy._encolar_sugerencia_hashtags(piezas)
    assert sorted(llamadas) == [("c1", ["instagram", "x"]), ("c2", ["facebook"])]


def test_copy_encadenado_es_best_effort(monkeypatch):
    # Un fallo encolando la sugerencia NUNCA rompe el post-proceso del copy (el copy ya está hecho).
    from keni_consola.dominio import copy as dom_copy

    def _explota(pid, twins):
        raise RuntimeError("cola llena")

    monkeypatch.setattr(dom_sh, "lanzar_para_contenido", _explota)
    dom_copy._encolar_sugerencia_hashtags([{"publicacion_id": "c1", "red": "x", "contenido": "h"}])
