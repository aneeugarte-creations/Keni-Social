"""Estudio de imagen — dominio: componer prompt + correr los motores relocalizados.

BARREL del paquete. RE-EXPORTA la superficie completa (pública Y privada referenciada desde
fuera) para no cambiar el comportamiento: quien importe `from ..dominio import estudio_imagen`
o haga `estudio_imagen.X` sigue viéndolo todo.

Mapa de submódulos:
  - `_comun`     : constantes de formato, `EstudioError`, helpers de subproceso/materialización.
  - `_motores`   : `editar` (Pillow) — recorte/adaptación determinista de la imagen de una pieza.
  - `_plantilla` : composición de marca DETERMINISTA por SPEC con el motor Node.
  - `_documento` : render del DOCUMENTO de capas (editor pro), plantilla con fotos, fronteras.

El arte PERTENECE a la pieza: una imagen es un objeto del almacen de media (`<uuid>.png`) y se
asocia a la pieza por `pieza.imagen`. La GENERACIÓN por IA NO vive aquí: corre por
`media.generar_imagen` (auto-ilustración del pipeline y botón «Generar con IA»); este paquete solo
COMPONE/RENDERIZA de forma determinista (plantilla de marca + documento de capas) y RECORTA.
"""
# ruff: noqa: F401  -- BARREL: todo lo importado aquí es re-export intencional de la superficie
# pública Y privada (consumidores hacen `estudio_imagen.X`, incluido `estudio_imagen._privado`).

from __future__ import annotations
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ... import (
    formatos_red,
    generaciones,
    libprompts,
    marca_assets,
    marcas,
    media,
    plantillas_marca,
    repos,
)
from ...motores.estudio_imagen import documento as doc_capas
from ...motores.estudio_imagen import spec_plantilla
from .. import generar, jobspec
from ._comun import (
    _ENV_NODE_BIN,
    _FORMATO_POR_RED,
    _FORMATOS_COMPONER,
    _MARCAS_VISUALES,
    _TIMEOUT_COMPONER_S,
    _TIMEOUT_EDITAR_S,
    ASPECTOS,
    FORMATOS,
    OPS_EDITAR,
    REGLAS_IMAGEN,
    EstudioError,
    _correr_motor,
    _correr_render_documento,
    _correr_render_node,
    _importar_salidas,
    _materializar,
    _materializar_logo,
    _node_bin,
    _nombre_local_plano,
    _resultado,
    _ruta_motor,
    _ruta_render_documento,
    _ruta_render_node,
    formato_por_red,
    marca_tiene_plantilla,
)
from ._documento import (
    _doc_plantilla_con_fotos,
    _fotos_de,
    _fuentes_extra_de_marca,
    _refs_imagenes,
    componer_desde_plantilla,
    componer_desde_plantilla_bytes,
    documento_desde_plantilla,
    documento_tiene_hueco,
    normalizar_opciones_export,
    parsear_encuadre,
    renderizar_documento,
    renderizar_documento_bytes,
    validar_capas,
    validar_documento,
)
from ._motores import _argv_editar, editar
from ._plantilla import (
    _componer_node,
    _componer_node_bytes,
    componer,
    componer_bytes,
    previsualizar_spec_bytes,
)

__all__ = [
    # Constantes / error de dominio
    "REGLAS_IMAGEN",
    "FORMATOS",
    "ASPECTOS",
    "OPS_EDITAR",
    "EstudioError",
    "marca_tiene_plantilla",
    "formato_por_red",
    # Edición determinista (recorte/adaptación de imagen de pieza)
    "editar",
    # Composición de marca por SPEC (Node)
    "componer",
    "componer_bytes",
    "previsualizar_spec_bytes",
    # Documento de capas / plantilla con fotos / fronteras
    "normalizar_opciones_export",
    "renderizar_documento",
    "renderizar_documento_bytes",
    "componer_desde_plantilla",
    "componer_desde_plantilla_bytes",
    "parsear_encuadre",
    "validar_documento",
    "documento_tiene_hueco",
    "validar_capas",
    "documento_desde_plantilla",
]
