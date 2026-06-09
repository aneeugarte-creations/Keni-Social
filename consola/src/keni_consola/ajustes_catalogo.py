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
# el de aparición en la UI. Repartidos por OBJETIVO: la MÁQUINA DE CONTENIDO (interruptor general +
# maestros de etapa + excepciones por marca + cadencia/topes) vive en el Monitor; Publicación, los
# automatismos de fondo (daemons on/off), el MOTOR DE NOTICIAS (ingesta/agrupación/traducción), el
# RANKING DE NOTICIAS (master + pesos del score) y los Ajustes finos operacionales (jobs, limpieza,
# alertas) viven en Configuración.
GRUPOS: tuple[tuple[str, str], ...] = (
    ("maquina_global", "Máquina de contenido (interruptor general)"),
    ("maestros_etapa", "Maestros de etapa (todas las marcas)"),
    ("automatizacion_marca", "Excepciones por marca"),
    ("pipeline_topes", "Admisión del flujo continuo"),
    ("publicacion", "Publicación"),
    ("publicacion_marca", "Publicación · excepciones por marca"),
    ("automatismos_generales", "Automatismos generales"),
    ("noticias_motor", "Motor de noticias · ingesta, agrupación y traducción"),
    ("noticias_ranking", "Ranking de noticias · jerarquización del pool"),
    ("tuning", "Ajustes finos · sistema, limpieza y alertas"),
)

# Grupos de la MÁQUINA DE CONTENIDO: el interruptor general, los maestros de etapa, sus excepciones
# por marca y los topes por barrido. Estos NO viven en Configuración (que se queda con lo global/
# genérico): se editan en el MONITOR, junto a la cola que controlan. La fuente de verdad de "qué es
# máquina" es esta tupla; el front la usa para repartir grupos entre Configuración y Monitor.
GRUPOS_MAQUINA: tuple[str, ...] = (
    "maquina_global",
    "maestros_etapa",
    "automatizacion_marca",
    "pipeline_topes",
)

# Las 6 ETAPAS de la máquina de contenido (grupo `maestros_etapa`), con NOMBRES CONSOLIDADOS:
# etapa = variable = toggle. La env de cada una es `KENI_PIPELINE_<ETAPA>` y su label "<Etapa> IA"
# (Selección no es IA), igual que la etapa en la vista de runs — 1 toggle = 1 etapa:
#   - KENI_PIPELINE_FUSION     → "Fusión IA"     (dedup IA de historias del mismo evento),
#   - KENI_PIPELINE_EDITORIAL  → "Editorial IA"  (perfil editorial IA para el encaje con la marca),
#   - KENI_PIPELINE_SELECCION  → "Selección"     (ingiere/agrupa y promueve las top a temas; no IA),
#   - KENI_PIPELINE_VALIDACION → "Validación IA" (criba la fuente con IA antes del copy),
#   - KENI_PIPELINE_COPY       → "Copy IA"       (genera el copy automático),
#   - KENI_PIPELINE_ARTE       → "Arte IA"       (genera la imagen por IA).
# La tupla es (env, etiqueta, descripción). El maestro vive en `maestros_etapa`; las excepciones
# por marca en `automatizacion_marca`. (Aprobación es gate humano: no tiene toggle.)
_ETAPA_FUSION = (config.ENV_PIPELINE_FUSION, "Fusión IA", "une con IA las historias del mismo evento (dedup semántico)")
_ETAPA_EDITORIAL = (config.ENV_PIPELINE_EDITORIAL, "Editorial IA", "encaje con la marca vía perfil editorial IA")
_ETAPA_SELECCION = (config.ENV_PIPELINE_SELECCION, "Selección", "ingiere y promueve historias a temas (no IA)")
_ETAPA_VALIDACION = (config.ENV_PIPELINE_VALIDACION, "Validación IA", "criba la fuente con IA antes de generar copy")
_ETAPA_COPY = (config.ENV_PIPELINE_COPY, "Copy IA", "genera copy automático de los temas que aún no lo tienen")
_ETAPA_ARTE = (config.ENV_PIPELINE_ARTE, "Arte IA", "genera imagen por IA para los temas con copy y sin imagen")

# Las 6 etapas en orden de flujo (Fusión → Editorial → Selección → Validación → Copy → Arte).
_ETAPAS: tuple[tuple[str, str, str], ...] = (
    _ETAPA_FUSION, _ETAPA_EDITORIAL, _ETAPA_SELECCION, _ETAPA_VALIDACION, _ETAPA_COPY, _ETAPA_ARTE,
)

# Etapas CON excepción por marca (`_ajustes_por_marca`). Las SEIS: apagar una marca la excluye de
# esa etapa, las demás siguen.
_ETAPAS_MARCA: tuple[tuple[str, str, str], ...] = _ETAPAS


def _maestros_etapa() -> list[Ajuste]:
    """Maestro GLOBAL de cada una de las 6 etapas. Apagar el maestro deja la etapa en espera para
    TODAS las marcas; las excepciones por marca solo restan con el maestro encendido."""
    return [
        Ajuste(
            clave=env_flag,
            tipo="bool",
            etiqueta=etiqueta,
            ayuda=f"Para todas las marcas: {desc}.",
            grupo="maestros_etapa",
            defecto=False,
        )
        for env_flag, etiqueta, desc in _ETAPAS
    ]


def _global_de_etapa(env_flag: str) -> bool:
    """Valor GLOBAL actual de una etapa (defecto de su toggle por-marca)."""
    return {
        config.ENV_PIPELINE_FUSION: config.fusion_semantica_activa,
        config.ENV_PIPELINE_EDITORIAL: config.perfil_editorial_activo,
        config.ENV_PIPELINE_SELECCION: config.ingesta_activa,
        config.ENV_PIPELINE_VALIDACION: config.qa_activo,
        config.ENV_PIPELINE_COPY: config.pipeline_activo,
        config.ENV_PIPELINE_ARTE: config.autogen_arte_activo,
    }[env_flag]()


def _ajustes_por_marca() -> list[Ajuste]:
    """Toggles `bool` por (marca × etapa) para las SEIS etapas (Fusión/Editorial/Selección/Validación/
    Copy/Arte). Se generan en caliente desde el catálogo de marcas, así que añadir una marca añade
    sus toggles sin código."""
    salida: list[Ajuste] = []
    for mid, nombre in marcas.opciones():
        for env_flag, etiqueta_etapa, _desc in _ETAPAS_MARCA:
            salida.append(
                Ajuste(
                    clave=config.clave_por_marca(env_flag, mid),
                    tipo="bool",
                    etiqueta=f"{nombre} · {etiqueta_etapa}",
                    ayuda=f"Apaga «{etiqueta_etapa}» solo para esta marca.",
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
            ayuda="Purga periódicamente el RUIDO del pool: historias no llevadas al tablero, de "
            "una sola fuente, con score bajo y sin actividad reciente (+ items huérfanos viejos). "
            "Conserva lo usado, corroborado, de score alto o reciente. No borra por edad sola.",
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
        Ajuste(
            clave=config.ENV_SUGERENCIAS_EDITORIALES,
            tipo="bool",
            etiqueta="Sugerencias editoriales",
            ayuda="Digest diario de sugerencias editoriales por marca.",
            grupo="automatismos_generales",
            defecto=False,
        ),
        # NOTA: Fusión (KENI_PIPELINE_FUSION) y Editorial/encaje (KENI_PIPELINE_EDITORIAL) ya NO viven
        # aquí: ahora son ETAPAS del pipeline (grupo `maestros_etapa` + excepción por marca), 1
        # toggle = 1 etapa, como el resto. Ver `_ETAPA_FUSION`/`_ETAPA_EDITORIAL`. El master
        # «Priorizar por rendimiento» (KENI_RENDIMIENTO_RANKING) tampoco: NO es un daemon on/off,
        # sino un modulador del ranking, así que vive con sus pesos en `noticias_ranking`.
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
        # --- Máquina de contenido · admisión del flujo continuo (grupo `pipeline_topes`) --- #
        # Viven en el MONITOR (junto a la cola que controlan), NO en Configuración. FLUJO CONTINUO:
        # no hay intervalo (tick corto fijo) ni topes por etapa; el volumen lo regulan estos knobs
        # de ADMISIÓN (y `KENI_MAX_JOBS` aguas abajo). In=out: solo entra lo que cabe en vuelo.
        Ajuste(
            clave=config.ENV_PIPELINE_MAX,
            tipo="int",
            etiqueta="Historias admitidas por marca",
            ayuda="Máximo de historias que la Selección admite de golpe por marca (acotado además "
            "por el cupo en vuelo: nunca entra más de lo que cabe).",
            grupo="pipeline_topes",
            defecto=config.PIPELINE_MAX_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_EN_VUELO_MAX,
            tipo="int",
            etiqueta="Piezas en vuelo por marca (regulador del flujo)",
            ayuda="Tope de piezas sin terminar (Validación pendiente o sin copy) por marca. Es EL "
            "regulador: no se admite más hasta que algo sale por el otro lado (in=out). Una pieza "
            "que falla repetidamente sale del cupo marcada como problema.",
            grupo="pipeline_topes",
            defecto=config.PIPELINE_EN_VUELO_MAX_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_AUTOGEN_ARTE_MAX,
            tipo="int",
            etiqueta="Arte: temas ilustrados por ciclo",
            ayuda="Máximo de temas a ilustrar en cada ciclo de la etapa de Arte (cada uno llama "
            "al proveedor de imagen; acota el gasto del proveedor).",
            grupo="pipeline_topes",
            defecto=config.AUTOGEN_ARTE_MAX_DEF,
            minimo=1,
        ),
        # --- Tuning (int/float/select) --------------------------------------------- #
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
            ayuda="Engagement (%) por debajo del cual una pieza publicada dispara una alerta de bajo "
            "rendimiento. Debe ser > 0 (un umbral nulo desactivaría la señal; usa el toggle maestro para eso).",
            grupo="tuning",
            defecto=config.ALERTAS_UMBRAL_ENGAGEMENT_DEF,
            minimo=0.1,
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
        Ajuste(
            clave=config.ENV_NOTICIAS_GC_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Limpieza noticias: intervalo (horas)",
            ayuda="Cada cuántas horas barre el daemon de limpieza del pool de noticias.",
            grupo="tuning",
            defecto=config.NOTICIAS_GC_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_NOTICIAS_GC_SCORE_UMBRAL,
            tipo="float",
            etiqueta="Limpieza noticias: umbral de score",
            ayuda="Una historia de UNA sola fuente con score por debajo de esto (y sin actividad "
            "reciente) se considera ruido y se purga. 0 = no purgar por score. [0-1].",
            grupo="tuning",
            defecto=config.NOTICIAS_GC_SCORE_UMBRAL_DEF,
            minimo=0,
            maximo=1,
        ),
        Ajuste(
            clave=config.ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
            tipo="int",
            etiqueta="Limpieza noticias: inactividad mínima (horas)",
            ayuda="Una historia más nueva que esto nunca se purga, aunque sea de baja relevancia "
            "(protege lo recién visto que aún podría agrupar más fuentes).",
            grupo="tuning",
            defecto=config.NOTICIAS_GC_INACTIVIDAD_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_PERFIL_EDITORIAL_TTL_HORAS,
            tipo="int",
            etiqueta="Perfil editorial: refresco (horas)",
            ayuda="Cada cuántas horas se re-extrae con IA el perfil editorial de cada marca "
            "(también se refresca antes si cambia la línea editorial).",
            grupo="noticias_motor",
            defecto=config.PERFIL_EDITORIAL_TTL_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_FUSION_SEMANTICA_MAX,
            tipo="int",
            etiqueta="Fusión semántica: historias por marca/barrido",
            ayuda="Máximo de historias por marca que se mandan a la IA a agrupar en cada barrido "
            "(acota coste y tamaño de contexto).",
            grupo="noticias_motor",
            defecto=config.FUSION_SEMANTICA_MAX_DEF,
            minimo=2,
        ),
        # --- Ranking de noticias · jerarquización del pool (grupo `noticias_ranking`) ----- #
        # El master «Priorizar por rendimiento» vive AQUÍ (no en automatismos): no arranca ningún
        # daemon, modula el ranking. Debajo, los pesos de la combinación lineal del score.
        Ajuste(
            clave=config.ENV_RENDIMIENTO_RANKING,
            tipo="bool",
            etiqueta="Priorizar por rendimiento (Metricool)",
            ayuda="El ranking da un empujón a las historias de las líneas editoriales que MEJOR "
            "funcionan en redes. Anti-sesgo: una línea solo cuenta con una muestra mínima de piezas "
            "medidas y se limita a un top-N (no monotematiza). Activa los tres ajustes de abajo.",
            grupo="noticias_ranking",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_SCORE_PESO_RENDIMIENTO,
            tipo="float",
            etiqueta="Ranking: peso rendimiento (líneas top)",
            ayuda="Cuánto pesa que la historia caiga en una línea editorial de alto rendimiento. Solo "
            "cuenta con «Priorizar por rendimiento» activo; si lo dejas vacío con esa opción activa, "
            "se aplica un auto-peso de 0.10 (renormalizando los demás pesos). [0-1].",
            grupo="noticias_ranking",
            defecto=config.SCORE_PESO_RENDIMIENTO_DEF,
            minimo=0,
            maximo=1,
        ),
        Ajuste(
            clave=config.ENV_RENDIMIENTO_TOP_N,
            tipo="int",
            etiqueta="Rendimiento: nº de líneas top",
            ayuda="Cuántas líneas (las de mejor engagement) reciben el empujón de rendimiento. Solo "
            "con «Priorizar por rendimiento» activo.",
            grupo="noticias_ranking",
            defecto=config.RENDIMIENTO_TOP_N_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_RENDIMIENTO_MIN_PIEZAS,
            tipo="int",
            etiqueta="Rendimiento: muestra mínima por línea",
            ayuda="Una línea solo cuenta como top si tiene al menos estas piezas medidas (anti-sesgo: "
            "evita encaramar una línea que «funcionó una vez»). Solo con «Priorizar por rendimiento» activo.",
            grupo="noticias_ranking",
            defecto=config.RENDIMIENTO_MIN_PIEZAS_DEF,
            minimo=1,
        ),
        # --- Ingesta (Ola A) ------------------------------------------------------ #
        Ajuste(
            clave=config.ENV_INGESTA_BATCH,
            tipo="int",
            etiqueta="Ingesta: feeds por barrido",
            ayuda="Máximo de feeds RSS a sondear por barrido del motor de ingesta.",
            grupo="noticias_motor",
            defecto=config.INGESTA_BATCH_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_INGESTA_WORKERS,
            tipo="int",
            etiqueta="Ingesta: descargas en paralelo",
            ayuda="Conexiones simultáneas para descargar feeds en un mismo barrido.",
            grupo="noticias_motor",
            defecto=config.INGESTA_WORKERS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_INGESTA_MAX_ITEMS,
            tipo="int",
            etiqueta="Ingesta: artículos por feed",
            ayuda="Máximo de artículos a archivar por feed y sondeo.",
            grupo="noticias_motor",
            defecto=config.INGESTA_MAX_ITEMS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_INGESTA_MAX_ERRORES,
            tipo="int",
            etiqueta="Ingesta: errores seguidos para auto-desactivar feed",
            ayuda="Tras este número de errores consecutivos el daemon apaga el feed "
            "automáticamente (Ola D). Se reintenta a mano desde la UI.",
            grupo="noticias_motor",
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
            grupo="noticias_motor",
            defecto=config.CLUSTER_VENTANA_H_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_CLUSTER_BREAKING_FUENTES,
            tipo="int",
            etiqueta="Clustering: fuentes mínimas para marcar breaking",
            ayuda="Número de fuentes distintas requeridas para que una historia se "
            "marque automáticamente como breaking en la ventana de breaking.",
            grupo="noticias_motor",
            defecto=config.CLUSTER_BREAKING_FUENTES_DEF,
            minimo=2,
        ),
        Ajuste(
            clave=config.ENV_CLUSTER_BREAKING_VENTANA_H,
            tipo="int",
            etiqueta="Clustering: ventana breaking (horas)",
            ayuda="Ventana de tiempo (horas) en la que deben coincidir las fuentes "
            "para que un cluster se marque como breaking.",
            grupo="noticias_motor",
            defecto=config.CLUSTER_BREAKING_VENTANA_H_DEF,
            minimo=1,
        ),
        # --- Jerarquización: pesos del algoritmo de ponderación del score (suman ~1) -------- #
        Ajuste(
            clave=config.ENV_SCORE_PESO_CORROBORACION,
            tipo="float",
            etiqueta="Ranking: peso corroboración (nº fuentes)",
            ayuda="Cuánto pesa que varias fuentes se hagan eco de una historia (señal de "
            "tendencia). Más alto = prioriza lo que cubren muchas fuentes. [0-1].",
            grupo="noticias_ranking",
            defecto=config.SCORE_PESO_CORROBORACION_DEF,
            minimo=0,
            maximo=1,
        ),
        Ajuste(
            clave=config.ENV_SCORE_PESO_MARCA,
            tipo="float",
            etiqueta="Ranking: peso relevancia de marca",
            ayuda="Cuánto pesa el encaje de la historia con la línea editorial de la marca "
            "(p. ej. UnoTV nacional MX, Claro Sports deporte MX). [0-1].",
            grupo="noticias_ranking",
            defecto=config.SCORE_PESO_MARCA_DEF,
            minimo=0,
            maximo=1,
        ),
        Ajuste(
            clave=config.ENV_SCORE_PESO_FRESCURA,
            tipo="float",
            etiqueta="Ranking: peso frescura (recencia)",
            ayuda="Cuánto pesa que la historia sea reciente. Más alto = favorece lo nuevo. [0-1].",
            grupo="noticias_ranking",
            defecto=config.SCORE_PESO_FRESCURA_DEF,
            minimo=0,
            maximo=1,
        ),
        Ajuste(
            clave=config.ENV_SCORE_PESO_VIRALIDAD,
            tipo="float",
            etiqueta="Ranking: peso viralidad",
            ayuda="Cuánto pesa la señal de viralidad agregada de la historia. [0-1].",
            grupo="noticias_ranking",
            defecto=config.SCORE_PESO_VIRALIDAD_DEF,
            minimo=0,
            maximo=1,
        ),
        Ajuste(
            clave=config.ENV_SCORE_BONUS_BREAKING,
            tipo="float",
            etiqueta="Ranking: bonus breaking",
            ayuda="Empujón extra (aditivo) al score de las historias marcadas como breaking. [0-1].",
            grupo="noticias_ranking",
            defecto=config.SCORE_BONUS_BREAKING_DEF,
            minimo=0,
            maximo=1,
        ),
        # --- Traducción (Ola D) -------------------------------------------------- #
        Ajuste(
            clave=config.ENV_TRAD_MIN_SCORE,
            tipo="float",
            etiqueta="Traducción: score mínimo de cluster",
            ayuda="Score mínimo de un cluster extranjero para entrar a traducción. "
            "0 = traducir todo cluster reciente; sube el valor para limitar a los más relevantes.",
            grupo="noticias_motor",
            defecto=config.TRAD_MIN_SCORE_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_TRAD_LOTE,
            tipo="int",
            etiqueta="Traducción: clusters por barrido",
            ayuda="Máximo de clusters extranjeros a traducir por barrido. "
            "El backlog pendiente se procesa en barridos sucesivos.",
            grupo="noticias_motor",
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
            grupo="noticias_motor",
            defecto=config.FEED_SLA_MIN_DEF,
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
    # select: el id se reporta tal cual; debe estar en `opciones` o cae al defecto.
    valor = crudo.strip()
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
    ids = {o["id"] for o in ajuste.opciones}
    if v not in ids:
        permitidos = ", ".join(repr(o["id"]) for o in ajuste.opciones)
        return None, f"'{ajuste.clave}' debe ser uno de: {permitidos}."
    return v, None
