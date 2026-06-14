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

from . import ajustes, config, marcas, preferencias
from .dominio.clustering import (
    LISTON_MIN_MARCA_DEF as _LISTON_MIN_MARCA_DEF,
    LISTON_MIN_SCORE_DEF as _LISTON_MIN_SCORE_DEF,
)

# Conjuntos de verdad/falsedad para flags (mismos que `config`, fuente del parseo de bool).
_VERDADEROS = frozenset({"1", "true", "yes", "si", "sí", "on"})
_FALSOS = frozenset({"0", "false", "no", "off", ""})

# Titulos humanos de cada grupo (orden estable del contrato GET /api/ajustes). El orden manda
# el de aparición en la UI. Reparto (Fase 3: UN solo sitio para los ajustes de la máquina): TODO
# lo de la máquina de contenido —interruptor general, maestros de etapa, excepciones por marca,
# topes de admisión, el MOTOR DE NOTICIAS completo y los finos operacionales (limpieza,
# alertas, caducidades)— vive en el drawer de ajustes del MONITOR, repartido en secciones (`GRUPOS_MAQUINA` +
# `GRUPOS_INVESTIGACION` + sistema). Publicación se edita en Programación, junto a lo que
# programa; el plan diario por marca, en su diálogo «Plan y horarios» (también Programación).
GRUPOS: tuple[tuple[str, str], ...] = (
    ("maquina_global", "Máquina de contenido"),
    ("maestros_investigacion", "Todas las marcas"),
    ("automatizacion_marca_investigacion", "Excepciones por marca"),
    ("maestros_produccion", "Todas las marcas"),
    ("automatizacion_marca_produccion", "Excepciones por marca"),
    ("pipeline_topes", "Admisión del flujo"),
    ("publicacion", "Publicación"),
    ("publicacion_marca", "Excepciones por marca"),
    ("automatismos_generales", "Automatismos"),
    ("noticias_entrada", "Qué entra al pool"),
    ("noticias_rendimiento", "Rendimiento en redes"),
    ("noticias_produccion", "Producción automática"),
    ("noticias_produccion_marca", "Plan diario por marca"),
    # `noticias_tecnico` quedó reducido al TTL del perfil editorial (el resto de su contenido
    # —batch/workers/lotes/ventanas— se degradó a solo-env); el título refleja lo que queda.
    ("noticias_tecnico", "Perfil editorial"),
    ("tuning", "Sistema, limpieza y alertas"),
)
# NOTA (auditoría 2026-06, matar ruido de UI): los grupos `noticias_orden` y `noticias_breaking`
# se RETIRARON del catálogo: eran solo pesos/umbrales del algoritmo de ranking/clustering
# (tunables de ingeniería). Sus claves `KENI_SCORE_*`/`KENI_CLUSTER_BREAKING_*` siguen vivas
# en el código y se leen de env/defecto (`config._crudo`); simplemente ya no se editan en UI.

# Grupos de la sección «Investigación» del drawer del MONITOR: el proceso de investigación (su
# maestro y sus excepciones por marca) + el MOTOR DE NOTICIAS en lenguaje editorial (qué entra →
# orden del pool → rendimiento → última hora → producción automática → técnico). Antes se
# pintaban en el menú ⋮ de Noticias (`NoticiasHub`); la Fase 3 los consolidó en el drawer del
# Monitor (UN solo sitio para los ajustes de la máquina). `noticias_produccion_marca` (el plan
# diario por marca) NO está aquí: su editor único es el diálogo «Plan y horarios» de
# Programación. El orden de la tupla es el de las secciones en pantalla.
GRUPOS_INVESTIGACION: tuple[str, ...] = (
    "maestros_investigacion",
    "automatizacion_marca_investigacion",
    "noticias_entrada",
    "noticias_rendimiento",
    "noticias_produccion",
    "noticias_tecnico",
)

# Grupos de la sección «Máquina de contenido» del drawer del MONITOR (proceso de PRODUCCIÓN,
# ADR 0011): el interruptor general, el maestro de Producción (Producción/Arte), sus excepciones
# por marca y los topes de admisión. El proceso de INVESTIGACIÓN vive en el MISMO drawer, en su
# propia sección (`GRUPOS_INVESTIGACION`). Estos grupos se editan en el Monitor, junto a la cola
# que controlan. La fuente de verdad de "qué pinta el Monitor" son estas tuplas; el front las usa
# para repartir grupos.
GRUPOS_MAQUINA: tuple[str, ...] = (
    "maquina_global",
    "maestros_produccion",
    "automatizacion_marca_produccion",
    "pipeline_topes",
)



def _maestros_etapa() -> list[Ajuste]:
    """Los interruptores de etapa de la máquina + los maestros virtuales (ADR 0011).

    La tira «Pipeline en vivo» del Monitor opera las etapas FÍSICAS una a una: Selección
    (`KENI_PIPELINE_SELECCION`), Validación (`KENI_PIPELINE_VALIDACION`), Copy
    (`KENI_PIPELINE_COPY`) y Arte (`KENI_PIPELINE_ARTE`). Cada una es su propia clave del
    store (sin fan-out): el operador puede apagar una etapa sin tocar las demás.

    `KENI_INVESTIGACION` y `KENI_PRODUCCION` son VIRTUALES (no se leen en runtime): al
    guardarlas, la API escribe sus etapas físicas (`config.ETAPAS_INVESTIGACION` /
    `config.ETAPAS_PRODUCCION`) con el mismo valor. Su valor mostrado es el de una etapa
    representativa (ingesta para Investigación, copy para Producción). SIGUEN en el catálogo
    aunque la tira ya no las pinte: son la base de las excepciones por marca
    (`KENI_INVESTIGACION::marca` apaga el proceso entero con un toggle), el respaldo de
    lectura del riel de Noticias (etapas sin flag propio en catálogo: Fusión/Clasificación/
    Ranking) y el interruptor «de proceso» para API/MCP. «Publicar» vive en `publicacion`.
    """
    return [
        Ajuste(
            clave=config.ENV_INVESTIGACION,
            tipo="bool",
            etiqueta="Investigación",
            ayuda="Para todas las marcas: recolecta, deduplica, clasifica, rankea y "
            "verifica noticias para dejar el pool listo (no escribe copy). Virtual: "
            "enciende/apaga TODAS las etapas del proceso a la vez.",
            grupo="maestros_investigacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_SELECCION,
            tipo="bool",
            etiqueta="Selección",
            ayuda="Etapa física: recolecta e ingiere noticias de las fuentes al pool.",
            grupo="maestros_investigacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_VALIDACION,
            tipo="bool",
            etiqueta="Validación",
            ayuda="Etapa física: criba/QA de la fuente antes de escribir copy.",
            grupo="maestros_investigacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PRODUCCION,
            tipo="bool",
            etiqueta="Producción",
            ayuda="Para todas las marcas: redacta el copy que convierte una noticia "
            "verificada en pieza publicable (el arte tiene interruptor propio). Virtual: "
            "equivale hoy a la etapa Copy.",
            grupo="maestros_produccion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_COPY,
            tipo="bool",
            etiqueta="Copy",
            ayuda="Etapa física: redacta el copy de los temas admitidos al flujo.",
            grupo="maestros_produccion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_ARTE,
            tipo="bool",
            etiqueta="Arte IA",
            ayuda="Para todas las marcas: genera imagen por IA para los temas con copy y sin "
            "imagen.",
            grupo="maestros_produccion",
            defecto=False,
        ),
    ]


def _global_de_etapa(env_flag: str) -> bool:
    """Valor GLOBAL actual de una etapa (defecto de su toggle por-marca).

    Delegado en el resolver ÚNICO (`config.etapa_global_activa`): la misma lectura que usan
    el daemon y la vista Pipelines, para que el toggle nunca muestre otra cosa que el estado real.
    """
    return config.etapa_global_activa(env_flag)


def _ajustes_por_marca() -> list[Ajuste]:
    """Toggles `bool` por marca para «Investigación», «Producción» (virtuales: fan-out a sus
    etapas) y «Arte».

    Apagar «Investigación» en una marca la excluye del tramo de pool (ingesta→verificación);
    apagar «Producción» la deja sin copy automático; apagar «Arte», sin imagen por IA. Se
    generan en caliente desde el catálogo de marcas."""
    salida: list[Ajuste] = []
    for mid, nombre in marcas.opciones():
        salida.append(
            Ajuste(
                clave=config.clave_por_marca(config.ENV_INVESTIGACION, mid),
                tipo="bool",
                etiqueta=f"{nombre} · Investigación",
                ayuda=f"Apaga la investigación de noticias (pool) solo para «{nombre}».",
                grupo="automatizacion_marca_investigacion",
                defecto=_global_de_etapa(config.ENV_PIPELINE_SELECCION),
            )
        )
        salida.append(
            Ajuste(
                clave=config.clave_por_marca(config.ENV_PRODUCCION, mid),
                tipo="bool",
                etiqueta=f"{nombre} · Producción",
                ayuda=f"Apaga la producción de copy solo para «{nombre}».",
                grupo="automatizacion_marca_produccion",
                defecto=_global_de_etapa(config.ENV_PIPELINE_COPY),
            )
        )
        salida.append(
            Ajuste(
                clave=config.clave_por_marca(config.ENV_PIPELINE_ARTE, mid),
                tipo="bool",
                etiqueta=f"{nombre} · Arte IA",
                ayuda=f"Apaga la imagen por IA solo para «{nombre}».",
                grupo="automatizacion_marca_produccion",
                defecto=_global_de_etapa(config.ENV_PIPELINE_ARTE),
            )
        )
    return salida


def _plan_por_marca() -> list[Ajuste]:
    """PLAN EDITORIAL DIARIO por marca (`KENI_PLAN_DIA::marca`, texto "categoria:n,…").

    Es EL ajuste de volumen: cuántos temas auto-producir al día y de qué tipo, llenando cada
    cupo con lo mejor de su categoría (p. ej. UnoTV: "mx:4,internacional:4,breaking:2,
    entretenimiento:2,evergreen:1" = 13/día). Sustituye a los cupos por franja. Vacío = sin
    plan (cae al cupo diario global). Se generan en caliente desde el catálogo de marcas."""
    return [
        Ajuste(
            clave=config.clave_por_marca(config.ENV_PLAN_DIA, mid),
            tipo="texto",
            etiqueta=f"{nombre} · plan diario",
            ayuda="Cupos por categoría, formato «categoria:n» separados por comas; "
            "vacío = sin plan.",
            grupo="noticias_produccion_marca",
            defecto="",
        )
        for mid, nombre in marcas.opciones()
    ]


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


@dataclass(frozen=True)
class Ajuste:
    """Un ajuste editable del catalogo (declarativo)."""

    clave: str
    tipo: str  # 'bool' | 'int' | 'float' | 'select'
    etiqueta: str
    ayuda: str
    grupo: str  # 'maestros_etapa' | 'automatizacion_marca_investigacion' | 'automatizacion_marca_produccion' | 'automatismos_generales' | 'publicacion' | 'tuning'
    defecto: Any
    peligroso: bool = False
    opciones: tuple[dict[str, str], ...] = ()  # solo 'select': [{id, etiqueta}, ...]
    minimo: float | None = None  # solo int/float
    maximo: float | None = None  # solo int/float


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
            etiqueta="Encendida/apagada",
            ayuda="Interruptor general de toda la automatización.",
            grupo="maquina_global",
            defecto=False,
        ),
        # --- Automatismos generales (barridos del sistema, sin dimensión por marca) ----- #
        # Las 6 etapas de la máquina (Fusión/Editorial/Selección/Validación/Copy/Arte) NO están aquí:
        # su maestro vive en `_maestros_etapa()` y las excepciones por marca en `_ajustes_por_marca()`.
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
        Ajuste(
            clave=config.ENV_NOTICIAS_GC,
            tipo="bool",
            etiqueta="Limpieza del pool de noticias",
            ayuda="Purga periódicamente del pool las historias no llevadas al tablero, de "
            "una sola fuente, con score bajo y sin actividad reciente (más items huérfanos viejos).",
            grupo="automatismos_generales",
            defecto=False,
        ),
        # Automatismos de ingesta extra (también daemons del Monitor): Trends, feeds de algoritmo y
        # digest de sugerencias. Antes solo se veían como ESTADO en el Monitor; al estar en el
        # catálogo, sus toggles son REALES (editables desde el Monitor y desde aquí).
        Ajuste(
            clave=config.ENV_TRENDS,
            tipo="bool",
            etiqueta="Google Trends",
            ayuda="Ingiere tendencias (con sus noticias) al pool de noticias.",
            grupo="automatismos_generales",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_ALGORITMOS_AUTO,
            tipo="bool",
            etiqueta="Feeds de algoritmo",
            ayuda="Refresca periódicamente los feeds de cambios de algoritmo por marca.",
            grupo="automatismos_generales",
            defecto=False,
        ),
        # Re-derivación periódica de patrones (antes solo-env, el único gate de daemon fuera
        # de la UI): re-lee Metricool cada N días y refresca los perfiles de patrones por
        # marca. Voz/Reglas (criterio humano) jamás se tocan.
        Ajuste(
            clave=config.ENV_PATRONES_AUTO,
            tipo="bool",
            etiqueta="Patrones de marca",
            ayuda="Re-deriva periódicamente los patrones editoriales de cada marca desde sus "
            "métricas reales (la voz y las reglas humanas no se tocan).",
            grupo="automatismos_generales",
            defecto=False,
        ),
        # NOTA: las etapas del tramo noticia→copy (Fusión/Editorial/Selección/Validación/Copy/
        # Avance) NO tienen toggle propio: las agrupa el interruptor único «Generar»
        # (`KENI_GENERAR`, virtual con fan-out; ver `claves_fisicas`). El master
        # «Priorizar por rendimiento» (KENI_RENDIMIENTO_RANKING) tampoco: NO es un daemon on/off,
        # sino un modulador del ranking, así que vive con sus pesos en `noticias_ranking`.
        # --- Publicacion (peligroso) ----------------------------------------------- #
        Ajuste(
            clave=config.ENV_PUBLICAR_REAL,
            tipo="bool",
            etiqueta="Publicación real",
            ayuda="Envía las piezas programadas al scheduler real de Metricool; apagado = dry-run.",
            grupo="publicacion",
            defecto=False,
            peligroso=True,
        ),
        # --- Máquina de contenido · admisión del flujo continuo (grupo `pipeline_topes`) --- #
        # Viven en el MONITOR (junto a la cola que controlan), NO en Configuración. FLUJO CONTINUO:
        # no hay intervalo (tick corto fijo) ni topes por etapa; el volumen lo regulan estos knobs
        # de ADMISIÓN (y `KENI_MAX_JOBS` aguas abajo). In=out: solo entra lo que cabe en vuelo.
        Ajuste(
            clave=config.ENV_PIPELINE_MAX,
            tipo="int",
            etiqueta="Historias admitidas por marca",
            ayuda="Máximo de historias que la Selección admite de golpe por marca.",
            grupo="pipeline_topes",
            defecto=config.PIPELINE_MAX_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_EN_VUELO_MAX,
            tipo="int",
            etiqueta="Piezas en vuelo por marca",
            ayuda="Tope de piezas sin terminar (Validación pendiente o sin copy) por marca; "
            "no se admite más hasta que algo termina.",
            grupo="pipeline_topes",
            defecto=config.PIPELINE_EN_VUELO_MAX_DEF,
            minimo=1,
        ),
        # (KENI_AUTOGEN_ARTE_MAX —temas ilustrados por ciclo— se DEGRADÓ a solo-env: batch
        # interno del barrido de Arte, no un control de operación. Sigue leyéndose de env.)
        # --- Economía de tokens (presupuesto diario + kill switch; `presupuesto_ia.py`) --- #
        # La generación usa la MISMA suscripción `claude` que el equipo: estos knobs evitan que
        # una avalancha de fondo agote los tokens de todos. Editables en caliente (Monitor).
        Ajuste(
            clave=config.ENV_GENERACION_PAUSADA,
            tipo="bool",
            etiqueta="Generación con IA: pausada",
            ayuda="No se encola nada nuevo y el worker deja de ejecutar jobs "
            "(lo encolado espera; lo que corre termina).",
            grupo="maquina_global",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PRESUPUESTO_TOKENS_DIA,
            tipo="int",
            etiqueta="Presupuesto diario de tokens",
            ayuda="Tokens (entrada+salida) de generación por día UTC; al agotarse se corta el "
            "trabajo automático (lo manual sigue hasta el margen); 0 = sin límite.",
            grupo="pipeline_topes",
            defecto=config.PRESUPUESTO_TOKENS_DIA_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_PRESUPUESTO_MARGEN_MANUAL,
            tipo="int",
            etiqueta="Margen extra para lanzamientos manuales (%)",
            ayuda="Con el presupuesto agotado, lo manual sigue funcionando hasta presupuesto + "
            "este margen; superado, corte total hasta el día siguiente.",
            grupo="pipeline_topes",
            defecto=config.PRESUPUESTO_MARGEN_MANUAL_DEF,
            minimo=0,
            maximo=100,
        ),
        # (KENI_PROMPT_MAX_CHARS —tope de contexto por generación— se DEGRADÓ a solo-env:
        # salvaguarda técnica de tokens, no un control editorial; el presupuesto diario y el
        # margen manual son los knobs de gasto del operador. Sigue leyéndose de env.)
        # --- Tuning (int/float/select) --------------------------------------------- #
        # Esfuerzo de razonamiento de TODA la generacion (`claude --effort`). Antes vivia
        # en el almacen aparte de `preferencias.py` (TOML local) detras de
        # `/api/config/esfuerzo`; consolidado aqui como select del catalogo (fuente unica;
        # aquel endpoint queda como shim deprecado). Las opciones/etiquetas salen de
        # `preferencias` (fuente unica de los niveles validos); "" = predeterminado del
        # modelo (no se pasa `--effort`).
        Ajuste(
            clave=config.ENV_ESFUERZO,
            tipo="select",
            etiqueta="Esfuerzo de razonamiento",
            ayuda="Cuánto «piensa» la IA al generar: más esfuerzo = mejor calidad, más lento "
            "y más caro. «Predeterminado» usa el esfuerzo por defecto del modelo.",
            grupo="tuning",
            defecto="",
            opciones=tuple(
                {"id": nivel, "etiqueta": preferencias.ESFUERZO_ETIQUETAS[nivel]}
                for nivel in ("", *preferencias.ESFUERZOS_VALIDOS)
            ),
        ),
        # (Los INTERVALOS de daemons —KENI_ALERTAS_INTERVALO_HORAS, KENI_MEDIA_GC_INTERVALO_HORAS,
        # KENI_NOTICIAS_GC_INTERVALO_HORAS— y la concurrencia KENI_MAX_JOBS se DEGRADARON a
        # solo-env: ritmo/capacidad de ingeniería, no controles de operación. El operador
        # gobierna QUÉ corre (toggles) y los UMBRALES de alto nivel, no cada cuánto barre
        # un hilo. Siguen leyéndose de env/defecto.)
        Ajuste(
            clave=config.ENV_ALERTAS_UMBRAL_ENGAGEMENT,
            tipo="float",
            etiqueta="Alertas: umbral de engagement (%)",
            ayuda="Engagement (%) por debajo del cual una pieza publicada dispara una alerta de bajo "
            "rendimiento.",
            grupo="tuning",
            defecto=config.ALERTAS_UMBRAL_ENGAGEMENT_DEF,
            minimo=0.1,
        ),
        Ajuste(
            clave=config.ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
            tipo="int",
            etiqueta="Limpieza media: antigüedad mínima (horas)",
            ayuda="Un objeto de media más nuevo que esto (horas) nunca se borra, aunque parezca "
            "huérfano.",
            grupo="tuning",
            defecto=config.MEDIA_GC_ANTIGUEDAD_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_NOTICIAS_GC_SCORE_UMBRAL,
            tipo="float",
            etiqueta="Limpieza noticias: umbral de score",
            ayuda="Una historia de una sola fuente con score por debajo de esto y sin actividad "
            "reciente se purga; 0 = no purgar por score (de 0 a 1).",
            grupo="tuning",
            defecto=config.NOTICIAS_GC_SCORE_UMBRAL_DEF,
            minimo=0,
            maximo=1,
        ),
        Ajuste(
            clave=config.ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
            tipo="int",
            etiqueta="Limpieza noticias: inactividad mínima (horas)",
            ayuda="Una historia más nueva que esto (horas) nunca se purga, aunque sea de baja "
            "relevancia.",
            grupo="tuning",
            defecto=config.NOTICIAS_GC_INACTIVIDAD_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_NOTICIAS_TTL_H,
            tipo="int",
            etiqueta="Noticias: caducidad del pool (horas)",
            ayuda="Una historia sin actividad en estas horas caduca sola (pasa a descartada; "
            "lo usado nunca caduca); 0 = sin caducidad.",
            grupo="tuning",
            defecto=config.NOTICIAS_TTL_H_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_NOTICIAS_RETENCION_H,
            tipo="int",
            etiqueta="Noticias: retención de lo caducado (horas)",
            ayuda="Lo caducado sin usar se borra definitivamente tras estas horas; "
            "0 = no borrar nunca (solo caducar).",
            grupo="tuning",
            defecto=config.NOTICIAS_RETENCION_H_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_PERFIL_EDITORIAL_TTL_HORAS,
            tipo="int",
            etiqueta="Refresco del perfil editorial (horas)",
            ayuda="Cada cuántas horas la IA vuelve a leer la línea editorial de cada marca para "
            "afinar el encaje de las noticias.",
            grupo="noticias_tecnico",
            defecto=config.PERFIL_EDITORIAL_TTL_HORAS_DEF,
            minimo=1,
        ),
        # --- Producción automática (grupo `noticias_produccion`) -------------------------- #
        # LISTÓN de producción automática: el panel lista TODO el pool jerarquizado, pero promover
        # una historia a tema dispara QA+copy (claude -p: coste real de tokens). Estos dos umbrales
        # son ese listón (la regla vive en `dominio.clustering.evaluar_liston`, explicable).
        Ajuste(
            clave=config.ENV_PROMOVER_MIN_SCORE,
            tipo="float",
            etiqueta="Relevancia mínima para producir en automático",
            ayuda="Una historia solo dispara la producción automática si su relevancia llega a "
            "este valor; 0 = sin listón (de 0 a 1).",
            grupo="noticias_produccion",
            defecto=_LISTON_MIN_SCORE_DEF,
            minimo=0,
            maximo=1,
        ),
        Ajuste(
            clave=config.ENV_PROMOVER_MIN_MARCA,
            tipo="float",
            etiqueta="Encaje mínimo con la marca",
            ayuda="Cuánto debe encajar la historia con los temas de la marca para producirse en "
            "automático (0.2 ≈ un término de la marca en el título); 0 = sin listón (de 0 a 1).",
            grupo="noticias_produccion",
            defecto=_LISTON_MIN_MARCA_DEF,
            minimo=0,
            maximo=1,
        ),
        # MADURACIÓN + CUPOS de volumen: dedican tiempo a ELEGIR (la corroboración se acumula
        # antes de competir por plaza) y anclan el volumen auto-producido a la cadencia real de
        # publicación de cada marca (pocas plazas por franja → selección, no goteo continuo).
        Ajuste(
            clave=config.ENV_PROMOVER_MADURACION_MIN,
            tipo="int",
            etiqueta="Minutos de maduración antes de producir",
            ayuda="Una historia espera estos minutos en el pool antes de poder producirse en "
            "automático; 0 = sin espera.",
            grupo="noticias_produccion",
            defecto=config.PROMOVER_MADURACION_MIN_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_CUPO_DIA,
            tipo="int",
            etiqueta="Cupo diario sin plan",
            ayuda="Techo de temas auto-producidos por marca en las últimas 24 horas cuando la "
            "marca no tiene plan diario; 0 = sin cupo.",
            grupo="noticias_produccion",
            defecto=config.CUPO_DIA_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_PLAN_DIA,
            tipo="texto",
            etiqueta="Plan diario por defecto",
            ayuda="Cupos por categoría para las marcas sin plan propio, formato «categoria:n» "
            "separados por comas (p. ej. «mx:4,internacional:4,breaking:2»); vacío = sin plan.",
            grupo="noticias_produccion",
            defecto="",
        ),
        # El master «Priorizar por rendimiento» vive AQUÍ (no en automatismos): no arranca ningún
        # daemon, modula el ranking. Sus tres parámetros (KENI_SCORE_PESO_RENDIMIENTO,
        # KENI_RENDIMIENTO_TOP_N, KENI_RENDIMIENTO_MIN_PIEZAS) se DEGRADARON a solo-env:
        # moduladores del algoritmo, no controles de operación. El operador decide SI se
        # prioriza; cuánto y cómo es tuning de ingeniería (env/defecto).
        Ajuste(
            clave=config.ENV_RENDIMIENTO_RANKING,
            tipo="bool",
            etiqueta="Dar prioridad a lo que mejor funciona",
            ayuda="Sube en el pool las historias de las líneas editoriales con mejor engagement "
            "real en redes.",
            grupo="noticias_rendimiento",
            defecto=False,
        ),
        # --- Qué entra al pool (grupo `noticias_entrada`) -------------------------- #
        # Solo queda el control EDITORIAL (el filtro por agenda de marca). Los tunables de
        # ingeniería de la ingesta se DEGRADARON a solo-env: KENI_INGESTA_BATCH/_WORKERS/
        # _MAX_ITEMS/_MAX_ERRORES (batch/concurrencia/topes/backoff), KENI_TRAD_MIN_SCORE/
        # _LOTE (umbral y lote de traducción), KENI_FEED_SLA_MIN (SLA técnico de fuentes),
        # KENI_CLUSTER_VENTANA_H y KENI_CLUSTER_BREAKING_PESO/_VENTANA_H (umbrales de
        # clustering/última hora). Todas siguen leyéndose de env/defecto.
        Ajuste(
            clave=config.ENV_INGESTA_FILTRO,
            tipo="bool",
            etiqueta="Solo noticias de los temas de la marca",
            ayuda="Una fuente asignada a una marca solo guarda noticias que mencionan algún tema "
            "de esa marca; el resto ni entra al pool.",
            grupo="noticias_entrada",
            defecto=True,
        ),
        # (Los pesos del score del pool —KENI_SCORE_PESO_CORROBORACION/_MARCA/_FRESCURA/
        # _VELOCIDAD/_VIRALIDAD— y KENI_SCORE_BONUS_BREAKING se DEGRADARON a solo-env junto
        # con su grupo `noticias_orden`: son el algoritmo de ranking, no operación.)
    ]


def catalogo() -> list[Ajuste]:
    """Lista completa de ajustes editables (la fuente de verdad): maestros de etapa, automatismos
    generales + publicación + tuning, y las excepciones por marca."""
    return (
        _maestros_etapa()
        + _construir_catalogo()
        + _ajustes_por_marca()
        + _plan_por_marca()
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


# Tope de longitud de un ajuste de tipo "texto" (defensa de la API; un plan real usa ~60).
_TEXTO_MAX = 500


def _castea(ajuste: Ajuste, crudo: str) -> Any:
    """Castea un valor CRUDO (str) al tipo del ajuste. Tolerante: ante un crudo invalido
    cae al `defecto` del ajuste (mismo espiritu que los accesores de `config`)."""
    if ajuste.tipo == "bool":
        return crudo.strip().lower() in _VERDADEROS
    if ajuste.tipo == "texto":
        return crudo.strip()
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
    # select: el id se reporta tal cual; debe estar en `opciones` o cae al defecto.
    valor = crudo.strip()
    ids = {o["id"] for o in ajuste.opciones}
    return valor if valor in ids else ajuste.defecto


# Maestros VIRTUALES (ADR 0011): cada uno hace fan-out a sus etapas físicas, y su estado
# mostrado se lee de una etapa REPRESENTATIVA (tras cualquier escritura desde la UI todas las
# etapas del maestro coinciden, así que la representativa basta).
_ETAPAS_VIRTUAL: dict[str, tuple[str, ...]] = {
    config.ENV_INVESTIGACION: config.ETAPAS_INVESTIGACION,
    config.ENV_PRODUCCION: config.ETAPAS_PRODUCCION,
}
_LECTURA_VIRTUAL: dict[str, str] = {
    config.ENV_INVESTIGACION: config.ENV_PIPELINE_SELECCION,
    config.ENV_PRODUCCION: config.ENV_PIPELINE_COPY,
}


def claves_fisicas(clave: str) -> list[str]:
    """Claves REALES del store que escribe/borra un ajuste del catálogo.

    Para casi todos es su propia clave. Para los maestros VIRTUALES «Investigación»/«Producción»
    (global o `::marca`) son sus etapas físicas (`_ETAPAS_VIRTUAL`) con el mismo sufijo de
    marca: un botón por proceso, varias claves coherentes — las etapas no pueden divergir desde
    la UI.
    """
    base, sep, marca = clave.partition(config.SEP_MARCA)
    etapas = _ETAPAS_VIRTUAL.get(base)
    if etapas is None:
        return [clave]
    sufijo = f"{sep}{marca}" if sep else ""
    return [f"{etapa}{sufijo}" for etapa in etapas]


def _clave_lectura(clave: str) -> str:
    """Clave que REPRESENTA el valor de un ajuste: la propia, salvo los maestros virtuales,
    cuyo estado mostrado se lee de su etapa representativa (`_LECTURA_VIRTUAL`)."""
    base, sep, marca = clave.partition(config.SEP_MARCA)
    repr_etapa = _LECTURA_VIRTUAL.get(base)
    if repr_etapa is None:
        return clave
    return f"{repr_etapa}{sep}{marca}" if sep else repr_etapa


def valor_y_fuente(ajuste: Ajuste) -> tuple[Any, str]:
    """Valor EFECTIVO (tipado) + su FUENTE ('store' | 'env' | 'defecto').

    Misma precedencia que `config._crudo`: store (UI) > env > defecto del catalogo. La clave
    virtual «Generar» se resuelve desde su clave de lectura (etapa de Copy).
    """
    clave = _clave_lectura(ajuste.clave)
    desde_store = ajustes.obtener(clave)
    if desde_store is not None:
        return _castea(ajuste, desde_store), "store"
    desde_env = os.environ.get(clave)
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

    if ajuste.tipo == "texto":
        if not isinstance(valor, str):
            return None, f"'{ajuste.clave}' espera texto."
        texto = valor.strip()
        if len(texto) > _TEXTO_MAX:
            return None, f"'{ajuste.clave}' admite hasta {_TEXTO_MAX} caracteres."
        # Un PLAN DIARIO se valida por forma: cada segmento no vacío debe ser «categoria:n».
        if ajuste.clave.split(config.SEP_MARCA, 1)[0] == config.ENV_PLAN_DIA and texto:
            for trozo in texto.split(","):
                cat, sep, n = trozo.partition(":")
                if not sep or not cat.strip() or not n.strip().isdigit():
                    return None, (
                        "El plan se escribe como «categoria:n» separados por comas "
                        "(p. ej. «mx:4,internacional:4,breaking:2»)."
                    )
        return texto, None

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
    ids = {o["id"] for o in ajuste.opciones}
    if v not in ids:
        permitidos = ", ".join(repr(o["id"]) for o in ajuste.opciones)
        return None, f"'{ajuste.clave}' debe ser uno de: {permitidos}."
    return v, None
