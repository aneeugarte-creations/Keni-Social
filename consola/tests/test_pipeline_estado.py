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


# --------------------------------------------------------------------------- #
# etapa_de_pieza (por PIEZA, para el Feed · Flujo C follow-up #3)               #
# --------------------------------------------------------------------------- #


def _pieza(**kw):
    """Forma pública mínima de una publicacion (lo que mira `etapa_de_pieza`)."""
    base = {"estado": "borrador", "falta_copy": True, "falta_imagen": True}
    base.update(kw)
    return base


def test_pieza_sin_copy_generando_copy():
    assert pe.etapa_de_pieza(_pieza(falta_copy=True)) == pe.ETAPA_GENERANDO_COPY


def test_pieza_con_copy_sin_imagen_generando_arte():
    etapa = pe.etapa_de_pieza(_pieza(falta_copy=False, falta_imagen=True))
    assert etapa == pe.ETAPA_GENERANDO_ARTE


def test_pieza_con_copy_e_imagen_aunque_pendiente_es_lista():
    # Copy + imagen ya hechos pero todavía en `pendiente` (auto-avance no la movió): está LISTA,
    # NO "generando copy" (regresión del caso por defecto que mentía con copy e imagen presentes).
    etapa = pe.etapa_de_pieza(_pieza(estado="pendiente", falta_copy=False, falta_imagen=False))
    assert etapa == pe.ETAPA_LISTA_REVISAR


def test_pieza_video_sin_video_es_generando_arte():
    # En VÍDEO el asset es el vídeo (`falta_video`), no la foto: sin vídeo NO está lista, aunque
    # `falta_imagen` sea False (la imagen es opcional en vídeo). Caso típico tras cambiar de
    # formato foto->vídeo: la pieza debe salir de "lista para revisar".
    etapa = pe.etapa_de_pieza(
        _pieza(formato="video", estado="pendiente", falta_copy=False, falta_imagen=False, falta_video=True)
    )
    assert etapa == pe.ETAPA_GENERANDO_ARTE


def test_pieza_video_con_video_es_lista_aunque_falte_imagen():
    # Con el vídeo presente, la pieza de vídeo está lista aunque `falta_imagen` (imagen opcional).
    etapa = pe.etapa_de_pieza(
        _pieza(formato="video", estado="pendiente", falta_copy=False, falta_imagen=True, falta_video=False)
    )
    assert etapa == pe.ETAPA_LISTA_REVISAR


def test_pieza_en_revision_lista_para_revisar():
    assert pe.etapa_de_pieza(_pieza(estado="en_revision")) == pe.ETAPA_LISTA_REVISAR


def test_pieza_estados_terminales_mapean_a_etapa():
    assert pe.etapa_de_pieza(_pieza(estado="aprobado")) == pe.ETAPA_APROBADA
    assert pe.etapa_de_pieza(_pieza(estado="programado")) == pe.ETAPA_PROGRAMADA
    assert pe.etapa_de_pieza(_pieza(estado="publicado")) == pe.ETAPA_PUBLICADA


def test_pieza_etapa_siempre_de_etapas_pieza():
    """Sea cual sea la entrada, la etapa devuelta es un literal del contrato del feed."""
    for estado in ("borrador", "en_revision", "aprobado", "programado", "publicado"):
        assert pe.etapa_de_pieza(_pieza(estado=estado)) in pe.ETAPAS_PIEZA
