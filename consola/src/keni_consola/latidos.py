"""Latidos de los daemons de fondo: fachada BEST-EFFORT sobre `db_latidos`.

QUÉ RESUELVE (auditoría 2026-06, observabilidad): hasta ahora el único signo de vida de
los daemons era el log. Si un hilo moría o un barrido llevaba horas fallando, nadie lo
veía sin entrar por ssh. Con esto cada daemon deja un LATIDO persistido (tabla
`daemon_latidos`) en cada iteración del bucle y en cada barrido, y el panel Sistema lo
muestra (endpoint `/api/sistema/daemons`), juzgando "atrasado" sin conocer la config.

CONTRATO DE SEGURIDAD: registrar un latido NUNCA rompe un barrido ni mata un hilo.
Todas las funciones capturan cualquier excepción (BD caída, esquema a medias, sin
DATABASE_URL en unit tests) y la degradan a un log debug. Además el latido de CICLO se
THROTTLEA (mínimo `_MIN_ENTRE_CICLOS_SEG` entre escrituras por daemon) para que un tick
corto no meta escrituras innecesarias.

Aparte de la tabla, este módulo mantiene el FICHERO de latido del PROCESO `daemons`
(`tocar_fichero`, lo escribe el bucle principal de `keni_consola.daemons`): es lo que
sondea el healthcheck del contenedor en deploy (sin depender de la BD para liveness).
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

_log = logging.getLogger("keni_consola.latidos")

# Nombre estable por módulo del sweep: los daemons gateados NO pasan nombre (bucle_gateado
# lo deriva del módulo de su `sweep_fn`); estos alias pulen los casos poco legibles para
# que el panel muestre nombres cortos y estables aunque el módulo se renombre.
_ALIAS = {
    "recolectar_daemon": "ingesta",
    "media_gc_daemon": "media_gc",
    "noticias_gc_daemon": "noticias_gc",
    "trends_daemon": "trends",
    "algoritmos_refresco": "algoritmos",
    "patrones_refresco": "patrones",
    "limpiador_generaciones": "limpiador",
    "eventos_scanner": "vencimientos",
}

# Daemons RETIRADOS/renombrados: sus filas viejas pueden seguir en `daemon_latidos`
# (el upsert nunca borra) pero ya no hay hilo que las actualice; la sonda del panel
# (`api.sistema.sonda_daemons`) las IGNORA para no pintar falsos "atrasado".
#   - "pipeline": el hilo único del pipeline se partió en "investigacion" + "produccion"
#     (cada loop late con su propio nombre); la fila vieja quedó suelta.
#   - "comercial": el apartado Comercial (snapshots) se retiró; su daemon de captura ya no
#     existe, así que su fila vieja en `daemon_latidos` (BD hosted) no la actualiza nadie.
RETIRADOS = frozenset({"pipeline", "comercial"})

# Daemons cuyo bucle corre sobre `daemon_util.bucle_gateado` y por tanto CONSUMEN el flag
# `barrido_solicitado` (POST /api/sistema/daemons/{daemon}/barrer): para ellos «Barrer ahora»
# funciona de verdad. Los bucles LEGADOS (programador, metricas, metricas_piezas, comercial)
# NO miran el flag: ofrecerles el botón sería mentir, así que la sonda del panel expone
# `barrible` y el front solo lo ofrece a estos. Mantener en sintonía con los call sites de
# `bucle_gateado` (el nombre sale de `nombre_de_sweep`/`_ALIAS` o del `nombre=` explícito).
BARRIBLES = frozenset({
    "ingesta",
    "media_gc",
    "noticias_gc",
    "trends",
    "algoritmos",
    "patrones",
    "limpiador",
    "vencimientos",
    "alertas_rendimiento",
    "investigacion",
    "produccion",
})

# GRUPO ("motor"/papel) de cada daemon: clasifica los daemons para el dashboard de
# "Workers" del panel Sistema (el front agrupa por aquí en vez de hardcodear nombres).
# Fuente única, igual que BARRIBLES. Cuatro grupos:
#   - "investigacion": alimentan el motor de REUTILIZAR (descubrir/ingerir/validar fuentes).
#   - "produccion":    el motor de CREAR borradores (Redactar + Ilustrar).
#   - "flujo":         actúan EN el flujo de publicación/comercial; NO gastan tokens claude.
#   - "infra":         pura infraestructura (métricas, GC, alertas, limpiador, patrones).
# Un daemon registrado que NO esté en ningún conjunto cae a "infra" por defecto (ver
# `grupo_de`): al añadir un daemon nuevo, clasifícalo aquí o asume que se pinta como infra.
GRUPO_INVESTIGACION = frozenset({"ingesta", "trends", "algoritmos", "investigacion"})
GRUPO_PRODUCCION = frozenset({"produccion"})
GRUPO_FLUJO = frozenset({"comercial", "programador", "vencimientos"})
GRUPO_INFRA = frozenset({
    "metricas",
    "metricas_piezas",
    "alertas_rendimiento",
    "media_gc",
    "patrones",
    "noticias_gc",
    "limpiador",
})

# Daemons que ENCOLAN/EJECUTAN `claude -p` y por tanto GASTAN tokens. El resto opera sin
# modelo (lee feeds/métricas, mueve piezas, GC). `patrones` deriva de Metricool SIN claude
# (verificado en patrones_refresco.py) => fuera. Fuente única para `gasta_tokens` en la sonda.
GASTA_TOKENS = frozenset({"investigacion", "produccion"})


# CLASE + MOTOR de cada daemon (dashboard de Workers, contrato ADITIVO con el de `grupo_de`).
# Mapeo EXPLÍCITO (fuente única, igual que GRUPO_*/GASTA_TOKENS), pensado para clasificar a mano
# cada daemon nuevo al añadirlo. Es una vista mas afilada que `grupo`:
#   - `clase`:  "ia"      -> gasta tokens Y tiene prompt (corre `claude -p`).
#               "maquina" -> parte de la MAQUINA de contenido pero NO-IA (alimenta/opera los
#                            motores sin modelo: feeds, scheduler, GC del pool de noticias).
#               "sistema" -> pura infraestructura (métricas, GC de media, alertas, limpiador,
#                            patrones, comercial).
#   - `motor`:  "investigacion" | "produccion" | None. El loop de la máquina (ADR 0011) al que
#               sirve el daemon; None para los de `sistema` (no pertenecen a ningún motor).
# Verificado contra cada módulo (punto de partida editable; reclasifica aquí al añadir un daemon):
#   - ia:  investigacion (loop de verificación/Verificar -> motor investigacion), produccion (loop de Redactar/Ilustrar
#          -> motor produccion).
#   - maquina/investigacion:  ingesta (recolección RSS), trends (Google Trends), algoritmos (feeds
#          de algoritmo), noticias_gc (limpia el POOL de noticias que alimenta reutilizar).
#   - maquina/produccion:     programador (publica la parrilla), vencimientos (escáner de eventos
#          que dispara producción por caducidad).
#   - sistema/None:  limpiador, media_gc, metricas, metricas_piezas, alertas_rendimiento, patrones
#          (deriva de Metricool SIN claude), comercial.
# Cualquier daemon NO mapeado cae a ("sistema", None) (ver `clase_de`/`motor_de`): nunca rompe el
# panel y, como mucho, sale como infraestructura hasta que se clasifique aquí.
_CLASE_MOTOR: dict[str, tuple[str, str | None]] = {
    "investigacion": ("ia", "investigacion"),
    "produccion": ("ia", "produccion"),
    "ingesta": ("maquina", "investigacion"),
    "trends": ("maquina", "investigacion"),
    "algoritmos": ("maquina", "investigacion"),
    "noticias_gc": ("maquina", "investigacion"),
    "programador": ("maquina", "produccion"),
    "vencimientos": ("maquina", "produccion"),
    "limpiador": ("sistema", None),
    "media_gc": ("sistema", None),
    "metricas": ("sistema", None),
    "metricas_piezas": ("sistema", None),
    "alertas_rendimiento": ("sistema", None),
    "patrones": ("sistema", None),
    "comercial": ("sistema", None),
}
_CLASE_MOTOR_DEFAULT: tuple[str, str | None] = ("sistema", None)


def clase_de(daemon: str) -> str:
    """Clase del daemon ("ia"|"maquina"|"sistema"); default "sistema" si no está mapeado."""
    return _CLASE_MOTOR.get(daemon, _CLASE_MOTOR_DEFAULT)[0]


def motor_de(daemon: str) -> str | None:
    """Motor del daemon ("investigacion"|"produccion") o None (sistema / no mapeado)."""
    return _CLASE_MOTOR.get(daemon, _CLASE_MOTOR_DEFAULT)[1]


# CLAVE de AJUSTE (KENI_*) que GOBIERNA el on/off de cada daemon: la que el front pasa a
# POST /api/ajustes para encender/apagar el daemon DESDE SU FILA (toggle in-place del panel
# Sistema). Fuente única, igual que BARRIBLES/GRUPO_*. Cada valor es una clave REAL del
# catálogo de ajustes (`ajustes_catalogo`) — un test lo verifica. Verificado contra el
# `activo_fn` de cada `bucle_gateado` (ver daemons.py + cada módulo):
#   - ingesta            -> KENI_PIPELINE_RECOLECTAR   (recolectar_daemon/_bucle: recolectar_activo)
#   - trends             -> KENI_TRENDS               (trends_daemon: trends_activo)
#   - algoritmos         -> KENI_ALGORITMOS_AUTO      (algoritmos_refresco: algoritmos_auto_activo)
#   - media_gc           -> KENI_MEDIA_GC             (media_gc_daemon: media_gc_activo)
#   - noticias_gc        -> KENI_NOTICIAS_GC          (noticias_gc_daemon: noticias_gc_activo)
#   - patrones           -> KENI_PATRONES_AUTO        (patrones_refresco: patrones_auto_activo)
#   - alertas_rendimiento-> KENI_ALERTAS_RENDIMIENTO  (alertas_rendimiento_activas)
#   - vencimientos       -> KENI_EVENTOS_VENCIMIENTOS (eventos_scanner: eventos_vencimientos_activos)
#   - investigacion      -> KENI_INVESTIGACION  (maestro virtual = sus etapas Recolectar+Verificar;
#                                           el loop gatea con gate_maquina(alguna_etapa_investigacion_activa),
#                                           que es True sii Recolectar o Verificar lo está. Interruptor PROPIO,
#                                           independiente de Producción —antes ambos compartían KENI_MAQUINA—.)
#   - produccion         -> KENI_MAQUINA   (loop pipeline: gate_maquina(alguna_etapa_produccion_activa),
#                                           que siempre es True bajo la máquina => su único interruptor de loop
#                                           ES el maestro de la máquina. Redactar/Ilustrar se gatean dentro.)
# Los gateados de máquina (investigacion/ingesta/trends/algoritmos) corren además bajo
# KENI_MAQUINA (AND), pero el toggle de SU fila gobierna su flag PROPIO; el maestro es otra fila.
# Por eso la sonda separa `gate_activo` (valor guardado del flag propio: lo que el switch refleja)
# de `activo` (efectivo: el flag propio AND la máquina): con la máquina apagada el switch sigue
# encendido y el estado pasa a «en espera», en vez de rebotar a apagado.
CLAVE_GATE = {
    "ingesta": "KENI_PIPELINE_RECOLECTAR",
    "trends": "KENI_TRENDS",
    "algoritmos": "KENI_ALGORITMOS_AUTO",
    "media_gc": "KENI_MEDIA_GC",
    "noticias_gc": "KENI_NOTICIAS_GC",
    "patrones": "KENI_PATRONES_AUTO",
    "alertas_rendimiento": "KENI_ALERTAS_RENDIMIENTO",
    "vencimientos": "KENI_EVENTOS_VENCIMIENTOS",
    "investigacion": "KENI_INVESTIGACION",
    "produccion": "KENI_MAQUINA",
}

# Daemons SIEMPRE-ON sin toggle de ajuste: su bucle corre incondicionalmente (legados con
# `while True`, o `limpiador` con `activo_fn=lambda: True`). No tienen fila-toggle => clave_gate
# null. Nota: `programador` SIEMPRE corre (su gate KENI_PUBLICAR_REAL solo decide publicar de
# verdad vs dry-run, no apaga el daemon), por eso queda sin gate de encendido.
SIN_GATE = frozenset({"limpiador", "programador", "comercial", "metricas", "metricas_piezas"})


def clave_gate_de(daemon: str) -> str | None:
    """Clave de ajuste (KENI_*) que enciende/apaga el daemon desde su fila, o None.

    None = el daemon es SIEMPRE-ON (sin toggle: legados/limpiador) o aún no está clasificado.
    El front usa esto para pintar (o no) el switch on/off in-place y, si lo hay, qué clave
    pasar a POST /api/ajustes. Fuente única, igual que `grupo_de`/`gasta_tokens`.
    """
    return CLAVE_GATE.get(daemon)


def grupo_de(daemon: str) -> str:
    """Grupo ("motor"/papel) de un daemon para el dashboard de Workers; default "infra".

    Un daemon no clasificado en ningún conjunto se trata como infraestructura: nunca
    rompe el panel y, como mucho, sale en el grupo equivocado hasta que se clasifique.
    """
    if daemon in GRUPO_INVESTIGACION:
        return "investigacion"
    if daemon in GRUPO_PRODUCCION:
        return "produccion"
    if daemon in GRUPO_FLUJO:
        return "flujo"
    return "infra"  # GRUPO_INFRA + cualquier daemon nuevo sin clasificar


def gasta_tokens(daemon: str) -> bool:
    """True si el daemon encola/ejecuta `claude -p` (gasta tokens); False el resto."""
    return daemon in GASTA_TOKENS


# ETIQUETA humana de cada daemon: lo que la tarjeta/fila del panel muestra en vez del nombre
# crudo. Fuente única (igual que el resto de la clasificación), keyed por el nombre CANÓNICO
# (tras `_ALIAS`: `ingesta` y `limpiador`). Un daemon no mapeado cae
# a su nombre capitalizado (ver `etiqueta_de`), así el panel nunca queda mudo.
ETIQUETA = {
    "investigacion": "Investigación",
    "produccion": "Producción",
    "ingesta": "Recolección de noticias",
    "trends": "Tendencias",
    "algoritmos": "Algoritmos de plataforma",
    "noticias_gc": "GC de noticias",
    "programador": "Programador de parrilla",
    "vencimientos": "Vencimientos",
    "comercial": "Comercial",
    "metricas": "Métricas",
    "metricas_piezas": "Métricas de piezas",
    "alertas_rendimiento": "Alertas de rendimiento",
    "media_gc": "GC de media",
    "patrones": "Patrones de marca",
    "limpiador": "Limpiador (cola y generaciones)",
}


def etiqueta_de(daemon: str) -> str:
    """Etiqueta humana del daemon para el panel; nombre capitalizado si no está mapeado."""
    return ETIQUETA.get(daemon) or (daemon[:1].upper() + daemon[1:])


# DESCRIPCION de UNA LINEA de qué hace cada daemon y cuándo: lo que el panel Sistema muestra
# bajo la etiqueta para que un humano sepa PARA QUÉ SIRVE sin leer el código. Fuente única
# (igual que ETIQUETA/clasificación), keyed por el nombre CANÓNICO (tras `_ALIAS`). Un daemon
# no mapeado cae a '' (ver `descripcion_de`): el panel no queda mudo (ya tiene etiqueta), solo
# sin la frase explicativa. Al añadir un daemon, descríbelo aquí.
DESCRIPCION = {
    "investigacion": "Verifica las historias del pool (fuentes, con IA) antes de admitirlas a producción.",
    "produccion": "Genera borradores con IA: redacta el copy e ilustra el arte de cada pieza.",
    "ingesta": "Recolecta noticias de feeds RSS y agencias al pool, las agrupa y traduce.",
    "trends": "Trae tendencias de Google Trends como fuente para el pool de noticias.",
    "algoritmos": "Refresca los feeds de algoritmo de cada plataforma.",
    "noticias_gc": "Purga el pool de noticias por antigüedad y baja relevancia.",
    "programador": "Publica la parrilla programada (dry-run salvo que KENI_PUBLICAR_REAL esté ON).",
    "vencimientos": "Escanea eventos y dispara producción por caducidad o recordatorio.",
    "metricas": "Refresca las métricas por cuenta desde Metricool.",
    "metricas_piezas": "Refresca las métricas por pieza publicada desde Metricool.",
    "alertas_rendimiento": "Detecta caídas de rendimiento de las piezas y emite alertas.",
    "media_gc": "Borra de S3 la media sin dueño (no referenciada por ninguna pieza).",
    "patrones": "Deriva los patrones editoriales de cada marca desde Metricool (sin IA).",
    "limpiador": "Repara la cola: reencola o cancela generaciones colgadas.",
}


def descripcion_de(daemon: str) -> str:
    """Frase de una línea de qué hace el daemon para el panel; '' si no está descrito."""
    return DESCRIPCION.get(daemon, "")


# PROMPTS de la Biblioteca que gobiernan cada agente IA (clase=ia): lo que el panel ofrece editar
# in-place (cada uno abre su doc en el editor). Cada entrada es {etiqueta, doc}, con `doc` = id del
# documento en la Biblioteca. SOLO los daemons IA tienen prompt (el resto no corre `claude -p`).
# Fuente única en el backend, en sintonía con las etapas IA de los cockpits (Verificar/Redactar/
# Ilustrar); un test verifica que cada `doc` existe en la Biblioteca.
PROMPTS: dict[str, list[dict[str, str]]] = {
    "investigacion": [{"etiqueta": "Verificar", "doc": "prompt/verificar"}],
    "produccion": [
        {"etiqueta": "Redactar", "doc": "prompt/redactar"},
        {"etiqueta": "Ilustrar", "doc": "prompt/ilustrar"},
    ],
}


def prompts_de(daemon: str) -> list[dict[str, str]]:
    """Prompts de la Biblioteca que gobiernan el agente IA; vacío si no es IA o no tiene."""
    return [dict(p) for p in PROMPTS.get(daemon, [])]


# DESCRIPCIÓN de EXACTAMENTE lo que hace cada daemon: el bloque que la página de detalle
# (`/maquina/agentes/{daemon}`) muestra para que cualquiera entienda el servicio sin leer código.
# Fuente única (igual que ETIQUETA/PROMPTS), keyed por nombre canónico. Verificado contra el
# sweep de cada módulo (auditoría 2026-06). Un daemon no mapeado cae a "" (la página lo omite).
DESCRIPCION: dict[str, str] = {
    "investigacion": (
        "Motor de REUTILIZAR (mitad investigación). Cada barrido lee el pool de noticias ya "
        "rankeado, caduca lo viejo, admite por marca las historias que superan los umbrales y "
        "lanza la verificación de la fuente con IA (claude -p). Deja temas verificados listos "
        "para que Producción escriba el copy. No publica ni escribe copy. Corre bajo la máquina "
        "y sus etapas Recolectar/Verificar; en vacío espacia el barrido (backoff) y recupera el "
        "ritmo en cuanto entra trabajo."
    ),
    "produccion": (
        "Motor de CREAR borradores (a partir de lo verificado). Cada barrido redacta el copy de "
        "los temas verificados (claude -p), genera la imagen por IA cuando toca y avanza los "
        "borradores completos (copy + arte) a la cola de revisión humana. El AVANCE corre siempre "
        "que la máquina esté encendida (así no quedan borradores atascados); Redactar e Ilustrar "
        "se gatean por su propio interruptor. NUNCA publica: todo para en el gate humano."
    ),
    "ingesta": (
        "Recolección persistente de noticias. Sondea en segundo plano los feeds RSS vencidos "
        "(cadencia por feed/categoría, con backoff por feed que falla), ingiere agencias, agrupa "
        "los artículos en historias, las re-puntúa y deduplica, fusiona semánticamente y traduce "
        "lo extranjero, y caduca el pool. Solo lee fuentes públicas y persiste; no genera ni "
        "publica. Alimenta el pool del que tira Investigación."
    ),
    "trends": (
        "Tendencias de Google como fuente externa. Cada barrido descarga el RSS «trending now» "
        "por geografía (def MX), parsea sus noticias y las inserta en el pool (deduplicadas). "
        "Solo añade material al pool; no genera ni publica."
    ),
    "algoritmos": (
        "Inteligencia de plataforma. Refresca los feeds que recogen cambios de algoritmo de las "
        "redes y persiste las entradas clasificadas. Solo lectura; alimenta el contexto, no "
        "produce contenido."
    ),
    "noticias_gc": (
        "Limpieza del pool de noticias por RELEVANCIA. Purga las historias de una sola fuente con "
        "score bajo, inactivas y nunca llevadas al tablero (más items sueltos viejos). Es "
        "ortogonal a la caducidad por antigüedad (esa la hace Recolección). Conservador: con su "
        "interruptor apagado no borra nada."
    ),
    "media_gc": (
        "Limpieza de media suelta en el almacén (S3/Garage). Borra los objetos de imagen que "
        "ninguna publicación referencia y son más viejos que el umbral de antigüedad, "
        "re-verificando antes de borrar para no tocar nada en uso. Conservador: apagado por "
        "defecto."
    ),
    "patrones": (
        "Re-derivación de los patrones editoriales de cada marca. Cada N días vuelve a leer las "
        "métricas reales de Metricool (mejores piezas) y reescribe el perfil de patrones "
        "(formatos, voces medidas, engagement) por marca. La Voz y las Reglas (criterio humano) "
        "no se tocan jamás."
    ),
    "alertas_rendimiento": (
        "Vigilancia de rendimiento. Compara el engagement de cada pieza publicada contra el "
        "umbral y emite una alerta interna cuando una rinde por debajo (idempotente por día). "
        "Solo lee y emite eventos; no cambia contenido."
    ),
    "vencimientos": (
        "Escáner de vencimientos del tablero. Detecta el contenido cuya fecha de entrega pasó sin "
        "cerrarse y emite el evento `contenido.vencido` (idempotente). Solo señala; no mueve "
        "piezas por sí mismo."
    ),
    "programador": (
        "Programador de la parrilla. Cada minuto prepara las piezas programadas que vencen, "
        "ejecuta el evergreen diario y recupera las aprobadas sin programar. En dry-run (def) "
        "solo marca; con la publicación real encendida envía al scheduler de Metricool. SIEMPRE "
        "activo: la publicación real es un interruptor aparte, no apaga el daemon."
    ),
    "comercial": (
        "Captura comercial. Toma snapshots periódicos de las interacciones/visualizaciones de las "
        "piezas activas para construir su serie temporal de rendimiento. Solo lee de Metricool y "
        "persiste; degrada honestamente si no hay datos."
    ),
    "metricas": (
        "Caché de métricas agregadas. Refresca en caliente los reportes por marca y rango desde "
        "Metricool, para que el dashboard abra sin esperar. Solo lectura."
    ),
    "metricas_piezas": (
        "Caché de métricas POR PIEZA. Recalcula el rendimiento individual de las piezas "
        "publicadas recientes desde Metricool. Solo lectura; alimenta las vistas de pieza."
    ),
    "limpiador": (
        "Reparador del sistema (siempre activo). Cierra como error/interrumpido las generaciones "
        "colgadas en «ejecutando» cuyo proceso murió (reinicio/deploy/OOM), repara los temas del "
        "pipeline atascados en verificación y purga registros viejos. Barre al arrancar y cada "
        "pocos minutos para que nada quede «Generando…» para siempre."
    ),
}


def descripcion_de(daemon: str) -> str:
    """Descripción humana de qué hace EXACTAMENTE el daemon (para la página de detalle); "" si no mapeado."""
    return DESCRIPCION.get(daemon, "")


# AJUSTES (claves del catálogo) que GOBIERNAN cada daemon: lo que la página de detalle ofrece
# editar in-place junto al toggle. La PRIMERA suele ser su `clave_gate` (encendido); el resto son
# los knobs que afinan su comportamiento. Cada clave debe existir en `ajustes_catalogo` (un test lo
# verifica); las que no existan ahí se ignoran al serializar (no rompen). Fuente única, como el
# resto de la clasificación. Un daemon sin entrada (comercial/metricas/metricas_piezas/limpiador)
# no expone ajustes: su comportamiento no tiene knobs de operación.
AJUSTES: dict[str, list[str]] = {
    "investigacion": [
        "KENI_INVESTIGACION", "KENI_PIPELINE_RECOLECTAR", "KENI_PIPELINE_VERIFICAR",
        "KENI_PIPELINE_MAX", "KENI_PIPELINE_EN_PROCESO_MAX",
        "KENI_PROMOVER_MIN_SCORE", "KENI_PROMOVER_MIN_MARCA", "KENI_PROMOVER_MADURACION_MIN",
    ],
    "produccion": [
        "KENI_PRODUCCION", "KENI_PIPELINE_ILUSTRAR",
        "KENI_GENERACION_PAUSADA", "KENI_PRESUPUESTO_TOKENS_DIA", "KENI_ESFUERZO",
    ],
    "ingesta": ["KENI_PIPELINE_RECOLECTAR", "KENI_INGESTA_FILTRO"],
    "trends": ["KENI_TRENDS"],
    "algoritmos": ["KENI_ALGORITMOS_AUTO"],
    "noticias_gc": [
        "KENI_NOTICIAS_GC", "KENI_NOTICIAS_GC_SCORE_UMBRAL", "KENI_NOTICIAS_GC_INACTIVIDAD_HORAS",
    ],
    "media_gc": ["KENI_MEDIA_GC", "KENI_MEDIA_GC_ANTIGUEDAD_HORAS"],
    "patrones": ["KENI_PATRONES_AUTO", "KENI_PERFIL_EDITORIAL_TTL_HORAS"],
    "alertas_rendimiento": ["KENI_ALERTAS_RENDIMIENTO", "KENI_ALERTAS_UMBRAL_ENGAGEMENT"],
    "vencimientos": ["KENI_EVENTOS_VENCIMIENTOS"],
    "programador": ["KENI_PUBLICAR_REAL"],
}


def ajustes_de(daemon: str) -> list[str]:
    """Claves de ajuste del catálogo que gobiernan el daemon (para editar en su detalle); [] si ninguna."""
    return list(AJUSTES.get(daemon, []))


# Mínimo entre DOS latidos de ciclo del mismo daemon (las de barrido no se throttlean:
# son una por sweep y traen el resultado). 30s mantiene el panel fresco con coste nulo.
_MIN_ENTRE_CICLOS_SEG = 30.0
_ultimo_ciclo: dict[str, float] = {}

# Fichero de latido del PROCESO daemons (healthcheck del contenedor). Override por env
# para tests/local; el default vive en /tmp (efímero, fuera del volumen de datos).
ENV_FICHERO_LATIDO = "KENI_DAEMONS_LATIDO_FICHERO"
_FICHERO_LATIDO_DEF = "/tmp/keni-daemons.latido"  # noqa: S108 -- señal de liveness, sin datos


def nombre_de_sweep(sweep_fn: Callable[[], Any]) -> str:
    """Nombre estable del daemon a partir del módulo donde vive su `sweep_fn`."""
    modulo = getattr(sweep_fn, "__module__", "") or ""
    corto = modulo.rsplit(".", 1)[-1] or "desconocido"
    return _ALIAS.get(corto, corto)


def ciclo(daemon: str, *, activo: bool, intervalo_seg: float, tick_seg: float) -> None:
    """Latido de CICLO (el bucle dio una iteración), throttleado y best-effort."""
    ahora = time.monotonic()
    if ahora - _ultimo_ciclo.get(daemon, 0.0) < _MIN_ENTRE_CICLOS_SEG:
        return
    try:
        from . import db_latidos

        db_latidos.latido_ciclo(
            daemon, activo=activo, intervalo_seg=intervalo_seg, tick_seg=tick_seg
        )
        _ultimo_ciclo[daemon] = ahora
    except Exception as e:  # noqa: BLE001 -- un latido jamás rompe un barrido
        _log.debug("Latido de ciclo de %s no registrado: %s", daemon, e)


def barrido(
    daemon: str,
    *,
    ok: bool,
    intervalo_seg: float,
    tick_seg: float,
    duracion_ms: int = 0,
    error: str = "",
    resumen: str = "",
) -> None:
    """Latido de BARRIDO (el sweep corrió, bien o mal), best-effort.

    Hace DOS cosas, cada una best-effort e independiente: (1) actualiza el RESUMEN acumulado
    del daemon en `daemon_latidos` (ultimo ok/error + contadores) y (2) deja una fila de
    HISTORIAL en `daemon_barridos` (una por barrido, recortada con cota dura). `resumen` es un
    texto corto opcional (qué hizo / nº items) que aporta el bucle si el sweep devuelve un str.
    """
    try:
        from . import db_latidos

        db_latidos.latido_barrido(
            daemon,
            ok=ok,
            intervalo_seg=intervalo_seg,
            tick_seg=tick_seg,
            duracion_ms=duracion_ms,
            error_txt=error,
            resumen=resumen,
        )
        _ultimo_ciclo[daemon] = time.monotonic()
    except Exception as e:  # noqa: BLE001 -- un latido jamás rompe un barrido
        _log.debug("Latido de barrido de %s no registrado: %s", daemon, e)
    # Historial por barrido (independiente del resumen acumulado: un fallo de uno no toca el otro).
    try:
        from . import db_latidos

        db_latidos.registrar_barrido(
            daemon, ok=ok, duracion_ms=duracion_ms, resumen=resumen, error_txt=error
        )
    except Exception as e:  # noqa: BLE001 -- el historial jamás rompe un barrido
        _log.debug("Historial de barrido de %s no registrado: %s", daemon, e)


def consumir_solicitud(daemon: str) -> bool:
    """Consume la solicitud de BARRIDO FORZADO pendiente del daemon, si la hay (best-effort).

    La escribe el back (POST /api/sistema/daemons/{daemon}/barrer) y la consulta
    `bucle_gateado` en cada tick: True => el bucle ejecuta el sweep YA (la solicitud queda
    limpiada de forma atomica en BD, asi dispara UN solo barrido). Mismo contrato de
    seguridad que el resto del modulo: un fallo de BD degrada a False (sin barrido extra,
    sin romper el bucle).
    """
    try:
        from . import db_latidos

        return db_latidos.consumir_solicitud_barrido(daemon)
    except Exception as e:  # noqa: BLE001 -- la consulta del flag jamás rompe el bucle
        _log.debug("Solicitud de barrido de %s no consultada: %s", daemon, e)
        return False


def fichero_latido() -> str:
    """Ruta del fichero de latido del proceso daemons (healthcheck del contenedor)."""
    return os.environ.get(ENV_FICHERO_LATIDO) or _FICHERO_LATIDO_DEF


def tocar_fichero() -> None:
    """Escribe el instante actual en el fichero de latido (best-effort, atómico).

    El healthcheck del contenedor `daemons` compara el MTIME del fichero con el reloj:
    si lleva demasiado sin tocarse, el proceso principal está colgado/muerto y autoheal
    reinicia el contenedor. Escritura a tmp + rename para no dejar un fichero a medias.
    """
    ruta = fichero_latido()
    try:
        tmp = f"{ruta}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(f"{time.time():.0f}\n")
        os.replace(tmp, ruta)
    except Exception as e:  # noqa: BLE001 -- liveness best-effort
        _log.debug("No se pudo tocar el fichero de latido %s: %s", ruta, e)
