"""Dominio AGENTES de la Consola Keni: el conjunto ABIERTO de agentes.

La Ola 2a unifico el contenido por MARCA en `<KENI_CONSOLA_RAIZ>/<marca>/`
(piezas, plantillas, RSS, hashtags, franjas, historial). Este modulo da el
salto conceptual: la carpeta de cada agente es su espacio de trabajo, con:

  - `CLAUDE.md`              contexto principal del agente (su "memoria").
  - `contexto/<nombre>.md`   sub-contextos opcionales (apuntes adicionales).
  - `runs/<id>.yaml`         ejecuciones de un prompt en esa carpeta.

DOS clases de agente conviven bajo la MISMA raiz:

  - MARCA-AGENTE: las 5 marcas del catalogo unico (`marcas.opciones()`) vienen DE
    SERIE. Su `id` = id de marca; `es_marca=True`; carpeta `<raiz>/<marca-id>/`;
    nombre del catalogo. Producen copy/piezas/metricas. NO se borran ni se
    renombran. Se reconocen por `marcas.es_marca(carpeta.name)`.

  - AGENTE GENERICO: se puede CREAR/CONECTAR/RENOMBRAR/BORRAR. Vive en
    `<raiz>/<slug>/` con un MANIFIESTO `.keni/agente.yaml` `{nombre, tipo, creado}`.
    `es_marca=False`; `id` = slug de la CARPETA (estable). Renombrar cambia solo el
    `nombre` (display) del manifiesto, NO el slug/carpeta (para no romper
    referencias). `n_publicaciones=0` (no es una marca).

DESCUBRIMIENTO: la lista de agentes = las 5 marcas ∪ las subcarpetas de `<raiz>`
que tengan `.keni/agente.yaml` y cuyo nombre de carpeta NO sea un id de marca.
Marcas primero (orden del catalogo), luego genericos (recientes primero por
`creado`, luego slug). El `id` de un agente (marca o generico) SIEMPRE resuelve.

LAYOUT (raiz = `KENI_CONSOLA_RAIZ`, def `~/keni-proyectos`; misma que `ficheros.py`):

    <raiz>/<marca|slug>/
        CLAUDE.md
        .keni/agente.yaml          # SOLO genericos: {nombre, tipo, creado}
        contexto/<nombre>.md
        runs/<id>.yaml

SEGURIDAD: todo cae DENTRO de la raiz de agentes. El id de una marca se valida
contra el catalogo; el slug de un generico se DERIVA del nombre y pasa por la
validacion anti-escape/caracteres de `_rutas.resolver_slug_agente` (sin `/`, `\\`,
`..`, control, comodines, ni rutas absolutas) y la ruta resuelta debe quedar
estrictamente dentro de la raiz (`is_relative_to`). Conectar acepta SOLO el nombre de una subcarpeta
existente (anti-traversal). Borrar es SOLO para genericos y SOLO dentro de la raiz
(`rmtree` defensivo). La escritura de CLAUDE.md, sub-contextos, runs y manifiesto es
DEFENSIVA (destino dentro de la carpeta del agente) y ATOMICA (tmp + os.replace)
como en `ficheros.py`/`secretos.py`. Sin shell. Errores en espanol.

ESTRUCTURA (refactor sin cambio de comportamiento): el dominio se reparte en
submodulos privados y este `__init__` es un BARREL que re-exporta su superficie
publica (y los privados referenciados desde fuera) para preservar `keni_consola.agentes.*`:

  - `_comun`     imports, excepciones, constantes, rutas, plantillas, IO atomica.
  - `_genericos` identidad/CRUD de agentes, resumen/listado, enumeracion para monitor.
  - `_contexto`  CLAUDE.md principal y sub-contextos `contexto/*.md`.
  - `_runs`      runs `runs/<id>.yaml`, su indice y la monitorizacion/agregados.
"""

from __future__ import annotations

# Imports re-exportados para PARIDAD de superficie con el modulo original (algun
# consumidor podria leer p.ej. `agentes.Path`/`agentes.indice`). No `import *`.
import re  # noqa: F401
import shutil  # noqa: F401
import unicodedata  # noqa: F401
import uuid  # noqa: F401
from datetime import datetime  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any  # noqa: F401

import yaml  # noqa: F401
from keni_shared.esquema_yaml import migrar, sellar  # noqa: F401

from .. import indice, marcas, repos  # noqa: F401
from ..io_atomico import escribir_atomico  # noqa: F401
from ._comun import (  # noqa: F401
    _ARCHIVO_MANIFIESTO,
    _DIR_CONTEXTO,
    _DIR_KENI,
    _DIR_RUNS,
    _PLANTILLA_DEF,
    _PLANTILLA_GENERICA_DEF,
    _PLANTILLA_POR_MARCA,
    _RE_NOMBRE_CONTEXTO,
    MODOS_RUN,
    AgenteExistente,
    AgenteInvalido,
    NombreAgenteInvalido,
    NombreContextoInvalido,
    OperacionNoPermitida,
    _escribir_texto_atomico,
    _escribir_yaml_atomico,
    _leer_yaml,
    _raiz,
    _render_claude_md,
    _render_claude_md_generico,
    _ruta_dentro_raiz,
    _tipo_plantilla,
    ahora_iso,
    nuevo_run_id,
)
from ._contexto import (  # noqa: F401
    _dir_contexto,
    _resolver_contexto,
    _reparar_nombre_contexto,
    borrar_contexto,
    guardar_claude_md,
    guardar_contexto,
    leer_claude_md,
    listar_contextos,
)
from ._genericos import (  # noqa: F401
    _agentes_genericos,
    _agentes_para_runs,
    _contar,
    _escribir_manifiesto,
    _leer_manifiesto,
    _mapa_nombres_agentes,
    _ruta_manifiesto,
    _slug_de_nombre,
    _slug_seguro,
    _slugs_genericos,
    borrar_agente,
    carpeta_agente,
    conectar_agente,
    crear_agente,
    es_agente,
    es_generico,
    listar_agentes,
    renombrar_agente,
    resumen_agente,
)
from ._runs import (  # noqa: F401
    _asegurar_indice_runs,
    _dir_runs,
    _entrada_indice_run,
    _id_indice_run,
    _indexar_run,
    _metricas_run,
    _parsear_run,
    _runs_en_disco,
    _sumar_metrica,
    actualizar_run,
    agregados_runs,
    contar_runs_globales,
    guardar_run,
    listar_runs,
    listar_runs_globales,
    obtener_run,
    reindexar_runs,
)

__all__ = [
    # excepciones
    "AgenteInvalido",
    "NombreAgenteInvalido",
    "AgenteExistente",
    "OperacionNoPermitida",
    "NombreContextoInvalido",
    # constantes
    "MODOS_RUN",
    # identidad / CRUD de agentes
    "es_agente",
    "es_generico",
    "carpeta_agente",
    "crear_agente",
    "conectar_agente",
    "renombrar_agente",
    "borrar_agente",
    "resumen_agente",
    "listar_agentes",
    # contexto editorial
    "leer_claude_md",
    "guardar_claude_md",
    "listar_contextos",
    "guardar_contexto",
    "borrar_contexto",
    # runs
    "nuevo_run_id",
    "ahora_iso",
    "guardar_run",
    "actualizar_run",
    "listar_runs",
    "obtener_run",
    "reindexar_runs",
    "listar_runs_globales",
    "contar_runs_globales",
    "agregados_runs",
]
