"""Config — accesores del dominio produccion. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _VERDADEROS,
    AUTOGEN_ARTE_MAX_DEF,
    ENV_AUTOGEN_ARTE_MAX,
    ENV_CONSOLA_URL_PUBLICA,
    ENV_GENERACIONES_TTL_HORAS,
    ENV_MEDIA_GC,
    ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
    ENV_MEDIA_GC_INTERVALO_HORAS,
    ENV_LIMPIADOR_INTERVALO_MIN,
    GENERACIONES_TTL_HORAS_DEF,
    MEDIA_GC_ANTIGUEDAD_HORAS_DEF,
    MEDIA_GC_INTERVALO_HORAS_DEF,
    LIMPIADOR_INTERVALO_MIN_DEF,
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


def autogen_arte_max() -> int:
    """Maximo de temas a auto-ilustrar por barrido (`KENI_AUTOGEN_ARTE_MAX`, def 3, min 1).

    Cada item llama al proveedor de imagen (coste): el cap evita rafagas por barrido.
    """
    return _entero(ENV_AUTOGEN_ARTE_MAX, AUTOGEN_ARTE_MAX_DEF, minimo=1)


def generaciones_ttl_seg() -> int:
    """Antigüedad (s) tras la cual una generacion `ejecutando` se considera colgada.

    `KENI_GENERACIONES_TTL_HORAS` (def 1 h, min 1). MUY por encima del wall-timeout (~10 min):
    asi el recolector nunca cierra una generacion que de verdad sigue viva.
    """
    return _entero(ENV_GENERACIONES_TTL_HORAS, GENERACIONES_TTL_HORAS_DEF, minimo=1) * 3600


def limpiador_intervalo_seg() -> int:
    """Cada cuanto barre el recolector de generaciones (`KENI_LIMPIADOR_INTERVALO_MIN`, def 10, min 1)."""
    return _entero(ENV_LIMPIADOR_INTERVALO_MIN, LIMPIADOR_INTERVALO_MIN_DEF, minimo=1) * 60


def consola_url_publica() -> str | None:
    """URL base publica de la consola (`KENI_CONSOLA_URL_PUBLICA`), sin barra final.

    Necesaria para construir URLs absolutas de media que Metricool pueda ingerir.
    Ejemplo: `https://social.kenitech.io`. None si no esta configurada (en ese caso
    el programador omite las URLs de media en el borrador enviado a Metricool y lo
    registra en el log).
    """
    crudo = _crudo(ENV_CONSOLA_URL_PUBLICA)
    return crudo.rstrip("/") if crudo else None
