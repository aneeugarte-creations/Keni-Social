"""Tests de la MESA DE REDACCIÓN (/api/noticias/mesa). OFFLINE, sin red.

La mesa devuelve el pool segmentado por las líneas del plan editorial diario de la marca
(cupo + progreso de 24 h + top-N candidatas por línea) y un bloque `fuera_de_plan`.
"""

from __future__ import annotations

from keni_consola import bootstrap_lineas, repos

from .conftest import _cliente  # noqa: F401  (usado por la fixture `cliente`)


def _linea_nacional() -> str:
    """Siembra las líneas y devuelve el id de 'Nacional' (unotv) — la línea que mapea el feed 'mx'.

    El plan y la mesa se clavan por id de línea; un feed 'mx' se reparte en esta línea.
    """
    bootstrap_lineas.inicializar_lineas()
    return repos.obtener_etiqueta_por_nombre("Nacional", "vertical", "unotv")["id"]


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
    # El plan y la mesa se clavan por LÍNEA (id de etiqueta vertical): un feed 'mx' se reparte
    # en la línea Nacional; 'breaking'/'evergreen' son señales del motor.
    from keni_consola import bootstrap_lineas, repos

    bootstrap_lineas.inicializar_lineas()
    nac = repos.obtener_etiqueta_por_nombre("Nacional", "vertical", "unotv")["id"]
    intl = repos.obtener_etiqueta_por_nombre("Internacional", "vertical", "unotv")["id"]
    monkeypatch.setenv("KENI_PLAN_DIA", f"{nac}:2,{intl}:1,breaking:1")
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
    # Breaking PRIMERO, luego el orden del plan (por id de línea).
    assert [ln["linea"] for ln in datos["lineas"]] == ["breaking", nac, intl]
    por_linea = {ln["linea"]: ln for ln in datos["lineas"]}
    assert por_linea[nac]["etiqueta"] == "Nacional"
    assert por_linea["breaking"]["etiqueta"] == "Última hora"
    assert por_linea[nac]["cupo"] == 2
    assert por_linea[nac]["en_pool"] == 2
    assert [h["id"] for h in por_linea[nac]["historias"]] == ["mx-top", "mx-baja"]
    assert por_linea["breaking"]["en_pool"] == 1
    assert por_linea["breaking"]["historias"][0]["id"] == "br1"
    assert por_linea[intl]["en_pool"] == 0
    assert datos["fuera_de_plan"]["en_pool"] == 1
    assert datos["fuera_de_plan"]["historias"][0]["id"] == "dep1"
    # Cada historia trae el contrato Historia (umbral + estado de pieza incluidos).
    h = por_linea[nac]["historias"][0]
    assert "promovible" in h and "pieza_estado" in h and "score_desglose" in h


def test_mesa_clasifica_por_contenido_si_el_feed_no_mapea(cliente, monkeypatch):
    """Si el slug del feed de una candidata NO cae en ninguna línea del plan, la mesa la
    reparte por CONTENIDO (keywords de la línea), no a «Fuera del plan». Es el caso de
    Fundación, cuyos feeds traen slugs gruesos (entretenimiento/internacional) que no mapean a
    sus líneas; aquí se reproduce con UnoTV dándole keywords a una línea y un feed sin mapeo.
    """
    bootstrap_lineas.inicializar_lineas()
    intl = repos.obtener_etiqueta_por_nombre("Internacional", "vertical", "unotv")["id"]
    # Como las líneas de Fundación, esta línea recibe keywords: una candidata cuyo feed NO
    # mapea ('gaming' no es línea de UnoTV) se clasifica por su texto.
    repos.actualizar_etiqueta(intl, {"keywords": "groenlandia, vikingos, fosil"})
    monkeypatch.setenv("KENI_PLAN_DIA", f"{intl}:2")
    _inicializar("sci", score=0.9, marca="unotv", categoria="gaming",
                 titulo="Hallazgo en Groenlandia revela el rastro de vikingos")
    # Sin coincidencia de keywords: el feed tampoco mapea -> fuera del plan.
    _inicializar("nada", score=0.7, marca="unotv", categoria="gaming",
                 titulo="El equipo gana el partido en el último minuto")

    datos = cliente.get("/api/noticias/mesa", params={"marca": "unotv"}).json()
    por_linea = {ln["linea"]: ln for ln in datos["lineas"]}
    assert [h["id"] for h in por_linea[intl]["historias"]] == ["sci"]
    assert datos["fuera_de_plan"]["en_pool"] == 1
    assert datos["fuera_de_plan"]["historias"][0]["id"] == "nada"


def test_mesa_extranjera_sin_traducir_se_ve_como_traduciendo(cliente, monkeypatch):
    """La mesa se ve SIEMPRE en español: una historia extranjera sin traducir SÍ aparece, pero con
    un placeholder "Traduciendo…" (nunca su titular en idioma original) y `traduciendo=True`. La
    traducida se muestra en español (titulo_es) y la nativa en español, normales."""
    nac = _linea_nacional()
    monkeypatch.setenv("KENI_PLAN_DIA", f"{nac}:5")
    _inicializar("es-nativa", score=0.9, categoria="mx", titulo="Noticia nacional", idioma="es")
    _inicializar("en-cruda", score=0.8, categoria="mx", titulo="Foreign breaking",
                 idioma="en", traducido=0)
    _inicializar("en-trad", score=0.7, categoria="mx", titulo="Foreign two",
                 idioma="en", traducido=1, titulo_es="Noticia traducida")
    datos = cliente.get("/api/noticias/mesa", params={"marca": "unotv"}).json()
    linea = {ln["linea"]: ln for ln in datos["lineas"]}[nac]
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
    nac = _linea_nacional()
    monkeypatch.setenv("KENI_PLAN_DIA", f"{nac}:2")
    for i in range(4):
        _inicializar(f"m{i}", score=0.9 - i * 0.1, categoria="mx", titulo=f"Nacional {i}")
    datos = cliente.get(
        "/api/noticias/mesa", params={"marca": "unotv", "por_linea": 2}
    ).json()
    linea = datos["lineas"][0]
    assert linea["en_pool"] == 4  # el conteo es del pool completo de la línea
    assert [h["id"] for h in linea["historias"]] == ["m0", "m1"]  # top-N rankeado


def test_mesa_conteo_honesto_escala_al_pool_real(cliente, monkeypatch):
    """El "300 vs 13": con el pool por encima de la muestra topada, `en_pool` refleja el pool REAL
    (escalado), no el recorte. `en_pool_total` es el COUNT(*) real; `historias[]` sigue siendo top-N.
    """
    from keni_consola.api.noticias import historias as _h

    nac = _linea_nacional()
    monkeypatch.setenv("KENI_PLAN_DIA", f"{nac}:2")
    # 6 candidatas en la línea Nacional, pero la muestra se topa a 3: el reparto/render ve 3.
    monkeypatch.setattr(_h, "_MESA_MUESTRA", 3)
    for i in range(6):
        _inicializar(f"m{i}", score=0.9 - i * 0.05, categoria="mx", titulo=f"Nacional {i}")

    datos = cliente.get(
        "/api/noticias/mesa", params={"marca": "unotv", "por_linea": 2}
    ).json()
    # Pool real honesto: 6 (no la muestra de 3).
    assert datos["en_pool_total"] == 6
    linea = datos["lineas"][0]
    # `en_pool` escalado al pool real (3 de la muestra · factor 6/3 = 6), no el recorte.
    assert linea["en_pool"] == 6
    # `historias[]` sigue siendo top-N por línea (top-2 rankeado), no el pool entero.
    assert [h["id"] for h in linea["historias"]] == ["m0", "m1"]


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
    nac = _linea_nacional()
    monkeypatch.setenv("KENI_PLAN_DIA", f"{nac}:2")
    # Un tema CON post real cuenta...
    _contenido_con_post(categoria=nac, titulo="Ya generada")
    # ...pero un tema SIN ningún post (promovido y con el copy sin generar, o fallido) NO:
    # es el "fantasma" que antes inflaba el plan (6 en el conteo con 5 posts visibles).
    repos.crear_publicacion(clase="contenido", titulo="Sin post", marca="unotv", categoria=nac)
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
    nac = _linea_nacional()
    monkeypatch.setenv("KENI_PLAN_DIA", f"{nac}:2")
    # Ambos con post real, así que lo ÚNICO que excluye al viejo es la fecha (no la falta
    # de pieza): de otro día (muy anterior a cualquier medianoche MX de hoy) NO cuenta.
    _contenido_con_post(categoria=nac, titulo="De ayer", creado="2020-01-01T00:00:00")
    # De hoy (creado=ahora por defecto): SÍ cuenta.
    _contenido_con_post(categoria=nac, titulo="De hoy")
    datos = cliente.get("/api/noticias/mesa", params={"marca": "unotv"}).json()
    linea = datos["lineas"][0]
    assert linea["generados"] == 1  # solo la de hoy
    assert linea["restante"] == 1
    assert datos["total_generados"] == 1


def test_mesa_claro_sports_navega_por_grupos(cliente, monkeypatch):
    # Claro Sports usa GRUPOS: la mesa devuelve la barra de chips (ordenada por prioridad
    # editorial, con su conteo) y la lista de candidatas con su grupo, clasificadas por keywords.
    # Sin plan, el front navega por estos grupos en vez de degradar a lista plana.
    bootstrap_lineas.inicializar_lineas()
    monkeypatch.delenv("KENI_PLAN_DIA", raising=False)
    monkeypatch.delenv("KENI_PLAN_DIA::claro-sports", raising=False)
    _inicializar("box1", score=0.9, marca="claro-sports", categoria="otros-deportes",
                 titulo="Canelo Álvarez confirma su próxima pelea de box")
    _inicializar("f1", score=0.8, marca="claro-sports", categoria="motor",
                 titulo="Checo Pérez debuta con Cadillac en la Fórmula 1")
    _inicializar("liga", score=0.7, marca="claro-sports", categoria="futbol",
                 titulo="Cruz Azul vence al América en la Liga MX")

    datos = cliente.get("/api/noticias/mesa", params={"marca": "claro-sports"}).json()
    # Barra de grupos: orden de prioridad editorial.
    nombres = [g["grupo"] for g in datos["grupos"]]
    assert nombres[:3] == ["Fútbol", "Motor", "Olímpicos"]
    conteo = {g["grupo"]: g["en_pool"] for g in datos["grupos"]}
    assert conteo["Boxeo"] == 1 and conteo["Motor"] == 1 and conteo["Fútbol"] == 1
    # Cada candidata trae su grupo clasificado por léxico.
    grupo_de = {h["id"]: h["grupo"] for h in datos["historias_grupo"]}
    assert grupo_de["box1"] == "Boxeo"
    assert grupo_de["f1"] == "Motor"
    assert grupo_de["liga"] == "Fútbol"

    # 2º nivel de navegación: cada grupo cuelga sus LÍNEAS (id + nombre + conteo), con las que
    # tienen candidatas arriba (conteo no-creciente) y las vacías al final.
    grupos_por_nombre = {g["grupo"]: g for g in datos["grupos"]}
    for g in datos["grupos"]:
        assert isinstance(g["lineas"], list)
        for ln in g["lineas"]:
            assert ln["linea"] and ln["nombre"]  # id + nombre visibles
        cuentas = [ln["en_pool"] for ln in g["lineas"]]
        assert cuentas == sorted(cuentas, reverse=True)  # candidatas primero, vacías al final

    # Cada candidata trae además su LÍNEA, que pertenece a su grupo y la cuenta como candidata.
    linea_de = {h["id"]: h["linea"] for h in datos["historias_grupo"]}
    for hid, gname in (("box1", "Boxeo"), ("f1", "Motor"), ("liga", "Fútbol")):
        assert linea_de[hid]  # clasificada en una línea concreta
        ln = next(x for x in grupos_por_nombre[gname]["lineas"] if x["linea"] == linea_de[hid])
        assert ln["en_pool"] >= 1


def test_mesa_sin_grupos_no_trae_barra(cliente):
    # UnoTV no usa grupos: el back NO emite `grupos`/`historias_grupo` (manda el plan en `lineas`).
    # El front deriva de ahí los chips planos de navegación (sin desplegable), conservando el plan.
    bootstrap_lineas.inicializar_lineas()
    _inicializar("c1", marca="unotv", categoria="mx")
    datos = cliente.get("/api/noticias/mesa", params={"marca": "unotv"}).json()
    assert datos["grupos"] == [] and datos["historias_grupo"] == []
