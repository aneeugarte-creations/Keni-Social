"""Contador de intentos por ETAPA del pipeline, keyed por `(sujeto, etapa)` y PERSISTENTE.

Espejo semantico de los helpers `intentos_de`/`anotar_intento`/`en_backoff` de `_comun.py`, pero
el contador vive en su PROPIA tabla (`intentos_etapa`, via `repos`) en vez de en el JSON
`copy_pendiente` del tema. Asi SOBREVIVE a la purga de la cola y a un "exito vacio" que limpiaria
el pendiente, y EXISTE tambien para etapas pre-tablero (el Verificador corre sobre el CLUSTER,
antes de que haya tema).

`sujeto` es la clave del trabajo: el `publicacion_id` (tema) o el `cluster_id` (verificacion
pre-tablero). `etapa` es uno de los nombres ESTABLES definidos aqui. El tope y el backoff REUSAN
`_MAX_INTENTOS_ETAPA`/`_BACKOFF_ETAPA_SEG` de `_comun.py` (UNA fuente para ambos contadores).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .. import repos
from ..tiempo import iso_utc
from ._comun import _BACKOFF_ETAPA_SEG, _MAX_INTENTOS_ETAPA

# Nombres ESTABLES de etapa (la clave `etapa` de la tabla). El Verificador corre pre-tablero
# (sobre el CLUSTER); el resto corre sobre el tema (publicacion). Son los identificadores que
# usan los llamantes del pipeline al contar/topar/resetear sus reintentos.
ETAPA_VERIFICAR = "verificar"
ETAPA_REDACTAR = "redactar"
ETAPA_ILUSTRAR = "ilustrar"
ETAPA_STOCK = "stock"
ETAPA_DECISOR = "decisor"
ETAPA_FUSIONAR = "fusionar"
ETAPA_TRADUCIR = "traducir"
ETAPA_PERFIL = "perfil"


def intentos(sujeto: str, etapa: str) -> int:
    """Intentos ya consumidos de la `etapa` para el `sujeto`. 0 si no hay registro."""
    return repos.intentos_etapa(sujeto, etapa)


def anotar(sujeto: str, etapa: str) -> int:
    """Suma 1 al contador de la `etapa` del `sujeto` (UPSERT atomico) y devuelve el nuevo valor."""
    return repos.anotar_intento_etapa(sujeto, etapa)


def tope_alcanzado(sujeto: str, etapa: str) -> bool:
    """True si la `etapa` del `sujeto` ya agoto `_MAX_INTENTOS_ETAPA` intentos (salida terminal)."""
    return intentos(sujeto, etapa) >= _MAX_INTENTOS_ETAPA


def en_backoff(sujeto: str, etapa: str) -> bool:
    """True si la etapa debe ESPERAR antes de reintentar (backoff creciente entre reintentos).

    Lee el nº de intentos + el instante del ultimo (`intento_ts`) y aplica `_BACKOFF_ETAPA_SEG`.
    Sin intentos o sin timestamp no hay espera. Mismo calculo que el `en_backoff` de `_comun.py`:
    comparacion lexicografica de ISO UTC canonicos. El barrido SALTA el sujeto (no duerme); un
    tick posterior lo reevalua.
    """
    n = intentos(sujeto, etapa)
    if n <= 0:
        return False
    ts = repos.intento_ts(sujeto, etapa)
    if not ts:
        return False
    espera = _BACKOFF_ETAPA_SEG[min(n, len(_BACKOFF_ETAPA_SEG)) - 1]
    umbral = iso_utc(datetime.now(UTC) - timedelta(seconds=espera))
    return ts > umbral  # ultimo intento mas reciente que el umbral: aun en espera


def reset(sujeto: str, etapa: str) -> None:
    """Borra el contador de la `etapa` del `sujeto`. Se llama al ÉXITO de la etapa. Idempotente."""
    repos.reset_intentos_etapa(sujeto, etapa)
