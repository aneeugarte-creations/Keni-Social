"""Etapa SUGERIR HASHTAGS (`dominio.sugerir_hashtags`): propone hashtags para un CONTENIDO que
aún no los lleva, sin tocar el copy. Los hashtags son GEMELOS en todas las redes: se calculan una
vez por contenido y se escriben idénticos en todas sus piezas.

Los helpers de parseo/armado son PUROS (sin BD); el gating y la persistencia usan Postgres
(fixture `entorno`). La sugerencia GRIS = FIJOS de la marca (firma) + temáticos de la IA (casados
con el pool plegando acentos), recortada a la cantidad típica; NO se rellena por frecuencia. El
hashtag de la LÍNEA va aparte (`hashtags_linea`), no en el gris.
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


def test_parsear_imagen_clave():
    assert (
        dom_sh._parsear_imagen_clave('{"hashtags": ["#x"], "imagen_clave": "niño usando tablet"}')
        == "niño usando tablet"
    )
    assert dom_sh._parsear_imagen_clave('{"hashtags": ["#x"]}') == ""  # sin clave -> ""
    assert dom_sh._parsear_imagen_clave("no hay json") == ""


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


def test_ensamblar_no_rellena_por_frecuencia_cuando_la_ia_no_da_nada_usable():
    # La IA solo propone tags fuera de la biblioteca: se descartan y NO se rellena con los
    # hashtags más usados de la marca. Solo queda la firma (lo único garantizado).
    out = dom_sh.ensamblar(["#papaleon", "#habemuspapa"], marca=_MARCA, cantidad=5)
    assert out == ["#unotv"]  # solo la firma; nada de relleno por frecuencia
    assert "#portalunotv" not in out


def test_ensamblar_casa_propuestos_sin_acento_con_la_ortografia_del_pool():
    # La IA suele devolver el tag SIN tilde; debe casar con el del pool (que sí la lleva) y emitirse
    # con la ortografía de la marca, no descartarse por el diacrítico (era el bug de "salían 2 de 5").
    assert "fútbolconcausa" in set(hb.candidatos("fundacion"))  # el pool lo tiene CON acento
    out = dom_sh.ensamblar(["#futbolconcausa", "#salud"], marca="fundacion", cantidad=5)
    assert "#fútbolconcausa" in out and "#salud" in out


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
    # Firma de la marca al frente + solo los temáticos válidos de la IA (sin relleno), inventado fuera.
    assert guardados[0] == "#unotv"
    assert "#portalunotv" not in guardados  # tag máquina de ingesta web, nunca
    assert "#internacional" in guardados and "#mexico" in guardados
    assert "#noexiste123" not in guardados
    assert guardados == ["#unotv", "#internacional", "#mexico"]  # firma + temáticos, nada más
    # GEMELO: las dos piezas del contenido llevan EXACTAMENTE la misma lista.
    listas = [json.loads(repos.obtener_pieza(i)["hashtags_sugeridos"]) for i in ids]
    assert listas[0] == listas[1] == guardados


def test_aplicar_sugerencia_no_mete_la_linea_en_el_gris(entorno):
    # El hashtag de la LÍNEA NO va en la sugerencia gris (`hashtags_sugeridos`): se propone aparte
    # y en rojo. El gris es solo firma + temáticos del pool.
    pid, ids = _crear_contenido(["instagram", "x"], "Cuerpo del post sin hashtags")
    et = repos.crear_etiqueta(
        nombre="Ciencia/Tech", clase="categoria", marca=_MARCA, hashtags="cienciatech",
    )
    repos.asignar_etiqueta(pid, et["id"])
    guardados = dom_sh.aplicar_sugerencia(pid, ["#internacional"])
    assert "#cienciatech" not in guardados  # la línea no se mezcla con el gris
    assert guardados == ["#unotv", "#internacional"]  # solo firma + temático
    listas = [json.loads(repos.obtener_pieza(i)["hashtags_sugeridos"]) for i in ids]
    assert listas[0] == listas[1] == guardados


def test_linea_hashtags_sale_de_la_categoria_del_contenido(entorno):
    # `linea_hashtags` se resuelve en el SELECT de piezas desde la etiqueta `categoria` del
    # contenido (su id ES `categoria`); la pieza lo expone como `hashtags_linea`.
    et = repos.crear_etiqueta(
        nombre="Ciencia/Tech", clase="categoria", marca=_MARCA, hashtags="cienciatech",
    )
    tema = repos.crear_publicacion(
        clase="contenido", titulo="Tema", marca=_MARCA, categoria=et["id"],
    )
    pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="x")["id"]
    assert pieza_a_dict(repos.obtener_pieza(pid))["hashtags_linea"] == ["#cienciatech"]


def test_linea_hashtags_vacio_sin_categoria(entorno):
    # Contenido sin categoría: el LEFT JOIN a `etiquetas` no casa -> `linea_hashtags` NULL -> "".
    _, ids = _crear_contenido(["instagram"], "Cuerpo del post sin hashtags")
    assert pieza_a_dict(repos.obtener_pieza(ids[0]))["hashtags_linea"] == []


def test_aplicar_sugerencia_guarda_imagen_clave_gemela(entorno):
    pid, ids = _crear_contenido(["instagram", "x"], "Cuerpo del post sin hashtags")
    dom_sh.aplicar_sugerencia(pid, ["#mexico"], "bandera de mexico")
    # La keyword de búsqueda de foto se guarda IDÉNTICA en todas las gemelas (como los hashtags).
    claves = [repos.obtener_pieza(i)["imagen_clave"] for i in ids]
    assert claves[0] == claves[1] == "bandera de mexico"


def test_aplicar_sugerencia_no_pisa_imagen_clave_con_vacio(entorno):
    pid, ids = _crear_contenido(["instagram"], "Cuerpo sin hashtags")
    dom_sh.aplicar_sugerencia(pid, ["#mexico"], "estadio de futbol")
    dom_sh.aplicar_sugerencia(pid, ["#mexico"], "")  # sin clave nueva: conserva la anterior
    assert repos.obtener_pieza(ids[0])["imagen_clave"] == "estadio de futbol"


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
