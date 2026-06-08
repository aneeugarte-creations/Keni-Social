"""Tests del pipeline de contenido CI→QA(fuente)→CD (ADITIVO, gateado por `KENI_PIPELINE`).

REDISEÑO QPC: la QA se movió a ANTES del copy y por PIEZA (tema/fuente). El barrido es ahora
CI (crea temas SIN copy) → QA de la FUENTE (criba permisiva por tema) → CD (copy SOLO de los
temas `no_verificado`). Todo OFFLINE: ni red (og:image mockeada), ni `claude` (`lanzar_copy` y
la generación de QA mockeados), ni feeds reales (items canned). Cubre:
  (a) gateado OFF por defecto -> el barrido NO produce nada;
  (b) con el flag, CI selecciona <= cap por marca, crea temas SIN copy y marca el item usado;
  (c) se emiten entradas de actividad de etapa CI (y, al lanzar, QA/CD);
  (d) una fuente `problema` NO genera copy y marca el tema ❗; una `no_verificado` SÍ genera
      copy y las piezas heredan el aviso ⚠️;
  (e) el cap por barrido (QA y CD) se respeta.

Las funciones PURAS (`items_ingeribles`, `qa_lexico`, `_extraer_og_image`) se prueban sin DB.
Los flujos con persistencia usan la fixture `entorno` (Postgres de pruebas; se salta si no hay).
"""

from __future__ import annotations

import json

from keni_consola import config, generaciones, redes, repos
from keni_consola import pipeline_contenido as pc

from .conftest import _cliente, lanzador_generacion_completa

_URL_OK = "https://ejemplo.test/feed.xml"

# Salidas canned de la QA de la fuente (semáforo + bloque json estructurado).
_QA_OK = (
    "🟢 Fuente apta.\n\n"
    '```json\n{"veredicto": "🟢", "resumen": "Sin problemas de peso", "hallazgos": []}\n```\n'
)
_QA_PROBLEMA = (
    "🔴 Problema de peso.\n\n"
    '```json\n{"veredicto": "🔴", "resumen": "Dato falso evidente", '
    '"hallazgos": [{"tipo": "dato", "gravedad": "error", "fragmento": "x", '
    '"explicacion": "es falso", "sugerencia": "no publicar"}]}\n```\n'
)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _item(**kw):
    base = {
        "titulo": "Un tema fresco",
        "resumen": "Por qué importa",
        "enlace": "https://ejemplo.test/nota",
        "fecha": "",
        "clave": "k1",
        "imagen": "",
    }
    base.update(kw)
    return base


def _mock_lanzar_copy(monkeypatch):
    """Parchea `gen_dom.lanzar_copy` para capturar las llamadas (sin `claude`)."""
    llamadas: list[dict] = []

    def fake(**kw):
        llamadas.append(kw)
        return {"id": f"gen-{len(llamadas)}"}

    monkeypatch.setattr(pc.gen_dom, "lanzar_copy", fake)
    return llamadas


def _mock_feed(monkeypatch, items):
    """Parchea la lectura de items del feed para devolver `items` canned (sin red)."""
    monkeypatch.setattr(pc, "_leer_items_fuente", lambda fuente: list(items))


def _mock_og_image(monkeypatch, url=""):
    """Parchea la resolución de og:image (sin red)."""
    monkeypatch.setattr(pc, "_FETCH_OG_IMAGE", lambda enlace: url)


# --------------------------------------------------------------------------- #
# Funciones PURAS (sin DB)                                                     #
# --------------------------------------------------------------------------- #


def test_items_ingeribles_filtra_usados_y_capa():
    items = [_item(clave="a"), _item(clave="b"), _item(clave="c")]
    elegidos = pc.items_ingeribles(items, vistas={"b"}, maximo=5)
    assert [i["clave"] for i in elegidos] == ["a", "c"]


def test_items_ingeribles_respeta_cap():
    items = [_item(clave=f"k{i}") for i in range(5)]
    elegidos = pc.items_ingeribles(items, vistas=set(), maximo=2)
    assert [i["clave"] for i in elegidos] == ["k0", "k1"]


def test_items_ingeribles_omite_sin_clave_o_sin_titulo():
    items = [_item(clave=""), _item(titulo="  "), _item(clave="ok")]
    elegidos = pc.items_ingeribles(items, vistas=set(), maximo=5)
    assert [i["clave"] for i in elegidos] == ["ok"]


def test_url_fuente_de_canoniza_http():
    item = _item(enlace="https://www.ejemplo.test/n/?utm_source=x&id=9#a")
    assert pc._url_fuente_de(item) == "ejemplo.test/n?id=9"


def test_url_fuente_de_vacia_si_no_http():
    assert pc._url_fuente_de(_item(enlace="")) == ""
    assert pc._url_fuente_de(_item(enlace="ftp://x/y")) == ""
    assert pc._url_fuente_de({"titulo": "x"}) == ""


def test_extraer_og_image():
    html = '<head><meta property="og:image" content="https://x.test/foto.jpg"></head>'
    assert pc._extraer_og_image(html) == "https://x.test/foto.jpg"


def test_extraer_og_image_ausente():
    assert pc._extraer_og_image("<head></head>") == ""
    assert pc._extraer_og_image("") == ""


def test_qa_lexico_listo_sin_observaciones():
    r = pc.qa_lexico({"red": "x", "contenido": "Copy corto y válido."})
    assert r["verdicto"] == "listo"
    assert r["observaciones"] == []


def test_qa_lexico_copy_vacio():
    r = pc.qa_lexico({"red": "x", "contenido": "   "})
    assert r["verdicto"] == "revisar"
    assert any("vacío" in o for o in r["observaciones"])


def test_qa_lexico_supera_limite_de_red():
    limite = next(red.limite for red in redes.REDES if red.id == "x")
    assert limite is not None
    r = pc.qa_lexico({"red": "x", "contenido": "a" * (limite + 1)})
    assert r["verdicto"] == "revisar"
    assert any("límite" in o for o in r["observaciones"])


# --------------------------------------------------------------------------- #
# (a) GATEADO OFF por defecto -> el barrido NO produce nada                    #
# --------------------------------------------------------------------------- #


def test_gateado_off_no_arranca_el_daemon():
    """Sin `KENI_PIPELINE`, el flag está OFF (def): el `bucle_gateado` no barrería."""
    assert config.pipeline_activo() is False


def test_iniciar_pipeline_no_genera_sin_flag(entorno, monkeypatch):
    """El daemon arranca pero, gateado OFF, NO crea temas (el barrido no corre)."""
    llamadas = _mock_lanzar_copy(monkeypatch)
    repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    _mock_feed(monkeypatch, [_item()])
    _mock_og_image(monkeypatch, "")

    from keni_consola import daemon_util

    daemon_util.bucle_gateado(
        activo_fn=config.pipeline_activo,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=pc.ejecutar_barrido,
        log=pc._log,
        _max_vueltas=1,
    )
    assert llamadas == []
    assert _etapas_de_actividad() == []
    # No se creó ningún tema del pipeline.
    assert pc.temas_pipeline() == []


# --------------------------------------------------------------------------- #
# (b)+(c) CI: crea temas SIN copy, dedup, y etapa CI en actividad              #
# --------------------------------------------------------------------------- #


def _etapas_de_actividad():
    """Etiquetas de las generaciones-marcador del pipeline (tipo 'pipeline_etapa'), recientes 1º."""
    return [
        g["etiqueta"]
        for g in generaciones.listar(limite=None)
        if g["tipo"] == pc.TIPO_ACTIVIDAD
    ]


def test_ci_crea_temas_sin_copy_y_dedup(entorno, monkeypatch):
    """CI selecciona <= cap, crea temas SIN copy, marca items usados; QA queda sin documento."""
    monkeypatch.setenv("KENI_PIPELINE", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "2")
    llamadas = _mock_lanzar_copy(monkeypatch)
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    # Sin documento de QA disponible: la fase QA no lanza nada (temas quedan sin veredicto) y CD
    # no genera copy. Aislamos así la fase CI sin tocar `claude`.
    monkeypatch.setattr(pc, "asegurar_documento_qa", lambda: "")

    fuente = repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    items = [_item(clave="a", titulo="Tema A"), _item(clave="b", titulo="Tema B"),
             _item(clave="c", titulo="Tema C")]
    _mock_feed(monkeypatch, items)
    _mock_og_image(monkeypatch, "")

    resumen = pc.ejecutar_barrido()

    # CI creó 2 temas (cap) SIN copy; CD no lanzó nada (sin QA aprobada).
    assert len(resumen["temas"]) == 2
    assert llamadas == []
    titulos = {t["titulo"] for t in pc.temas_pipeline()}
    assert {"Tema A", "Tema B"} <= titulos
    assert all((t.get("qa_veredicto") or "") == "" for t in pc.temas_pipeline())

    # dedup: A y B quedaron marcados usados.
    vistas = repos.claves_vistas(fuente["id"])
    assert {"a", "b"} <= vistas

    # Etapa CI en la actividad.
    assert any(e.startswith("CI · ") for e in _etapas_de_actividad())

    # dedup efectiva: un SEGUNDO barrido crea el restante (C).
    pc.ejecutar_barrido()
    assert {t["titulo"] for t in pc.temas_pipeline()} >= {"Tema A", "Tema B", "Tema C"}


def test_ci_guarda_copy_pendiente_con_imagen_propia(entorno, monkeypatch):
    """Feed de marca PROPIA: la og:image resuelta queda en `copy_pendiente` del tema."""
    import json

    monkeypatch.setenv("KENI_PIPELINE", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "1")
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setattr(pc, "asegurar_documento_qa", lambda: "")

    repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    _mock_feed(monkeypatch, [_item(clave="p1", titulo="Nota propia")])
    _mock_og_image(monkeypatch, "https://casa.test/foto.jpg")

    pc.ejecutar_barrido()

    temas = pc.temas_pipeline()
    assert len(temas) == 1
    pend = json.loads(temas[0]["copy_pendiente"])
    assert pend["imagen"] == "https://casa.test/foto.jpg"
    assert pend["tipo_contenido"] == "fuente"


def test_ci_persiste_url_fuente_canonica(entorno, monkeypatch):
    """CI: un item con `enlace` http(s) persiste `url_fuente` CANÓNICA en el tema creado."""
    monkeypatch.setenv("KENI_PIPELINE", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "1")
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setattr(pc, "asegurar_documento_qa", lambda: "")

    repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    # Enlace con tracking + esquema + www: la canónica los normaliza (cruce por URL).
    enlace = "https://www.ejemplo.test/nota-1?utm_source=rss&id=7#frag"
    _mock_feed(monkeypatch, [_item(clave="u1", titulo="Tema con URL", enlace=enlace)])
    _mock_og_image(monkeypatch, "")

    pc.ejecutar_barrido()

    temas = pc.temas_pipeline()
    assert len(temas) == 1
    tema = repos.obtener_contenido(temas[0]["id"])
    assert (tema.get("url_fuente") or "") == "ejemplo.test/nota-1?id=7"


def test_ci_url_fuente_vacia_si_enlace_no_http(entorno, monkeypatch):
    """CI: un item sin enlace http(s) deja `url_fuente` vacía (no rompe la creación del tema)."""
    monkeypatch.setenv("KENI_PIPELINE", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "1")
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setattr(pc, "asegurar_documento_qa", lambda: "")

    repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    _mock_feed(monkeypatch, [_item(clave="u2", titulo="Sin enlace", enlace="")])
    _mock_og_image(monkeypatch, "")

    pc.ejecutar_barrido()

    temas = pc.temas_pipeline()
    assert len(temas) == 1
    tema = repos.obtener_contenido(temas[0]["id"])
    assert (tema.get("url_fuente") or "") == ""


# --------------------------------------------------------------------------- #
# (d) QA de la fuente: problema NO genera copy (❗); no_verificado SÍ (⚠️)      #
# --------------------------------------------------------------------------- #


def _tema_pipeline(titulo="Tema", marca="unotv", **campos):
    # `copy_pendiente` lo fija CI (`crear_tema_de`) en producción: parámetros del copy a lanzar
    # SOLO si la QA de la fuente pasa. La fase CD exige que esté presente; lo sembramos aquí.
    campos.setdefault(
        "copy_pendiente",
        json.dumps({"nota": "Nota de origen a cribar.", "redes_ids": ["x"]}),
    )
    return repos.crear_contenido(
        clase="contenido", titulo=titulo, marca=marca, origen=pc.ORIGEN_PIPELINE,
        descripcion="Nota de origen a cribar.", **campos,
    )


def test_qa_problema_no_genera_copy_y_marca_tema(entorno, monkeypatch):
    """Una QA de la fuente `problema` -> NO se lanza copy y el tema queda ❗ con hallazgos."""
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_QA_PROBLEMA))  # noqa: F841
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(titulo="Tema malo")

    # Fase QA: lanza la criba (síncrona en test) -> el procesar persiste el veredicto en el tema.
    pc.ejecutar_qa(autor=None)
    refrescado = repos.obtener_contenido(tema["id"])
    assert refrescado["qa_veredicto"] == pc.VERDICTO_PROBLEMA
    assert "es falso" in (refrescado["qa_hallazgos"] or "")

    # Fase CD: un tema `problema` NO entra a copy (ahorro de tokens).
    pc.ejecutar_cd(autor=None)
    assert llamadas == []
    assert pc.temas_para_copy() == []


def test_qa_no_verificado_genera_copy_con_aviso(entorno, monkeypatch):
    """Una QA `no_verificado` -> SÍ se lanza copy y las piezas heredan el aviso ⚠️."""
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_QA_OK))  # noqa: F841
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(titulo="Tema ok")

    pc.ejecutar_qa(autor=None)
    refrescado = repos.obtener_contenido(tema["id"])
    assert refrescado["qa_veredicto"] == pc.VERDICTO_NO_VERIFICADO

    # Fase CD: el tema está listo para copy.
    listos = pc.temas_para_copy()
    assert [t["id"] for t in listos] == [tema["id"]]
    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 1
    # La pieza hereda el aviso ⚠️ por el veredicto inicial.
    assert llamadas[0]["veredicto_inicial"] == pc.VERDICTO_NO_VERIFICADO
    # Limpia copy_pendiente: la fase CD no lo relanza.
    assert (repos.obtener_contenido(tema["id"])["copy_pendiente"] or "") == ""
    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 1


def test_qa_no_relanza_tema_ya_cribado(entorno, monkeypatch):
    """Un tema con veredicto ya no se re-criba (idempotente)."""
    _tema_pipeline(titulo="Ya cribado", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    assert pc.temas_sin_qa() == []


def test_qa_respeta_cap_de_lanzamientos(entorno, monkeypatch):
    """El cap por barrido de QA (`_QA_LANZAR_MAX`) acota los lanzamientos de criba."""
    cliente = _cliente()  # noqa: F841 -- lanzador noop: deja la QA en `ejecutando` (en_curso)
    monkeypatch.setattr(pc, "_QA_LANZAR_MAX", 2)
    for i in range(4):
        _tema_pipeline(titulo=f"T{i}", id=f"tqa{i}")

    cribados = pc.ejecutar_qa(autor=None)
    assert len(cribados) == 2  # solo 2 cribas lanzadas; el resto en el próximo barrido.


def test_cd_respeta_cap_de_lanzamientos(entorno, monkeypatch):
    """El cap por barrido de CD (`_CD_LANZAR_MAX`) acota los lanzamientos de copy."""
    llamadas = _mock_lanzar_copy(monkeypatch)
    monkeypatch.setattr(pc, "_CD_LANZAR_MAX", 2)
    import json

    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    for i in range(4):
        _tema_pipeline(
            titulo=f"C{i}", id=f"tcd{i}",
            qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente=pend,
        )

    lanzados = pc.ejecutar_cd(autor=None)
    assert len(lanzados) == 2
    assert len(llamadas) == 2


# --------------------------------------------------------------------------- #
# Fundido de la selección de autogen_copy en la etapa de copy (news-pool)      #
# --------------------------------------------------------------------------- #


def test_temas_autogen_sin_copy_selecciona_origenes_de_noticias(entorno):
    """La etapa de copy también redacta los temas del news-pool (orígenes de noticias) sin copy.

    Un tema con origen en `ORIGENES_AUTOGEN`, con marca y sin copy entra; el de origen "" no.
    """
    bueno = repos.crear_contenido(
        clase="contenido", titulo="Noticia rss", marca="unotv", origen="rss",
    )
    repos.crear_contenido(
        clase="contenido", titulo="Tecleado a mano", marca="unotv", origen="",
    )
    ids = {t["id"] for t in pc.temas_autogen_sin_copy()}
    assert bueno["id"] in ids
    # El tecleado (origen "") NO entra.
    assert len(ids) == 1


def test_ejecutar_cd_funde_pool_via_autogen_lanzar(entorno, monkeypatch):
    """`ejecutar_cd` lanza copy de los temas del pool vía `autogen_copy.lanzar_para_topic`."""
    from keni_consola import autogen_copy

    lanzadas: list[str] = []
    monkeypatch.setattr(
        autogen_copy, "lanzar_para_topic",
        lambda item: lanzadas.append(item["id"]) or {"id": f"g-{item['id']}"},
    )
    repos.crear_contenido(
        clase="contenido", titulo="Noticia pool", marca="unotv", origen="rss",
    )
    lanzados = pc.ejecutar_cd(autor=None)
    assert len(lanzadas) == 1
    assert len(lanzados) == 1


def test_ejecutar_cd_salta_pool_de_marca_apagada(entorno, monkeypatch):
    """La exclusión por marca de «Generar copy» (ENV_PIPELINE) también aplica al pool."""
    from keni_consola import autogen_copy

    monkeypatch.setattr(pc.config, "marca_apagada", lambda env, marca: marca == "unotv")
    lanzadas: list[str] = []
    monkeypatch.setattr(
        autogen_copy, "lanzar_para_topic",
        lambda item: lanzadas.append(item["id"]) or {"id": "g"},
    )
    repos.crear_contenido(
        clase="contenido", titulo="Apagada", marca="unotv", origen="rss",
    )
    pc.ejecutar_cd(autor=None)
    assert lanzadas == []


# --------------------------------------------------------------------------- #
# Etapa de ARTE del pipeline (toggle "Generar arte", KENI_AUTOGEN_ARTE)        #
# --------------------------------------------------------------------------- #


def test_ejecutar_arte_off_por_defecto_no_hace_nada(entorno, monkeypatch):
    """Sin `KENI_AUTOGEN_ARTE`, la etapa de arte no ilustra (devuelve [])."""
    monkeypatch.delenv(config.ENV_AUTOGEN_ARTE, raising=False)
    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    assert pc.ejecutar_arte() == []


def test_ejecutar_arte_gateado_corre_seleccion_y_lanzamiento(entorno, monkeypatch):
    """Con el toggle + máquina ON y proveedor configurado, ilustra vía autogen_arte."""
    from keni_consola import autogen_arte

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_AUTOGEN_ARTE, "1")
    monkeypatch.setattr(autogen_arte.media, "proveedor_configurado", lambda: True)
    item = {"id": "t1", "titulo": "Tema", "marca": "unotv"}
    monkeypatch.setattr(pc.repos, "listar_contenido", lambda **_k: [item])
    monkeypatch.setattr(autogen_arte, "_plataformas_por_item", lambda items: {})
    monkeypatch.setattr(autogen_arte, "ids_ya_procesados", lambda: set())
    monkeypatch.setattr(autogen_arte, "_etiquetas_por_item", lambda: {})
    monkeypatch.setattr(autogen_arte, "topics_sin_arte", lambda *a, **k: [item])
    adjuntados: list[str] = []
    monkeypatch.setattr(
        autogen_arte, "lanzar_para_topic",
        lambda it: adjuntados.append(it["id"]) or {"contenido_id": it["id"]},
    )
    res = pc.ejecutar_arte()
    assert adjuntados == ["t1"]
    assert len(res) == 1


def test_ejecutar_arte_sin_proveedor_no_ilustra(entorno, monkeypatch):
    """Con el toggle ON pero sin proveedor de imagen, la etapa de arte no hace nada."""
    from keni_consola import media

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_AUTOGEN_ARTE, "1")
    monkeypatch.setattr(media, "proveedor_configurado", lambda: False)
    assert pc.ejecutar_arte() == []
