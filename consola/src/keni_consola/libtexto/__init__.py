"""Almacen UNICO de la Texto: PROMPTS + LINEA EDITORIAL (files-as-truth).

Reemplaza la autoria de "skills" (carpetas `SKILL.md` + `keni.yaml` con formularios) por un
almacen plano de DOCUMENTOS markdown editables con el mismo editor a pantalla completa. Cada
documento es un `.md` con frontmatter YAML + cuerpo (el cuerpo ES el contenido: el prompt, o
la pieza editorial). Conviven las DOS piezas clave del proyecto, distinguidas por `tipo`:

  - `prompt`    : una instruccion que se LANZA sobre contenido/areas (motor de generacion).
  - `editorial` : la LINEA EDITORIAL (voz de marca, plataformas, tropicalizacion, reglas).
                  Se ADJUNTA a un prompt al lanzarlo (auto por marca + ajustable).

LAYOUT EN DISCO (la jerarquia de carpetas ES la navegacion):

    <raiz>/
      prompts/<carpeta...>/<slug>.md          # tipo: prompt
      editorial/<carpeta...>/<slug>.md         # tipo: editorial
      .papelera/<id-aplanado>__<ts>.md         # borrados (restaurables)

El `id` de un documento es su ruta relativa POSIX bajo `<raiz>` SIN extension, p.ej.
`prompts/investigacion/resumen` o `editorial/marcas/unotv`. Es estable y legible.

FRONTMATTER (minimo; todo lo demas es el cuerpo):
    titulo, tipo, carpeta, creado, actualizado
    (solo editorial) clase ∈ {marca,voz,plataforma,tropicalizacion,reglas}, marcas: [ids]

SEGURIDAD: el id se sanea contra traversal (segmentos `[a-z0-9-]`, primer segmento = tipo
valido, sin `..`); las rutas se resuelven y se comprueba que caen ESTRICTAMENTE dentro de
`raiz()`; las escrituras son ATOMICAS (`io_atomico`). Todo error sale en espanol.

La raiz se sobreescribe con `KENI_TEXTO_DIR` (los tests lo apuntan a un tmp).

--

ESTE MÓDULO ES UN BARREL. La implementación vive en submódulos por categoría
(`_comun`, `_rutas`, `_io`, `_validacion`, `_crud`, `_versiones`, `_semilla`,
`_editorial`); aquí se re-exporta la superficie pública (Y los privados que algún
consumidor importa, p.ej. `_ruta_de_id` en los tests) para no cambiar nada de cara afuera.
"""

from __future__ import annotations

# Re-exporta los módulos estándar/internos que el módulo original exponía como atributos
# (consumidores o tests podrían acceder a `libtexto.re`, `libtexto.config`, etc.); se
# conservan para PARIDAD de superficie pública con el fichero monolítico previo.
import re as re
import shutil as shutil
from dataclasses import dataclass as dataclass
from dataclasses import field as field
from datetime import UTC as UTC
from datetime import datetime as datetime
from pathlib import Path as Path

import yaml as yaml

from .. import config as config
from .. import rutas as rutas
from .. import versionado as versionado
from ..io_atomico import escribir_atomico as escribir_atomico
from ._comun import (
    _CARPETAS_GLOBALES,
    _CLASES_GLOBALES,
    _PAPELERA,
    _RE_SLUG,
    CLASES,
    ESTADO_DEFECTO,
    ESTADOS,
    PILARES_EDITORIALES,
    PIPELINES,
    ROLES_PROMPT,
    SALIDAS,
    TIPOS,
    Documento,
    TextoError,
    _ahora_iso,
    _lista_str,
    _segmentos_validos,
    _slug,
)
from ._crud import (
    _coincide_busqueda,
    _coincide_carpeta,
    borrar,
    crear,
    guardar,
    listar,
    listar_carpetas,
    listar_papelera,
    obtener,
    restaurar,
    vaciar_papelera,
)
from ._editorial import (
    editoriales_de_marca,
    editoriales_de_pipeline,
    previsualizar_pipeline,
    prompt_base_de,
    validacion_editorial,
)
from ._io import _leer, _parsear, _serializar
from ._rutas import (
    _carpeta_relativa,
    _id_de_ruta,
    _id_unico,
    _ruta_de_id,
    migrar_dir_legacy,
    raiz,
)
from ._semilla import (
    cuerpo_efectivo,
    dir_semilla,
    importar_semilla,
    obtener_semilla,
)
from ._validacion import (
    _validar_clase,
    _validar_estado,
    _validar_etiquetas,
    _validar_marcas,
    _validar_pipelines,
    _validar_prioridad,
    _validar_rol,
)
from ._versiones import historial, restaurar_version, version

# `__all__` lista TODA la superficie re-exportada por el barrel: la pública Y los
# privados que algún consumidor importa (p.ej. tests hacen `from libtexto import
# _ruta_de_id`). Incluirlos aquí preserva la superficie del módulo monolítico y marca
# las re-exportaciones como intencionadas (no son imports muertos).
__all__ = [
    # constantes / tipos (_comun)
    "TIPOS",
    "CLASES",
    "SALIDAS",
    "ESTADOS",
    "ESTADO_DEFECTO",
    "ROLES_PROMPT",
    "PIPELINES",
    "PILARES_EDITORIALES",
    "Documento",
    "TextoError",
    "_CARPETAS_GLOBALES",
    "_CLASES_GLOBALES",
    "_PAPELERA",
    "_RE_SLUG",
    "_ahora_iso",
    "_lista_str",
    "_segmentos_validos",
    "_slug",
    # rutas / ids (_rutas)
    "raiz",
    "migrar_dir_legacy",
    "_carpeta_relativa",
    "_id_de_ruta",
    "_id_unico",
    "_ruta_de_id",
    # io (_io)
    "_leer",
    "_parsear",
    "_serializar",
    # validacion (_validacion)
    "_validar_clase",
    "_validar_estado",
    "_validar_etiquetas",
    "_validar_marcas",
    "_validar_pipelines",
    "_validar_prioridad",
    "_validar_rol",
    # crud (_crud)
    "listar",
    "obtener",
    "listar_carpetas",
    "crear",
    "guardar",
    "borrar",
    "listar_papelera",
    "restaurar",
    "vaciar_papelera",
    "_coincide_busqueda",
    "_coincide_carpeta",
    # versiones (_versiones)
    "historial",
    "version",
    "restaurar_version",
    # editorial / pipelines (_editorial)
    "editoriales_de_marca",
    "editoriales_de_pipeline",
    "prompt_base_de",
    "previsualizar_pipeline",
    "validacion_editorial",
    # semilla (_semilla)
    "dir_semilla",
    "obtener_semilla",
    "cuerpo_efectivo",
    "importar_semilla",
]
