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
from .dominio.agrupar import UMBRAL_MIN_SCORE_DEF as _UMBRAL_MIN_SCORE_DEF
from .dominio.generar import MAX_SLIDES_CARRUSEL as _MAX_SLIDES_CARRUSEL

# Conjuntos de verdad/falsedad para flags (mismos que `config`, fuente del parseo de bool).
_VERDADEROS = frozenset({"1", "true", "yes", "si", "sí", "on"})
_FALSOS = frozenset({"0", "false", "no", "off", ""})

# Titulos humanos de cada grupo (orden estable del contrato GET /api/ajustes). El orden manda
# el de aparición en la UI. Cada grupo lo edita su superficie propia: los toggles de etapa y sus
# knobs operacionales en la vista Pipeline (por etapa), el presupuesto y el esfuerzo en Economía,
# los automatismos en el detalle de cada daemon (/sistema), la publicación en Programación y el
# plan diario por marca en «Plan y horarios» (también Programación).
GRUPOS: tuple[tuple[str, str], ...] = (
    ("maquina_global", "Máquina de contenido"),
    ("maestros_investigacion", "Todas las marcas"),
    ("automatizacion_marca_investigacion", "Excepciones por marca"),
    ("maestros_produccion", "Todas las marcas"),
    ("automatizacion_marca_produccion", "Excepciones por marca"),
    # `pipeline_topes` quedó reducido al PRESUPUESTO de tokens/coste (los caps de admisión se
    # degradaron a solo-env); se edita en la página de Economía, no en el drawer de la máquina.
    ("pipeline_topes", "Economía de tokens"),
    ("pieza", "Publicación"),
    ("publicacion_marca", "Excepciones por marca"),
    ("presupuesto_marca", "Presupuesto por marca"),
    ("automatismos_generales", "Automatismos"),
    ("noticias_rendimiento", "Rendimiento en redes"),
    ("noticias_produccion", "Producción automática"),
    ("noticias_produccion_marca", "Plan diario por marca"),
    # `tuning` quedó reducido al esfuerzo de razonamiento (el resto —umbrales/cadencias de
    # barrido— se degradó a solo-env); se edita en la página de Economía (palanca calidad/coste).
    ("tuning", "Esfuerzo de razonamiento"),
)
# NOTA: los grupos `noticias_orden` y `noticias_breaking` NO están en el catálogo: son solo
# pesos/umbrales del algoritmo de ranking/clustering (tunables de ingeniería). Sus claves
# `KENI_SCORE_*`/`KENI_CLUSTER_BREAKING_*` viven en el código y se leen de env/defecto
# (`config._crudo`); no se editan en UI.



def _maestros_etapa() -> list[Ajuste]:
    """Los interruptores de etapa de la máquina, uno por etapa física (ADR 0011).

    La vista Pipeline opera cada etapa por su propia clave del store (sin fan-out): Recolectar
    (`KENI_PIPELINE_RECOLECTAR`), Verificar (`KENI_PIPELINE_VERIFICAR`), Redactar
    (`KENI_PIPELINE_REDACTAR`), Ilustrar (`KENI_PIPELINE_ILUSTRAR`)… El operador apaga una etapa
    sin tocar las demás; la cascada (crítica apaga lo posterior) la calcula la propia vista a
    partir de estos estados. «Publicar» vive en `pieza`.
    """
    return [
        Ajuste(
            clave=config.ENV_PIPELINE_RECOLECTAR,
            tipo="bool",
            etiqueta="Recolectar",
            ayuda="Etapa física: recolecta noticias de las fuentes al pool.",
            grupo="maestros_investigacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_FUSIONAR,
            tipo="bool",
            etiqueta="Fusionar",
            ayuda="Etapa física: dedup semántico (Haiku) de las notas del mismo hecho con titulares "
            "distintos antes de priorizar. ON por defecto.",
            grupo="maestros_investigacion",
            defecto=True,
        ),
        Ajuste(
            clave=config.ENV_PRIORIZAR_PERFIL_IA,
            tipo="bool",
            etiqueta="Priorizar",
            ayuda="Etapa física: refresca el perfil editorial por marca (Haiku) para que el ranking "
            "del pool puntúe con sus keywords. OFF por defecto.",
            grupo="maestros_investigacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_TRENDS,
            tipo="bool",
            etiqueta="Google Trends",
            ayuda="Fuente de ingesta extra: un daemon ingiere las tendencias de Google (con sus "
            "noticias) al pool, en paralelo a las fuentes RSS de Recolectar.",
            grupo="maestros_investigacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_VERIFICAR,
            tipo="bool",
            etiqueta="Verificar",
            ayuda="Etapa física: verificación/verificación de la fuente antes de escribir el copy.",
            grupo="maestros_investigacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_TRADUCIR,
            tipo="bool",
            etiqueta="Traducir",
            ayuda="Etapa física: traduce a español de México los clusters extranjeros recientes "
            "antes de admitirlos. ON por defecto.",
            grupo="maestros_investigacion",
            defecto=True,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_ADMITIR,
            tipo="bool",
            etiqueta="Admitir",
            ayuda="Etapa física: promueve las historias verificadas del pool a temas en la mesa de "
            "redacción. ADITIVA sobre Recolectar (necesita ambas). ON por defecto.",
            grupo="maestros_investigacion",
            defecto=True,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_DECISOR,
            tipo="bool",
            etiqueta="Decisor",
            ayuda="Etapa física: elige el formato (foto vs carrusel) del tema antes de Redactar. "
            "OFF por defecto (sin ella, Redactar decide el formato en su propio prompt).",
            grupo="maestros_produccion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_REDACTAR,
            tipo="bool",
            etiqueta="Redactar",
            ayuda="Etapa física: redacta el copy de los temas admitidos al flujo.",
            grupo="maestros_produccion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_SUGERIR_HASHTAGS,
            tipo="bool",
            etiqueta="Keywords",
            ayuda="Etapa física: propone hashtags + la keyword visual que alimenta el buscador de "
            "stock. READ-ONLY (solo deja una propuesta en gris). ON por defecto.",
            grupo="maestros_produccion",
            defecto=True,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_REVISAR,
            tipo="bool",
            etiqueta="Revisar",
            ayuda="Etapa física: verificación ADVISORY de voz/calidad del copy antes del avance "
            "(no bloquea; solo degrada y deja nota). OFF por defecto.",
            grupo="maestros_produccion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_ILUSTRAR,
            tipo="bool",
            etiqueta="Ilustrar",
            ayuda="Para todas las marcas: genera imagen por IA para los temas con copy y sin "
            "imagen.",
            grupo="maestros_produccion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_PIPELINE_STOCK,
            tipo="bool",
            etiqueta="Stock",
            ayuda="Para los temas con copy y sin imagen, baja una foto de AYUDA (la original del "
            "RSS o una de bancos gratuitos) para que el feed no salga en gris. Es solo ayuda "
            "visual (atenuada, «SIN LICENCIA»): nunca se publica sin autorizar. ON por defecto.",
            grupo="maestros_produccion",
            defecto=True,
        ),
        Ajuste(
            clave=config.ENV_CRITICA_IA,
            tipo="bool",
            etiqueta="Crítica",
            ayuda="Añade a la cadena de aprobación un nivel de revisión IA con visión sobre la "
            "pieza terminada (tras los OK humanos). OFF por defecto.",
            grupo="maestros_produccion",
            defecto=False,
        ),
    ]


def _default_de_etapa(env_flag: str) -> bool:
    """Default DE FÁBRICA de una etapa (el valor del toggle por-marca cuando no hay override).

    Delegado en el resolver ÚNICO (`config.etapa_default`): el suelo que ve una marca sin su
    propio override, la misma lectura que usan el daemon y la vista Pipeline.
    """
    return config.etapa_default(env_flag)


# Fases EDITABLES por marca de cada proceso (ADR 0011, rev. fase×marca): cada fase tiene su
# toggle `ENV::marca` independiente, así apagar una fase en una marca NO afecta a las demás
# (p. ej. UnoTV apaga Crítica sin tocar el resto). Los pasos PRE-marca o cross-marca (Clasificar,
# Cotejar…) quedan SOLO globales: no se puede gatear por una marca que aún no existe.
_FASES_MARCA_INVESTIGACION: tuple[tuple[str, str], ...] = (
    (config.ENV_PIPELINE_RECOLECTAR, "Recolectar"),
    (config.ENV_PIPELINE_FUSIONAR, "Fusionar"),
    (config.ENV_PIPELINE_TRADUCIR, "Traducir"),
    (config.ENV_PRIORIZAR_PERFIL_IA, "Priorizar"),
    (config.ENV_PIPELINE_VERIFICAR, "Verificar"),
    (config.ENV_PIPELINE_ADMITIR, "Admitir"),
)
_FASES_MARCA_PRODUCCION: tuple[tuple[str, str], ...] = (
    (config.ENV_PIPELINE_DECISOR, "Decisor"),
    (config.ENV_PIPELINE_REDACTAR, "Redactar"),
    (config.ENV_PIPELINE_SUGERIR_HASHTAGS, "Keywords"),
    (config.ENV_PIPELINE_ILUSTRAR, "Ilustrar"),
    (config.ENV_PIPELINE_STOCK, "Stock"),
    (config.ENV_PIPELINE_REVISAR, "Revisar"),
    (config.ENV_CRITICA_IA, "Crítica"),
)


def _ajustes_por_marca() -> list[Ajuste]:
    """Toggles `bool` por marca: cada FASE del pipeline editable por separado (`ENV_FASE::marca`).

    Apagar una fase concreta (Recolectar, Verificar, Redactar, Crítica…) la desvía SOLO en esa
    marca, sin afectar a las demás. Se generan en caliente desde el catálogo de marcas."""
    salida: list[Ajuste] = []
    for mid, nombre in marcas.opciones():
        # Cada fase del proceso, por separado (la divergencia por fase que permite la rev. fase×marca).
        for flag, etapa in _FASES_MARCA_INVESTIGACION:
            salida.append(
                Ajuste(
                    clave=config.clave_por_marca(flag, mid),
                    tipo="bool",
                    etiqueta=f"{nombre} · {etapa}",
                    ayuda=f"Apaga la fase «{etapa}» solo para «{nombre}».",
                    grupo="automatizacion_marca_investigacion",
                    defecto=_default_de_etapa(flag),
                )
            )
        for flag, etapa in _FASES_MARCA_PRODUCCION:
            salida.append(
                Ajuste(
                    clave=config.clave_por_marca(flag, mid),
                    tipo="bool",
                    etiqueta=f"{nombre} · {etapa}",
                    ayuda=f"Apaga la fase «{etapa}» solo para «{nombre}».",
                    grupo="automatizacion_marca_produccion",
                    defecto=_default_de_etapa(flag),
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


def _plan_redes_por_marca() -> list[Ajuste]:
    """REDES del plan diario por marca (`KENI_PLAN_REDES::marca`, CSV de ids de red).

    Declara qué redes espera el plan por slot (`facebook,instagram`, …); el calendario las usa
    para marcar huecos por red. No cambia cómo se generan las piezas. Vacío = sin selección. Se
    generan en caliente desde el catálogo de marcas."""
    return [
        Ajuste(
            clave=config.clave_por_marca(config.ENV_PLAN_REDES, mid),
            tipo="texto",
            etiqueta=f"{nombre} · redes del plan",
            ayuda="Ids de red separados por comas; el calendario marca huecos por red.",
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


# Topes de tokens por motor (env, etiqueta) que se ofrecen TAMBIÉN por marca, separando IN/OUT.
_TOPES_TOKENS_MARCA: tuple[tuple[str, str], ...] = (
    (config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA, "tokens entrada · Investigación"),
    (config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA, "tokens salida · Investigación"),
    (config.ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA, "tokens entrada · Producción"),
    (config.ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA, "tokens salida · Producción"),
)


def _presupuesto_por_marca() -> list[Ajuste]:
    """Presupuesto diario de coste (USD) y PARADA DE EMERGENCIA por marca (`KENI_*::marca`).

    Mismo patrón de override por-marca que las etapas: son INDEPENDIENTES del control global y el
    corte de un job de la marca toma el MÁS restrictivo entre su control de marca y el global (ver
    `presupuesto_ia`). El cap USD `0` = la marca no añade tope (solo aplica el global); la parada,
    apagada por defecto. Se generan en caliente desde el catálogo de marcas (añadir una marca añade
    sus controles sin tocar código)."""
    salida: list[Ajuste] = []
    for mid, nombre in marcas.opciones():
        salida.append(
            Ajuste(
                clave=config.clave_por_marca(config.ENV_PRESUPUESTO_USD_DIA, mid),
                tipo="float",
                etiqueta=f"{nombre} · presupuesto (USD/día)",
                ayuda=f"Coste real (USD) de generación de «{nombre}» por día UTC; al agotarse se "
                "corta su trabajo automático (lo manual sigue hasta el margen); 0 = sin tope "
                "propio (solo aplica el cap global). Corta el más restrictivo entre marca y global.",
                grupo="presupuesto_marca",
                defecto=0.0,
                minimo=0,
            )
        )
        salida.append(
            Ajuste(
                clave=config.clave_por_marca(config.ENV_GENERACION_PAUSADA, mid),
                tipo="bool",
                etiqueta=f"{nombre} · parada de emergencia",
                ayuda=f"Corta TODA la generación de «{nombre}» (fondo y manual) sin tocar al resto; "
                "ortogonal al kill switch global (basta con que uno de los dos esté activo).",
                grupo="presupuesto_marca",
                defecto=False,
            )
        )
        # Ritmo PROPIO de la marca: manda sobre el global; escala los caps por barrido de «nombre».
        salida.append(
            Ajuste(
                clave=config.clave_por_marca(config.ENV_RITMO, mid),
                tipo="int",
                etiqueta=f"{nombre} · ritmo de producción (%)",
                ayuda=f"Escala cuánto trabajo nuevo entra por barrido para «{nombre}»; 100% = "
                "normal, 50% = mitad, 25% = un cuarto. Baja el gasto sin apagar etapas.",
                grupo="presupuesto_marca",
                defecto=config.RITMO_DEF,
                minimo=10,
                maximo=100,
            )
        )
        # Topes de tokens por motor (IN/OUT) PROPIOS de la marca: 0 = sin tope (solo el global).
        for env, etapa in _TOPES_TOKENS_MARCA:
            salida.append(
                Ajuste(
                    clave=config.clave_por_marca(env, mid),
                    tipo="int",
                    etiqueta=f"{nombre} · {etapa}",
                    ayuda=f"Tope de tokens de «{nombre}» por día UTC en {etapa.lower()}; al agotarse "
                    "corta ese motor de la marca (lo manual sigue hasta el margen); 0 = sin tope "
                    "propio. Corta el más restrictivo entre marca y global.",
                    grupo="presupuesto_marca",
                    defecto=0,
                    minimo=0,
                )
            )
    return salida


@dataclass(frozen=True)
class Ajuste:
    """Un ajuste editable del catalogo (declarativo)."""

    clave: str
    tipo: str  # 'bool' | 'int' | 'float' | 'select'
    etiqueta: str
    ayuda: str
    grupo: str  # 'maestros_etapa' | 'automatizacion_marca_investigacion' | 'automatizacion_marca_produccion' | 'automatismos_generales' | 'pieza' | 'tuning'
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
        # Las 6 etapas de la máquina (Fusionar/Priorizar/Recolectar/Verificar/Redactar/Ilustrar) NO están aquí:
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
            etiqueta="Limpieza de media suelta",
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
            "una sola fuente, con score bajo y sin actividad reciente (más items sueltos viejos).",
            grupo="automatismos_generales",
            defecto=False,
        ),
        # Automatismos de ingesta extra (también daemons del Monitor): feeds de algoritmo y digest
        # de sugerencias. Al estar en el catálogo, sus toggles son REALES (editables desde el
        # Monitor y desde aquí). Google Trends, por ser ingesta del pool, vive con Investigación.
        Ajuste(
            clave=config.ENV_ALGORITMOS_AUTO,
            tipo="bool",
            etiqueta="Feeds de algoritmo",
            ayuda="Refresca periódicamente los feeds de cambios de algoritmo por marca.",
            grupo="automatismos_generales",
            defecto=False,
        ),
        # Re-derivación periódica de patrones: re-lee Metricool cada N días y refresca los
        # perfiles de patrones por marca. Voz/Reglas (criterio humano) jamás se tocan.
        Ajuste(
            clave=config.ENV_PATRONES_AUTO,
            tipo="bool",
            etiqueta="Patrones de marca",
            ayuda="Re-deriva periódicamente los patrones editoriales de cada marca desde sus "
            "métricas reales (la voz y las reglas humanas no se tocan).",
            grupo="automatismos_generales",
            defecto=False,
        ),
        # NOTA: las etapas de la fase noticia→copy (Recolectar/Verificar/Redactar…) tienen su
        # propio toggle en `_maestros_etapa()`, no aquí. El master «Priorizar por rendimiento»
        # (KENI_RENDIMIENTO_RANKING) NO es un daemon on/off sino un modulador de la priorización,
        # así que vive con sus pesos en `noticias_ranking`.
        # --- Pieza (peligroso) ----------------------------------------------- #
        Ajuste(
            clave=config.ENV_PUBLICAR_REAL,
            tipo="bool",
            etiqueta="Publicación real",
            ayuda="El botón de publicar envía la pieza a Metricool de verdad; apagado = solo previsualiza.",
            grupo="pieza",
            defecto=False,
            peligroso=True,
        ),
        # (Los CAPS de admisión del flujo continuo —KENI_PIPELINE_MAX (historias admitidas por
        # marca) y KENI_PIPELINE_EN_PROCESO_MAX (piezas en proceso por marca)— se DEGRADARON a
        # solo-env: topes de capacidad de ingeniería, no controles editoriales. Igual que
        # KENI_AUTOGEN_ARTE_MAX, KENI_AUTOGEN_COPY_MAX y KENI_MAX_JOBS. Siguen leyéndose de
        # env/defecto, con override por marca vía store para los caps por marca.)
        # --- Economía de tokens (presupuesto diario + kill switch; `presupuesto_ia.py`) --- #
        # NOTA: estos topes de presupuesto se editan en la página de ECONOMÍA (gasto real +
        # proyección), no en el drawer «Ajustes de la máquina»; siguen en el catálogo para que
        # `/api/ajustes` los persista cuando Economía los guarda por clave.
        # La generación usa la MISMA suscripción `claude` que el equipo: estos knobs evitan que
        # una ráfaga de fondo agote los tokens de todos. Editables en caliente (Monitor).
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
            clave=config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA,
            tipo="int",
            etiqueta="Tope diario de tokens de entrada · Investigación",
            ayuda="Tokens de entrada del motor de investigación por día UTC; al agotarse se corta "
            "SOLO ese motor (lo manual sigue hasta el margen); 0 = sin límite. Rige a la vez que "
            "el tope de salida y el cap global de coste: corta el más restrictivo.",
            grupo="pipeline_topes",
            defecto=config.PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA,
            tipo="int",
            etiqueta="Tope diario de tokens de salida · Investigación",
            ayuda="Tokens de salida del motor de investigación por día UTC; al agotarse se corta "
            "SOLO ese motor (lo manual sigue hasta el margen); 0 = sin límite. Rige a la vez que "
            "el tope de entrada y el cap global de coste: corta el más restrictivo.",
            grupo="pipeline_topes",
            defecto=config.PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA,
            tipo="int",
            etiqueta="Tope diario de tokens de entrada · Producción",
            ayuda="Tokens de entrada del motor de producción por día UTC; al agotarse se corta "
            "SOLO ese motor (lo manual sigue hasta el margen); 0 = sin límite. Rige a la vez que "
            "el tope de salida y el cap global de coste: corta el más restrictivo.",
            grupo="pipeline_topes",
            defecto=config.PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA,
            tipo="int",
            etiqueta="Tope diario de tokens de salida · Producción",
            ayuda="Tokens de salida del motor de producción por día UTC; al agotarse se corta "
            "SOLO ese motor (lo manual sigue hasta el margen); 0 = sin límite. Rige a la vez que "
            "el tope de entrada y el cap global de coste: corta el más restrictivo.",
            grupo="pipeline_topes",
            defecto=config.PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_PRESUPUESTO_USD_DIA,
            tipo="float",
            etiqueta="Presupuesto diario de coste (USD)",
            ayuda="Coste real (USD) de generación por día UTC; al agotarse se corta el trabajo "
            "automático (lo manual sigue hasta el margen); 0 = sin límite. Mejor proxy del "
            "gasto que los tokens; rige a la vez que el presupuesto de tokens (corta el más "
            "restrictivo).",
            grupo="pipeline_topes",
            defecto=config.PRESUPUESTO_USD_DIA_DEF,
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
        # RITMO global de producción: dial gradual del gasto. Escala los caps por barrido de la
        # auto-producción sin apagar etapas. Cada marca puede sobreescribirlo (ver
        # `_presupuesto_por_marca`).
        Ajuste(
            clave=config.ENV_RITMO,
            tipo="int",
            etiqueta="Ritmo de producción (%)",
            ayuda="Escala cuánto trabajo nuevo entra por barrido; 100% = normal, 50% = mitad, "
            "25% = un cuarto. Baja el gasto sin apagar etapas.",
            grupo="pipeline_topes",
            defecto=config.RITMO_DEF,
            minimo=10,
            maximo=100,
        ),
        # (KENI_PROMPT_MAX_CHARS —tope de contexto por generación— se DEGRADÓ a solo-env:
        # salvaguarda técnica de tokens, no un control editorial; el presupuesto diario y el
        # margen manual son los knobs de gasto del operador. Sigue leyéndose de env.)
        # --- Tuning (int/float/select) --------------------------------------------- #
        # Esfuerzo de razonamiento de TODA la generacion (`claude --effort`). Select del
        # catalogo (fuente unica); el endpoint `/api/config/esfuerzo` queda como shim
        # deprecado. Las opciones/etiquetas salen de `preferencias` (fuente unica de los
        # niveles validos); "" = predeterminado del modelo (no se pasa `--effort`).
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
        # (Los UMBRALES y CADENCIAS de barrido —KENI_ALERTAS_UMBRAL_ENGAGEMENT,
        # KENI_MEDIA_GC_ANTIGUEDAD_HORAS, KENI_NOTICIAS_GC_SCORE_UMBRAL,
        # KENI_NOTICIAS_GC_INACTIVIDAD_HORAS, KENI_NOTICIAS_TTL_H, KENI_NOTICIAS_RETENCION_H,
        # KENI_PERFIL_EDITORIAL_TTL_HORAS— se DEGRADARON a solo-env, junto a los INTERVALOS de
        # daemon y KENI_MAX_JOBS: tunables de ingeniería, no controles de operación. El operador
        # gobierna QUÉ corre (los toggles on/off de cada daemon), no cada umbral de su barrido.
        # Siguen leyéndose de env/defecto.)
        # --- Producción automática (grupo `noticias_produccion`) -------------------------- #
        # UMBRAL de producción automática: el panel lista TODO el pool jerarquizado, pero promover
        # una historia a tema dispara Verificar+Redactar (claude -p: coste real de tokens). Este
        # umbral de score es ese mínimo (la regla vive en `dominio.agrupar.evaluar_umbral`).
        Ajuste(
            clave=config.ENV_PROMOVER_MIN_SCORE,
            tipo="float",
            etiqueta="Relevancia mínima para producir en automático",
            ayuda="Una historia solo dispara la producción automática si su relevancia llega a "
            "este valor; 0 = sin umbral (de 0 a 1).",
            grupo="noticias_produccion",
            defecto=_UMBRAL_MIN_SCORE_DEF,
            minimo=0,
            maximo=1,
        ),
        # Tope de slides del panel automático de carrusel (Redactar, camino Decisor=carrusel):
        # cuántas tarjetas EXTRA (sin portada) pide el modelo como máximo. El tope técnico de
        # IG/FB (`MAX_SLIDES_CARRUSEL`) es el techo: `dominio.generar` lo recorta igual aunque
        # se configure más alto.
        Ajuste(
            clave=config.ENV_CARRUSEL_MAX_SLIDES,
            tipo="int",
            etiqueta="Slides máximos del carrusel automático",
            ayuda="Cuántas tarjetas extra (sin contar la portada) puede pedir como máximo el "
            "panel editorial automático; un carrusel corto se siente menos saturado.",
            grupo="noticias_produccion",
            defecto=config.CARRUSEL_MAX_SLIDES_DEF,
            minimo=2,
            maximo=_MAX_SLIDES_CARRUSEL,
        ),
        # Canal PORTAL — copy AUTOMÁTICO (legado). OFF: los temas del Portal nacen con su pieza
        # mecánica (foto del artículo + titular como copy-in) y el copy lo lanza un humano con
        # «Generar» desde el feed Portal. ON: la producción los redacta sola (como antes).
        Ajuste(
            clave=config.ENV_PORTAL_COPY_AUTO,
            tipo="bool",
            etiqueta="Copy automático del Portal",
            ayuda="Redactar en automático los temas del canal Portal (fuente propia). Apagado, "
            "la tarjeta del Portal nace con la foto del artículo y su titular, y el copy se "
            "genera solo al pulsar «Generar».",
            grupo="noticias_produccion",
            defecto=False,
        ),
        # (KENI_PROMOVER_MADURACION_MIN —minutos de maduración antes de producir— se DEGRADÓ a
        # solo-env. El VOLUMEN lo gobierna el PLAN EDITORIAL DIARIO por marca (`KENI_PLAN_DIA::marca`,
        # gate de auto-producción): se edita en Programación → «Plan y horarios», no aquí. Sin plan
        # por marca, esa marca no auto-produce.)
        # El master «Priorizar por rendimiento» vive AQUÍ (no en automatismos): no arranca ningún
        # daemon, modula la priorización. Sus tres parámetros (KENI_SCORE_PESO_RENDIMIENTO,
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
        # --- Entrada al pool (sin controles editables) -------------------------- #
        # La puerta del pool NO filtra: se archiva TODO lo que entra por un feed (el filtro por
        # vocabulario se retiró — «digerir todo y decidir aguas abajo»). Los tunables de ingeniería
        # de la ingesta (KENI_INGESTA_BATCH/_WORKERS/_MAX_ITEMS/_MAX_ERRORES, KENI_TRAD_MIN_SCORE/
        # _LOTE, KENI_FEED_SLA_MIN, KENI_CLUSTER_VENTANA_H, KENI_CLUSTER_BREAKING_PESO/_VENTANA_H) y
        # los pesos del score del pool (KENI_SCORE_PESO_*, KENI_SCORE_BONUS_BREAKING) se leen de
        # env/defecto, fuera de la UI.
    ]


def catalogo() -> list[Ajuste]:
    """Lista completa de ajustes editables (la fuente de verdad): maestros de etapa, automatismos
    generales + publicación + tuning, y las excepciones por marca."""
    return (
        _maestros_etapa()
        + _construir_catalogo()
        + _ajustes_por_marca()
        + _plan_por_marca()
        + _plan_redes_por_marca()
        + _publicacion_por_marca()
        + _presupuesto_por_marca()
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


def valor_y_fuente(ajuste: Ajuste) -> tuple[Any, str]:
    """Valor EFECTIVO (tipado) + su FUENTE ('store' | 'env' | 'defecto').

    Misma precedencia que `config._crudo`: store (UI) > env > defecto del catalogo.
    """
    clave = ajuste.clave
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
        base_clave = ajuste.clave.split(config.SEP_MARCA, 1)[0]
        # Un PLAN DIARIO se valida por forma: cada segmento no vacío debe ser «categoria:n».
        if base_clave == config.ENV_PLAN_DIA and texto:
            for trozo in texto.split(","):
                cat, sep, n = trozo.partition(":")
                if not sep or not cat.strip() or not n.strip().isdigit():
                    return None, (
                        "El plan se escribe como «categoria:n» separados por comas "
                        "(p. ej. «mx:4,internacional:4,breaking:2»)."
                    )
        # Las REDES del plan se validan por catálogo: cada id debe ser una red canónica.
        if base_clave == config.ENV_PLAN_REDES and texto:
            from . import redes

            for trozo in texto.split(","):
                rid = trozo.strip().lower()
                if rid and not redes.es_red(rid):
                    permitidas = ", ".join(redes.ids())
                    return None, (
                        f"'{rid}' no es una red válida; usa ids separados por comas "
                        f"({permitidas})."
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
