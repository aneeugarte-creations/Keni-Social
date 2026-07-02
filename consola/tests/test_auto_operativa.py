"""Tests PUROS de la Fase 3 auto-operativa (sin DB ni red).

Cubren la lógica determinista de las tres automatizaciones, sin tocar Postgres:
  1. `rota.responsable_por_marca_hoy` — auto-asignación de responsable desde la rota.
  2. `metricas_pieza._es_reciente` — ventana del refresco proactivo por pieza.
  3. `dominio.eventos` — resumen humano de los nuevos eventos de alerta.

Los daemons y la capa de I/O (`auto_responsable`, `metricas_piezas_refresco`,
`alertas_rendimiento`) se ejercen con DB en los tests de integración; aquí queda
clavada la lógica pura, que es la que decide.
"""

from __future__ import annotations

from datetime import datetime

from keni_consola import auto_responsable, metricas_pieza
from keni_consola import rota as r
from keni_consola.dominio import eventos

# --------------------------------------------------------------------------- #
# 1. Núcleo puro de reparto desde la rota                                      #
#                                                                              #
# `rota.responsable_por_marca_hoy` es el kernel determinista del reparto PUSH  #
# (quién cubre una marca hoy). Hoy NO está cableado a la creación de contenido #
# —el modelo operativo es «la lista» (PULL) para TODAS las marcas— pero se     #
# conserva como el gancho de un eventual PUSH por marca, así que lo dejamos    #
# clavado. La capa de I/O (`responsable_automatico`) devuelve None siempre     #
# (test al final de esta sección).                                            #
# --------------------------------------------------------------------------- #

HOY = "2026-05-30"  # sábado real (irrelevante para esta función, pero estable)


def _turno(fecha: str, franja: str, miembro: str) -> dict:
    return {"fecha": fecha, "franja_id": franja, "miembro_id": miembro}


def test_responsable_elige_a_quien_cubre_la_marca_hoy():
    turnos = [_turno(HOY, "f1", "u2"), _turno("2026-05-29", "f1", "u1")]
    marcas = {"u1": ["unotv"], "u2": ["unotv"]}
    assert r.responsable_por_marca_hoy("unotv", HOY, turnos, marcas) == "u2"


def test_responsable_excluye_franja_de_descanso():
    turnos = [_turno(HOY, "fd", "u1")]
    marcas = {"u1": ["unotv"]}
    assert (
        r.responsable_por_marca_hoy("unotv", HOY, turnos, marcas, {"fd"}) is None
    )


def test_responsable_solo_de_la_marca_de_la_pieza():
    turnos = [_turno(HOY, "f1", "u1")]
    marcas = {"u1": ["nacion-gamer"]}
    assert r.responsable_por_marca_hoy("unotv", HOY, turnos, marcas) is None


def test_responsable_determinista_id_menor():
    turnos = [_turno(HOY, "f1", "u9"), _turno(HOY, "f1", "u3"), _turno(HOY, "f1", "u5")]
    marcas = {m: ["unotv"] for m in ("u3", "u5", "u9")}
    assert r.responsable_por_marca_hoy("unotv", HOY, turnos, marcas) == "u3"


def test_responsable_sin_marca_o_sin_turnos_es_none():
    turnos = [_turno(HOY, "f1", "u1")]
    marcas = {"u1": ["unotv"]}
    assert r.responsable_por_marca_hoy("", HOY, turnos, marcas) is None
    assert r.responsable_por_marca_hoy("unotv", HOY, [], marcas) is None
    # Nadie de turno hoy (turno de otro día).
    assert (
        r.responsable_por_marca_hoy(
            "unotv", HOY, [_turno("2026-05-29", "f1", "u1")], marcas
        )
        is None
    )


def test_responsable_automatico_nace_libre_en_todas_las_marcas():
    """«La lista» (reparto PULL) es universal: ninguna marca auto-asigna; la pieza nace LIBRE.

    Antes solo claro-sports devolvía None y el resto auto-asignaba desde la rota; ahora el
    modelo es uniforme y `responsable_automatico` devuelve None para CUALQUIER marca (y sin
    marca), sin consultar la rota."""
    assert auto_responsable.responsable_automatico("claro-sports", HOY) is None
    assert auto_responsable.responsable_automatico("unotv", HOY) is None
    assert auto_responsable.responsable_automatico("piso-15") is None
    assert auto_responsable.responsable_automatico("") is None


# --------------------------------------------------------------------------- #
# 2. Ventana del refresco proactivo por pieza                                  #
# --------------------------------------------------------------------------- #

AHORA = datetime(2026, 5, 30, 12, 0, 0)


def test_es_reciente_dentro_de_la_ventana():
    assert metricas_pieza._es_reciente("2026-05-20T10:00:00", AHORA, 30) is True


def test_no_es_reciente_fuera_de_la_ventana():
    assert metricas_pieza._es_reciente("2026-01-01T10:00:00", AHORA, 30) is False


def test_es_reciente_tolerante_con_fecha_vacia_o_invalida():
    # Sin fecha o con fecha basura: no excluimos (mejor refrescar de más).
    assert metricas_pieza._es_reciente("", AHORA, 30) is True
    assert metricas_pieza._es_reciente("no-es-fecha", AHORA, 30) is True


def test_listado_piezas_propaga_metricas_granulares(monkeypatch):
    """El drill-down de Analíticas aplana el desglose granular + formato de cada pieza.

    `listado_piezas_publicadas` hace un mapeo campo-a-campo del dict de rendimiento; las
    claves nuevas (likes/comentarios/.../formato) deben viajar a la salida. Mockeamos
    `rendimiento` (la cache/fuente) para no tocar Postgres ni la red: test puro."""
    rend = {
        "encontrado": True,
        "visualizaciones": 1000,
        "interacciones": 80,
        "engagement_pct": 8.0,
        "likes": 60,
        "comentarios": 12,
        "compartidos": 5,
        "guardados": 3,
        "video_views": 900,
        "tiempo_medio_vis_s": 7,
        "clics_enlace": 4,
        "seguidores_netos_atribuidos": 2,
        "formato": "carrusel",
        "url": "https://x/p",
        "publicado": "2026-05-20",
        "fuente": "metricool",
        "generado_en": "2026-05-30T12:00:00",
    }
    monkeypatch.setattr(metricas_pieza, "rendimiento", lambda m, r, i: rend)
    contenidos = [
        {
            "id": "c1",
            "titulo": "Pieza",
            "marca": "unotv",
            "marca_nombre": "UnoTV",
            "plataformas": [{"id": "p1", "red": "instagram", "id_post_metricool": "post-1"}],
        }
    ]
    filas = metricas_pieza.listado_piezas_publicadas(contenidos)
    assert len(filas) == 1
    fila = filas[0]
    assert fila["likes"] == 60
    assert fila["comentarios"] == 12
    assert fila["compartidos"] == 5
    assert fila["guardados"] == 3
    assert fila["video_views"] == 900
    assert fila["tiempo_medio_vis_s"] == 7
    assert fila["clics_enlace"] == 4
    assert fila["seguidores_netos_atribuidos"] == 2
    assert fila["formato"] == "carrusel"


def test_calculo_error_incluye_claves_granulares_en_none(monkeypatch):
    """El camino de ERROR de `_calcular` (la fuente revienta) deja las claves granulares
    presentes como None (sin dato), no ausentes: el aplanado nunca tropieza con un KeyError."""
    def _explota(*_a, **_k):
        raise RuntimeError("fuente caída")

    monkeypatch.setattr(metricas_pieza.servicio, "construir_metricas_pieza", _explota)
    # `marcas.id_metricas_de` puede tocar config; lo neutralizamos para que el test sea puro.
    monkeypatch.setattr(metricas_pieza.marcas, "id_metricas_de", lambda m: m)

    payload = metricas_pieza._calcular("unotv", "instagram", "post-x")
    assert payload["encontrado"] is False
    for clave in (
        "likes", "comentarios", "compartidos", "guardados", "video_views",
        "tiempo_medio_vis_s", "clics_enlace", "seguidores_netos_atribuidos", "formato",
    ):
        assert clave in payload and payload[clave] is None


# --------------------------------------------------------------------------- #
# 3. Resumen humano de los nuevos eventos de alerta                            #
# --------------------------------------------------------------------------- #




def test_evento_bajo_rendimiento_en_catalogo_y_resumen():
    assert "pieza.bajo_rendimiento" in eventos.TIPOS_EVENTO
    payload = eventos.construir_payload(
        "pieza.bajo_rendimiento",
        {"titulo": "Resumen del día", "red_nombre": "Instagram", "engagement_pct": 0.4},
    )
    assert "Resumen del día" in payload["resumen"]
    assert "0.4%" in payload["resumen"]
    assert "Instagram" in payload["resumen"]


def test_evento_revision_estancada_en_catalogo_y_resumen():
    assert "revision.estancada" in eventos.TIPOS_EVENTO
    payload = eventos.construir_payload(
        "revision.estancada",
        {"marca": "unotv", "marca_nombre": "UnoTV", "n": 5, "horas": 24},
    )
    assert "5 pieza(s)" in payload["resumen"]
    assert "24 h" in payload["resumen"]
    assert "UnoTV" in payload["resumen"]


# --------------------------------------------------------------------------- #
# 4. Cola de revisión estancada: conteo puro por marca + emisión agregada      #
# --------------------------------------------------------------------------- #


def _pieza_en_revision(marca: str, enviado: str, actualizado: str = "") -> dict:
    return {
        "marca": marca,
        "enviado_a_revision_en": enviado,
        "fecha_actualizacion": actualizado,
    }


def test_estancadas_por_marca_cuenta_solo_las_que_superan_el_umbral():
    from keni_consola.alertas_rendimiento import estancadas_por_marca

    ahora = datetime.fromisoformat("2026-07-01T12:00:00")
    pubs = [
        _pieza_en_revision("unotv", "2026-06-29T10:00:00"),   # ~50 h: estancada
        _pieza_en_revision("unotv", "2026-07-01T09:00:00"),   # 3 h: fresca
        _pieza_en_revision("claro-sports", "2026-06-30T11:00:00"),  # 25 h: estancada
        _pieza_en_revision("", "2026-06-01T00:00:00"),        # sin marca: se ignora
        _pieza_en_revision("unotv", "no-es-fecha"),           # ilegible: no cuenta
        # Legada sin sello de envío: cae a `fecha_actualizacion` (28 h -> estancada).
        _pieza_en_revision("unotv", "", "2026-06-30T08:00:00"),
    ]
    conteo = estancadas_por_marca(pubs, ahora=ahora, horas=24)
    assert conteo == {"unotv": 2, "claro-sports": 1}


def test_emitir_revision_estancada_agrega_por_marca_y_avisa(monkeypatch):
    from keni_consola import alertas_rendimiento as ar

    pubs = [
        _pieza_en_revision("unotv", "2026-01-01T00:00:00"),
        _pieza_en_revision("unotv", "2026-01-01T00:00:00"),
    ]
    monkeypatch.setattr(ar.repos, "listar_piezas", lambda **_k: pubs)
    emitidos: list[tuple] = []
    avisos: list[tuple] = []
    monkeypatch.setattr(
        ar.eventos,
        "emitir",
        lambda tipo, datos, **kw: emitidos.append((tipo, datos, kw)) or True,
    )
    monkeypatch.setattr(
        ar.notificaciones,
        "tras_revision_estancada",
        lambda marca, n, horas: avisos.append((marca, n, horas)),
    )

    assert ar._emitir_revision_estancada("2026-07-01", 24) == 1
    # UN evento agregado por marca, con clave idempotente marca+día.
    tipo, datos, kw = emitidos[0]
    assert tipo == "revision.estancada"
    assert datos["marca"] == "unotv" and datos["n"] == 2 and datos["horas"] == 24
    assert kw["clave_idempotencia"] == "revision.estancada:unotv:2026-07-01"
    # Y UN aviso in-app agregado (solo cuando el evento es NUEVO).
    assert avisos == [("unotv", 2, 24)]


def test_emitir_revision_estancada_ya_emitido_no_reavisa(monkeypatch):
    from keni_consola import alertas_rendimiento as ar

    pubs = [_pieza_en_revision("unotv", "2026-01-01T00:00:00")]
    monkeypatch.setattr(ar.repos, "listar_piezas", lambda **_k: pubs)
    monkeypatch.setattr(ar.eventos, "emitir", lambda *_a, **_k: False)  # ya emitido hoy
    avisos: list[tuple] = []
    monkeypatch.setattr(
        ar.notificaciones,
        "tras_revision_estancada",
        lambda *a: avisos.append(a),
    )
    assert ar._emitir_revision_estancada("2026-07-01", 24) == 0
    assert avisos == []
