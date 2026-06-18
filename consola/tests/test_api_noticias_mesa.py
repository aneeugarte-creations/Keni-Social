"""Tests de la MESA DE REDACCIÓN (/api/noticias/mesa) y del restaurar. OFFLINE, sin red.

La mesa devuelve el pool segmentado por las líneas del plan editorial diario de la marca
(cupo + progreso de 24 h + top-N candidatas por línea) y un bloque `fuera_de_plan`. El
restaurar es el deshacer del descarte rápido (descartada -> pool).
"""

from __future__ import annotations

from keni_consola import repos

from .conftest import _cliente  # noqa: F401  (usado por la fixture `cliente`)


def _inicializar(cid, *, score=0.5, categoria="mx", breaking=0, estado="nuevo", marca="unotv",
             titulo="Historia de prueba", idioma="", traducido=0, titulo_es=""):
    repos.upsert_noticia_cluster({
        "id": cid, "titulo": titulo, "resumen": "Resumen", "marca": marca,
        "categoria": categoria, "clave": f"t:{cid}", "n_items": 1, "n_fuentes": 2,
        "senal": 100, "score": score, "breaking": breaking,
        "primer_visto": "2026-06-01T00:00:00+00:00",
        "ultimo_visto": "2026-06-05T12:00:00+00:00", "estado": estado,
        "idioma": idioma, "traducido": traducido, "titulo_es": titulo_es,
    })
    return repos.obtener_noticia_cluster(cid)


def _contenido_con_post(*, marca="unotv", categoria="mx", titulo="Generada", creado=""):
    """Un `contenido` del plan CON un post real (pieza `es_publicacion=1`).

    Es lo que el plan cuenta: solo los temas que YA produjeron una publicación. Un
    `contenido` sin piezas (promovido pero con el copy aún sin generar, o fallido/borrado)
    NO cuenta — para eso se crea con `repos.crear_publicacion` a secas en los tests.
    """
    kw = {"clase": "contenido", "titulo": titulo, "marca": marca, "categoria": categoria}
    if creado:
        kw["creado"] = creado
    contenido = repos.crear_publicacion(**kw)
    repos.crear_pieza_fila(
        publicacion_id=contenido["id"], red="facebook", marca=marca, copy="Post",
        es_publicacion=True,
    )
    return contenido


# --------------------------------------------------------------------------- #
# GET /api/noticias/mesa                                                       #
# --------------------------------------------------------------------------- #


def test_mesa_requiere_marca_concreta(cliente):
    assert cliente.get("/api/noticias/mesa").status_code == 400
    assert cliente.get("/api/noticias/mesa", params={"marca": "nope"}).status_code == 400


def test_mesa_segmenta_por_lineas_del_plan(cliente, monkeypatch):
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:2,internacional:1,breaking:1")
    _inicializar("mx-top", score=0.9, categoria="mx", titulo="Nacional top")
    _inicializar("mx-baja", score=0.3, categoria="mx", titulo="Nacional floja")
    # Breaking: compite por la línea 'breaking' aunque su feed sea futbol.
    _inicializar("br1", score=0.8, categoria="futbol", breaking=1, titulo="Última hora")
    # Sin línea en el plan: va a fuera_de_plan.
    _inicializar("dep1", score=0.7, categoria="gaming", titulo="Gaming sin línea")
    # Usada/descartada: no son candidatas (estado != nuevo).
    _inicializar("usada", estado="usado", categoria="mx")

    datos = cliente.get("/api/noticias/mesa", params={"marca": "unotv"}).json()
    assert datos["marca"] == "unotv"
    assert datos["plan"] is True
    assert datos["total_objetivo"] == 4
    # Breaking PRIMERO, luego el orden del plan.
    assert [ln["linea"] for ln in datos["lineas"]] == ["breaking", "mx", "internacional"]
    por_linea = {ln["linea"]: ln for ln in datos["lineas"]}
    assert por_linea["mx"]["cupo"] == 2
    assert por_linea["mx"]["en_pool"] == 2
    assert [h["id"] for h in por_linea["mx"]["historias"]] == ["mx-top", "mx-baja"]
    assert por_linea["breaking"]["en_pool"] == 1
    assert por_linea["breaking"]["historias"][0]["id"] == "br1"
    assert por_linea["internacional"]["en_pool"] == 0
    assert datos["fuera_de_plan"]["en_pool"] == 1
    assert datos["fuera_de_plan"]["historias"][0]["id"] == "dep1"
    # Cada historia trae el contrato Historia (umbral + estado de pieza incluidos).
    h = por_linea["mx"]["historias"][0]
    assert "promovible" in h and "pieza_estado" in h and "score_desglose" in h


def test_mesa_extranjera_sin_traducir_se_ve_como_traduciendo(cliente, monkeypatch):
    """La mesa se ve SIEMPRE en español: una historia extranjera sin traducir SÍ aparece, pero con
    un placeholder "Traduciendo…" (nunca su titular en idioma original) y `traduciendo=True`. La
    traducida se muestra en español (titulo_es) y la nativa en español, normales."""
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:5")
    _inicializar("es-nativa", score=0.9, categoria="mx", titulo="Noticia nacional", idioma="es")
    _inicializar("en-cruda", score=0.8, categoria="mx", titulo="Foreign breaking",
                 idioma="en", traducido=0)
    _inicializar("en-trad", score=0.7, categoria="mx", titulo="Foreign two",
                 idioma="en", traducido=1, titulo_es="Noticia traducida")
    datos = cliente.get("/api/noticias/mesa", params={"marca": "unotv"}).json()
    linea = {ln["linea"]: ln for ln in datos["lineas"]}["mx"]
    por_id = {h["id"]: h for h in linea["historias"]}
    assert set(por_id) == {"es-nativa", "en-cruda", "en-trad"}  # todas visibles
    # Extranjera sin traducir: placeholder, nunca el titular en idioma original.
    assert por_id["en-cruda"]["traduciendo"] is True
    assert por_id["en-cruda"]["titulo"] == "Traduciendo…"
    assert por_id["en-cruda"]["titulo_original"] == "Foreign breaking"
    # Traducida y nativa: en español y SIN marca de traduciendo.
    assert por_id["en-trad"]["titulo"] == "Noticia traducida"
    assert por_id["en-trad"]["traduciendo"] is False
    assert por_id["es-nativa"]["traduciendo"] is False


def test_mesa_respeta_top_n_por_linea(cliente, monkeypatch):
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:2")
    for i in range(4):
        _inicializar(f"m{i}", score=0.9 - i * 0.1, categoria="mx", titulo=f"Nacional {i}")
    datos = cliente.get(
        "/api/noticias/mesa", params={"marca": "unotv", "por_linea": 2}
    ).json()
    linea = datos["lineas"][0]
    assert linea["en_pool"] == 4  # el conteo es del pool completo de la línea
    assert [h["id"] for h in linea["historias"]] == ["m0", "m1"]  # top-N rankeado


def test_mesa_sin_plan_degrada_a_fuera_de_plan(cliente, monkeypatch):
    monkeypatch.delenv("KENI_PLAN_DIA", raising=False)
    monkeypatch.delenv("KENI_PLAN_DIA::unotv", raising=False)
    _inicializar("c1", categoria="mx")
    datos = cliente.get("/api/noticias/mesa", params={"marca": "unotv"}).json()
    assert datos["plan"] is False
    assert datos["lineas"] == []
    assert datos["total_objetivo"] == 0
    assert datos["fuera_de_plan"]["en_pool"] == 1


def test_mesa_descuenta_lo_generado_en_el_progreso(cliente, monkeypatch):
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:2")
    # Un tema CON post real cuenta...
    _contenido_con_post(categoria="mx", titulo="Ya generada")
    # ...pero un tema SIN ningún post (promovido y con el copy sin generar, o fallido) NO:
    # es el "fantasma" que antes inflaba el plan (6 en el conteo con 5 posts visibles).
    repos.crear_publicacion(clase="contenido", titulo="Sin post", marca="unotv", categoria="mx")
    datos = cliente.get("/api/noticias/mesa", params={"marca": "unotv"}).json()
    linea = datos["lineas"][0]
    assert linea["generados"] == 1  # solo el que tiene post; el fantasma no cuenta
    assert linea["restante"] == 1
    assert datos["total_generados"] == 1


def test_mesa_solo_cuenta_la_jornada_mx_no_lo_de_dias_previos(cliente, monkeypatch):
    """El contador es la PARRILLA DEL DÍA (jornada MX): lo de días anteriores no suma.

    Es el reset diario que pedía el piloto: una pieza creada antes de la medianoche de
    México (aquí, hace años) NO cuenta; solo lo generado en la jornada de hoy. Así, al día
    siguiente el plan vuelve a 0 aunque la pieza vieja siga viva en el tablero.
    """
    monkeypatch.setenv("KENI_PLAN_DIA", "mx:2")
    # Ambos con post real, así que lo ÚNICO que excluye al viejo es la fecha (no la falta
    # de pieza): de otro día (muy anterior a cualquier medianoche MX de hoy) NO cuenta.
    _contenido_con_post(categoria="mx", titulo="De ayer", creado="2020-01-01T00:00:00")
    # De hoy (creado=ahora por defecto): SÍ cuenta.
    _contenido_con_post(categoria="mx", titulo="De hoy")
    datos = cliente.get("/api/noticias/mesa", params={"marca": "unotv"}).json()
    linea = datos["lineas"][0]
    assert linea["generados"] == 1  # solo la de hoy
    assert linea["restante"] == 1
    assert datos["total_generados"] == 1


# --------------------------------------------------------------------------- #
# POST /api/noticias/historias/{id}/restaurar                                  #
# --------------------------------------------------------------------------- #


def test_restaurar_devuelve_descartada_al_pool(cliente):
    _inicializar("c1", estado="nuevo")
    cliente.post("/api/noticias/historias/c1/descartar")
    assert repos.obtener_noticia_cluster("c1")["estado"] == "descartado"
    r = cliente.post("/api/noticias/historias/c1/restaurar")
    assert r.status_code == 200
    assert r.json()["historia"]["estado"] == "nuevo"
    assert repos.obtener_noticia_cluster("c1")["estado"] == "nuevo"


def test_restaurar_es_idempotente_sobre_una_nueva(cliente):
    _inicializar("c1", estado="nuevo")
    r = cliente.post("/api/noticias/historias/c1/restaurar")
    assert r.status_code == 200
    assert r.json()["historia"]["estado"] == "nuevo"


def test_restaurar_usada_400_e_inexistente_404(cliente):
    _inicializar("c1", estado="nuevo")
    cont = repos.crear_publicacion(clase="contenido", titulo="Tema", marca="unotv")
    repos.actualizar_noticia_cluster("c1", estado="usado", publicacion_id=cont["id"])
    assert cliente.post("/api/noticias/historias/c1/restaurar").status_code == 400
    assert cliente.post("/api/noticias/historias/nope/restaurar").status_code == 404
