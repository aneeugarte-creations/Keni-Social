"""Tests del pipeline de contenido CI→QA(fuente)→CD (ADITIVO, gateado por `KENI_PIPELINE_COPY`).

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


def _ci_desde_feed(marca="unotv", *, maximo=2):
    """CI feed→tema con los building blocks `ingerir_marca` + `crear_tema_de` (sin el barrido).

    El barrido auto ahora promueve CLUSTERS rankeados; estos building blocks de feed siguen
    existiendo y se cubren aquí en aislamiento (dedup, copy_pendiente con og:image, url_fuente).
    """
    trabajos = pc.ingerir_marca(marca, maximo=maximo)
    claves: set[str] = set()
    return [t for tr in trabajos if (t := pc.crear_tema_de(tr, claves_vistas=claves))]


def _sembrar_cluster(cid, *, marca="unotv", titulo="Historia X", score=0.5, estado="nuevo"):
    """Siembra un cluster del pool (Ola B) para los tests de promoción CI→tema."""
    repos.upsert_noticia_cluster({
        "id": cid, "titulo": titulo, "resumen": "Resumen de la historia", "marca": marca,
        "categoria": "mx", "geo": "MX", "clave": f"t:{cid}", "n_items": 1, "n_fuentes": 2,
        "idiomas": ["es"], "senal": 100, "score": score, "breaking": 0,
        "primer_visto": "2026-06-01T00:00:00+00:00", "ultimo_visto": "2026-06-05T12:00:00+00:00",
        "estado": estado,
    })
    return repos.obtener_noticia_cluster(cid)


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
    """Sin `KENI_PIPELINE_COPY`, el flag está OFF (def): el `bucle_gateado` no barrería."""
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
    """CI feed→tema (building blocks) selecciona <= cap, crea temas SIN copy y dedup efectiva."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)

    fuente = repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    items = [_item(clave="a", titulo="Tema A"), _item(clave="b", titulo="Tema B"),
             _item(clave="c", titulo="Tema C")]
    _mock_feed(monkeypatch, items)
    _mock_og_image(monkeypatch, "")

    temas = _ci_desde_feed(maximo=2)

    # CI creó 2 temas (cap) SIN copy ni veredicto de QA.
    assert len(temas) == 2
    titulos = {t["titulo"] for t in pc.temas_pipeline()}
    assert {"Tema A", "Tema B"} <= titulos
    assert all((t.get("qa_veredicto") or "") == "" for t in pc.temas_pipeline())

    # dedup: A y B quedaron marcados usados.
    vistas = repos.claves_vistas(fuente["id"])
    assert {"a", "b"} <= vistas

    # Etapa CI en la actividad.
    assert any(e.startswith("CI · ") for e in _etapas_de_actividad())

    # dedup efectiva: un SEGUNDO pase crea el restante (C).
    _ci_desde_feed(maximo=2)
    assert {t["titulo"] for t in pc.temas_pipeline()} >= {"Tema A", "Tema B", "Tema C"}


def test_ci_guarda_copy_pendiente_con_imagen_propia(entorno, monkeypatch):
    """Feed de marca PROPIA: la og:image resuelta queda en `copy_pendiente` del tema."""
    import json

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)

    repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    _mock_feed(monkeypatch, [_item(clave="p1", titulo="Nota propia")])
    _mock_og_image(monkeypatch, "https://casa.test/foto.jpg")

    temas = _ci_desde_feed(maximo=1)

    assert len(temas) == 1
    pend = json.loads(pc.temas_pipeline()[0]["copy_pendiente"])
    assert pend["imagen"] == "https://casa.test/foto.jpg"
    assert pend["tipo_contenido"] == "fuente"


def test_ci_persiste_url_fuente_canonica(entorno, monkeypatch):
    """CI: un item con `enlace` http(s) persiste `url_fuente` CANÓNICA en el tema creado."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)

    repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    # Enlace con tracking + esquema + www: la canónica los normaliza (cruce por URL).
    enlace = "https://www.ejemplo.test/nota-1?utm_source=rss&id=7#frag"
    _mock_feed(monkeypatch, [_item(clave="u1", titulo="Tema con URL", enlace=enlace)])
    _mock_og_image(monkeypatch, "")

    temas = _ci_desde_feed(maximo=1)

    assert len(temas) == 1
    tema = repos.obtener_contenido(temas[0]["id"])
    assert (tema.get("url_fuente") or "") == "ejemplo.test/nota-1?id=7"


def test_ci_persiste_fuente_nombre_de_la_fuente(entorno, monkeypatch):
    """CI (feed RSS): el tema conserva el NOMBRE del medio (`fuente_nombre` = nombre de la fuente).

    Se copia al `contenido` al promover para que la cabecera de grupo del feed muestre la
    procedencia aunque el item/cluster de origen desaparezca después.
    """
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)

    repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    _mock_feed(monkeypatch, [_item(clave="fn1", titulo="Tema con medio")])
    _mock_og_image(monkeypatch, "")

    temas = _ci_desde_feed(maximo=1)

    assert len(temas) == 1
    tema = repos.obtener_contenido(temas[0]["id"])
    assert (tema.get("fuente_nombre") or "") == "Diario"


def test_ci_url_fuente_vacia_si_enlace_no_http(entorno, monkeypatch):
    """CI: un item sin enlace http(s) deja `url_fuente` vacía (no rompe la creación del tema)."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)

    repos.crear_fuente_rss("Diario", _URL_OK, marca="unotv")
    _mock_feed(monkeypatch, [_item(clave="u2", titulo="Sin enlace", enlace="")])
    _mock_og_image(monkeypatch, "")

    temas = _ci_desde_feed(maximo=1)
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
    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")        # etapa QA activa (criba la fuente)
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")  # etapa CD activa (aun así, un 'problema' no genera copy)
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
    """Una QA `no_verificado` -> el ENCADENADO dispara el copy YA y las piezas heredan el ⚠️.

    ENCADENADO POR EVENTOS: el `procesar` de la QA, al persistir un veredicto apto, lanza el
    copy de ESE tema al instante (antes esperaba al siguiente barrido de CD, +20 min). El
    barrido queda de red de seguridad. DEDUP AL ÉXITO: el lanzamiento NO limpia
    `copy_pendiente` (lo limpia el post-procesado del copy al completar); un copy fallido se
    reintenta y, en cuanto hay pieza, el tema sale de la selección.
    """
    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")        # etapa QA activa (criba la fuente)
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")  # etapa CD activa (genera copy del tema apto)
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_QA_OK))  # noqa: F841
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(titulo="Tema ok")

    pc.ejecutar_qa(autor=None)
    refrescado = repos.obtener_contenido(tema["id"])
    assert refrescado["qa_veredicto"] == pc.VERDICTO_NO_VERIFICADO

    # ENCADENADO QA→copy: el copy se disparó al persistirse el veredicto (sin esperar a CD).
    assert len(llamadas) == 1
    # La pieza hereda el aviso ⚠️ por el veredicto inicial.
    assert llamadas[0]["veredicto_inicial"] == pc.VERDICTO_NO_VERIFICADO
    # Dedup AL ÉXITO: el lanzador pide la limpieza al post-procesado (no limpia al encolar).
    assert llamadas[0]["limpiar_pendiente"] is True
    assert (repos.obtener_contenido(tema["id"])["copy_pendiente"] or "").strip()

    # Éxito del copy (simulado): nace la pieza -> el tema sale de la selección de CD y el
    # barrido (red de seguridad) NO lo relanza.
    repos.crear_contenido_plataforma(contenido_id=tema["id"], red="x", copy="Hola X")
    assert pc.temas_para_copy() == []
    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 1


def test_encadenado_no_dispara_copy_si_cd_apagada(entorno, monkeypatch):
    """El encadenado QA→copy respeta el gate de CD: con «Generar copy» OFF no lanza nada."""
    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")
    monkeypatch.delenv("KENI_PIPELINE_COPY", raising=False)
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_QA_OK))  # noqa: F841
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(titulo="Sin CD")

    pc.ejecutar_qa(autor=None)

    assert repos.obtener_contenido(tema["id"])["qa_veredicto"] == pc.VERDICTO_NO_VERIFICADO
    assert llamadas == []  # el encadenado no salta el toggle de copy


def test_encadenado_cola_llena_no_rompe_la_qa(entorno, monkeypatch):
    """`ColaLlenaError` al encadenar el copy NO rompe el procesar de la QA (lo recoge el barrido)."""
    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_QA_OK))  # noqa: F841

    def _llena(**_kw):
        raise generaciones.ColaLlenaError("cola llena")

    monkeypatch.setattr(pc.gen_dom, "lanzar_copy", _llena)
    tema = _tema_pipeline(titulo="Cola llena")

    pc.ejecutar_qa(autor=None)  # no debe reventar

    # El veredicto SÍ quedó persistido y el tema sigue elegible para el barrido de CD.
    assert repos.obtener_contenido(tema["id"])["qa_veredicto"] == pc.VERDICTO_NO_VERIFICADO
    assert [t["id"] for t in pc.temas_para_copy()] == [tema["id"]]


def test_copy_fallido_se_reintenta_en_el_siguiente_barrido(entorno, monkeypatch):
    """DEDUP AL ÉXITO: un copy que falló (sin piezas, `copy_pendiente` intacto) se RELANZA.

    Antes `copy_pendiente` se limpiaba al ENCOLAR y un copy fallido jamás se reintentaba (el
    tema quedaba huérfano para siempre). El doble lanzamiento mientras el job está EN VUELO
    lo evita la clave de idempotencia de `dominio.generar.lanzar` (no este filtro).
    """
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(titulo="Reintento", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)

    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 1
    # El lanzamiento NO limpió `copy_pendiente` (lo limpia el post-procesado al ÉXITO).
    assert (repos.obtener_contenido(tema["id"])["copy_pendiente"] or "").strip()

    # El copy "falló" (no nació pieza): el siguiente barrido lo reintenta.
    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 2

    # Éxito (pieza creada): deja de relanzarse.
    repos.crear_contenido_plataforma(contenido_id=tema["id"], red="x", copy="Listo")
    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 2


def test_qa_no_relanza_tema_ya_cribado(entorno, monkeypatch):
    """Un tema con veredicto ya no se re-criba (idempotente)."""
    _tema_pipeline(titulo="Ya cribado", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    assert pc.temas_sin_qa() == []


def test_temas_sin_qa_no_se_mata_de_hambre_con_backlog(entorno, monkeypatch):
    """Regresión de INANICIÓN: con backlog > ventana, los temas NUEVOS sin QA SÍ entran.

    Antes `temas_pipeline` recortaba la lista CRUDA a los N más viejos; en cuanto esos N ya
    estaban cribados, los temas nuevos quedaban FUERA de la ventana y QA no los veía jamás (en
    prod: 126 historias 'usado' atascadas sin veredicto). Ahora el recorte se aplica sobre los
    PENDIENTES, así que el nuevo entra aunque los viejos llenen el crudo.
    """
    monkeypatch.setenv("KENI_PIPELINE_QA_REVISAR_MAX", "2")
    _tema_pipeline(titulo="Viejo 1", id="v1", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _tema_pipeline(titulo="Viejo 2", id="v2", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _tema_pipeline(titulo="Nuevo", id="n1")  # sin veredicto -> pendiente
    assert [t["id"] for t in pc.temas_sin_qa()] == ["n1"]


def test_temas_para_copy_no_se_mata_de_hambre_con_backlog(entorno, monkeypatch):
    """Mismo anti-inanición para CD: un tema nuevo listo entra aunque los viejos llenen el crudo."""
    monkeypatch.setenv("KENI_PIPELINE_QA_REVISAR_MAX", "2")
    # Viejos no_verificado pero YA copiados (copy_pendiente vacío -> no pasan el filtro de CD),
    # ocuparían la ventana cruda. El nuevo (no_verificado + copy_pendiente + sin pieza) es el listo.
    _tema_pipeline(titulo="Viejo 1", id="v1", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente="")
    _tema_pipeline(titulo="Viejo 2", id="v2", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente="")
    _tema_pipeline(titulo="Nuevo", id="n1", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    assert [t["id"] for t in pc.temas_para_copy()] == ["n1"]


def test_qa_respeta_cap_de_lanzamientos(entorno, monkeypatch):
    """El cap por barrido de QA (`config.pipeline_qa_max()`) acota los lanzamientos de criba."""
    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")  # etapa QA activa para que el cap aplique a lanzamientos
    cliente = _cliente()  # noqa: F841 -- lanzador noop: deja la QA en `ejecutando` (en_curso)
    monkeypatch.setenv("KENI_PIPELINE_QA_MAX", "2")
    for i in range(4):
        _tema_pipeline(titulo=f"T{i}", id=f"tqa{i}")

    cribados = pc.ejecutar_qa(autor=None)
    assert len(cribados) == 2  # solo 2 cribas lanzadas; el resto en el próximo barrido.


def test_cd_respeta_cap_de_lanzamientos(entorno, monkeypatch):
    """El cap por barrido de CD (`config.pipeline_copy_max()`) acota los lanzamientos de copy."""
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")  # etapa CD activa para que el cap aplique
    llamadas = _mock_lanzar_copy(monkeypatch)
    monkeypatch.setenv("KENI_PIPELINE_COPY_MAX", "2")
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
# 1 toggle = 1 etapa: Noticias/QA/Copy independientes por marca                 #
# --------------------------------------------------------------------------- #


def test_solo_noticias_promueve_cluster_qa_saltada_cd_no(entorno, monkeypatch):
    """Solo «Crear noticias» ON: CI promueve la historia top, QA la marca 'saltada', CD no copia."""
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.delenv("KENI_PIPELINE_VALIDACION", raising=False)        # QA off -> etapa saltada
    monkeypatch.delenv("KENI_PIPELINE_COPY", raising=False)  # Copy off -> CD no corre
    monkeypatch.setenv("KENI_PIPELINE_MAX", "5")
    llamadas = _mock_lanzar_copy(monkeypatch)
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _sembrar_cluster("c1", titulo="Historia caliente", score=0.8)

    resumen = pc.ejecutar_barrido()

    # CI promovió el cluster a un tema del pipeline.
    assert len(resumen["temas"]) == 1
    assert any(t["titulo"] == "Historia caliente" for t in pc.temas_pipeline())
    # QA desactivada: el tema queda 'saltada' (no se lanza criba).
    assert all((t.get("qa_veredicto") or "") == pc.QA_SALTADA for t in pc.temas_pipeline())
    # CD desactivada: no se genera copy aunque haya tema listo.
    assert llamadas == []
    # El cluster quedó marcado usado (no se re-promueve).
    assert repos.obtener_noticia_cluster("c1")["estado"] == "usado"


def test_promover_clusters_top_n_por_score(entorno, monkeypatch):
    """`promover_clusters_marca` promueve las top-N historias por score y las marca usado."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _sembrar_cluster("baja", titulo="Score bajo", score=0.1)
    _sembrar_cluster("alta", titulo="Score alto", score=0.9)
    _sembrar_cluster("media", titulo="Score medio", score=0.5)

    temas = pc.promover_clusters_marca("unotv", maximo=2)

    # Solo las 2 de mayor score (alta, media); todas con origen pipeline y copy pendiente.
    assert {t["titulo"] for t in temas} == {"Score alto", "Score medio"}
    assert all(t["origen"] == pc.ORIGEN_PIPELINE for t in temas)
    assert all((t.get("copy_pendiente") or "").strip() for t in temas)
    assert repos.obtener_noticia_cluster("alta")["estado"] == "usado"
    assert repos.obtener_noticia_cluster("baja")["estado"] == "nuevo"  # no promovida


def test_crear_tema_de_cluster_dedup_no_repromueve(entorno, monkeypatch):
    """Una historia cuyo título ya está en el tablero reciente no crea un segundo tema."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    cluster = _sembrar_cluster("c1", titulo="Historia repetida", score=0.7)
    # Sembramos la clave del título como ya vista para forzar el dedup.
    from keni_consola.dominio import dedup as _dedup
    claves = {_dedup.clave("Historia repetida")}

    tema = pc.crear_tema_de_cluster(cluster, [], claves_vistas=claves)

    assert tema is None  # duplicado: no se crea
    assert repos.obtener_noticia_cluster("c1")["estado"] == "usado"  # pero se marca usado


# --------------------------------------------------------------------------- #
# Serial POR MARCA: el gate de CI no promueve más historias mientras la marca  #
# tenga cola EN VUELO (sin cribar / sin copy). Cada item entra y se completa.  #
# --------------------------------------------------------------------------- #


def test_crear_tema_de_cluster_copia_fuente_y_fecha_de_la_nota(entorno, monkeypatch):
    """La promoción CI→tema COPIA la procedencia de la nota original al `contenido`.

    `fuente_nombre` viene del item más reciente del cluster, y `fecha_fuente` prefiere su
    `publicado_en` (cuando el medio publicó la nota). Se copian porque el GC de noticias
    puede borrar el cluster y la pieza debe conservar fuente y fecha para la UI.
    """
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    cluster = _sembrar_cluster("cf1", titulo="Historia con medio", score=0.7)
    items = [{
        "titulo": "Historia con medio", "url": "https://record.com.mx/nota-1",
        "url_canonica": "record.com.mx/nota-1", "fuente_nombre": "Récord",
        "publicado_en": "2026-06-09T21:21:00+00:00", "imagen": "",
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    guardado = repos.obtener_contenido(tema["id"])
    assert (guardado.get("fuente_nombre") or "") == "Récord"
    assert (guardado.get("fecha_fuente") or "") == "2026-06-09T21:21:00+00:00"
    assert (guardado.get("url_fuente") or "") == "record.com.mx/nota-1"


def test_crear_tema_de_cluster_fecha_cae_a_primer_visto(entorno, monkeypatch):
    """Si el medio no traía fecha (`publicado_en` vacío), `fecha_fuente` cae al `primer_visto`
    del cluster (cuándo capturó la historia el Radar). Sin items, también."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    cluster = _sembrar_cluster("cf2", titulo="Historia sin fecha de medio", score=0.7)
    items = [{
        "titulo": "Historia sin fecha de medio", "url": "https://medio.test/n",
        "url_canonica": "medio.test/n", "fuente_nombre": "Medio", "publicado_en": "",
        "imagen": "",
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    guardado = repos.obtener_contenido(tema["id"])
    # `primer_visto` del cluster sembrado por `_sembrar_cluster`.
    assert (guardado.get("fecha_fuente") or "") == "2026-06-01T00:00:00+00:00"


def test_temas_en_vuelo_cuenta_pendientes_de_qa_o_copy(entorno):
    """`temas_en_vuelo` cuenta los temas sin terminar las fases de IA (QA pendiente o sin copy).

    En vuelo: veredicto ''/'en_curso' (QA pendiente) y 'no_verificado'/'saltada' SIN copy. NO en
    vuelo: 'problema' (terminal) ni 'no_verificado' que YA tiene copy en una pieza por plataforma.
    """
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Pendiente QA", qa_veredicto="", copy_pendiente=pend)          # +1
    _tema_pipeline(titulo="QA en curso", qa_veredicto=pc.QA_EN_CURSO, copy_pendiente=pend)  # +1
    _tema_pipeline(titulo="Apto sin copy", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente=pend)  # +1
    _tema_pipeline(titulo="Saltada sin copy", qa_veredicto=pc.QA_SALTADA, copy_pendiente=pend)  # +1
    _tema_pipeline(titulo="Problema", qa_veredicto=pc.VERDICTO_PROBLEMA, copy_pendiente=pend)  # terminal: 0
    con_copy = _tema_pipeline(titulo="Apto con copy", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente=pend)
    # Una pieza por plataforma CON copy -> ya pasó la etapa de copy: no cuenta como en vuelo.
    repos.crear_contenido_plataforma(contenido_id=con_copy["id"], red="x", copy="Copy listo")

    assert pc.temas_en_vuelo("unotv") == 4


def test_ci_serial_no_promueve_si_marca_llena(entorno, monkeypatch):
    """Gate SERIAL: si la marca ya tiene >= cupo en vuelo, CI no promueve clusters nuevos."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")  # ingesta_activa: CI corre
    monkeypatch.setenv("KENI_PIPELINE_EN_VUELO_MAX", "2")
    # 2 temas en vuelo (pendientes de QA) -> cupo 0 para unotv.
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="En vuelo 1", qa_veredicto="", copy_pendiente=pend)
    _tema_pipeline(titulo="En vuelo 2", qa_veredicto="", copy_pendiente=pend)
    _sembrar_cluster("hot", titulo="Historia caliente", score=0.9)

    res = pc._ejecutar_barrido()

    assert res["temas"] == []  # cupo agotado: no se promueve nada
    assert repos.obtener_noticia_cluster("hot")["estado"] == "nuevo"  # el cluster sigue disponible


def test_ci_serial_promueve_solo_hasta_el_cupo(entorno, monkeypatch):
    """Gate SERIAL: con cupo parcial, CI promueve como mucho `cupo` historias (no `pipeline_max`)."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "3")  # pipeline_max alto: el límite real es el cupo
    monkeypatch.setenv("KENI_PIPELINE_EN_VUELO_MAX", "3")
    # 2 en vuelo -> cupo 1: solo entra 1 historia aunque haya 3 clusters y pipeline_max=3.
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="En vuelo 1", qa_veredicto="", copy_pendiente=pend)
    _tema_pipeline(titulo="En vuelo 2", qa_veredicto="", copy_pendiente=pend)
    _sembrar_cluster("c1", titulo="Hist 1", score=0.9)
    _sembrar_cluster("c2", titulo="Hist 2", score=0.8)
    _sembrar_cluster("c3", titulo="Hist 3", score=0.7)

    res = pc._ejecutar_barrido()

    assert len(res["temas"]) == 1  # cupo=1, no min(3, pipeline_max)
    assert res["temas"][0]["titulo"] == "Hist 1"  # la de mayor score


def test_ejecutar_qa_salta_marca_desactivada(entorno, monkeypatch):
    """QA global ON pero apagada para la marca: ejecutar_qa marca el tema 'saltada' (no criba)."""
    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")
    monkeypatch.setattr(
        pc.config, "marca_apagada",
        lambda env, marca: env == config.ENV_PIPELINE_VALIDACION and marca == "unotv",
    )
    tema = _tema_pipeline(titulo="Marca sin QA")

    cribados = pc.ejecutar_qa(autor=None)

    assert repos.obtener_contenido(tema["id"])["qa_veredicto"] == pc.QA_SALTADA
    assert any(c["verdicto"] == pc.QA_SALTADA for c in cribados)


def test_temas_para_copy_incluye_qa_saltada(entorno):
    """Un tema con QA 'saltada' fluye a CD igual que 'no_verificado'; un 'problema' no."""
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Saltada ok", qa_veredicto=pc.QA_SALTADA, copy_pendiente=pend)
    _tema_pipeline(titulo="Problema", qa_veredicto=pc.VERDICTO_PROBLEMA, copy_pendiente=pend)

    titulos = {t["titulo"] for t in pc.temas_para_copy()}
    assert "Saltada ok" in titulos
    assert "Problema" not in titulos


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
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")  # etapa CD activa (sin el global, ejecutar_cd no corre)
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
    """La exclusión por marca de «Generar copy» (ENV_PIPELINE_COPY) también aplica al pool."""
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")  # etapa CD activa; la exclusión es por marca, no global
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
# Etapa de ARTE del pipeline (toggle "Generar arte", KENI_PIPELINE_ARTE)        #
# --------------------------------------------------------------------------- #


def test_ejecutar_arte_off_por_defecto_no_hace_nada(entorno, monkeypatch):
    """Sin `KENI_PIPELINE_ARTE`, la etapa de arte no ilustra (devuelve [])."""
    monkeypatch.delenv(config.ENV_PIPELINE_ARTE, raising=False)
    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    assert pc.ejecutar_arte() == []


def test_ejecutar_arte_gateado_corre_seleccion_y_lanzamiento(entorno, monkeypatch):
    """Con el toggle + máquina ON y proveedor configurado, ilustra vía autogen_arte."""
    from keni_consola import autogen_arte

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_ARTE, "1")
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
    monkeypatch.setenv(config.ENV_PIPELINE_ARTE, "1")
    monkeypatch.setattr(media, "proveedor_configurado", lambda: False)
    assert pc.ejecutar_arte() == []


# --------------------------------------------------------------------------- #
# Diversidad en la promoción (MMR suave) + estado protegido en el upsert       #
# --------------------------------------------------------------------------- #


def test_clusters_para_promover_diversifica_titulos_casi_identicos(entorno):
    """Un macro-tema (dos historias casi idénticas) no se come todas las plazas del barrido."""
    _sembrar_cluster("dup1", titulo="Messi gana el premio en París", score=0.9)
    _sembrar_cluster("dup2", titulo="Messi gana el premio en París hoy", score=0.8)
    _sembrar_cluster("otra", titulo="Sismo de magnitud en la capital", score=0.5)

    elegidos = pc.clusters_para_promover("unotv", maximo=2)

    assert [c["id"] for c in elegidos] == ["dup1", "otra"]  # el casi-duplicado cede su plaza


def test_clusters_para_promover_suave_rellena_si_solo_hay_duplicados(entorno):
    """Si todo el pool es el mismo macro-tema, se rellena igual (nunca devuelve menos)."""
    _sembrar_cluster("dup1", titulo="Messi gana el premio en París", score=0.9)
    _sembrar_cluster("dup2", titulo="Messi gana el premio en París hoy", score=0.8)
    elegidos = pc.clusters_para_promover("unotv", maximo=2)
    assert {c["id"] for c in elegidos} == {"dup1", "dup2"}


def test_upsert_cluster_no_revierte_estado_ni_contenido_id(entorno):
    """Anti-TOCTOU daemon↔pipeline: un recalc del daemon (upsert con datos stale) NO puede
    devolver a 'nuevo' una historia ya promovida ni borrar su enlace al tema."""
    _sembrar_cluster("c1", titulo="Historia promovida", score=0.7)
    repos.actualizar_noticia_cluster("c1", estado="usado", contenido_id="tema-77")

    # El daemon recalcula con una foto VIEJA (estado 'nuevo', sin contenido_id) y upsertea.
    stale = dict(repos.obtener_noticia_cluster("c1"), estado="nuevo", contenido_id="", score=0.9)
    repos.upsert_noticia_cluster(stale)

    tras = repos.obtener_noticia_cluster("c1")
    assert tras["estado"] == "usado"          # el estado promovido NO se revierte
    assert tras["contenido_id"] == "tema-77"  # el enlace al tema NO se pierde
    assert tras["score"] == 0.9               # los agregados sí se actualizan


# --------------------------------------------------------------------------- #
# Encadenado copy→arte por eventos + saneadores y helpers SQL del pipeline      #
# --------------------------------------------------------------------------- #


def test_encadenar_arte_tras_copy_ilustra_ese_tema(entorno, monkeypatch):
    """El post-procesado del copy dispara el ARTE de ESE tema al instante (gates ON)."""
    from keni_consola import autogen_arte, media

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_ARTE, "1")
    monkeypatch.setattr(media, "proveedor_configurado", lambda: True)
    monkeypatch.setattr(autogen_arte, "ids_ya_procesados", lambda: set())
    lanzados: list[str] = []
    monkeypatch.setattr(
        autogen_arte, "lanzar_para_topic",
        lambda it: lanzados.append(it["id"]) or {"contenido_id": it["id"]},
    )
    tema = repos.crear_contenido(
        clase="contenido", titulo="Ilustrable", marca="unotv", origen=pc.ORIGEN_PIPELINE,
    )

    res = pc.encadenar_arte_tras_copy(tema["id"])

    assert lanzados == [tema["id"]]
    assert res is not None


def test_encadenar_arte_tras_copy_respeta_gates(entorno, monkeypatch):
    """Con el toggle de arte OFF (o el tema ya ilustrado) el encadenado NO lanza nada."""
    from keni_consola import autogen_arte, media

    # Toggle OFF: ni siquiera consulta el tema.
    monkeypatch.delenv(config.ENV_PIPELINE_ARTE, raising=False)
    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    assert pc.encadenar_arte_tras_copy("cualquiera") is None

    # Toggle ON pero tema YA ilustrado (dedup por etiqueta): tampoco.
    monkeypatch.setenv(config.ENV_PIPELINE_ARTE, "1")
    monkeypatch.setattr(media, "proveedor_configurado", lambda: True)
    tema = repos.crear_contenido(
        clase="contenido", titulo="Ya ilustrado", marca="unotv", origen=pc.ORIGEN_PIPELINE,
    )
    monkeypatch.setattr(autogen_arte, "ids_ya_procesados", lambda: {tema["id"]})
    monkeypatch.setattr(
        autogen_arte, "lanzar_para_topic",
        lambda it: (_ for _ in ()).throw(AssertionError("no debe ilustrar un tema ya hecho")),
    )
    assert pc.encadenar_arte_tras_copy(tema["id"]) is None


def test_sanear_qa_en_curso_huerfanos_resetea_solo_viejos(entorno):
    """El saneador devuelve a re-criba ('') SOLO los `en_curso` más viejos que el umbral.

    Cierra el ZOMBI: si la criba muere sin finalizador, el tema quedaba `en_curso` para
    siempre (excluido de `temas_sin_qa` y contando en el cupo en vuelo de su marca).
    """
    from keni_consola import db

    zombi = _tema_pipeline(titulo="Zombi", qa_veredicto=pc.QA_EN_CURSO)
    vivo = _tema_pipeline(titulo="Vivo", qa_veredicto=pc.QA_EN_CURSO)
    # Envejecemos el `actualizado` del zombi más allá del umbral (el del vivo queda reciente).
    con = db._conectar()
    try:
        con.execute(
            "UPDATE contenido SET actualizado = ? WHERE id = ?",
            ("2020-01-01T00:00:00", zombi["id"]),
        )
        con.commit()
    finally:
        con.close()

    n = repos.sanear_qa_en_curso_huerfanos("2025-01-01T00:00:00")

    assert n == 1
    assert (repos.obtener_contenido(zombi["id"])["qa_veredicto"] or "") == ""  # a re-criba
    assert repos.obtener_contenido(vivo["id"])["qa_veredicto"] == pc.QA_EN_CURSO  # intacto


def test_ids_contenido_con_copy_filtra_por_marca(entorno):
    """`ids_contenido_con_copy` empuja el filtro a SQL: solo ids con pieza con copy redactado."""
    a = repos.crear_contenido(clase="contenido", titulo="A", marca="unotv")
    b = repos.crear_contenido(clase="contenido", titulo="B", marca="claro-sports")
    sin_copy = repos.crear_contenido(clase="contenido", titulo="C", marca="unotv")
    repos.crear_contenido_plataforma(contenido_id=a["id"], red="x", copy="hola")
    repos.crear_contenido_plataforma(contenido_id=b["id"], red="x", copy="hola")
    repos.crear_contenido_plataforma(contenido_id=sin_copy["id"], red="x", copy="")

    assert repos.ids_contenido_con_copy("unotv") == {a["id"]}
    assert {a["id"], b["id"]} <= repos.ids_contenido_con_copy()
    assert sin_copy["id"] not in repos.ids_contenido_con_copy()


def test_listar_contenido_origenes_filtra_en_sql(entorno):
    """`listar_contenido_origenes` trae solo los orígenes pedidos y excluye el estado dado."""
    rss = repos.crear_contenido(clase="contenido", titulo="R", marca="unotv", origen="rss")
    repos.crear_contenido(clase="contenido", titulo="M", marca="unotv", origen="")
    hecho = repos.crear_contenido(clase="contenido", titulo="H", marca="unotv", origen="rss")
    repos.actualizar_contenido(hecho["id"], {"estado": "hecha"})

    ids = {t["id"] for t in repos.listar_contenido_origenes(["rss"], excluir_estado="hecha")}
    assert ids == {rss["id"]}
    # Sin exclusión, el 'hecha' también sale; con lista vacía, nada (y sin query).
    assert hecho["id"] in {t["id"] for t in repos.listar_contenido_origenes(["rss"])}
    assert repos.listar_contenido_origenes([]) == []
