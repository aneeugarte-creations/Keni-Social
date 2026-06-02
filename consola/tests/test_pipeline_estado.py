"""Tests de la observabilidad de la TUBERIA automatica (PURO, sin DB ni red).

`pipeline_estado.etapa_de_tema` deriva la ETAPA de cada tema (priorizada / generando copy /
generando arte / lista para revisar / fuera) de las senales que ya existen; `contar_por_etapa`
agrega. Es logica pura: dicts en memoria.
"""

from __future__ import annotations

from keni_consola import pipeline_estado as pe


def _item(**kw):
    base = {
        "id": "c1",
        "clase": "contenido",
        "origen": "equipo",
        "estado": "pendiente",
        "titulo": "Un tema",
    }
    base.update(kw)
    return base


def _plat(**kw):
    base = {"id": "p1", "estado": "pendiente", "copy": "", "imagen": ""}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# etapa_de_tema                                                                 #
# --------------------------------------------------------------------------- #


def test_priorizada_sin_copy_ni_etiqueta():
    """Tema auto-generable, sin copy y sin encolar -> en cola (priorizada)."""
    assert pe.etapa_de_tema(_item(), []) == pe.ETAPA_PRIORIZADA
    assert pe.etapa_de_tema(_item(), [_plat()]) == pe.ETAPA_PRIORIZADA


def test_generando_copy_si_etiquetado_autogen():
    """Sin copy todavia pero ya etiquetado `autogen` -> copy encolado (generando_copy)."""
    etapa = pe.etapa_de_tema(_item(), [_plat()], etiquetas=["autogen"])
    assert etapa == pe.ETAPA_GENERANDO_COPY


def test_generando_arte_con_copy_sin_imagen():
    """Tiene copy en alguna red pero le falta imagen -> arte en curso (generando_arte)."""
    etapa = pe.etapa_de_tema(_item(), [_plat(copy="Texto")])
    assert etapa == pe.ETAPA_GENERANDO_ARTE


def test_lista_para_revisar_con_copy_e_imagen():
    """Copy + imagen listos -> lista para revisar (aunque el estado siga 'pendiente')."""
    etapa = pe.etapa_de_tema(_item(), [_plat(copy="Texto", imagen="img.png")])
    assert etapa == pe.ETAPA_LISTA_REVISAR


def test_lista_para_revisar_si_ya_en_revision():
    """Una pieza ya en revision/aprobado salio de produccion -> lista para revisar."""
    for estado in ("en_revision", "aprobado", "programado", "publicado"):
        etapa = pe.etapa_de_tema(_item(), [_plat(estado=estado, copy="x")])
        assert etapa == pe.ETAPA_LISTA_REVISAR, estado


def test_la_etapa_mas_avanzada_gana_entre_redes():
    """Con varias redes en distinto punto, gana la mas avanzada (una lista basta)."""
    plats = [_plat(id="a", copy="x"), _plat(id="b", copy="x", imagen="img.png")]
    assert pe.etapa_de_tema(_item(), plats) == pe.ETAPA_LISTA_REVISAR


def test_fuera_si_tarea():
    assert pe.etapa_de_tema(_item(clase="tarea"), []) == pe.ETAPA_FUERA


def test_fuera_si_cerrado():
    assert pe.etapa_de_tema(_item(estado="hecha"), [_plat(copy="x")]) == pe.ETAPA_FUERA


def test_fuera_si_origen_no_autogenerable():
    """Alta tecleada legada (origen='') no entra a la tuberia automatica -> fuera."""
    assert pe.etapa_de_tema(_item(origen=""), []) == pe.ETAPA_FUERA


# --------------------------------------------------------------------------- #
# contar_por_etapa                                                              #
# --------------------------------------------------------------------------- #


def test_contar_agrega_por_etapa_con_forma_estable():
    items = [
        _item(id="prior"),
        _item(id="copy_en_curso"),
        _item(id="arte"),
        _item(id="lista"),
        _item(id="tarea", clase="tarea"),  # FUERA: no se cuenta por defecto
    ]
    plataformas = {
        "prior": [_plat()],
        "copy_en_curso": [_plat()],
        "arte": [_plat(copy="x")],
        "lista": [_plat(copy="x", imagen="img.png")],
        "tarea": [],
    }
    etiquetas = {"copy_en_curso": ["autogen"]}
    conteo = pe.contar_por_etapa(
        items, plataformas_por_item=plataformas, etiquetas_por_item=etiquetas
    )
    # Forma estable: todas las etapas de la tuberia presentes (en 0 si no aplica), SIN 'fuera'.
    assert set(conteo) == set(pe.ETAPAS[:-1])
    assert conteo[pe.ETAPA_PRIORIZADA] == 1
    assert conteo[pe.ETAPA_GENERANDO_COPY] == 1
    assert conteo[pe.ETAPA_GENERANDO_ARTE] == 1
    assert conteo[pe.ETAPA_LISTA_REVISAR] == 1
    assert pe.ETAPA_FUERA not in conteo


def test_contar_incluir_fuera_suma_los_excluidos():
    items = [_item(id="prior"), _item(id="tarea", clase="tarea")]
    conteo = pe.contar_por_etapa(
        items, plataformas_por_item={"prior": [_plat()], "tarea": []}, incluir_fuera=True
    )
    assert conteo[pe.ETAPA_PRIORIZADA] == 1
    assert conteo[pe.ETAPA_FUERA] == 1


def test_contar_vacio_devuelve_etapas_en_cero():
    conteo = pe.contar_por_etapa([])
    assert conteo == {e: 0 for e in pe.ETAPAS[:-1]}
