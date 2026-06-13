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


def _envejecer_intento(tema_id, campo):
    """Retrasa el timestamp del último intento de la etapa (saca el tema del backoff)."""
    pend = json.loads(repos.obtener_contenido(tema_id)["copy_pendiente"])
    pend[f"{campo}_ts"] = "2020-01-01T00:00:00"
    repos.actualizar_contenido(tema_id, {"copy_pendiente": json.dumps(pend)})


def _sembrar_cluster(
    cid, *, marca="unotv", titulo="Historia X", score=0.5, estado="nuevo",
    resumen="México: el gobierno informa de seguridad en la CDMX", ultimo_visto=None,
    verificacion="corroborada", n_fuentes=2, categoria="mx", breaking=0,
    qa_veredicto="",
):
    """Siembra un cluster del pool (Ola B) para los tests de promoción CI→tema.

    Por defecto el cluster SUPERA el listón de producción automática (`noticias_liston`):
    FRESCO (`ultimo_visto` ≈ ahora), corroborado y con encaje de marca unotv por el resumen.
    Los tests del propio listón pasan valores que lo incumplen a propósito.

    `qa_veredicto`: estado de la criba del cluster. Por defecto "" (sin cribar, el estado del que
    parte la QA de investigación). La ADMISIÓN solo promueve las VERIFICADAS, así que los tests
    que llaman DIRECTO a la promoción (sin pasar por la fase QA) deben sembrar el cluster ya
    verificado (`VERDICTO_NO_VERIFICADO`) — es el camino real, no el atajo sin filtro.
    """
    from datetime import UTC, datetime

    repos.upsert_noticia_cluster({
        "id": cid, "titulo": titulo, "resumen": resumen, "marca": marca,
        "categoria": categoria, "geo": "MX", "clave": f"t:{cid}", "n_items": 1,
        "n_fuentes": n_fuentes, "idiomas": ["es"], "senal": 100, "score": score,
        "breaking": breaking, "primer_visto": "2026-06-01T00:00:00+00:00",
        "ultimo_visto": ultimo_visto
        or datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
        "estado": estado, "verificacion": verificacion,
    })
    if qa_veredicto:
        repos.marcar_cluster_qa(cid, qa_veredicto)
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


# --------------------------------------------------------------------------- #
# Cuerpo del artículo + limpieza del snippet RSS (enriquecer la nota)          #
# --------------------------------------------------------------------------- #


def test_limpiar_snippet_decodifica_y_quita_boilerplate():
    # Caso REAL de UnoTV: entidad sin decodificar + cola de WordPress.
    crudo = (
        "Normalistas mantienen cerrada la autopista [&#8230;] "
        "The post Normalistas bloquean la caseta appeared first on UnoTV ."
    )
    limpio = pc._limpiar_snippet(crudo)
    assert "The post" not in limpio
    assert "appeared first on" not in limpio
    assert "&#8230;" not in limpio and "[…]" not in limpio
    assert limpio.startswith("Normalistas mantienen cerrada la autopista")


def test_limpiar_snippet_vacio():
    assert pc._limpiar_snippet("") == ""


def test_extraer_texto_articulo_jsonld():
    cuerpo = "Primer párrafo del cuerpo. " * 20  # supera _ART_MIN_TEXTO
    html = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "NewsArticle", "headline": "T", "articleBody": ' + json.dumps(cuerpo) + "}"
        "</script></head><body><p>ruido</p></body></html>"
    )
    texto = pc._extraer_texto_articulo(html)
    assert texto.startswith("Primer párrafo del cuerpo.")
    assert "ruido" not in texto


def test_extraer_texto_articulo_parrafos_fallback():
    parrafo = "Este es un párrafo de cuerpo con suficiente longitud para no ser cruft."
    html = (
        "<html><body><article>"
        "<p>corto</p>"  # < _ART_MIN_P_CHARS: se descarta
        f"<p>{parrafo}</p><p>{parrafo}</p><p>{parrafo}</p>"
        "</article></body></html>"
    )
    texto = pc._extraer_texto_articulo(html)
    assert parrafo in texto
    assert "corto" not in texto


def test_extraer_texto_articulo_sin_cuerpo_es_vacio():
    assert pc._extraer_texto_articulo("<html><body><p>x</p></body></html>") == ""
    assert pc._extraer_texto_articulo("") == ""


def test_nota_de_item_limpia_resumen_y_anexa_cuerpo():
    item = {
        "titulo": "Título",
        "resumen": "Resumen [&#8230;] The post Título appeared first on UnoTV .",
        "enlace": "https://ejemplo.test/n",
    }
    nota = pc._nota_de_item(item, "Cuerpo real del artículo.")
    assert "The post" not in nota
    assert "Artículo:\nCuerpo real del artículo." in nota
    assert "Fuente: https://ejemplo.test/n" in nota


def test_nota_de_cluster_incluye_texto_de_cada_fuente():
    # Antes la nota solo llevaba título + 1 resumen + URLs; ahora lleva el texto de CADA fuente.
    items = [
        {"fuente_nombre": "UnoTV", "titulo": "Bloqueo en caseta", "url": "https://uno.test/a",
         "resumen": "Normalistas cierran la autopista."},
        {"fuente_nombre": "Infobae", "titulo": "Refuerzan seguridad", "url": "https://info.test/b",
         "resumen": "Autoridades vigilan la zona."},
    ]
    cuerpos = {"https://uno.test/a": "Cuerpo UnoTV largo.", "https://info.test/b": "Cuerpo Infobae largo."}
    nota = pc._nota_de_cluster("Caseta bajo vigilancia", "Resumen del cluster", items, cuerpos)
    # Las dos fuentes aportan medio, resumen y cuerpo (no solo el link).
    assert "UnoTV" in nota and "Infobae" in nota
    assert "Cuerpo UnoTV largo." in nota and "Cuerpo Infobae largo." in nota
    assert "https://uno.test/a" in nota and "https://info.test/b" in nota
    assert "sintetiza y cruza" in nota


def test_nota_de_cluster_sin_cuerpos_cae_a_resumenes():
    items = [{"fuente_nombre": "UnoTV", "titulo": "T", "url": "https://uno.test/a", "resumen": "Resumen A"}]
    nota = pc._nota_de_cluster("Título", "Resumen", items, None)
    assert "Resumen A" in nota and "https://uno.test/a" in nota


def test_fetch_cuerpo_gateado_off_no_toca_la_red(monkeypatch):
    # Sin el flag, NO se llama al seam de red y devuelve "" (comportamiento previo).
    monkeypatch.delenv("KENI_PIPELINE_FETCH_FUENTE", raising=False)
    llamado = {"n": 0}

    def _boom(enlace):
        llamado["n"] += 1
        return "no debería"

    monkeypatch.setattr(pc, "_FETCH_ARTICULO", _boom)
    assert pc._fetch_cuerpo("https://ejemplo.test/n") == ""
    assert llamado["n"] == 0


def test_fetch_cuerpo_gateado_on_usa_el_seam(monkeypatch):
    monkeypatch.setenv("KENI_PIPELINE_FETCH_FUENTE", "1")
    monkeypatch.setattr(pc, "_FETCH_ARTICULO", lambda enlace: "  Cuerpo del artículo.  ")
    assert pc._fetch_cuerpo("https://ejemplo.test/n") == "Cuerpo del artículo."
    # Enlace vacío: ni se intenta.
    assert pc._fetch_cuerpo("") == ""


def test_en_backoff_puro_segun_intentos_y_timestamp():
    """`en_backoff` (PURO sobre el dict): espera tras un intento RECIENTE; sin ts/intentos no."""
    from keni_consola.tiempo import ahora_iso

    reciente = json.dumps({"qa_intentos": 1, "qa_intentos_ts": ahora_iso()})
    assert pc.en_backoff({"id": "t", "copy_pendiente": reciente}, "qa_intentos") is True
    viejo = json.dumps({"qa_intentos": 1, "qa_intentos_ts": "2020-01-01T00:00:00"})
    assert pc.en_backoff({"id": "t", "copy_pendiente": viejo}, "qa_intentos") is False
    # Temas previos al backoff (intentos sin timestamp) y temas sin intentos: sin espera.
    legacy = json.dumps({"qa_intentos": 2})
    assert pc.en_backoff({"id": "t", "copy_pendiente": legacy}, "qa_intentos") is False
    assert pc.en_backoff({"id": "t", "copy_pendiente": ""}, "qa_intentos") is False


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
    # Un item RSS suelto NO es un panel: una sola nota y sin catálogo de fotos por nota.
    assert pend["n_notas"] == 1
    assert pend["fotos_notas"] == []


def test_fotos_notas_de_cluster_solo_propias_con_su_titulo(entorno, monkeypatch):
    """`_fotos_notas_de_cluster`: foto propia POR NOTA (con su título), sin duplicar; ajenas fuera."""
    from keni_consola.pipeline_contenido import _ingesta

    propia = repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    ajena = repos.crear_fuente_rss("Tercero", "https://otro.test/feed.xml", marca="unotv")
    items = [
        {"fuente_id": propia["id"], "titulo": "Concierto A", "imagen": "https://casa.test/a.jpg", "url": "https://casa.test/1"},
        {"fuente_id": ajena["id"], "titulo": "Robada", "imagen": "https://otro.test/robada.jpg", "url": "https://otro.test/1"},
        {"fuente_id": propia["id"], "titulo": "Concierto A bis", "imagen": "https://casa.test/a.jpg", "url": "https://casa.test/1b"},
        {"fuente_id": propia["id"], "titulo": "Concierto B", "imagen": "https://casa.test/b.jpg", "url": "https://casa.test/2"},
        {"fuente_id": propia["id"], "titulo": "Sin foto", "imagen": "", "url": "https://casa.test/3"},
    ]
    assert _ingesta._fotos_notas_de_cluster(items) == [
        {"titulo": "Concierto A", "imagen": "https://casa.test/a.jpg"},
        {"titulo": "Concierto B", "imagen": "https://casa.test/b.jpg"},
    ]
    # La PORTADA del tema es la primera foto propia.
    assert _ingesta._imagen_de_cluster(items) == "https://casa.test/a.jpg"


def test_imagen_de_cluster_og_image_solo_como_rescate(entorno, monkeypatch):
    """Sin foto en NINGÚN item propia, la portada se resuelve por og:image (un solo fetch)."""
    from keni_consola.pipeline_contenido import _ingesta

    propia = repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    _mock_og_image(monkeypatch, "https://casa.test/og.jpg")
    items = [
        {"fuente_id": propia["id"], "imagen": "", "url": "https://casa.test/1"},
        {"fuente_id": propia["id"], "imagen": "", "url": "https://casa.test/2"},
    ]
    assert _ingesta._imagen_de_cluster(items) == "https://casa.test/og.jpg"
    # Sin fuentes propias, "" (no se toca la red ni se usa la foto de un tercero).
    ajena = repos.crear_fuente_rss("Tercero", "https://otro.test/feed.xml", marca="unotv")
    assert _ingesta._imagen_de_cluster(
        [{"fuente_id": ajena["id"], "imagen": "https://otro.test/x.jpg", "url": "https://otro.test/1"}]
    ) == ""


def test_cd_pasa_fotos_notas_y_n_notas_al_copy(entorno, monkeypatch):
    """CD: `fotos_notas`/`n_notas` del copy_pendiente viajan a `lanzar_copy` (habilitan el carrusel)."""
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    fotos = [
        {"titulo": "Concierto A", "imagen": "https://casa.test/a.jpg"},
        {"titulo": "Concierto B", "imagen": "https://casa.test/b.jpg"},
    ]
    tema = _tema_pipeline(
        titulo="Panel de conciertos",
        qa_veredicto=pc.VERDICTO_NO_VERIFICADO,
        copy_pendiente=json.dumps({
            "nota": "Nota", "redes_ids": ["x", "instagram", "facebook"],
            "imagen": "https://casa.test/a.jpg",
            "fotos_notas": fotos, "n_notas": 4,
            "tipo_contenido": "fuente",
        }),
    )
    pc.lanzar_copy_de_tema(repos.obtener_contenido(tema["id"]), autor=None)
    assert len(llamadas) == 1
    assert llamadas[0]["imagen_fuente"] == "https://casa.test/a.jpg"
    assert llamadas[0]["fotos_notas"] == fotos
    assert llamadas[0]["n_notas"] == 4


def test_cd_pendiente_viejo_sin_panel_no_ofrece_carrusel(entorno, monkeypatch):
    """Compat: un copy_pendiente anterior al carrusel sigue funcionando (n_notas=1, sin fotos)."""
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(
        titulo="Pendiente legado",
        qa_veredicto=pc.VERDICTO_NO_VERIFICADO,
        copy_pendiente=json.dumps({
            "nota": "Nota", "redes_ids": ["x"], "imagen": "https://casa.test/a.jpg",
        }),
    )
    pc.lanzar_copy_de_tema(repos.obtener_contenido(tema["id"]), autor=None)
    assert llamadas[0]["fotos_notas"] == []
    assert llamadas[0]["n_notas"] == 1


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

    # QA de la fuente (síncrona en test) -> el procesar persiste el veredicto en el tema. El
    # camino tema-QA es el manual/legado (`lanzar_qa_fuente`); el barrido criba CLUSTERS, no temas.
    pc.lanzar_qa_fuente(tema, autor=None)
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

    pc.lanzar_qa_fuente(tema, autor=None)
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

    pc.lanzar_qa_fuente(tema, autor=None)

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

    pc.lanzar_qa_fuente(tema, autor=None)  # no debe reventar

    # El veredicto SÍ quedó persistido y el tema sigue elegible para el barrido de CD.
    assert repos.obtener_contenido(tema["id"])["qa_veredicto"] == pc.VERDICTO_NO_VERIFICADO
    assert [t["id"] for t in pc.temas_para_copy()] == [tema["id"]]


def test_qa_cluster_problema_no_se_admite(entorno, monkeypatch):
    """ADR 0011 F3: la QA corre sobre la HISTORIA; una `problema` NO se materializa como contenido."""
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "5")
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_QA_PROBLEMA))  # noqa: F841
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _sembrar_cluster("c-malo", titulo="Historia dudosa", score=0.8)

    # Un tick de investigación: QA (síncrona en test) marca el cluster, la admisión decide.
    res = pc._ejecutar_investigacion()

    assert repos.obtener_noticia_cluster("c-malo")["qa_veredicto"] == pc.VERDICTO_PROBLEMA
    assert res["temas"] == []  # 'problema' NO cruza a producción
    assert pc.temas_pipeline() == []
    # La historia sigue en el pool (visible con su veredicto), sin promover.
    assert repos.obtener_noticia_cluster("c-malo")["estado"] == "nuevo"


def test_qa_cluster_ok_se_admite_heredando_veredicto(entorno, monkeypatch):
    """ADR 0011 F3: una historia que pasa la QA se admite y el TEMA HEREDA el veredicto del cluster."""
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "5")
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_QA_OK))  # noqa: F841
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _sembrar_cluster("c-ok", titulo="Historia verificada", score=0.8)

    res = pc._ejecutar_investigacion()

    assert repos.obtener_noticia_cluster("c-ok")["qa_veredicto"] == pc.VERDICTO_NO_VERIFICADO
    assert len(res["temas"]) == 1
    tema = res["temas"][0]
    # El contenido nace VERIFICADO (frontera "QA = investigación" alineada en los datos).
    assert repos.obtener_contenido(tema["id"])["qa_veredicto"] == pc.VERDICTO_NO_VERIFICADO
    assert repos.obtener_noticia_cluster("c-ok")["estado"] == "usado"


def test_qa_cluster_acotada_por_el_embudo(entorno, monkeypatch):
    """ADR 0011 F3: la criba se acota al EMBUDO (tope en vuelo) — no recorre todo el pool por tick."""
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")
    monkeypatch.setenv("KENI_PIPELINE_EN_VUELO_MAX", "1")  # embudo de 1
    cliente = _cliente(lanzar_generacion=lanzador_generacion_completa(_QA_OK))  # noqa: F841
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    for i in range(3):
        _sembrar_cluster(f"c{i}", titulo=f"Historia {i}", score=0.9 - i * 0.1)

    cribados = pc.ejecutar_qa_clusters(autor=None)

    # Con tope en vuelo = 1, solo se criba 1 historia en este tick (la mejor del ranking).
    assert len(cribados) == 1
    assert cribados[0]["id"] == "c0"


def test_copy_fallido_se_reintenta_tras_el_backoff(entorno, monkeypatch):
    """DEDUP AL ÉXITO + BACKOFF: un copy fallido se RELANZA, pero solo PASADA la espera creciente.

    Antes `copy_pendiente` se limpiaba al ENCOLAR y un copy fallido jamás se reintentaba (el
    tema quedaba huérfano para siempre). El doble lanzamiento mientras el job está EN VUELO
    lo evita la clave de idempotencia de `dominio.generar.lanzar` (no este filtro). Con el tick
    corto, el reintento INMEDIATO quemaba los 3 intentos en <1 min: ahora el barrido SALTA el
    tema mientras dura el backoff del intento (`_BACKOFF_ETAPA_SEG`).
    """
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(titulo="Reintento", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)

    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 1
    # El lanzamiento NO limpió `copy_pendiente` (lo limpia el post-procesado al ÉXITO).
    assert (repos.obtener_contenido(tema["id"])["copy_pendiente"] or "").strip()

    # El copy "falló" (no nació pieza), pero el tick INMEDIATO no relanza: backoff en curso.
    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 1

    # Pasada la espera (timestamp envejecido), el barrido sí lo reintenta.
    _envejecer_intento(tema["id"], "cd_intentos")
    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 2

    # Éxito (pieza creada): deja de relanzarse.
    repos.crear_contenido_plataforma(contenido_id=tema["id"], red="x", copy="Listo")
    _envejecer_intento(tema["id"], "cd_intentos")
    pc.ejecutar_cd(autor=None)
    assert len(llamadas) == 2


def test_qa_no_relanza_tema_ya_cribado(entorno, monkeypatch):
    """Un tema con veredicto ya no se re-criba (idempotente)."""
    _tema_pipeline(titulo="Ya cribado", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    assert pc.temas_sin_qa() == []


def test_temas_sin_qa_devuelve_todos_los_pendientes(entorno):
    """FLUJO CONTINUO: sin recorte por etapa; los pendientes entran TODOS (los cribados no).

    El volumen lo acota la ADMISIÓN (gate serial en vuelo por marca), no una ventana de revisión:
    aquí solo puede haber, como mucho, lo admitido.
    """
    _tema_pipeline(titulo="Viejo 1", id="v1", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _tema_pipeline(titulo="Viejo 2", id="v2", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _tema_pipeline(titulo="Nuevo A", id="n1")  # sin veredicto -> pendiente
    _tema_pipeline(titulo="Nuevo B", id="n2")
    assert {t["id"] for t in pc.temas_sin_qa()} == {"n1", "n2"}


def test_temas_para_copy_devuelve_todos_los_listos(entorno):
    """FLUJO CONTINUO: CD ve TODOS los temas listos (cribados+pendiente de copy), sin ventana."""
    # Viejos no_verificado pero YA copiados (copy_pendiente vacío -> no pasan el filtro de CD).
    _tema_pipeline(titulo="Viejo 1", id="v1", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente="")
    _tema_pipeline(titulo="Viejo 2", id="v2", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente="")
    _tema_pipeline(titulo="Nuevo A", id="n1", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _tema_pipeline(titulo="Nuevo B", id="n2", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    assert {t["id"] for t in pc.temas_para_copy()} == {"n1", "n2"}


def test_cd_sin_tope_lanza_todos_los_listos(entorno, monkeypatch):
    """FLUJO CONTINUO: la fase CD redacta TODOS los temas listos en un tick (sin cap por etapa)."""
    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    import json

    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    for i in range(4):
        _tema_pipeline(
            titulo=f"C{i}", id=f"tcd{i}",
            qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente=pend,
        )

    lanzados = pc.ejecutar_cd(autor=None)
    assert len(lanzados) == 4
    assert len(llamadas) == 4


def test_cd_reintentos_agotados_marca_problema_sin_lanzar(entorno, monkeypatch):
    """REINTENTOS ACOTADOS en CD: un copy que ya agotó sus intentos sale TERMINAL (problema)."""
    import json

    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    pend = json.dumps({"nota": "n", "redes_ids": ["x"], "cd_intentos": pc._MAX_INTENTOS_ETAPA})
    tema = _tema_pipeline(titulo="Copy agotado", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente=pend)

    lanzados = pc.ejecutar_cd(autor=None)

    assert lanzados == [] and llamadas == []
    refrescado = repos.obtener_contenido(tema["id"])
    assert refrescado["qa_veredicto"] == pc.VERDICTO_PROBLEMA
    assert "falló" in (refrescado["qa_hallazgos"] or "")
    assert pc.temas_en_vuelo("unotv") == 0  # terminal: libera la admisión de su marca


def test_cd_reintento_anota_intentos_acumulados(entorno, monkeypatch):
    """Cada relanzamiento de copy suma su intento (el tope corta el bucle de reintentos)."""
    import json

    monkeypatch.setenv("KENI_PIPELINE_COPY", "1")
    llamadas = _mock_lanzar_copy(monkeypatch)
    tema = _tema_pipeline(titulo="Suma intentos", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)

    pc.ejecutar_cd(autor=None)  # 1er intento (el copy mockeado "falla": no nace pieza)
    _envejecer_intento(tema["id"], "cd_intentos")  # fuera del backoff: el barrido reintenta
    pc.ejecutar_cd(autor=None)  # 2º intento

    assert len(llamadas) == 2
    pend = json.loads(repos.obtener_contenido(tema["id"])["copy_pendiente"])
    assert pend["cd_intentos"] == 2


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


def test_dos_loops_investigacion_y_produccion_separan_fases(entorno, monkeypatch):
    """ADR 0011 F3: `ejecutar_investigacion` cubre CI+QA y `ejecutar_produccion` CD+arte+avance.

    El barrido combinado (`_ejecutar_barrido`) es la unión exacta de ambos, así el disparo a
    demanda y los tests siguen viendo el resumen completo aunque en producción cada proceso
    corra en su propio hilo/lock/cadencia.
    """
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.delenv("KENI_PIPELINE_VALIDACION", raising=False)  # QA saltada
    monkeypatch.delenv("KENI_PIPELINE_COPY", raising=False)  # Copy off
    monkeypatch.setenv("KENI_PIPELINE_MAX", "5")
    _mock_lanzar_copy(monkeypatch)
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _sembrar_cluster("c1", titulo="Historia caliente", score=0.8)

    # INVESTIGACIÓN: admite (CI) + criba (QA). Solo expone {temas, cribados}.
    inv = pc._ejecutar_investigacion()
    assert set(inv) == {"temas", "cribados"}
    assert len(inv["temas"]) == 1
    assert any(t["titulo"] == "Historia caliente" for t in pc.temas_pipeline())

    # PRODUCCIÓN: copy + arte + avance. Solo expone {lanzados, artes, avances}.
    prod = pc._ejecutar_produccion()
    assert set(prod) == {"lanzados", "artes", "avances"}

    # El combinado es la unión de las claves de ambos procesos.
    combinado = pc._ejecutar_barrido()
    assert set(combinado) == {"temas", "cribados", "lanzados", "artes", "avances"}


def test_promover_clusters_top_n_por_score(entorno, monkeypatch):
    """`promover_clusters_marca` promueve las top-N historias por score y las marca usado."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    # Verificadas (estado real tras la QA): la admisión SIEMPRE criba — solo promueve verificadas.
    _sembrar_cluster("baja", titulo="Score bajo", score=0.1, qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _sembrar_cluster("alta", titulo="Score alto", score=0.9, qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _sembrar_cluster("media", titulo="Score medio", score=0.5, qa_veredicto=pc.VERDICTO_NO_VERIFICADO)

    temas = pc.promover_clusters_marca("unotv", maximo=2)

    # Solo las 2 de mayor score (alta, media); todas con origen pipeline y copy pendiente.
    assert {t["titulo"] for t in temas} == {"Score alto", "Score medio"}
    assert all(t["origen"] == pc.ORIGEN_PIPELINE for t in temas)
    assert all((t.get("copy_pendiente") or "").strip() for t in temas)
    assert repos.obtener_noticia_cluster("alta")["estado"] == "usado"
    assert repos.obtener_noticia_cluster("baja")["estado"] == "nuevo"  # no promovida


def test_promover_clusters_marca_filtra_sin_cribar_por_defecto(entorno, monkeypatch):
    """El filtro de QA es OBLIGATORIO por defecto (ADR 0011 F3): un cluster SIN cribar (veredicto
    '') NO se promueve aunque gane en score/listón — no existe un camino que promueva sin verificar.
    """
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _sembrar_cluster("sin_cribar", titulo="Aún sin QA", score=0.9)  # qa_veredicto='' por defecto
    _sembrar_cluster("verificada", titulo="Ya verificada", score=0.5,
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)

    temas = pc.promover_clusters_marca("unotv", maximo=5)  # SIN qa_estados: cae al filtro por defecto

    assert {t["titulo"] for t in temas} == {"Ya verificada"}  # la sin cribar NO cruza
    assert repos.obtener_noticia_cluster("sin_cribar")["estado"] == "nuevo"  # se queda en el pool


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


def test_crear_tema_de_cluster_resuelve_og_image_de_fuente_propia(entorno, monkeypatch):
    """Cluster con item de fuente PROPIA sin foto en el feed: se RESUELVE la og:image del artículo.

    Así la pieza nace con arte (`copy_pendiente.imagen` + `tipo_contenido='fuente'`) en vez de
    "Falta imagen". La og:image solo se resuelve para fuentes propias (derechos)."""
    import json

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    fuente = repos.crear_fuente_rss("Casa", _URL_OK, marca="unotv", propia=True)
    _mock_og_image(monkeypatch, "https://casa.test/foto-nota.jpg")
    cluster = _sembrar_cluster("cp1", titulo="Historia propia", score=0.7)
    items = [{
        "titulo": "Historia propia", "url": "https://unotv.test/nota", "url_canonica": "unotv.test/nota",
        "fuente_id": fuente["id"], "fuente_nombre": "UnoTV", "publicado_en": "", "imagen": "",
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    pend = json.loads(repos.obtener_contenido(tema["id"])["copy_pendiente"])
    assert pend["imagen"] == "https://casa.test/foto-nota.jpg"
    assert pend["tipo_contenido"] == "fuente"


def test_crear_tema_de_cluster_no_resuelve_og_image_de_fuente_ajena(entorno, monkeypatch):
    """Fuente NO propia (medio ajeno): no resolvemos su og:image (sin derechos). Sin foto en el
    feed, el tema nace sin imagen aunque la resolución estuviera disponible."""
    import json

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    fuente = repos.crear_fuente_rss("Ajeno", _URL_OK, marca="unotv", propia=False)
    # Si llegara a resolverse, sería esta URL; el test verifica que NO se usa.
    _mock_og_image(monkeypatch, "https://ajeno.test/foto.jpg")
    cluster = _sembrar_cluster("ca1", titulo="Historia ajena", score=0.7)
    items = [{
        "titulo": "Historia ajena", "url": "https://medio.test/nota", "url_canonica": "medio.test/nota",
        "fuente_id": fuente["id"], "fuente_nombre": "Medio", "publicado_en": "", "imagen": "",
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    pend = json.loads(repos.obtener_contenido(tema["id"])["copy_pendiente"])
    assert pend["imagen"] == ""
    assert pend["tipo_contenido"] == ""


def test_crear_tema_de_cluster_no_usa_imagen_de_feed_ajeno(entorno, monkeypatch):
    """Item de fuente AJENA con foto en el feed (media-tag): NO se usa (sin derechos).

    Antes había un fallback a "cualquier imagen ya capturada en los items": colaba fotos de
    medios ajenos en las piezas (y encendía la etapa Arte sin arte). Solo fuentes PROPIAS
    aportan imagen; sin ellas, el tema nace sin foto y el arte lo decide la etapa de Arte IA."""
    import json

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    fuente = repos.crear_fuente_rss("Ajeno2", _URL_OK, marca="unotv", propia=False)
    cluster = _sembrar_cluster("ca2", titulo="Historia ajena con foto", score=0.7)
    items = [{
        "titulo": "Historia ajena con foto", "url": "https://medio.test/nota2",
        "url_canonica": "medio.test/nota2", "fuente_id": fuente["id"],
        "fuente_nombre": "Medio", "publicado_en": "",
        "imagen": "https://medio.test/foto-ajena.jpg",  # media-tag del feed ajeno
    }]

    tema = pc.crear_tema_de_cluster(cluster, items, claves_vistas=set())

    assert tema is not None
    pend = json.loads(repos.obtener_contenido(tema["id"])["copy_pendiente"])
    assert pend["imagen"] == ""
    assert pend["tipo_contenido"] == ""


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


# --------------------------------------------------------------------------- #
# FRESCURA: caducidad TTL de temas en vuelo (ventana deslizante)               #
# --------------------------------------------------------------------------- #


def test_caducidad_libera_el_gate_y_excluye_de_las_fases(entorno):
    """Un tema EN VUELO que supera el TTL caduca: sale del gate serial (libera hueco para lo
    fresco del ranking) y NINGUNA fase lo retoma (ni QA lo criba ni CD le genera copy)."""
    from datetime import datetime, timedelta, timezone

    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Atascado", qa_veredicto="", copy_pendiente=pend)
    _tema_pipeline(titulo="Apto viejo", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente=pend)
    assert pc.temas_en_vuelo("unotv") == 2

    futuro = datetime.now(timezone.utc) + timedelta(hours=25)  # > TTL (def 24 h)
    assert pc.caducar_temas_viejos(ahora=futuro) == 2

    # Liberan el gate, no se re-criban ni generan copy, y quedan marcados con el motivo.
    assert pc.temas_en_vuelo("unotv") == 0
    assert pc.temas_sin_qa() == []
    assert pc.temas_para_copy() == []
    temas = {t["titulo"]: t for t in pc.temas_pipeline()}
    assert temas["Atascado"]["qa_veredicto"] == pc.QA_CADUCADA
    assert "Caducada" in (temas["Atascado"].get("notas") or "")


def test_caducidad_respeta_lo_fresco_y_lo_terminal(entorno):
    """La caducidad NO toca lo fresco (dentro del TTL) ni lo que ya salió del vuelo
    ('problema' terminal, o apto CON copy ya generado)."""
    from datetime import datetime, timedelta, timezone

    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Fresco", qa_veredicto="", copy_pendiente=pend)
    _tema_pipeline(titulo="Problema viejo", qa_veredicto=pc.VERDICTO_PROBLEMA, copy_pendiente=pend)
    con_copy = _tema_pipeline(
        titulo="Con copy", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente=pend
    )
    repos.crear_contenido_plataforma(contenido_id=con_copy["id"], red="x", copy="Copy listo")

    # Dentro del TTL: nada caduca (lo en vuelo sigue siendo fresco).
    pronto = datetime.now(timezone.utc) + timedelta(hours=1)
    assert pc.caducar_temas_viejos(ahora=pronto) == 0
    # Pasado el TTL: solo caduca el EN VUELO; terminal y con-copy intactos.
    futuro = datetime.now(timezone.utc) + timedelta(hours=25)
    assert pc.caducar_temas_viejos(ahora=futuro) == 1
    temas = {t["titulo"]: t for t in pc.temas_pipeline()}
    assert temas["Problema viejo"]["qa_veredicto"] == pc.VERDICTO_PROBLEMA
    assert temas["Con copy"]["qa_veredicto"] == pc.VERDICTO_NO_VERIFICADO


def test_caducado_libera_hueco_para_lo_fresco_del_ranking(entorno, monkeypatch):
    """Tras caducar el backlog, la admisión vuelve a tener cupo: entra lo fresco del ranking
    (la historia top de HOY), no lo que quedó atascado ayer (sin colas intermedias)."""
    from datetime import datetime, timedelta, timezone

    from keni_consola.pipeline_contenido import _ingesta

    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.setenv("KENI_PIPELINE_EN_VUELO_MAX", "1")
    monkeypatch.delenv("KENI_PIPELINE_VALIDACION", raising=False)
    monkeypatch.delenv("KENI_PIPELINE_COPY", raising=False)
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    _tema_pipeline(titulo="Backlog vencido", qa_veredicto="", copy_pendiente=pend)
    _sembrar_cluster("hot", titulo="Lo fresco de hoy", score=0.9)
    # Con el backlog en vuelo, el cupo (1) está agotado: no entra nada.
    assert pc._ejecutar_barrido()["temas"] == []
    # Caduca el backlog (reloj adelantado > TTL) y el siguiente tick admite lo fresco.
    assert _ingesta.caducar_temas_viejos(
        ahora=datetime.now(timezone.utc) + timedelta(hours=25)
    ) == 1
    res = pc._ejecutar_barrido()
    assert [t["titulo"] for t in res["temas"]] == ["Lo fresco de hoy"]


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


# --------------------------------------------------------------------------- #
# Volumen: PLAN EDITORIAL DIARIO (cupos por categoría, lo mejor de cada tipo) o,    #
# sin plan, cupo diario simple (24 h móviles).                                       #
# --------------------------------------------------------------------------- #


def test_cupo_dia_corta_la_admision(entorno, monkeypatch):
    """Sin plan, con el cupo DIARIO (24 h móviles) agotado, CI no admite más."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.setenv("KENI_CUPO_DIA", "1")
    pend = json.dumps({"nota": "n", "redes_ids": ["x"]})
    t = _tema_pipeline(
        titulo="Producido hoy", qa_veredicto=pc.VERDICTO_NO_VERIFICADO, copy_pendiente=pend
    )
    repos.crear_contenido_plataforma(contenido_id=t["id"], red="x", copy="Copy listo")
    _sembrar_cluster("hot", titulo="Historia caliente", score=0.9)

    res = pc._ejecutar_barrido()

    assert res["temas"] == []
    assert repos.obtener_noticia_cluster("hot")["estado"] == "nuevo"


def test_plan_llena_cupos_por_categoria_con_lo_mejor(entorno, monkeypatch):
    """Con plan, cada categoría se lleva SUS mejores historias y las demás no compiten."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "10")
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:1,internacional:1")
    _sembrar_cluster("mx1", titulo="Nacional floja", score=0.5, categoria="mx")
    _sembrar_cluster("mx2", titulo="Nacional top", score=0.9, categoria="mx")
    _sembrar_cluster(
        "int1", titulo="Internacional unica historia", score=0.4, categoria="internacional",
        resumen="México observa la cumbre internacional",
    )
    _sembrar_cluster("dep1", titulo="Deportiva fuera de plan", score=0.95, categoria="deportes")

    res = pc._ejecutar_barrido()

    titulos = {t["titulo"] for t in res["temas"]}
    # La mejor de mx + la única de internacional; la deportiva (sin cupo en el plan) NO entra.
    assert titulos == {"Nacional top", "Internacional unica historia"}
    assert repos.obtener_noticia_cluster("dep1")["estado"] == "nuevo"
    assert repos.obtener_noticia_cluster("mx1")["estado"] == "nuevo"


def test_plan_breaking_consume_slot_breaking(entorno, monkeypatch):
    """Una historia BREAKING compite por el cupo 'breaking', no por el de su categoría."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.setenv("KENI_PIPELINE_MAX", "10")
    monkeypatch.setenv("KENI_PLAN_DIA", "breaking:1")
    _sembrar_cluster("br1", titulo="Ultima hora corroborada", score=0.8, categoria="mx", breaking=1)
    _sembrar_cluster("mx9", titulo="Nacional normal", score=0.9, categoria="mx")

    res = pc._ejecutar_barrido()

    assert [t["titulo"] for t in res["temas"]] == ["Ultima hora corroborada"]


def test_plan_descuenta_lo_ya_generado_hoy(entorno, monkeypatch):
    """El cupo de una categoría descuenta lo GENERADO en 24 h (contenido.categoria persistida)."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    monkeypatch.setenv("KENI_PIPELINE_SELECCION", "1")
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:1")
    # Generado previo de la línea mx (la categoría vive EN el contenido, no en el cluster),
    # CON post real (es_publicacion=1): un tema sin post no consumiría cupo (no cuenta).
    ya = repos.crear_contenido(
        clase="contenido", titulo="Ya generada", marca="unotv", categoria="mx"
    )
    repos.crear_contenido_plataforma(
        contenido_id=ya["id"], red="facebook", marca="unotv", copy="P", es_publicacion=True
    )
    _sembrar_cluster("hoy", titulo="Nacional nueva", score=0.9, categoria="mx")

    res = pc._ejecutar_barrido()

    assert res["temas"] == []  # cupo mx (1) ya consumido por el generado previo
    assert repos.obtener_noticia_cluster("hoy")["estado"] == "nuevo"


def test_promocion_persiste_categoria_en_el_contenido(entorno, monkeypatch):
    """Al promover, la LÍNEA queda en `contenido.categoria` ('breaking' si lo era)."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    # El plan declara la línea 'breaking' para que la última hora consuma SU cupo (y no el
    # de su categoría de feed): así la breaking sale a la vez que la nacional. Sin línea
    # 'breaking' en el plan, una última hora competiría por el cupo 'mx' (ver
    # test_plan_sin_linea_breaking_compite_por_su_feed) y desplazaría a la nacional.
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:1,breaking:1")
    _sembrar_cluster("cat1", titulo="Nacional persistida", score=0.9, categoria="mx",
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _sembrar_cluster("cat2", titulo="Urgente persistida", score=0.9, categoria="mx", breaking=1,
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)

    temas = pc.promover_clusters_marca(
        "unotv", maximo=2, cupos_categoria={"mx": 1, "breaking": 1}
    )

    por_titulo = {t["titulo"]: t for t in temas}
    assert por_titulo["Nacional persistida"]["categoria"] == "mx"
    assert por_titulo["Urgente persistida"]["categoria"] == "breaking"


def test_plan_por_marca_gana_al_global(entorno, monkeypatch):
    """`KENI_PLAN_DIA::marca` (store) SUSTITUYE al plan global para esa marca."""
    overrides = {"KENI_PLAN_DIA::unotv": "internacional:2"}
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda clave: overrides.get(clave))
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:4")
    assert config.plan_dia("unotv") == {"internacional": 2}
    assert config.plan_dia("claro-sports") == {"mx": 4}
    assert config.parsear_plan("mx:4, breaking:2, malformado, x:abc, vacio:0") == {
        "mx": 4, "breaking": 2,
    }


def test_cupo_produccion_restante_none_sin_cupos(entorno, monkeypatch):
    """Cupo diario a 0 -> None (la admisión queda solo con el gate serial)."""
    monkeypatch.setenv("KENI_CUPO_DIA", "0")
    from keni_consola.pipeline_contenido import _ingesta

    assert _ingesta.cupo_produccion_restante("unotv") is None
    assert _ingesta.cupos_categoria_restantes("unotv") is None  # sin plan


def test_plan_breaking_excede_su_cupo_con_tope_extra(entorno, monkeypatch):
    """La última hora EXCEDE el plan: techo efectivo = cupo + KENI_BREAKING_EXTRA_DIA."""
    from keni_consola.pipeline_contenido import _ingesta

    monkeypatch.setenv("KENI_PLAN_DIA", "breaking:1")
    monkeypatch.setenv("KENI_BREAKING_EXTRA_DIA", "1")
    # El cupo del plan (1) YA está consumido por una breaking generada hoy: tema CON post
    # real (pieza es_publicacion=1); un tema sin post no consumiría cupo (no cuenta).
    breaking = repos.crear_contenido(
        clase="contenido", titulo="Breaking previa", marca="unotv", categoria="breaking"
    )
    repos.crear_contenido_plataforma(
        contenido_id=breaking["id"], red="facebook", marca="unotv", copy="P", es_publicacion=True
    )
    # Queda el hueco EXTRA: una nueva última hora aún sale al feed.
    assert _ingesta.cupos_categoria_restantes("unotv") == {"breaking": 1}
    # Con el extra a 0 el plan vuelve a ser techo duro también para breaking.
    monkeypatch.setenv("KENI_BREAKING_EXTRA_DIA", "0")
    assert _ingesta.cupos_categoria_restantes("unotv") == {}


def test_cupos_solo_cuentan_la_jornada_mx_no_dias_previos(entorno, monkeypatch):
    """La admisión cuenta por PARRILLA DEL DÍA (jornada MX): lo de días anteriores reabre cupo.

    A medianoche de México los cupos del plan vuelven a 0; una pieza generada en un día
    anterior (aquí, hace años) ya no consume cupo hoy, así que el auto-feed puede volver a
    llenar el plan de la nueva jornada.
    """
    from keni_consola.pipeline_contenido import _ingesta

    monkeypatch.setenv("KENI_PLAN_DIA", "mx:1")
    # Ambos con post real (es_publicacion=1): lo ÚNICO que excluye al viejo es la fecha.
    # De otra jornada: NO consume el cupo de hoy -> queda el hueco íntegro.
    ayer = repos.crear_contenido(
        clase="contenido", titulo="Nacional de ayer", marca="unotv", categoria="mx",
        creado="2020-01-01T00:00:00",
    )
    repos.crear_contenido_plataforma(
        contenido_id=ayer["id"], red="facebook", marca="unotv", copy="P", es_publicacion=True
    )
    assert _ingesta.cupos_categoria_restantes("unotv") == {"mx": 1}
    # De hoy: consume el cupo -> sin hueco.
    hoy = repos.crear_contenido(
        clase="contenido", titulo="Nacional de hoy", marca="unotv", categoria="mx"
    )
    repos.crear_contenido_plataforma(
        contenido_id=hoy["id"], red="facebook", marca="unotv", copy="P", es_publicacion=True
    )
    assert _ingesta.cupos_categoria_restantes("unotv") == {}


def test_plan_sin_linea_breaking_compite_por_su_feed(entorno, monkeypatch):
    """Si el plan no declara 'breaking', la última hora no queda invisible: compite por el
    cupo de su categoría de FEED."""
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:1")
    _sembrar_cluster("brx", titulo="Ultima hora sin linea propia", score=0.9,
                     categoria="mx", breaking=1, qa_veredicto=pc.VERDICTO_NO_VERIFICADO)

    elegidos = pc.clusters_para_promover("unotv", maximo=5, cupos_categoria={"mx": 1})

    assert [c["id"] for c in elegidos] == ["brx"]


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
    # Una historia USADA desde el panel (curación humana) también entra: si su lanzamiento
    # síncrono falló (cola llena / generación pausada), este es su ÚNICO reintento.
    historia = repos.crear_contenido(
        clase="contenido", titulo="Breaking curada", marca="unotv", origen="historia",
    )
    ids = {t["id"] for t in pc.temas_autogen_sin_copy()}
    assert bueno["id"] in ids
    assert historia["id"] in ids
    # El tecleado (origen "") NO entra.
    assert len(ids) == 2


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
    _sembrar_cluster("dup1", titulo="Messi gana el premio en París", score=0.9,
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _sembrar_cluster("dup2", titulo="Messi gana el premio en París hoy", score=0.8,
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _sembrar_cluster("otra", titulo="Sismo de magnitud en la capital", score=0.5,
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)

    elegidos = pc.clusters_para_promover("unotv", maximo=2)

    assert [c["id"] for c in elegidos] == ["dup1", "otra"]  # el casi-duplicado cede su plaza


def test_clusters_para_promover_suave_rellena_si_solo_hay_duplicados(entorno):
    """Si todo el pool es el mismo macro-tema, se rellena igual (nunca devuelve menos)."""
    _sembrar_cluster("dup1", titulo="Messi gana el premio en París", score=0.9,
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _sembrar_cluster("dup2", titulo="Messi gana el premio en París hoy", score=0.8,
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    elegidos = pc.clusters_para_promover("unotv", maximo=2)
    assert {c["id"] for c in elegidos} == {"dup1", "dup2"}


# --------------------------------------------------------------------------- #
# LISTÓN de producción automática: promover cuesta tokens (QA+copy con IA);    #
# el ruido se queda en el pool aunque haya plazas libres.                       #
# --------------------------------------------------------------------------- #


def test_clusters_para_promover_respeta_el_liston(entorno):
    """Solo las historias que superan el listón compiten por plaza; el ruido queda en el pool."""
    from datetime import UTC, datetime, timedelta

    # Todas VERIFICADAS (pasaron la criba): así el ÚNICO discriminante de la promoción es el
    # listón, no el filtro de QA (que ya cribó a todas por igual).
    _sembrar_cluster("apta", titulo="Sismo sacude la CDMX", score=0.9,
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    # Sin encaje de marca: ni el título ni el resumen casan el vocabulario unotv.
    _sembrar_cluster(
        "irrelevante", titulo="Gossip de celebridades en Hollywood", score=0.8,
        resumen="Rumores del espectáculo extranjero", qa_veredicto=pc.VERDICTO_NO_VERIFICADO,
    )
    # Verificación dudosa: jamás dispara producción automática, puntúe lo que puntúe.
    _sembrar_cluster("dudosa", titulo="Increíble suceso en México hoy", score=0.7,
                     verificacion="dudosa", qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    # Vieja sin señales: su score persistido era alto, pero el listón recalcula AHORA.
    _sembrar_cluster(
        "vieja", titulo="México: nota de hace una semana", score=0.95, n_fuentes=1,
        ultimo_visto=(datetime.now(UTC) - timedelta(days=7)).replace(tzinfo=None)
        .isoformat(timespec="seconds"), qa_veredicto=pc.VERDICTO_NO_VERIFICADO,
    )

    elegidos = pc.clusters_para_promover("unotv", maximo=4)

    # Hay 4 plazas, pero solo la apta supera el listón (el resto NO rellena plazas libres).
    assert [c["id"] for c in elegidos] == ["apta"]


def test_promover_clusters_marca_no_promueve_bajo_liston(entorno, monkeypatch):
    """El barrido CI deja en el pool (estado `nuevo`) lo que no supera el listón: ni tema ni copy."""
    monkeypatch.setattr(pc, "_autor_pipeline", lambda: None)
    _sembrar_cluster("apta", titulo="Sismo sacude la CDMX", score=0.9,
                     qa_veredicto=pc.VERDICTO_NO_VERIFICADO)
    _sembrar_cluster(
        "irrelevante", titulo="Gossip de celebridades en Hollywood", score=0.8,
        resumen="Rumores del espectáculo extranjero", qa_veredicto=pc.VERDICTO_NO_VERIFICADO,
    )

    temas = pc.promover_clusters_marca("unotv", maximo=2)

    assert [t["titulo"] for t in temas] == ["Sismo sacude la CDMX"]
    assert repos.obtener_noticia_cluster("apta")["estado"] == "usado"
    # La irrelevante sigue `nuevo`: visible en el panel, usable a mano, expirable por edad.
    assert repos.obtener_noticia_cluster("irrelevante")["estado"] == "nuevo"


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
    NOTA: el reaper usa ahora su saneo PER-TEMA (`reaper_generaciones._sanear_qa_en_curso`,
    con WARN por tema y destino según el toggle); esta primitiva SQL en lote sigue en repos.
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


def _envejecer_actualizado(tema_id, fecha="2020-01-01T00:00:00"):
    """Retrasa el `actualizado` de un tema (lo vuelve zombi para los saneadores)."""
    from keni_consola import db

    con = db._conectar()
    try:
        con.execute("UPDATE contenido SET actualizado = ? WHERE id = ?", (fecha, tema_id))
        con.commit()
    finally:
        con.close()


def test_reaper_qa_zombi_re_criba_con_validacion_activa(entorno, monkeypatch):
    """El saneo del reaper devuelve a re-criba ('') SOLO los `en_curso` zombis (per-tema)."""
    from keni_consola import reaper_generaciones

    monkeypatch.setenv("KENI_PIPELINE_VALIDACION", "1")
    zombi = _tema_pipeline(titulo="Zombi", qa_veredicto=pc.QA_EN_CURSO)
    vivo = _tema_pipeline(titulo="Vivo", qa_veredicto=pc.QA_EN_CURSO)
    _envejecer_actualizado(zombi["id"])

    n = reaper_generaciones._sanear_qa_en_curso()

    assert n == 1
    assert (repos.obtener_contenido(zombi["id"])["qa_veredicto"] or "") == ""  # a re-criba
    assert repos.obtener_contenido(vivo["id"])["qa_veredicto"] == pc.QA_EN_CURSO  # intacto


def test_reaper_qa_zombi_saltada_con_validacion_apagada(entorno, monkeypatch):
    """Con la etapa de Validación APAGADA, el zombi pasa a 'saltada' (CD lo recoge), no a re-criba."""
    from keni_consola import reaper_generaciones

    monkeypatch.delenv("KENI_PIPELINE_VALIDACION", raising=False)  # etapa off (def)
    zombi = _tema_pipeline(titulo="Zombi sin QA", qa_veredicto=pc.QA_EN_CURSO)
    _envejecer_actualizado(zombi["id"])

    n = reaper_generaciones._sanear_qa_en_curso()

    assert n == 1
    assert repos.obtener_contenido(zombi["id"])["qa_veredicto"] == pc.QA_SALTADA


def test_ejecutar_arte_fallo_masivo_emite_un_error_agregado(entorno, monkeypatch, caplog):
    """>50% de lanzamientos de arte fallidos en un ciclo -> UN único ERROR agregado (proveedor)."""
    import logging

    from keni_consola import autogen_arte

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_ARTE, "1")
    monkeypatch.setattr(autogen_arte.media, "proveedor_configurado", lambda: True)
    items = [
        {"id": "t1", "titulo": "Tema 1", "marca": "unotv"},
        {"id": "t2", "titulo": "Tema 2", "marca": "unotv"},
    ]
    monkeypatch.setattr(pc.repos, "listar_contenido", lambda **_k: items)
    monkeypatch.setattr(autogen_arte, "_plataformas_por_item", lambda items: {})
    monkeypatch.setattr(autogen_arte, "ids_ya_procesados", lambda: set())
    monkeypatch.setattr(autogen_arte, "_etiquetas_por_item", lambda: {})
    monkeypatch.setattr(autogen_arte, "topics_sin_arte", lambda *a, **k: list(items))
    monkeypatch.setattr(
        autogen_arte, "lanzar_para_topic",
        lambda it: (_ for _ in ()).throw(RuntimeError("proveedor caído")),
    )

    with caplog.at_level(logging.ERROR, logger="keni_consola.pipeline_contenido"):
        res = pc.ejecutar_arte()

    assert res == []
    agregados = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "fallido(s) en este barrido" in r.getMessage()
    ]
    assert len(agregados) == 1
    assert "2/2" in agregados[0].getMessage()
    # Correlación: el resumen lista los temas afectados.
    assert "t1" in agregados[0].getMessage() and "t2" in agregados[0].getMessage()


def test_ejecutar_arte_fallo_aislado_sin_error_agregado(entorno, monkeypatch, caplog):
    """Un fallo de arte AISLADO (<=50% del ciclo) no dispara la señal de proveedor caído."""
    import logging

    from keni_consola import autogen_arte

    monkeypatch.setenv(config.ENV_MAQUINA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_ARTE, "1")
    monkeypatch.setattr(autogen_arte.media, "proveedor_configurado", lambda: True)
    items = [
        {"id": "t1", "titulo": "Tema 1", "marca": "unotv"},
        {"id": "t2", "titulo": "Tema 2", "marca": "unotv"},
    ]
    monkeypatch.setattr(pc.repos, "listar_contenido", lambda **_k: items)
    monkeypatch.setattr(autogen_arte, "_plataformas_por_item", lambda items: {})
    monkeypatch.setattr(autogen_arte, "ids_ya_procesados", lambda: set())
    monkeypatch.setattr(autogen_arte, "_etiquetas_por_item", lambda: {})
    monkeypatch.setattr(autogen_arte, "topics_sin_arte", lambda *a, **k: list(items))

    def _solo_t1_falla(it):
        if it["id"] == "t1":
            raise RuntimeError("fallo puntual")
        return {"contenido_id": it["id"]}

    monkeypatch.setattr(autogen_arte, "lanzar_para_topic", _solo_t1_falla)

    with caplog.at_level(logging.ERROR, logger="keni_consola.pipeline_contenido"):
        res = pc.ejecutar_arte()

    assert len(res) == 1  # t2 sí se ilustró
    assert not [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "fallido(s) en este barrido" in r.getMessage()
    ]


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


def test_lanzar_para_topic_sella_pipeline_y_marcador_cd(entorno, monkeypatch):
    """El copy de un tema del TABLERO es trabajo del PIPELINE: se lanza `tipo='pipeline'`
    (no el legado "autogen") y deja el marcador de etapa CD correlacionado al tema, para que
    Producción lo muestre dentro de la run (stream en el detalle + métricas sumadas)."""
    from keni_consola import autogen_copy

    capturas: dict[str, object] = {}

    def _fake_lanzar_copy(**kwargs):
        capturas.update(kwargs)
        return {"id": "gen-tablero-1"}

    monkeypatch.setattr(autogen_copy.dom_generar, "lanzar_copy", _fake_lanzar_copy)
    marcadores: list[tuple] = []
    monkeypatch.setattr(
        pc, "registrar_etapa",
        lambda etapa, marca, detalle, contenido_id="", gen_id="": marcadores.append(
            (etapa, marca, detalle, contenido_id, gen_id)
        ),
    )

    item = {"id": "tema-tablero", "marca": "unotv", "origen": "equipo",
            "titulo": "Nota del equipo", "descripcion": "La nota."}
    gen = autogen_copy.lanzar_para_topic(item)

    assert gen == {"id": "gen-tablero-1"}
    assert capturas["tipo"] == "pipeline"
    assert capturas["contenido_id"] == "tema-tablero"
    assert capturas["titulo"] == "Nota del equipo"  # etiqueta legible, no "Auto-copy"
    assert len(marcadores) == 1
    etapa, marca, detalle, contenido_id, gen_id = marcadores[0]
    assert etapa == pc.ETAPA_CD
    assert marca == "unotv"
    assert contenido_id == "tema-tablero"
    assert gen_id == "gen-tablero-1"
