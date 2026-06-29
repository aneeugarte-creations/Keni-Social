"""Reparto de marcas en DOS cuentas de Claude (A/B) y derivacion del carril de cola por cuenta.

El aislamiento REAL de cada cuenta es su `CLAUDE_CONFIG_DIR` (un subdir por cuenta bajo /data, con
sus propias credenciales): lo monta el contenedor del worker que sirve esa cuenta. Aqui solo vive
la POLITICA (que marca va a que cuenta) y la derivacion del CARRIL de cola por cuenta, para que el
encolado de un job de INVESTIGACION lo rute al worker de la cuenta de su marca.

Reparto por DEFECTO (piloto AMX):
  - Cuenta A: claro-sports
  - Cuenta B: unotv, nacion-gamer, unotv-us, fundacion
  - Marcas sin reparto (p.ej. piso-15) y los jobs SIN marca / cross-marca -> cuenta POR DEFECTO.

Configurable como el resto de overrides por-marca (STORE > ENV):
  - `KENI_CUENTA_CLAUDE::<marca>` = "a"|"b" reasigna esa marca.
  - `KENI_CUENTA_CLAUDE_DEFECTO` = "a"|"b" fija la cuenta por defecto (def "a").
"""
from __future__ import annotations

import os
from collections.abc import Iterable

from .config import clave_por_marca
from .dominio import jobspec

# Prefijo del override por-marca y nombre de la cuenta por defecto (mismo idiom `ENV_*` que el
# resto de la config; el override por-marca usa `clave_por_marca` -> `KENI_CUENTA_CLAUDE::<marca>`).
ENV_CUENTA_CLAUDE = "KENI_CUENTA_CLAUDE"
ENV_CUENTA_CLAUDE_DEFECTO = "KENI_CUENTA_CLAUDE_DEFECTO"

# Reparto por defecto del piloto. Las marcas ausentes caen a la cuenta por defecto.
_REPARTO_DEFECTO: dict[str, str] = {
    "claro-sports": jobspec.CUENTA_A,
    "unotv": jobspec.CUENTA_B,
    "nacion-gamer": jobspec.CUENTA_B,
    "unotv-us": jobspec.CUENTA_B,
    "fundacion": jobspec.CUENTA_B,
}


def _valor(clave: str) -> str:
    """Valor crudo store-aware (STORE > ENV) de una clave; "" si no esta.

    Misma precedencia que `config._crudo` (el store editable gana al entorno), con import
    PEREZOSO de `ajustes` para no acoplar este modulo al ciclo config<-ajustes a nivel de import.
    """
    from . import ajustes

    desde_store = ajustes.obtener(clave)
    if desde_store is not None and desde_store.strip():
        return desde_store.strip()
    return (os.environ.get(clave) or "").strip()


def cuenta_por_defecto() -> str:
    """Cuenta de Claude por defecto (`KENI_CUENTA_CLAUDE_DEFECTO`, def 'a'). Validada a A|B."""
    valor = _valor(ENV_CUENTA_CLAUDE_DEFECTO).lower()
    return valor if valor in jobspec.CUENTAS else jobspec.CUENTA_A


def cuenta_de_marca(marca: str) -> str:
    """Cuenta de Claude (A|B) que sirve a `marca`.

    Precedencia: override por-marca del store/env (`KENI_CUENTA_CLAUDE::<marca>`) > reparto por
    defecto del piloto > cuenta por defecto (marcas sin reparto y jobs SIN marca / cross-marca).
    """
    if marca:
        override = _valor(clave_por_marca(ENV_CUENTA_CLAUDE, marca)).lower()
        if override in jobspec.CUENTAS:
            return override
        if marca in _REPARTO_DEFECTO:
            return _REPARTO_DEFECTO[marca]
    return cuenta_por_defecto()


def clave_cuenta_marca(marca: str) -> str:
    """Clave de store del override de cuenta de `marca` (`KENI_CUENTA_CLAUDE::<marca>`)."""
    return clave_por_marca(ENV_CUENTA_CLAUDE, marca)


def override_de_marca(marca: str) -> str | None:
    """Override EXPLÍCITO de cuenta de `marca` ("a"|"b"), o None si usa el reparto por defecto.

    Lee store>env como `cuenta_de_marca`, pero NO cae al reparto/defecto: distingue "asignada a
    mano" de "heredada". Base del flag `por_defecto` que muestra el panel de cuentas.
    """
    valor = _valor(clave_cuenta_marca(marca)).lower()
    return valor if valor in jobspec.CUENTAS else None


def asignar_marca(marca: str, cuenta: str | None) -> None:
    """Fija (o limpia) la cuenta de `marca` en el store.

    `cuenta` "a"|"b" escribe el override; None/"" lo BORRA (la marca vuelve a su reparto por
    defecto). Lanza `ValueError` si la cuenta no es válida. Centralizar aquí el formato de la clave
    y su lectura (`override_de_marca`/`cuenta_de_marca`) deja un único sitio que la conoce.
    """
    from . import ajustes

    clave = clave_cuenta_marca(marca)
    if not cuenta:
        ajustes.borrar(clave)
        return
    cuenta = cuenta.lower()
    if cuenta not in jobspec.CUENTAS:
        raise ValueError(f"cuenta inválida: {cuenta!r} (esperado 'a' o 'b')")
    ajustes.guardar(clave, cuenta)


def marcas_de_cuenta(cuenta: str) -> list[str]:
    """Ids canónicos de las marcas que sirve la cuenta de Claude (A|B), en orden de catálogo.

    Recorre el catálogo vivo de marcas y se queda con las que `cuenta_de_marca` rutea a `cuenta`
    (incluye las que caen ahí por la cuenta por defecto). Base de la etiqueta legible del indicador.
    """
    from . import marcas

    return [m for m in marcas.ids() if cuenta_de_marca(m) == cuenta]


def etiqueta_de_cuenta(cuenta: str) -> str:
    """Etiqueta legible de una cuenta = nombres humanos de SUS marcas unidos por ` · `.

    P. ej. la cuenta B -> "UnoTV · Nación Gamer". Cadena vacía si la cuenta no sirve ninguna marca.
    """
    from . import marcas

    return " · ".join(marcas.etiqueta_de(m) for m in marcas_de_cuenta(cuenta))


def cuentas_visibles(*, es_admin: bool, marcas: Iterable[str]) -> list[str]:
    """Cuentas de Claude (A|B) que un usuario puede VER en el indicador, en orden A→B.

    - admin / superadmin (`es_admin=True`) -> AMBAS cuentas (gobiernan toda la operación).
    - editor -> la(s) cuenta(s) de sus `marcas` (`cuenta_de_marca` por marca); puede dar una o
      ambas. Editor SIN marcas -> lista vacía (no ve el indicador).
    PURA: no toca request ni BD; el call-site le pasa el rol y las marcas ya resueltas.
    """
    if es_admin:
        return list(jobspec.CUENTAS)
    vistas = {cuenta_de_marca(m) for m in marcas if m}
    return [c for c in jobspec.CUENTAS if c in vistas]


def carril_de_marca(marca: str) -> str:
    """Carril de cola de la cuenta de `marca`: rutar un job de INVESTIGACION al worker de su cuenta.

    Lo usa el encolado de los pasos de investigacion (traducir/perfil/fusionar/clasificar) para
    estampar `spec["carril"]` segun la marca, de modo que el worker de esa cuenta lo reclame.
    """
    return jobspec.carril_de_cuenta(cuenta_de_marca(marca))
