"""Config — accesores del dominio produccion. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _VERDADEROS,
    AUTOGEN_ARTE_MAX_DEF,
    AUTOGEN_COPY_MAX_DEF,
    RITMO_DEF,
    CARRUSEL_MAX_SLIDES_DEF,
    ENV_AUTOGEN_ARTE_MAX,
    ENV_AUTOGEN_COPY_MAX,
    ENV_RITMO,
    ENV_CARRUSEL_MAX_SLIDES,
    ENV_CONSOLA_URL_PUBLICA,
    ENV_GENERACIONES_TTL_HORAS,
    ENV_MEDIA_GC,
    ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
    ENV_MEDIA_GC_INTERVALO_HORAS,
    ENV_LIMPIADOR_INTERVALO_MIN,
    ENV_PIEZAS_PURGA_DIAS,
    ENV_USO_MUESTREO_MIN,
    GENERACIONES_TTL_HORAS_DEF,
    MEDIA_GC_ANTIGUEDAD_HORAS_DEF,
    MEDIA_GC_INTERVALO_HORAS_DEF,
    LIMPIADOR_INTERVALO_MIN_DEF,
    PIEZAS_PURGA_DIAS_DEF,
    USO_MUESTREO_MIN_DEF,
    _crudo,
    _entero,
)

# --------------------------------------------------------------------------- #
# Exclusiones POR MARCA de las etapas de auto-producción                       #
# --------------------------------------------------------------------------- #
#
# Cada etapa (pipeline/ingesta, auto-copy, auto-arte, auto-avance) sigue gateada GLOBALMENTE por
# su flag (el daemon solo barre con el global ON). Encima de eso, una marca se puede APAGAR de
# forma explícita: un override en el store con clave `f"{ENV}::{marca}"` y valor falsy ("0"/"no")
# EXCLUYE esa marca de esa etapa. Caso de uso: el global ON produce todas las marcas; apagas
# nacion-gamer y deja de producirse, claro-sports sigue. El override SOLO excluye: no consulta el
# global (por eso las funciones de selección/barrido siguen siendo testeables con el global OFF),
# y solo tiene efecto cuando la etapa global está encendida (sin global, el daemon ni barre).

# Separador de la clave por-marca. No aparece en los ids de marca (`claro-sports`, etc.).
SEP_MARCA = "::"


def clave_por_marca(env_flag: str, marca: str) -> str:
    """Clave de store del override por-marca de una etapa: `KENI_AUTOGEN::claro-sports`."""
    return f"{env_flag}{SEP_MARCA}{marca}"


def marca_apagada(env_flag: str, marca: str) -> bool:
    """True si `marca` está EXPLÍCITAMENTE apagada para la etapa `env_flag` (override falsy).

    Solo mira el override por-marca del store; NO consulta el flag global (eso lo hace el daemon
    al decidir si barre). Sin override -> False (no excluida): la etapa corre para esa marca como
    siempre. Es la guarda que los barridos consultan para SALTAR las marcas apagadas a mano.
    """
    from . import ajustes  # perezoso: evita el ciclo config <- ajustes

    crudo = ajustes.obtener(clave_por_marca(env_flag, marca))
    if crudo is None or not crudo.strip():
        return False  # sin override explícito: la marca NO está apagada
    return crudo.strip().lower() not in _VERDADEROS


def media_gc_activo() -> bool:
    """True si el daemon de GC de media sin referencia debe BARRER (`KENI_MEDIA_GC`).

    Def OFF (conservador): sin el flag NO se borra ningun objeto del almacen. Con el flag,
    un hilo demonio barre cada N horas y borra los objetos SIN REFERENCIA (no referenciados por
    ninguna pieza ni catalogados en catalogo-media) y mas viejos que el umbral. El
    hilo arranca SIEMPRE pero, gateado, solo actua cuando el flag esta activo.
    """
    return _crudo(ENV_MEDIA_GC).lower() in _VERDADEROS


def piezas_purga_dias() -> int:
    """Retencion (dias) de un borrador MUERTO del tablero antes de purgarlo (`KENI_PIEZAS_PURGA_DIAS`).

    Politica de retencion DELIBERADA (aprobada por el dueño), no un GC tecnico: un tema
    auto-generado (pipeline/portal/historia) sin NINGUNA huella humana se borra pasados N dias;
    lo publicado o tocado por una persona se conserva PARA SIEMPRE (las señales de "tocado"
    viven en `db_purga_piezas`). Def 90; 0 (o negativo -> clamp a 0) APAGA la purga.
    """
    return _entero(ENV_PIEZAS_PURGA_DIAS, PIEZAS_PURGA_DIAS_DEF, minimo=0)


def media_gc_intervalo_horas() -> int:
    """Cada cuantas horas barre el daemon de GC de media (`KENI_MEDIA_GC_INTERVALO_HORAS`, def 24, min 1)."""
    return _entero(
        ENV_MEDIA_GC_INTERVALO_HORAS, MEDIA_GC_INTERVALO_HORAS_DEF, minimo=1
    )


def media_gc_antiguedad_horas() -> int:
    """Antiguedad MINIMA (horas) de un objeto para considerarlo borrable (`KENI_MEDIA_GC_ANTIGUEDAD_HORAS`).

    Def 24h, min 1: un objeto mas NUEVO que esto NUNCA se borra, aunque parezca sin referencia,
    para no eliminar las variantes recien generadas por el Estudio que el usuario aun revisa.
    """
    return _entero(
        ENV_MEDIA_GC_ANTIGUEDAD_HORAS, MEDIA_GC_ANTIGUEDAD_HORAS_DEF, minimo=1
    )


def ritmo(marca: str) -> int:
    """Ritmo de producción VIGENTE (porcentaje) que escala los caps por barrido (`KENI_RITMO`).

    Control de gradación del gasto SIN apagar etapas: 100 = sin freno; bajarlo recorta
    proporcionalmente cuánto trabajo nuevo entra por barrido. El override por marca del store
    (`KENI_RITMO::marca`) MANDA sobre el env/default global (`KENI_RITMO`); `marca=""` lee el
    global. CLAMP a [10, 100]: el ritmo nunca congela del todo (mínimo 10); el apagado es otra
    palanca (toggles de etapa, parada de emergencia).
    """
    from . import ajustes  # perezoso: evita el ciclo config <- ajustes

    valor = _entero(ENV_RITMO, RITMO_DEF)  # env/default global
    if marca:
        crudo = ajustes.obtener(clave_por_marca(ENV_RITMO, marca))
        if crudo is not None and crudo.strip():
            try:
                valor = int(crudo.strip())  # override por marca MANDA
            except ValueError:
                pass
    return max(10, min(100, valor))


def autogen_arte_max() -> int:
    """Maximo de temas a auto-ilustrar por barrido (`KENI_AUTOGEN_ARTE_MAX`, def 3, min 1).

    Cada item llama al proveedor de imagen (coste): el cap evita rafagas por barrido. El RITMO
    GLOBAL (`ritmo("")`) lo escala hacia abajo para frenar el gasto sin apagar la etapa (ritmo
    100 = cap de fábrica).
    """
    base = _entero(ENV_AUTOGEN_ARTE_MAX, AUTOGEN_ARTE_MAX_DEF, minimo=1)
    return max(1, round(base * ritmo("") / 100))


def autogen_copy_max(marca: str) -> int:
    """Maximo de temas autogen a redactar por marca y barrido (`KENI_AUTOGEN_COPY_MAX`, def 12, min 1).

    Tope del carril 2 de Redactar (news-pool): acota cuantos temas sin copy de UNA marca se
    encolan en cada barrido, para que activar el toggle de una marca con backlog no dispare una
    rafaga de `claude -p`. El override por marca del store (`KENI_AUTOGEN_COPY_MAX::marca`) MANDA
    sobre el default; sin override, cae al env/default global. Min 1. El RITMO de la marca
    (`ritmo(marca)`) escala el cap hacia abajo para frenar el gasto sin apagar la etapa (ritmo
    100 = cap de fábrica).
    """
    from . import ajustes  # perezoso: evita el ciclo config <- ajustes

    base = _entero(ENV_AUTOGEN_COPY_MAX, AUTOGEN_COPY_MAX_DEF, minimo=1)
    if marca:
        crudo = ajustes.obtener(clave_por_marca(ENV_AUTOGEN_COPY_MAX, marca))
        if crudo is not None and crudo.strip():
            try:
                base = max(1, int(crudo.strip()))
            except ValueError:
                pass
    return max(1, round(base * ritmo(marca) / 100))


def carrusel_max_slides() -> int:
    """Tope EDITORIAL de slides extra del panel automático de carrusel (`KENI_CARRUSEL_MAX_SLIDES`,
    def 9, min 2: un carrusel de 1 slide no es panel).

    No conoce el tope TÉCNICO de `dominio.generar.MAX_SLIDES_CARRUSEL` (evita el acoplo
    config -> dominio); quien llama este accesor aplica el min() final con ese tope.
    """
    return _entero(ENV_CARRUSEL_MAX_SLIDES, CARRUSEL_MAX_SLIDES_DEF, minimo=2)


def generaciones_ttl_seg() -> int:
    """Antigüedad (s) tras la cual una generacion `ejecutando` se considera colgada.

    `KENI_GENERACIONES_TTL_HORAS` (def 1 h, min 1). MUY por encima del wall-timeout (~10 min):
    asi el recolector nunca cierra una generacion que de verdad sigue viva.
    """
    return _entero(ENV_GENERACIONES_TTL_HORAS, GENERACIONES_TTL_HORAS_DEF, minimo=1) * 3600


def limpiador_intervalo_seg() -> int:
    """Cada cuanto barre el recolector de generaciones (`KENI_LIMPIADOR_INTERVALO_MIN`, def 10, min 1)."""
    return _entero(ENV_LIMPIADOR_INTERVALO_MIN, LIMPIADOR_INTERVALO_MIN_DEF, minimo=1) * 60


def uso_muestreo_intervalo_seg() -> int:
    """Cada cuanto muestrea el daemon el uso de la cuenta (`KENI_USO_MUESTREO_MIN`, def 20, min 1)."""
    return _entero(ENV_USO_MUESTREO_MIN, USO_MUESTREO_MIN_DEF, minimo=1) * 60


def consola_url_publica() -> str | None:
    """URL base publica de la consola (`KENI_CONSOLA_URL_PUBLICA`), sin barra final.

    Necesaria para construir URLs absolutas de media que Metricool pueda ingerir.
    Ejemplo: `https://social.kenitech.io`. None si no esta configurada (en ese caso
    el programador omite las URLs de media en el borrador enviado a Metricool y lo
    registra en el log).
    """
    crudo = _crudo(ENV_CONSOLA_URL_PUBLICA)
    return crudo.rstrip("/") if crudo else None
