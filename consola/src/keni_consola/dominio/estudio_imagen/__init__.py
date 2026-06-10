"""Estudio de imagen — dominio: componer prompt + correr los motores relocalizados.

BARREL del paquete. El módulo `dominio/estudio_imagen.py` (~1010 líneas) se partió por
responsabilidad en submódulos privados; este `__init__.py` RE-EXPORTA la superficie completa
(pública Y privada referenciada desde fuera) para no cambiar el comportamiento ni la superficie:
quien importe `from ..dominio import estudio_imagen` o haga `estudio_imagen.X` sigue viéndolo todo.

Mapa de submódulos:
  - `_comun`        : constantes de formato, `EstudioError`, helpers de subproceso/materialización.
  - `_prompt`       : composición del prompt generativo + `generar_variante` (IA).
  - `_motores`      : `editar` (Pillow), `expandir` y `retocar` (outpainting/retoque IA).
  - `_plantilla`    : composición de marca DETERMINISTA por SPEC con el motor Node.
  - `_documento`    : render del DOCUMENTO de capas (editor pro), plantilla con fotos, fronteras.
  - `_set_formatos` : set multi-formato "de un tiro" desde UNA imagen aportada (Fase 3).
  - `_revision`     : revisión legal/editorial con `claude -p` (gate humano).

Superficie de primera clase que reemplaza a la skill `estudio-imagen` (borrada con el resto del
sistema de skills). El arte PERTENECE a la pieza: una imagen es un objeto del almacen de media
(`<uuid>.png`) y se asocia a la publicacion por `publicacion.imagen`.

Tres capacidades, todas reutilizando la infra existente (sin red en tests):
  - GENERAR variantes (IA)    -> `media.generar_imagen` (un solo punto de red, mockeable).
  - EDITAR (determinista)     -> motor `motores/estudio_imagen/editar.py` por subproceso.
  - EXPANDIR (outpainting IA)  -> motor `motores/estudio_imagen/expandir.py` por subproceso.
"""
# ruff: noqa: F401  -- BARREL: todo lo importado aquí es re-export intencional de la superficie
# pública Y privada (consumidores hacen `estudio_imagen.X`, incluido `estudio_imagen._privado`).

from __future__ import annotations

# Imports de módulo conservados (paridad de `dir()`: el módulo original los exponía como
# atributos, y algún flujo/test podría tocarlos como `estudio_imagen.<modulo>`).
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
    libtexto,
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
    _ESTILO_MARCA,
    _FORMATO_POR_RED,
    _FORMATOS_COMPONER,
    _MARCAS_VISUALES,
    _TIMEOUT_COMPONER_S,
    _TIMEOUT_EDITAR_S,
    _TIMEOUT_EXPANDIR_S,
    _TIMEOUT_RETOCAR_S,
    ASPECTOS,
    FORMATOS,
    OPS_EDITAR,
    PROMPT_IMAGEN_DEFECTO,
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
from ._motores import _argv_editar, editar, expandir, retocar
from ._plantilla import (
    _componer_node,
    _componer_node_bytes,
    componer,
    componer_bytes,
    previsualizar_spec_bytes,
)
from ._prompt import componer_prompt, generar_variante
from ._revision import _instruccion_revision, revisar
from ._set_formatos import _encajar_a_lienzo, _logo_de_marca, generar_set_formatos

__all__ = [
    # Constantes / error de dominio
    "REGLAS_IMAGEN",
    "FORMATOS",
    "ASPECTOS",
    "OPS_EDITAR",
    "PROMPT_IMAGEN_DEFECTO",
    "EstudioError",
    "marca_tiene_plantilla",
    "formato_por_red",
    # Prompt / generación IA
    "componer_prompt",
    "generar_variante",
    # Motores (editar / expandir / retocar)
    "editar",
    "expandir",
    "retocar",
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
    # Set multi-formato
    "generar_set_formatos",
    # Revisión
    "revisar",
]
