"""Catalogo DECLARATIVO de ajustes editables (la fuente de verdad para la API admin).

Cada ajuste enlaza una env var `KENI_*` (su `clave`) con su tipo, etiqueta/ayuda para la UI,
grupo, si es peligroso, su valor por defecto y, segun el tipo, sus opciones (select) o sus
cotas (int/float). La API admin (`api/ajustes.py`) usa este catalogo para:
  - PINTAR el formulario (un dict por ajuste con su valor EFECTIVO + de donde viene).
  - VALIDAR lo que escribe el admin (`validar_valor`) antes de persistirlo en el store.
  - ACOTAR las claves escribibles: SOLO se guardan claves del catalogo; el resto del codigo
    sigue cayendo a env como hasta hoy (precedencia STORE > ENV > DEFECTO en `config._crudo`).

El VALOR efectivo y su FUENTE se calculan con la misma precedencia que `config._crudo`:
store (UI) > env > defecto del catalogo. NO importamos `config` aqui (los accesores numericos
de `config` ya aplican sus propios minimos/defaults); leemos el store via `ajustes.obtener` y
el entorno via `os.environ` directamente para reportar la fuente con fidelidad.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from . import ajustes, config, marcas

# Conjuntos de verdad/falsedad para flags (mismos que `config`, fuente del parseo de bool).
_VERDADEROS = frozenset({"1", "true", "yes", "si", "sí", "on"})
_FALSOS = frozenset({"0", "false", "no", "off", ""})

# Titulos humanos de cada grupo (orden estable del contrato GET /api/ajustes). El orden manda
# el de aparición en la UI: PRIMERO el interruptor general de la máquina de contenido (kill-switch
# global), luego los maestros de etapa, las excepciones por marca, después Publicación, y los
# automatismos generales (barridos del sistema) al final.
GRUPOS: tuple[tuple[str, str], ...] = (
    ("maquina_global", "Máquina de contenido (interruptor general)"),
    ("maestros_etapa", "Maestros de etapa (todas las marcas)"),
    ("automatizacion_marca", "Excepciones por marca"),
    ("publicacion", "Publicación"),
    ("publicacion_marca", "Publicación · excepciones por marca"),
    ("automatismos_generales", "Automatismos generales"),
    ("tuning", "Ajustes finos"),
)

# Etapas de auto-producción. Cada etapa tiene DOS controles que comparten NOMBRE (match 1:1):
#   - un MAESTRO global (clave `ENV`), grupo `maestros_etapa`: apagarlo deja la etapa EN ESPERA
#     para TODAS las marcas (el daemon no barre);
#   - una EXCEPCIÓN por marca (clave `ENV::marca`), grupo `automatizacion_marca`: solo puede APAGAR
#     marcas sueltas con el maestro encendido (sin override, la marca sigue al maestro).
# La tupla es (env, etiqueta, descripción genérica) y alimenta AMBOS controles.
_ETAPAS_MARCA: tuple[tuple[str, str, str], ...] = (
    (config.ENV_PIPELINE, "Auto-producción", "ingiere fuentes, hace QA y genera copy automático"),
    (config.ENV_AUTOGEN, "Auto-copy", "genera copy automático de los temas que aún no lo tienen"),
    (config.ENV_AUTOGEN_ARTE, "Auto-arte", "genera imagen por IA para los temas con copy y sin imagen"),
    (config.ENV_AUTO_AVANCE, "Auto-avance", "lleva solas a revisión las piezas listas"),
)


def _maestros_etapa() -> list[Ajuste]:
    """Maestro GLOBAL de cada etapa (uno por entrada de `_ETAPAS_MARCA`). Mismo NOMBRE que su
    excepción por marca (match 1:1). Apagar el maestro deja la etapa en espera para TODAS las
    marcas; las excepciones por marca solo restan (apagan marcas sueltas) con el maestro encendido."""
    return [
        Ajuste(
            clave=env_flag,
            tipo="bool",
            etiqueta=etiqueta,
            ayuda=f"Maestro de TODAS las marcas: {desc}. Si lo apagas, ninguna marca corre esta "
            "etapa; las excepciones por marca solo pueden apagar marcas concretas.",
            grupo="maestros_etapa",
            defecto=False,
        )
        for env_flag, etiqueta, desc in _ETAPAS_MARCA
    ]


def _global_de_etapa(env_flag: str) -> bool:
    """Valor GLOBAL actual de una etapa (defecto de su toggle por-marca)."""
    return {
        config.ENV_PIPELINE: config.pipeline_activo,
        config.ENV_AUTOGEN: config.autogen_activo,
        config.ENV_AUTOGEN_ARTE: config.autogen_arte_activo,
        config.ENV_AUTO_AVANCE: config.auto_avance_activo,
    }[env_flag]()


def _ajustes_por_marca() -> list[Ajuste]:
    """Toggles `bool` por (marca × etapa) para la auto-producción. Se generan en caliente
    desde el catálogo de marcas, así que añadir una marca añade sus toggles sin tocar código."""
    salida: list[Ajuste] = []
    for mid, nombre in marcas.opciones():
        for env_flag, etiqueta_etapa, desc in _ETAPAS_MARCA:
            salida.append(
                Ajuste(
                    clave=config.clave_por_marca(env_flag, mid),
                    tipo="bool",
                    etiqueta=f"{nombre} · {etiqueta_etapa}",
                    ayuda=f"Excepción de «{etiqueta_etapa}» para esta marca ({desc}). Apágala para "
                    "excluir solo a esta marca; sin tocarla, sigue al maestro de la etapa.",
                    grupo="automatizacion_marca",
                    defecto=_global_de_etapa(env_flag),
                )
            )
    return salida


def _publicacion_por_marca() -> list[Ajuste]:
    """Excepción de PUBLICACIÓN REAL por marca (clave `KENI_PUBLICAR_REAL::marca`). Mismo patrón
    que las etapas: con el maestro encendido, apagar una marca la deja en dry-run mientras el
    resto publica de verdad. Sin override, la marca sigue al maestro. Se generan desde el catálogo
    de marcas, así que añadir una marca añade su excepción sin tocar código."""
    return [
        Ajuste(
            clave=config.clave_por_marca(config.ENV_PUBLICAR_REAL, mid),
            tipo="bool",
            etiqueta=nombre,
            ayuda=f"Si la apagas, «{nombre}» se queda en dry-run aunque la publicación real esté "
            "activa; sin tocarla, sigue al maestro.",
            grupo="publicacion_marca",
            defecto=config.publicar_real(),
        )
        for mid, nombre in marcas.opciones()
    ]


def _autofeed_cap_por_marca() -> list[Ajuste]:
    """Excepción del TOPE DIARIO del auto-feed por marca (clave `KENI_AUTOFEED_CAP::marca`).

    A diferencia de las etapas (toggle bool), el override del auto-feed es un ENTERO: cada marca
    puede tener su propio tope (incl. 0 = sin auto-feed para esa marca) mientras el resto sigue
    al global. Mismo mecanismo `clave_por_marca` que `marca_apagada`/`_ETAPAS_MARCA`; sin override
    la marca cae al cap global (`config.autofeed_cap`). Se generan desde el catálogo de marcas."""
    return [
        Ajuste(
            clave=config.clave_por_marca(config.ENV_AUTOFEED_CAP, mid),
            tipo="int",
            etiqueta=f"{nombre} · Auto-feed: tope diario",
            ayuda="Tope diario de auto-feed solo para esta marca (0 = desactiva el auto-feed de "
            "esta marca). Sin tocarla, sigue al tope global.",
            grupo="automatizacion_marca",
            defecto=config.autofeed_cap(),
            minimo=0,
        )
        for mid, nombre in marcas.opciones()
    ]


@dataclass(frozen=True)
class Ajuste:
    """Un ajuste editable del catalogo (declarativo)."""

    clave: str
    tipo: str  # 'bool' | 'int' | 'float' | 'select'
    etiqueta: str
    ayuda: str
    grupo: str  # 'maestros_etapa' | 'automatizacion_marca' | 'automatismos_generales' | 'publicacion' | 'tuning'
    defecto: Any
    peligroso: bool = False
    opciones: tuple[dict[str, str], ...] = ()  # solo 'select': [{id, etiqueta}, ...]
    minimo: float | None = None  # solo int/float
    maximo: float | None = None  # solo int/float


_GEO_OPCIONES: tuple[dict[str, str], ...] = (
    {"id": "MX", "etiqueta": "México"},
    {"id": "US", "etiqueta": "Estados Unidos"},
    {"id": "ES", "etiqueta": "España"},
    {"id": "AR", "etiqueta": "Argentina"},
    {"id": "CO", "etiqueta": "Colombia"},
    {"id": "CL", "etiqueta": "Chile"},
)


def _construir_catalogo() -> list[Ajuste]:
    """Construye la lista de ajustes editables. Se llama en cada `catalogo()` (las opciones
    de marca dependen del catalogo de marcas, que es estable pero se resuelve en caliente)."""
    return [
        # --- Interruptor GENERAL de la máquina de contenido (kill-switch global) -------- #
        # Va PRIMERO y en su propio grupo (`maquina_global`) para que se pinte arriba del todo
        # en la pestaña Básica. Apagado (defecto) = NADA automático de contenido corre, aunque
        # los toggles individuales estén ON; encendido = cada subsistema sigue su propio toggle.
        Ajuste(
            clave=config.ENV_MAQUINA,
            tipo="bool",
            etiqueta="Máquina de contenido: encendida/apagada",
            ayuda="Interruptor general de toda la automatización de contenido. APAGADO (por "
            "defecto): nada automático corre —ni ingesta, ni auto-copy/arte, ni breaking, ni "
            "investigación, ni radar, ni avances— aunque los toggles individuales estén "
            "encendidos. ENCENDIDO: cada subsistema sigue su propio toggle. No afecta a la "
            "publicación ni a los barridos de mantenimiento (métricas, alertas, limpieza).",
            grupo="maquina_global",
            defecto=False,
        ),
        # --- Automatismos generales (barridos del sistema, sin dimensión por marca) ----- #
        # Las etapas de auto-producción (Auto-copy, Auto-arte, Auto-producción, Auto-avance) NO
        # están aquí: su maestro vive en `_maestros_etapa()` y sus excepciones en `_ajustes_por_marca()`.
        Ajuste(
            clave=config.ENV_PIPELINE_LINEAS,
            tipo="bool",
            etiqueta="Auto-etiquetar líneas",
            ayuda="Al ingerir, clasifica cada pieza en su línea (vertical) y su origen "
            "(interno / petición externa) por palabras clave. Sin línea queda con un aviso; "
            "nunca se descarta.",
            grupo="automatismos_generales",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_ALERTAS_ACTIVAS,
            tipo="bool",
            etiqueta="Alertas de rendimiento",
            ayuda="Barrido que emite alertas cuando una pieza publicada rinde por debajo del umbral de engagement.",
            grupo="automatismos_generales",
            defecto=True,
        ),
        Ajuste(
            clave=config.ENV_EVENTOS_VENCIMIENTOS,
            tipo="bool",
            etiqueta="Eventos de vencimientos",
            ayuda="Barrido que detecta contenido vencido en el tablero y dispara los eventos "
            "internos correspondientes.",
            grupo="automatismos_generales",
            defecto=True,
        ),
        Ajuste(
            clave=config.ENV_AUTO_PREAPROBACION,
            tipo="bool",
            etiqueta="Pre-aprobación de bajo riesgo",
            ayuda="Auto-aprueba los niveles inferiores de la cadena de aprobación para piezas "
            "de bajo riesgo (el último nivel siempre queda a un humano).",
            grupo="automatismos_generales",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_MEDIA_GC,
            tipo="bool",
            etiqueta="Limpieza de media huérfana",
            ayuda="Borra periódicamente los objetos de imagen del Estudio que ninguna "
            "publicación usa y son más viejos que el umbral de antigüedad.",
            grupo="automatismos_generales",
            defecto=False,
        ),
        # --- Motor de noticias (Olas A–D + Ola 6) -------------------------------- #
        # Todos arrancan OFF: la máquina entera se activa desde aquí; ninguno publica.
        Ajuste(
            clave=config.ENV_INGESTA,
            tipo="bool",
            etiqueta="Noticias · Motor de ingesta",
            ayuda="Sondea en background los feeds RSS y persiste artículos en el archivo "
            "de noticias (Ola A). Solo lee fuentes públicas; no genera ni publica nada. "
            "Seguro: la producción lo necesita activo.",
            grupo="automatismos_generales",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_TRADUCCION,
            tipo="bool",
            etiqueta="Noticias · Traducción/tropicalización MX",
            ayuda="Traduce y tropicaliza al español MX las noticias extranjeras (Radar + "
            "historias). Usa Haiku, best-effort: si falla, el Radar sigue funcionando. "
            "Apagado por defecto (forma parte de la máquina de contenido).",
            grupo="automatismos_generales",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_BREAKING,
            tipo="bool",
            etiqueta="Noticias · Carril rápido de breaking (Claro)",
            ayuda="Hilo demonio que barre el snapshot del Investigador y pre-genera "
            "borradores de breaking para Claro Sports sin draft (Ola C). Solo crea "
            "borradores; nunca publica. Seguro.",
            grupo="automatismos_generales",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_AUTOFEED,
            tipo="bool",
            etiqueta="Auto-feed · pool → feed automático",
            ayuda="Lleva solas al feed las historias relevantes del pool (cajones, "
            "investigación, RSS, ya deduplicadas) como borradores con copy+QA, respetando un "
            "tope diario por marca (Ola E). Nunca publica: todo cae en el feed para imagen + "
            "aprobación humana. Conservador por defecto (OFF).",
            grupo="automatismos_generales",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_INVESTIGACION,
            tipo="bool",
            etiqueta="Noticias · Agentes de investigación (background)",
            ayuda="Daemon que ejecuta los briefs de investigación activos y deposita "
            "candidatos fechados para revisión humana (Ola 6). Cada barrido lanza "
            "claude -p por brief: conservador por defecto (OFF).",
            grupo="automatismos_generales",
            defecto=False,
        ),
        # --- Publicacion (peligroso) ----------------------------------------------- #
        Ajuste(
            clave=config.ENV_PUBLICAR_REAL,
            tipo="bool",
            etiqueta="Publicación real",
            ayuda="¡Cuidado! Si se activa, el sistema envía las piezas programadas al scheduler "
            "real de Metricool. Sin esto opera en dry-run.",
            grupo="publicacion",
            defecto=False,
            peligroso=True,
        ),
        # --- Tuning (int/float/select) --------------------------------------------- #
        Ajuste(
            clave=config.ENV_AUTOGEN_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Auto-copy: intervalo (horas)",
            ayuda="Cada cuántas horas barre el daemon de auto-generación de copy.",
            grupo="tuning",
            defecto=config.AUTOGEN_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_AUTOGEN_MAX,
            tipo="int",
            etiqueta="Auto-copy: máximo por barrido",
            ayuda="Máximo de temas a auto-generar por barrido (cada uno lanza una generación).",
            grupo="tuning",
            defecto=config.AUTOGEN_MAX_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_AUTOGEN_ARTE_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Auto-arte: intervalo (horas)",
            ayuda="Cada cuántas horas barre el daemon de auto-generación de arte.",
            grupo="tuning",
            defecto=config.AUTOGEN_ARTE_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_AUTOGEN_ARTE_MAX,
            tipo="int",
            etiqueta="Auto-arte: máximo por barrido",
            ayuda="Máximo de temas a auto-ilustrar por barrido (cada uno llama al proveedor de imagen).",
            grupo="tuning",
            defecto=config.AUTOGEN_ARTE_MAX_DEF,
            minimo=1,
        ),
        # --- Auto-feed (Ola E) --------------------------------------------------- #
        Ajuste(
            clave=config.ENV_AUTOFEED_INTERVALO_MIN,
            tipo="int",
            etiqueta="Auto-feed: intervalo (minutos)",
            ayuda="Cada cuántos minutos barre el daemon de auto-feed el pool de historias.",
            grupo="tuning",
            defecto=config.AUTOFEED_INTERVALO_MIN_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_AUTOFEED_UMBRAL,
            tipo="float",
            etiqueta="Auto-feed: umbral de relevancia",
            ayuda="Score mínimo (0–1) de una historia para entrar sola al feed. "
            "Sube el valor para dejar entrar solo lo más relevante.",
            grupo="tuning",
            defecto=config.AUTOFEED_UMBRAL_DEF,
            minimo=0,
            maximo=1,
        ),
        Ajuste(
            clave=config.ENV_AUTOFEED_CAP,
            tipo="int",
            etiqueta="Auto-feed: tope diario por marca",
            ayuda="Máximo de piezas que el auto-feed crea por marca y día (cada una encola un "
            "copy+QA). Admite excepción por marca (abajo); 0 = desactiva el auto-feed.",
            grupo="tuning",
            defecto=config.AUTOFEED_CAP_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_RADAR_AUTO_GEO,
            tipo="select",
            etiqueta="Radar: geografía",
            ayuda="País del Radar de tendencias (lo usa el daemon de breaking).",
            grupo="tuning",
            defecto=config.RADAR_AUTO_GEO_DEF,
            opciones=_GEO_OPCIONES,
        ),
        Ajuste(
            clave=config.ENV_ALERTAS_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Alertas: intervalo (horas)",
            ayuda="Cada cuántas horas corre el barrido de alertas de rendimiento.",
            grupo="tuning",
            defecto=config.ALERTAS_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_ALERTAS_UMBRAL_ENGAGEMENT,
            tipo="float",
            etiqueta="Alertas: umbral de engagement (%)",
            ayuda="Engagement (%) por debajo del cual una pieza publicada dispara una alerta de bajo rendimiento.",
            grupo="tuning",
            defecto=config.ALERTAS_UMBRAL_ENGAGEMENT_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_MAX_JOBS,
            tipo="int",
            etiqueta="Jobs simultáneos",
            ayuda="Máximo de generaciones `claude` ejecutándose a la vez.",
            grupo="tuning",
            defecto=config.MAX_JOBS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_MEDIA_GC_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Limpieza media: intervalo (horas)",
            ayuda="Cada cuántas horas barre el daemon de limpieza de media huérfana.",
            grupo="tuning",
            defecto=config.MEDIA_GC_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
            tipo="int",
            etiqueta="Limpieza media: antigüedad mínima (horas)",
            ayuda="Un objeto de media más nuevo que esto nunca se borra, aunque parezca "
            "huérfano (protege las variantes del Estudio que aún se revisan).",
            grupo="tuning",
            defecto=config.MEDIA_GC_ANTIGUEDAD_HORAS_DEF,
            minimo=1,
        ),
        # --- Ingesta (Ola A) ------------------------------------------------------ #
        Ajuste(
            clave=config.ENV_INGESTA_BATCH,
            tipo="int",
            etiqueta="Ingesta: feeds por barrido",
            ayuda="Máximo de feeds RSS a sondear por barrido del motor de ingesta.",
            grupo="tuning",
            defecto=config.INGESTA_BATCH_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_INGESTA_WORKERS,
            tipo="int",
            etiqueta="Ingesta: descargas en paralelo",
            ayuda="Conexiones simultáneas para descargar feeds en un mismo barrido.",
            grupo="tuning",
            defecto=config.INGESTA_WORKERS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_INGESTA_MAX_ITEMS,
            tipo="int",
            etiqueta="Ingesta: artículos por feed",
            ayuda="Máximo de artículos a archivar por feed y sondeo.",
            grupo="tuning",
            defecto=config.INGESTA_MAX_ITEMS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_INGESTA_MAX_ERRORES,
            tipo="int",
            etiqueta="Ingesta: errores seguidos para auto-desactivar feed",
            ayuda="Tras este número de errores consecutivos el daemon apaga el feed "
            "automáticamente (Ola D). Se reintenta a mano desde la UI.",
            grupo="tuning",
            defecto=config.INGESTA_MAX_ERRORES_DEF,
            minimo=1,
        ),
        # --- Clustering (Ola B) -------------------------------------------------- #
        Ajuste(
            clave=config.ENV_CLUSTER_VENTANA_H,
            tipo="int",
            etiqueta="Clustering: ventana de agrupación (horas)",
            ayuda="Solo se cargan los clusters con actividad en esta ventana para "
            "decidir si un item nuevo pertenece a uno existente. Acota el trabajo.",
            grupo="tuning",
            defecto=config.CLUSTER_VENTANA_H_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_CLUSTER_BREAKING_FUENTES,
            tipo="int",
            etiqueta="Clustering: fuentes mínimas para marcar breaking",
            ayuda="Número de fuentes distintas requeridas para que una historia se "
            "marque automáticamente como breaking en la ventana de breaking.",
            grupo="tuning",
            defecto=config.CLUSTER_BREAKING_FUENTES_DEF,
            minimo=2,
        ),
        Ajuste(
            clave=config.ENV_CLUSTER_BREAKING_VENTANA_H,
            tipo="int",
            etiqueta="Clustering: ventana breaking (horas)",
            ayuda="Ventana de tiempo (horas) en la que deben coincidir las fuentes "
            "para que un cluster se marque como breaking.",
            grupo="tuning",
            defecto=config.CLUSTER_BREAKING_VENTANA_H_DEF,
            minimo=1,
        ),
        # --- Carril breaking (Ola C) --------------------------------------------- #
        Ajuste(
            clave=config.ENV_BREAKING_INTERVALO_MIN,
            tipo="int",
            etiqueta="Breaking: intervalo de barrido (minutos)",
            ayuda="Cada cuántos minutos barre el daemon del carril rápido de breaking.",
            grupo="tuning",
            defecto=config.BREAKING_INTERVALO_MIN_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_BREAKING_MAX,
            tipo="int",
            etiqueta="Breaking: borradores por barrido",
            ayuda="Máximo de borradores breaking a preparar por barrido "
            "(cada uno lanza claude -p).",
            grupo="tuning",
            defecto=config.BREAKING_MAX_DEF,
            minimo=1,
        ),
        # --- Traducción (Ola D) -------------------------------------------------- #
        Ajuste(
            clave=config.ENV_TRAD_MIN_SCORE,
            tipo="float",
            etiqueta="Traducción: score mínimo de cluster",
            ayuda="Score mínimo de un cluster extranjero para entrar a traducción. "
            "0 = traducir todo cluster reciente; sube el valor para limitar a los más relevantes.",
            grupo="tuning",
            defecto=config.TRAD_MIN_SCORE_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_TRAD_LOTE,
            tipo="int",
            etiqueta="Traducción: clusters por barrido",
            ayuda="Máximo de clusters extranjeros a traducir por barrido. "
            "El backlog pendiente se procesa en barridos sucesivos.",
            grupo="tuning",
            defecto=config.TRAD_LOTE_DEF,
            minimo=1,
        ),
        # --- SLA de frescura (Ola D) --------------------------------------------- #
        Ajuste(
            clave=config.ENV_FEED_SLA_MIN,
            tipo="int",
            etiqueta="Ingesta: SLA de frescura por feed (minutos)",
            ayuda="Un feed activo sin items nuevos en más de este margen aparece como "
            "'stale' en el panel de salud (/salud).",
            grupo="tuning",
            defecto=config.FEED_SLA_MIN_DEF,
            minimo=1,
        ),
        # --- Agentes de investigación (Ola 6) ------------------------------------ #
        Ajuste(
            clave=config.ENV_INVESTIGACION_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Investigación: intervalo (horas)",
            ayuda="Cada cuántas horas barre el daemon de investigación los briefs activos.",
            grupo="tuning",
            defecto=config.INVESTIGACION_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_INVESTIGACION_MAX,
            tipo="int",
            etiqueta="Investigación: máximo de briefs por barrido",
            ayuda="Máximo de briefs activos a ejecutar por barrido (cada uno lanza claude -p).",
            grupo="tuning",
            defecto=config.INVESTIGACION_MAX_DEF,
            minimo=1,
        ),
    ]


def catalogo() -> list[Ajuste]:
    """Lista completa de ajustes editables (la fuente de verdad): maestros de etapa, automatismos
    generales + publicación + tuning, y las excepciones por marca."""
    return (
        _maestros_etapa()
        + _construir_catalogo()
        + _ajustes_por_marca()
        + _autofeed_cap_por_marca()
        + _publicacion_por_marca()
    )


def por_clave(clave: str) -> Ajuste | None:
    """Ajuste del catalogo con esa `clave` (= nombre ENV), o None si no es editable."""
    for ajuste in catalogo():
        if ajuste.clave == clave:
            return ajuste
    return None


# --------------------------------------------------------------------------- #
# Casteo / validacion por tipo                                                #
# --------------------------------------------------------------------------- #


def _castea(ajuste: Ajuste, crudo: str) -> Any:
    """Castea un valor CRUDO (str) al tipo del ajuste. Tolerante: ante un crudo invalido
    cae al `defecto` del ajuste (mismo espiritu que los accesores de `config`)."""
    if ajuste.tipo == "bool":
        return crudo.strip().lower() in _VERDADEROS
    if ajuste.tipo == "int":
        try:
            valor = int(crudo)
        except (TypeError, ValueError):
            return ajuste.defecto
        if ajuste.minimo is not None and valor < ajuste.minimo:
            return int(ajuste.minimo)
        if ajuste.maximo is not None and valor > ajuste.maximo:
            return int(ajuste.maximo)
        return valor
    if ajuste.tipo == "float":
        try:
            valor = float(crudo)
        except (TypeError, ValueError):
            return ajuste.defecto
        if ajuste.minimo is not None and valor < ajuste.minimo:
            return float(ajuste.minimo)
        if ajuste.maximo is not None and valor > ajuste.maximo:
            return float(ajuste.maximo)
        return valor
    # select: el id se reporta tal cual (mayusculas para geo, igual que `config.radar_auto_geo`)
    valor = crudo.strip()
    if ajuste.clave == config.ENV_RADAR_AUTO_GEO:
        valor = valor.upper()
    ids = {o["id"] for o in ajuste.opciones}
    return valor if valor in ids else ajuste.defecto


def valor_y_fuente(ajuste: Ajuste) -> tuple[Any, str]:
    """Valor EFECTIVO (tipado) + su FUENTE ('store' | 'env' | 'defecto').

    Misma precedencia que `config._crudo`: store (UI) > env > defecto del catalogo.
    """
    desde_store = ajustes.obtener(ajuste.clave)
    if desde_store is not None:
        return _castea(ajuste, desde_store), "store"
    desde_env = os.environ.get(ajuste.clave)
    if desde_env is not None and desde_env.strip() != "":
        return _castea(ajuste, desde_env), "env"
    return ajuste.defecto, "defecto"


def a_dict(ajuste: Ajuste) -> dict[str, Any]:
    """Serializa un ajuste a su dict de API (con valor efectivo + fuente).

    Forma EXACTA del contrato con el frontend: `clave, tipo, etiqueta, ayuda, grupo,
    peligroso, valor (tipado), fuente, defecto (tipado)`, y solo cuando aplica `opciones`
    (select) y `min`/`max` (int/float).
    """
    valor, fuente = valor_y_fuente(ajuste)
    salida: dict[str, Any] = {
        "clave": ajuste.clave,
        "tipo": ajuste.tipo,
        "etiqueta": ajuste.etiqueta,
        "ayuda": ajuste.ayuda,
        "grupo": ajuste.grupo,
        "peligroso": ajuste.peligroso,
        "valor": valor,
        "fuente": fuente,
        "defecto": ajuste.defecto,
    }
    if ajuste.tipo == "select":
        salida["opciones"] = [dict(o) for o in ajuste.opciones]
    if ajuste.minimo is not None:
        salida["min"] = ajuste.minimo
    if ajuste.maximo is not None:
        salida["max"] = ajuste.maximo
    return salida


def validar_valor(ajuste: Ajuste, valor: Any) -> tuple[str | None, str | None]:
    """Valida/castea `valor` (del body de la API) y devuelve `(str_a_guardar, error)`.

    Exactamente uno de los dos es None: en exito `(str, None)`, en error `(None, mensaje)`.
    El string devuelto es lo que se persiste en el store (formato env-like).

    Reglas por tipo:
      - bool: acepta true/false (json) o "1"/"0"/"true"/"false"/... (texto). Guarda "1"/"0".
      - int: entero (o str numerico); respeta min/max -> error si fuera de rango.
      - float: numero (o str numerico); respeta min/max -> error si fuera de rango.
      - select: el id debe estar en `opciones` (geo se normaliza a mayusculas). Guarda el id.
    """
    if ajuste.tipo == "bool":
        if isinstance(valor, bool):
            return ("1" if valor else "0"), None
        if isinstance(valor, (int, float)) and valor in (0, 1):
            return ("1" if valor else "0"), None
        if isinstance(valor, str):
            v = valor.strip().lower()
            if v in _VERDADEROS:
                return "1", None
            if v in _FALSOS:
                return "0", None
        return None, f"'{ajuste.clave}' espera un valor booleano (true/false)."

    if ajuste.tipo == "int":
        if isinstance(valor, bool):  # bool es subtipo de int: rechazar explicito
            return None, f"'{ajuste.clave}' espera un número entero."
        try:
            n = int(valor) if not isinstance(valor, str) else int(valor.strip())
        except (TypeError, ValueError):
            return None, f"'{ajuste.clave}' espera un número entero."
        if ajuste.minimo is not None and n < ajuste.minimo:
            return None, f"'{ajuste.clave}' debe ser ≥ {int(ajuste.minimo)}."
        if ajuste.maximo is not None and n > ajuste.maximo:
            return None, f"'{ajuste.clave}' debe ser ≤ {int(ajuste.maximo)}."
        return str(n), None

    if ajuste.tipo == "float":
        if isinstance(valor, bool):
            return None, f"'{ajuste.clave}' espera un número."
        try:
            n = float(valor) if not isinstance(valor, str) else float(valor.strip())
        except (TypeError, ValueError):
            return None, f"'{ajuste.clave}' espera un número."
        if ajuste.minimo is not None and n < ajuste.minimo:
            return None, f"'{ajuste.clave}' debe ser ≥ {ajuste.minimo}."
        if ajuste.maximo is not None and n > ajuste.maximo:
            return None, f"'{ajuste.clave}' debe ser ≤ {ajuste.maximo}."
        return repr(n), None

    # select
    if not isinstance(valor, str):
        return None, f"'{ajuste.clave}' espera uno de los valores permitidos."
    v = valor.strip()
    if ajuste.clave == config.ENV_RADAR_AUTO_GEO:
        v = v.upper()
    ids = {o["id"] for o in ajuste.opciones}
    if v not in ids:
        permitidos = ", ".join(repr(o["id"]) for o in ajuste.opciones)
        return None, f"'{ajuste.clave}' debe ser uno de: {permitidos}."
    return v, None
