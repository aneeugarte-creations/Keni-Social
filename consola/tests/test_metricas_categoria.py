"""Agregación del rendimiento del periodo por LÍNEA (clase `categoria`) y por ORIGEN.

Prueba la lógica PURA de `metricas_categoria` (sin BD ni golpear Metricool): se le pasan las
piezas del periodo + los índices de enlace + las etiquetas en memoria, y se verifica la
agregación (nº de piezas, sumas de visualizaciones/interacciones, engagement medio, cubo
"Sin línea"/"Sin origen", orden). Es el mismo patrón que el resto de agregaciones del
módulo: separar la agregación de la lectura para poder testearla sin Postgres.
"""

from __future__ import annotations

from keni_consola import metricas_categoria


def _pieza(id_post, titulo, vis, inter, eng):
    return {
        "id": id_post,
        "titulo": titulo,
        "visualizaciones": vis,
        "interacciones": inter,
        "engagement_pct": eng,
    }


def test_nombre_de_categoria_eje_unico_categoria():
    """La LÍNEA sale SOLO de la `categoria` (eje único): las señales del motor son su propio cubo
    («Última hora», «Evergreen»); categoría activa por id; vacía/retirada/desconocida → "" (Sin
    línea). Ya NO se respalda con la etiqueta categoria asignada (eso lo cubre el backfill 0046)."""
    categorias = {"et-nac": "Nacional", "et-int": "Internacional"}
    f = metricas_categoria.nombre_de_categoria
    # Señales del motor: cada una su propio cubo (coincide con los chips/el filtro).
    assert f("evergreen", categoria_por_id=categorias) == "Evergreen"
    assert f("breaking", categoria_por_id=categorias) == "Última hora"
    # Id de categoría ACTIVA → su nombre.
    assert f("et-nac", categoria_por_id=categorias) == "Nacional"
    # Vacía o id de categoría RETIRADA/desconocida → "" (cae en "Sin línea").
    assert f("", categoria_por_id=categorias) == ""
    assert f("et-ciencia", categoria_por_id=categorias) == ""


def test_agrupar_por_eje_suma_y_engagement_medio():
    """Dos piezas de la misma línea: suma vis/inter y promedia engagement."""
    piezas = [
        _pieza("M1", "Gol de último minuto", 1000, 100, 10.0),
        _pieza("M2", "Resumen jornada", 3000, 150, 5.0),
    ]
    cubos = metricas_categoria.agrupar_por_eje(
        piezas,
        valor_por_contenido={"c1": "Futbol", "c2": "Futbol"},
        enlace_por_id={"M1": "c1", "M2": "c2"},
        enlace_por_titulo={},
        etiquetas_definidas=[{"id": "et-fut", "nombre": "Futbol"}],
        sin_valor=metricas_categoria.SIN_CATEGORIA,
    )
    por_nombre = {c["nombre"]: c for c in cubos}
    fut = por_nombre["Futbol"]
    assert fut["id"] == "et-fut"
    assert fut["piezas"] == 2
    assert fut["visualizaciones"] == 4000
    assert fut["interacciones"] == 250
    assert fut["engagement_pct"] == 7.5  # media de 10 y 5
    # La línea definida sin piezas (no hay) no aplica aquí; "Sin línea" queda en 0.
    assert por_nombre[metricas_categoria.SIN_CATEGORIA]["piezas"] == 0


def test_piezas_sin_linea_caen_en_cubo_sin_linea():
    """Pieza enlazada a contenido sin etiqueta categoria -> cubo 'Sin línea'."""
    piezas = [_pieza("M9", "Nota suelta", 500, 20, 4.0)]
    cubos = metricas_categoria.agrupar_por_eje(
        piezas,
        valor_por_contenido={},  # c desconocido / sin valor
        enlace_por_id={"M9": "c9"},
        enlace_por_titulo={},
        etiquetas_definidas=[],
        sin_valor=metricas_categoria.SIN_CATEGORIA,
    )
    por_nombre = {c["nombre"]: c for c in cubos}
    sin = por_nombre[metricas_categoria.SIN_CATEGORIA]
    assert sin["id"] == ""  # el cubo "Sin línea" no tiene id de etiqueta
    assert sin["piezas"] == 1
    assert sin["visualizaciones"] == 500
    assert sin["interacciones"] == 20


def test_pieza_no_enlazada_tambien_cae_en_sin_linea():
    """Pieza sin enlace por id ni por título -> 'Sin línea' (no rompe)."""
    piezas = [_pieza("M-DESCONOCIDA", "Pieza fuera de la consola", 100, 5, 5.0)]
    cubos = metricas_categoria.agrupar_por_eje(
        piezas,
        valor_por_contenido={"c1": "Futbol"},
        enlace_por_id={},
        enlace_por_titulo={},
        etiquetas_definidas=[{"id": "et-fut", "nombre": "Futbol"}],
        sin_valor=metricas_categoria.SIN_CATEGORIA,
    )
    por_nombre = {c["nombre"]: c for c in cubos}
    assert por_nombre[metricas_categoria.SIN_CATEGORIA]["piezas"] == 1
    assert por_nombre["Futbol"]["piezas"] == 0


def test_fallback_por_titulo_normalizado():
    """Sin enlace por id, casa por título normalizado (acentos/mayúsculas)."""
    piezas = [_pieza("SIN-ID", "  Presidencia HOY  ", 800, 80, 10.0)]
    titulo_norm = metricas_categoria._normalizar_titulo("Presidencia hoy")
    cubos = metricas_categoria.agrupar_por_eje(
        piezas,
        valor_por_contenido={"c5": "Presidencia"},
        enlace_por_id={},
        enlace_por_titulo={titulo_norm: "c5"},
        etiquetas_definidas=[{"id": "et-pres", "nombre": "Presidencia"}],
        sin_valor=metricas_categoria.SIN_CATEGORIA,
    )
    por_nombre = {c["nombre"]: c for c in cubos}
    assert por_nombre["Presidencia"]["piezas"] == 1
    assert por_nombre["Presidencia"]["visualizaciones"] == 800


def test_linea_definida_sin_piezas_aparece_con_ceros():
    """Una LÍNEA definida de la marca sin piezas en el periodo sale igualmente (0)."""
    cubos = metricas_categoria.agrupar_por_eje(
        [],
        valor_por_contenido={},
        enlace_por_id={},
        enlace_por_titulo={},
        etiquetas_definidas=[{"id": "et-vir", "nombre": "Virales"}],
        sin_valor=metricas_categoria.SIN_CATEGORIA,
    )
    por_nombre = {c["nombre"]: c for c in cubos}
    assert por_nombre["Virales"]["piezas"] == 0
    assert por_nombre["Virales"]["engagement_pct"] == 0.0
    assert por_nombre["Virales"]["id"] == "et-vir"


def test_orden_por_piezas_desc_y_sin_linea_al_final():
    """Ordena por nº de piezas desc; el cubo 'Sin línea' siempre al final."""
    piezas = [
        _pieza("A", "uno", 100, 10, 1.0),  # Futbol
        _pieza("B", "dos", 100, 10, 1.0),  # Futbol
        _pieza("C", "tres", 100, 10, 1.0),  # Presidencia
        _pieza("D", "cuatro", 100, 10, 1.0),  # sin línea
    ]
    cubos = metricas_categoria.agrupar_por_eje(
        piezas,
        valor_por_contenido={"cA": "Futbol", "cB": "Futbol", "cC": "Presidencia"},
        enlace_por_id={"A": "cA", "B": "cB", "C": "cC"},  # D no enlaza
        enlace_por_titulo={},
        etiquetas_definidas=[
            {"id": "1", "nombre": "Futbol"},
            {"id": "2", "nombre": "Presidencia"},
        ],
        sin_valor=metricas_categoria.SIN_CATEGORIA,
    )
    nombres = [c["nombre"] for c in cubos]
    assert nombres[0] == "Futbol"  # 2 piezas
    assert nombres[1] == "Presidencia"  # 1 pieza
    assert nombres[-1] == metricas_categoria.SIN_CATEGORIA  # siempre al final


def test_agrupar_categorias_y_origenes_combina_los_dos_ejes():
    """`agrupar_categorias_y_origenes` agrega el MISMO listado por categoría y por origen."""
    piezas = [
        _pieza("M1", "Gol", 1000, 100, 10.0),  # c1: Futbol / interno
        _pieza("M2", "Petición club", 2000, 100, 5.0),  # c2: Futbol / peticion_externa
    ]
    out = metricas_categoria.agrupar_categorias_y_origenes(
        piezas,
        categoria_por_contenido={"c1": "Futbol", "c2": "Futbol"},
        origen_por_contenido={"c1": "interno", "c2": "peticion_externa"},
        enlace_por_id={"M1": "c1", "M2": "c2"},
        enlace_por_titulo={},
        categorias_definidas=[{"id": "l1", "nombre": "Futbol"}],
        origenes_definidos=[
            {"id": "o1", "nombre": "interno"},
            {"id": "o2", "nombre": "peticion_externa"},
        ],
    )
    assert set(out) == {"categorias", "origenes"}
    categorias = {c["nombre"]: c for c in out["categorias"]}
    assert categorias["Futbol"]["piezas"] == 2
    assert categorias["Futbol"]["visualizaciones"] == 3000
    origenes = {c["nombre"]: c for c in out["origenes"]}
    assert origenes["interno"]["piezas"] == 1
    assert origenes["interno"]["visualizaciones"] == 1000
    assert origenes["peticion_externa"]["piezas"] == 1
    assert origenes["peticion_externa"]["visualizaciones"] == 2000


def test_valor_por_contenido_toma_solo_etiquetas_de_la_clase():
    """`_valor_por_contenido` resuelve solo las etiquetas de la clase pedida."""
    asignaciones = {"c1": ["et-fut", "et-interno"], "c2": ["et-interno"]}
    categorias = {"et-fut": "Futbol"}  # solo las de clase categoria
    out = metricas_categoria._valor_por_contenido(asignaciones, categorias)
    assert out == {"c1": "Futbol"}  # c2 no tiene etiqueta categoria


def test_categorias_por_pieza_mapea_solo_las_atribuibles(monkeypatch):
    """`categorias_por_pieza` resuelve la LÍNEA de cada pieza vía BD (monkeypatcheada).

    Cruza por `id_post_metricool` -> contenido y lee su `categoria` (eje único de línea). Una
    pieza sin contenido enlazado NO aparece en el mapa (el llamante usa "Sin línea"): honesto.
    """
    from keni_consola import repos

    monkeypatch.setattr(
        repos,
        "listar_publicacion",
        # La LÍNEA vive en `categoria` (id de la categoría), no en el tag asignado.
        lambda marca=None: [
            {"id": "c1", "titulo": "Gol", "id_post_metricool": "M1", "categoria": "et-vir"}
        ],
    )
    monkeypatch.setattr(repos, "listar_piezas_fila", lambda: [])
    monkeypatch.setattr(
        repos,
        "listar_etiquetas",
        lambda marca=None, clase=None, solo_activas=False: [{"id": "et-vir", "nombre": "Virales"}],
    )

    piezas = [
        {"id": "M1", "titulo": "Gol"},
        {"id": "M2", "titulo": "Pieza sin contenido"},
    ]
    salida = metricas_categoria.categorias_por_pieza("unotv", piezas)
    assert salida == {"M1": "Virales"}  # M2 no enlaza -> no aparece (Sin línea en el flujo)
