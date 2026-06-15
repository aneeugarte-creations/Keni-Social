"""Pipeline de contenido CI→CD→QA por marca (fase3 auto-produccion, Flujo "tubería").

BARREL del paquete. La implementación está repartida en submódulos por ETAPA —para que cada
fase se lea y testee aislada— y este `__init__` REEXPORTA toda la superficie pública (Y los
símbolos privados que algún consumidor importa directamente), de modo que `keni_consola
.pipeline_contenido` resuelve EXACTAMENTE igual que cuando era un módulo único. Submódulos:

  - `_comun`   — constantes del flujo, seams de `og:image`, sello de actividad por etapa,
                 autor de los lanzamientos y lecturas de temas/copy compartidas entre fases.
  - `_ingesta` — CI: selección pura de items + creación de temas (sin copy) + dedup.
  - `_qa`      — QA: criba de la FUENTE (pre-copy, `claude -p`) + veredicto léxico.
  - `_copy`    — CD: lanza copy de los temas con QA `no_verificado` (+ news-pool autogen).
  - `_barrido` — orquesta CI→QA→CD→arte→avance bajo single-flight, y el hilo demonio.

PROBLEMA QUE RESUELVE
=====================
Los daemons existentes (`autogen_copy`, `autogen_arte`, `radar_auto`) automatizan PASOS
sueltos del tablero, pero no hay un flujo que, por MARCA, lea sus fuentes RSS frescas y las
lleve de extremo a extremo —ingesta → creación de copy+arte de marca → validación
automática— dejando BORRADORES listos para la aprobación humana, y que REGISTRE cada ETAPA
como un pipeline de CI/CD (visible en "Actividad IA"). Este daemon (espejo de `autogen_copy`/
`radar_auto`) hace exactamente eso, cada N horas y por marca con feeds activos:

  - CI — RECOLECCIÓN DE FUENTES: lee items frescos (no usados) de los feeds activos de la marca,
    elige hasta un CAP, y CREA un `contenido` (tema) por item SIN generar copy todavía. Para
    feeds de MARCA PROPIA (`propia`) resuelve la `og:image` del artículo (la foto real); para
    feeds de no-propia / tendencia, sin imagen. Guarda en el tema (`copy_pendiente`, JSON) los
    parámetros que la fase CD necesitará para lanzar el copy. Marca el item del feed como USADO
    (dedup). Registra UNA entrada de actividad etapa="CI".
  - QA — CRIBA DE LA FUENTE (pre-copy): por cada TEMA nuevo sin veredicto, lanza un `claude -p`
    que evalúa la NOTA DE ORIGEN (no el copy: aún no existe) contra el DOCUMENTO de Texto
    de criterios. Es PERMISIVO y devuelve un veredicto ESTRUCTURADO con dos salidas:
    `no_verificado` (nada de peso en contra: seguir; la pieza llevará ⚠️ "no verificado") o
    `problema` (algo de peso: NO se genera copy; el tema se marca ❗ con los hallazgos). Por
    defecto `no_verificado` cuando hay duda (permisivo). El veredicto + hallazgos se PERSISTEN
    sobre el tema (`qa_veredicto`/`qa_hallazgos`). Sin tope por etapa (el volumen lo regula la
    admisión). Registra etapa="QA" por tema, enlazada a la generación (stream).
  - CD — CREACIÓN DE CONTENIDO: por cada tema cuya QA salió `no_verificado` y que aún no tiene
    copy, lanza la generación de copy por el camino PROBADO (`dominio.generar.lanzar_copy`) con
    los parámetros guardados (`imagen_fuente` para marca propia). NUNCA genera copy de un tema
    `problema` (ahorra tokens). Registra etapa="CD" por tema y limpia `copy_pendiente`.

ORDEN Y ASINCRONÍA (DOS FASES ENTRE BARRIDOS)
=============================================
La QA es asíncrona (`claude -p`): un tema cribado en un barrido NO tiene veredicto en ESE mismo
barrido. Por eso el flujo es de DOS FASES entre barridos: la fase QA marca el tema; la fase CD
de un barrido POSTERIOR actúa sobre los temas `no_verificado` sin copy. Se eligió esta vía
(no encadenar la QA→copy dentro del worker) por ser la más limpia y reusar el mismo patrón
async que ya tenía el QA editorial: el estado vive en el TEMA, es idempotente y auto-curativo.

El borrador queda `borrador` para el paso de APROBACIÓN HUMANA en la parrilla. Nada se
publica; NUNCA se llama a Metricool.

SEGURO POR DISEÑO (CONSERVADOR)
===============================
  - GATEADO: el daemon solo barre con `KENI_PIPELINE_REDACTAR=1` (def OFF). Sin el flag, el
    comportamiento existente NO cambia (este modulo es ADITIVO: nadie lo invoca con el flag
    ausente). El hilo arranca SIEMPRE y comprueba el flag en cada ciclo (apagar/encender en
    runtime sin reiniciar).
  - SOLO LECTURA DE FUENTES: la ingesta solo LEE feeds RSS y resuelve `og:image`; el guard
    SSRF de los feeds sigue aplicando aguas arriba (`http_feed`).
  - CAP por barrido y por marca (`KENI_PIPELINE_MAX`, def 3): cada item lanza un `claude -p`;
    el cap evita avalanchas. El cap del worker (`KENI_MAX_JOBS`) sigue aplicando aguas abajo.
  - DEDUP: al crear el tema (CI), el item del feed se marca USADO (`repos.marcar_item`); el
    siguiente barrido lo salta. La ingesta lee `claves_vistas` para no re-elegir lo ya usado.
  - NO PUBLICA: el borrador nace `borrador` y pasa por la MISMA revisión/aprobación humana;
    la publicación real (Metricool) sigue gated por `KENI_PUBLICAR_REAL` (no se toca aquí).

La SELECCIÓN de items (`items_ingeribles`) y el VEREDICTO léxico (`qa_lexico`) son PUROS y
testeables. El LANZAMIENTO reutiliza `lanzar_copy` sin tocar su contrato: bajo riesgo.
"""

from __future__ import annotations

# Módulos/seams que la superficie histórica del módulo exponía (un consumidor podía hacer
# `pipeline_contenido.repos`, etc.); se reexportan para preservar el `dir()` exacto.
import logging
import re
import threading
from typing import Any

from .. import config, daemon_util, generaciones, libtexto, marcas, redes, repos
from ..dominio import dedup, jobspec
from ..dominio import generar as gen_dom
from ..dominio import qa_editorial as dom_qa
from ..estados import CLASE_CONTENIDO, ORIGENES_AUTOGEN
from ._barrido import (
    _ejecutar_barrido,
    _ejecutar_investigacion,
    _ejecutar_produccion,
    _intervalo_investigacion_segundos,
    _intervalo_produccion_segundos,
    _intervalo_segundos,
    ejecutar_arte,
    ejecutar_avance,
    ejecutar_barrido,
    ejecutar_cd,
    ejecutar_investigacion,
    ejecutar_produccion,
    ejecutar_qa_clusters,
    iniciar_pipeline,
)
from ._comun import (
    _BACKOFF_ETAPA_SEG,
    _DEFAULT_QA_CRITERIOS,
    _DIAS_DEDUP,
    _FETCH_ARTICULO,
    _FETCH_OG_IMAGE,
    _FORMATO_PIPELINE,
    _MAX_INTENTOS_ETAPA,
    _OG_MAX_BYTES,
    _OG_TIMEOUT_S,
    _RE_CONTENT,
    _RE_OG_IMAGE,
    _TITULO_QA,
    _ETIQUETA_QA,
    ETAPA_ARTE,
    ETAPA_CD,
    ETAPA_CI,
    ETAPA_QA,
    ORIGEN_PIPELINE,
    PROMPT_QA_ID,
    QA_EN_CURSO,
    QA_SALTADA,
    QA_CADUCADA,
    TIPO_ACTIVIDAD,
    TIPO_PIPELINE,
    VERDICTO_NO_VERIFICADO,
    VERDICTO_PROBLEMA,
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
    embudo_qa,
    en_backoff,
    intentos_de,
    marcar_fallo_etapa,
    registrar_etapa,
    temas_pipeline,
    EMBUDO_QA_ESTADOS,
)
from ._calidad import (
    avisos_calidad,
    avisos_coherencia,
    avisos_voz,
    verificar_calidad_pieza,
)
from ._copy import (
    encadenar_arte_tras_copy,
    encadenar_copy_tras_qa,
    lanzar_copy_de_tema,
    temas_autogen_sin_copy,
    temas_para_copy,
)
from ._ingesta import (
    _AVISO_SIN_LINEA,
    _auto_etiquetar_linea,
    _claves_dedup_marca,
    _copy_pendiente_de,
    _fecha_fuente_iso,
    _fetch_cuerpo,
    _leer_items_fuente,
    _nota_de_cluster,
    _nota_de_item,
    _redes_de_fuente,
    _url_fuente_de,
    caducar_qa_clusters_en_curso,
    clusters_para_promover,
    clusters_pendientes_qa,
    crear_tema_de,
    crear_tema_de_cluster,
    fuentes_activas_de_marca,
    ingerir_marca,
    items_ingeribles,
    caducar_temas_viejos,
    promover_clusters_marca,
    temas_en_vuelo,
)
from ._qa import (
    _contexto_qa_fuente,
    asegurar_documento_qa,
    dom_qa_titulo,
    lanzar_qa_cluster,
    lanzar_qa_fuente,
    qa_lexico,
    temas_sin_qa,
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
    "libtexto",
    "dedup",
    "gen_dom",
    "jobspec",
    "dom_qa",
    "CLASE_CONTENIDO",
    "ORIGENES_AUTOGEN",
    "_log",
    # constantes de flujo
    "ORIGEN_PIPELINE",
    "TIPO_ACTIVIDAD",
    "TIPO_PIPELINE",
    "ETAPA_CI",
    "ETAPA_CD",
    "ETAPA_QA",
    "ETAPA_ARTE",
    "PROMPT_QA_ID",
    "QA_EN_CURSO",
    "QA_SALTADA",
    "QA_CADUCADA",
    "VERDICTO_NO_VERIFICADO",
    "VERDICTO_PROBLEMA",
    "_DIAS_DEDUP",
    "_FORMATO_PIPELINE",
    "_TITULO_QA",
    "_ETIQUETA_QA",
    "_DEFAULT_QA_CRITERIOS",
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
    "embudo_qa",
    "EMBUDO_QA_ESTADOS",
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
    "items_ingeribles",
    "_leer_items_fuente",
    "fuentes_activas_de_marca",
    "_redes_de_fuente",
    "_copy_pendiente_de",
    "_fecha_fuente_iso",
    "_AVISO_SIN_LINEA",
    "_auto_etiquetar_linea",
    "crear_tema_de",
    "crear_tema_de_cluster",
    "clusters_para_promover",
    "clusters_pendientes_qa",
    "promover_clusters_marca",
    "temas_en_vuelo",
    "caducar_temas_viejos",
    "caducar_qa_clusters_en_curso",
    "_claves_dedup_marca",
    "_url_fuente_de",
    "_nota_de_item",
    "_nota_de_cluster",
    "_fetch_cuerpo",
    "ingerir_marca",
    # QA
    "qa_lexico",
    "asegurar_documento_qa",
    "dom_qa_titulo",
    "_contexto_qa_fuente",
    "lanzar_qa_fuente",
    "lanzar_qa_cluster",
    "temas_sin_qa",
    # CD
    "lanzar_copy_de_tema",
    "temas_para_copy",
    "temas_autogen_sin_copy",
    "encadenar_copy_tras_qa",
    "encadenar_arte_tras_copy",
    # CALIDAD del copy (criba advisory pre-avance)
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
    "ejecutar_qa_clusters",
    "ejecutar_cd",
    "ejecutar_arte",
    "ejecutar_avance",
    "_intervalo_segundos",
    "_intervalo_investigacion_segundos",
    "_intervalo_produccion_segundos",
    "iniciar_pipeline",
]
