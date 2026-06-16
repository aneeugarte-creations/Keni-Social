"""Pipeline de contenido por marca (ADR 0011 F3, auto-producción).

BARREL del paquete. La implementación está repartida en submódulos por ETAPA —para que cada
fase se lea y testee aislada— y este `__init__` REEXPORTA toda la superficie pública (y los
símbolos privados que algún consumidor importa directamente), de modo que
`keni_consola.pipeline_contenido` resuelve igual que cuando era un módulo único. Submódulos:

  - `_comun`     — constantes del flujo, seams de `og:image`/artículo, sello de actividad por
                   etapa, autor de los lanzamientos y lecturas de temas/copy compartidas.
  - `_ref`       — proxy perezoso al paquete para honrar el monkeypatch de seams en los tests.
  - `_admitir`   — ADMITIR (CI): promueve HISTORIAS (clusters) ya verificadas del pool rankeado
                   a temas SIN copy, con dedup, cupos por marca/plan y caducidad (TTL).
  - `_verificar` — VERIFICAR (verificación): verifica la FUENTE de la HISTORIA (`claude -p`) ANTES de
                   admitir + verificación léxico del copy para la vista de runs (`verificacion_lexica`).
  - `_redactar`  — REDACTAR (CD): lanza el copy de los temas con verificación `no_verificado` sin copy
                   (+ los temas del news-pool sin copy).
  - `_revisar`   — revisión de calidad ADVISORY del copy (voz + coherencia), pre-avance.
  - `_avance`    — pasa los borradores COMPLETOS (copy + arte) a la cola de revisión humana.
  - `_barrido`   — orquesta los DOS procesos (investigación / producción) bajo single-flight
                   y arranca sus hilos demonio.

DOS PROCESOS (ADR 0011 F3)
==========================
El espinazo noticia->pieza son DOS loops independientes, cada uno con su gate, cadencia y
advisory lock (ver `_barrido`):

  • INVESTIGACIÓN — caducidad (TTL) -> VERIFICAR la fuente de las historias candidatas del pool
    (verificación sobre el CLUSTER, pre-admisión, asíncrona vía `claude -p`) -> ADMITIR las verificadas
    como temas (heredando su verificación). La frontera "verificación = investigación" vive en los datos: la
    admisión solo promueve historias ya verificadas (`no_verificado`/`saltada`); las `problema`
    nunca se materializan (fail-closed).
  • PRODUCCIÓN — REDACTAR el copy de los temas verificados -> ILUSTRAR (etapa de arte) -> AVANCE
    de los borradores completos a la cola de revisión humana.

ASINCRONÍA (DOS FASES)
======================
La verificación es asíncrona (`claude -p`): una historia verificada en un barrido NO tiene verificación en
ESE mismo barrido; el `procesar` lo persiste en el cluster y la admisión de un barrido POSTERIOR
la promueve. El estado vive en el cluster/tema: idempotente y auto-curativo.

SEGURO POR DISEÑO
=================
Cada etapa está GATEADA por su toggle bajo el maestro `KENI_MAQUINA` (apagar/encender en runtime
sin reiniciar). NADA se publica solo: el borrador nace `borrador`, el AVANCE solo lo mueve a la
cola de revisión HUMANA, y la publicación real sigue gated por `KENI_PUBLICAR_REAL`. El verificación
léxico (`verificacion_lexica`) es PURO y testeable.
"""

from __future__ import annotations

# Módulos/seams que la superficie histórica del módulo exponía (un consumidor podía hacer
# `pipeline_contenido.repos`, etc.); se reexportan para preservar el `dir()` exacto.
import logging
import re
import threading
from typing import Any

from .. import config, daemon_util, generaciones, libprompts, marcas, redes, repos
from ..dominio import dedup, jobspec
from ..dominio import generar as gen_dom
from ..dominio import verificar_fuente as dom_verificar
from ..estados import CLASE_CONTENIDO, ORIGENES_AUTOGEN
from ._barrido import (
    _ejecutar_barrido,
    _ejecutar_investigacion,
    _ejecutar_produccion,
    _intervalo_investigacion_segundos,
    _intervalo_produccion_segundos,
    _intervalo_segundos,
    ejecutar_ilustrar,
    ejecutar_avance,
    ejecutar_barrido,
    ejecutar_redactar,
    ejecutar_investigacion,
    ejecutar_produccion,
    ejecutar_verificar_clusters,
    iniciar_pipeline,
)
from ._comun import (
    _BACKOFF_ETAPA_SEG,
    _DEFAULT_VERIFICACION_CRITERIOS,
    _DIAS_DEDUP,
    _FETCH_ARTICULO,
    _FETCH_OG_IMAGE,
    _FORMATO_PIPELINE,
    _MAX_INTENTOS_ETAPA,
    _OG_MAX_BYTES,
    _OG_TIMEOUT_S,
    _RE_CONTENT,
    _RE_OG_IMAGE,
    _TITULO_VERIFICACION,
    _ETIQUETA_VERIFICACION,
    ETAPA_ILUSTRAR,
    ETAPA_REDACTAR,
    ETAPA_ADMITIR,
    ETAPA_VERIFICAR,
    ORIGEN_PIPELINE,
    PROMPT_VERIFICACION_ID,
    VERIFICACION_EN_CURSO,
    VERIFICACION_SALTADA,
    VERIFICACION_CADUCADA,
    TIPO_ACTIVIDAD,
    TIPO_PIPELINE,
    VERIFICACION_NO_VERIFICADO,
    VERIFICACION_PROBLEMA,
    _autor_pipeline,
    _copy_pendiente_leido,
    _extraer_og_image,
    _extraer_texto_articulo,
    _fetch_articulo_real,
    _fetch_og_image_real,
    _limpiar_snippet,
    _log,
    _tiene_copy,
    anotar_intento,
    admision_verificacion,
    en_backoff,
    intentos_de,
    marcar_fallo_etapa,
    registrar_etapa,
    temas_pipeline,
    ADMISION_VERIFICACION_ESTADOS,
)
from ._revisar import (
    avisos_calidad,
    avisos_coherencia,
    avisos_voz,
    verificar_calidad_pieza,
)
from ._redactar import (
    encadenar_ilustrar_tras_redactar,
    lanzar_redactar_de_tema,
    temas_autogen_sin_copy,
    temas_para_redactar,
)
from ._admitir import (
    _AVISO_SIN_LINEA,
    _auto_etiquetar_linea,
    _claves_dedup_marca,
    _copy_pendiente_de,
    _fetch_cuerpo,
    _nota_de_cluster,
    caducar_verificacion_clusters_en_curso,
    clusters_para_promover,
    clusters_pendientes_verificar,
    crear_tema_de_cluster,
    caducar_temas_viejos,
    promover_clusters_marca,
    temas_en_proceso,
)
from ._verificar import (
    _contexto_verificacion_fuente,
    asegurar_documento_verificacion,
    dom_verificacion_titulo,
    lanzar_verificar_cluster,
    verificacion_lexica,
)

# Superficie pública reexportada. Incluye los módulos/seams que la forma histórica del módulo
# exponía y los símbolos PRIVADOS que algún consumidor o test importa directamente: el `dir()`
# del barrel debe coincidir con el del módulo único original. `__all__` también marca cada
# nombre como REEXPORTADO (ruff no lo trata como import sin usar).
__all__ = [
    # módulos / seams reexportados (forma histórica: `pipeline_contenido.<modulo>`)
    "Any",
    "logging",
    "re",
    "threading",
    "config",
    "daemon_util",
    "generaciones",
    "marcas",
    "redes",
    "repos",
    "libprompts",
    "dedup",
    "gen_dom",
    "jobspec",
    "dom_verificar",
    "CLASE_CONTENIDO",
    "ORIGENES_AUTOGEN",
    "_log",
    # constantes de flujo
    "ORIGEN_PIPELINE",
    "TIPO_ACTIVIDAD",
    "TIPO_PIPELINE",
    "ETAPA_ADMITIR",
    "ETAPA_REDACTAR",
    "ETAPA_VERIFICAR",
    "ETAPA_ILUSTRAR",
    "PROMPT_VERIFICACION_ID",
    "VERIFICACION_EN_CURSO",
    "VERIFICACION_SALTADA",
    "VERIFICACION_CADUCADA",
    "VERIFICACION_NO_VERIFICADO",
    "VERIFICACION_PROBLEMA",
    "_DIAS_DEDUP",
    "_FORMATO_PIPELINE",
    "_TITULO_VERIFICACION",
    "_ETIQUETA_VERIFICACION",
    "_DEFAULT_VERIFICACION_CRITERIOS",
    # og:image (seams inyectables)
    "_RE_OG_IMAGE",
    "_RE_CONTENT",
    "_OG_MAX_BYTES",
    "_OG_TIMEOUT_S",
    "_FETCH_OG_IMAGE",
    "_fetch_og_image_real",
    "_extraer_og_image",
    # cuerpo del artículo + limpieza del snippet (seam inyectable + puras)
    "_FETCH_ARTICULO",
    "_fetch_articulo_real",
    "_extraer_texto_articulo",
    "_limpiar_snippet",
    # actividad / autor / lecturas compartidas
    "registrar_etapa",
    "admision_verificacion",
    "ADMISION_VERIFICACION_ESTADOS",
    "_autor_pipeline",
    "_copy_pendiente_leido",
    "_tiene_copy",
    "temas_pipeline",
    "_MAX_INTENTOS_ETAPA",
    "_BACKOFF_ETAPA_SEG",
    "intentos_de",
    "anotar_intento",
    "en_backoff",
    "marcar_fallo_etapa",
    # CI
    "_copy_pendiente_de",
    "_AVISO_SIN_LINEA",
    "_auto_etiquetar_linea",
    "crear_tema_de_cluster",
    "clusters_para_promover",
    "clusters_pendientes_verificar",
    "promover_clusters_marca",
    "temas_en_proceso",
    "caducar_temas_viejos",
    "caducar_verificacion_clusters_en_curso",
    "_claves_dedup_marca",
    "_nota_de_cluster",
    "_fetch_cuerpo",
    # verificación
    "verificacion_lexica",
    "asegurar_documento_verificacion",
    "dom_verificacion_titulo",
    "_contexto_verificacion_fuente",
    "lanzar_verificar_cluster",
    # CD
    "lanzar_redactar_de_tema",
    "temas_para_redactar",
    "temas_autogen_sin_copy",
    "encadenar_ilustrar_tras_redactar",
    # CALIDAD del copy (verificación advisory pre-avance)
    "avisos_voz",
    "avisos_coherencia",
    "avisos_calidad",
    "verificar_calidad_pieza",
    # barrido / daemon
    "ejecutar_barrido",
    "_ejecutar_barrido",
    "ejecutar_investigacion",
    "_ejecutar_investigacion",
    "ejecutar_produccion",
    "_ejecutar_produccion",
    "ejecutar_verificar_clusters",
    "ejecutar_redactar",
    "ejecutar_ilustrar",
    "ejecutar_avance",
    "_intervalo_segundos",
    "_intervalo_investigacion_segundos",
    "_intervalo_produccion_segundos",
    "iniciar_pipeline",
]
