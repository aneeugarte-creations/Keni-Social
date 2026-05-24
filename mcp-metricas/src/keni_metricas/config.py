"""Configuracion local por persona: que cuentas gestiona y sus credenciales.

El archivo vive en `~/.config/keni-metricas/config.toml` (o la ruta de
`KENI_METRICAS_CONFIG`). Las credenciales NUNCA salen de la maquina.
Por defecto la fuente es `muestra` (datos offline), asi que el MCP funciona
sin configurar nada. Ver `credenciales.ejemplo.toml`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .fuentes.base import CuentaNoEncontrada, FuenteMetricas
from .schema import Cuenta, Pieza, Plataforma, ResumenMetricas

# Valores aceptados para `fuente`. `muestra` = datos offline (defecto); `real` =
# adaptadores que pegan a las APIs reales (requiere credenciales).
FUENTES_VALIDAS: frozenset[str] = frozenset({"muestra", "real"})


class ConfigInvalida(ValueError):
    """El config.toml existe pero no se puede usar (sintaxis o contenido invalido).

    Hereda de `ValueError` para que los CLIs que ya capturan `ValueError` la
    traten como un error de dominio (mensaje en espanol, sin traceback de
    `tomllib` ni KeyError crudos). El `doctor` la reporta como ❌.
    """


def ruta_config() -> Path:
    if (p := os.environ.get("KENI_METRICAS_CONFIG")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-metricas" / "config.toml"


def _parsear_marcas(valor: str | list | None) -> list[str]:
    """Normaliza la lista de marcas (de env var coma-separada o de la lista TOML)."""
    if not valor:
        return []
    crudas = valor.split(",") if isinstance(valor, str) else valor
    # preserva el orden declarado y descarta duplicados/vacios
    vistas: list[str] = []
    for m in crudas:
        m = str(m).strip()
        if m and m not in vistas:
            vistas.append(m)
    return vistas


@dataclass
class CuentaConfig:
    id: str
    nombre: str
    plataformas: dict[Plataforma, str]  # plataforma -> handle / id en esa plataforma


@dataclass
class Config:
    fuente: str = "muestra"  # "muestra" | "real"
    cuentas: list[CuentaConfig] = field(default_factory=list)
    credenciales: dict[str, dict] = field(default_factory=dict)  # plataforma -> {clave: valor}
    # marcas (ids) que gestiona esta persona. Vacio = todas (compatibilidad).
    marcas: list[str] = field(default_factory=list)


def _parsear_cuenta(idx: int, c: object) -> CuentaConfig:
    """Valida una entrada `[[cuenta]]` del TOML y la materializa (B4).

    Exige `id` y `nombre`, y que cada plataforma declarada sea valida; ante
    cualquier fallo lanza `ConfigInvalida` con un mensaje en espanol que indica
    QUE cuenta (por posicion e id si lo hay) y QUE campo esta mal.
    """
    # `n` identifica la cuenta para el humano: 1-based, mas el id si lo trae.
    n = f"#{idx + 1}"
    if not isinstance(c, dict):
        raise ConfigInvalida(
            f"La cuenta {n} del config no es una tabla [[cuenta]] valida."
        )
    etiqueta = f"{n} (id={c['id']!r})" if c.get("id") else n
    for campo in ("id", "nombre"):
        valor = c.get(campo)
        if not (isinstance(valor, str) and valor.strip()):
            raise ConfigInvalida(
                f"La cuenta {etiqueta} no tiene un campo {campo!r} valido "
                "(es obligatorio y no puede estar vacio)."
            )

    plataformas_crudas = c.get("plataformas") or {}
    if not isinstance(plataformas_crudas, dict):
        raise ConfigInvalida(
            f"El campo 'plataformas' de la cuenta {etiqueta} debe ser una tabla "
            "plataforma -> handle/id."
        )
    plataformas: dict[Plataforma, str] = {}
    validas = ", ".join(sorted(p.value for p in Plataforma))
    for k, v in plataformas_crudas.items():
        try:
            plataforma = Plataforma(k)
        except ValueError as e:
            raise ConfigInvalida(
                f"La cuenta {etiqueta} declara una plataforma invalida {k!r}. "
                f"Validas: {validas}."
            ) from e
        plataformas[plataforma] = str(v)

    return CuentaConfig(id=c["id"], nombre=c["nombre"], plataformas=plataformas)


def cargar_config() -> Config:
    datos: dict = {}
    ruta = ruta_config()
    if ruta.exists():
        try:
            datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            # B1: un TOML mal formado no debe tumbar los comandos con un
            # traceback de tomllib. Lo convertimos en un error de dominio en
            # espanol con la ruta y, si esta disponible, la linea del fallo.
            linea = getattr(e, "lineno", None)
            ubicacion = f" (linea {linea})" if linea else ""
            raise ConfigInvalida(
                f"El config en {ruta} tiene un error de sintaxis TOML{ubicacion}: {e}"
            ) from e
        except OSError as e:
            raise ConfigInvalida(
                f"No se pudo leer el config en {ruta}: {e}"
            ) from e

    fuente = os.environ.get("KENI_METRICAS_FUENTE") or datos.get("fuente", "muestra")
    # B5: una `fuente` desconocida hoy caia en silencio (ceros). La rechazamos.
    if fuente not in FUENTES_VALIDAS:
        validas = ", ".join(sorted(FUENTES_VALIDAS))
        raise ConfigInvalida(
            f"Fuente invalida {fuente!r}. Usa una de: {validas}."
        )

    cuentas = [_parsear_cuenta(i, c) for i, c in enumerate(datos.get("cuenta", []))]

    # La env var tiene prioridad sobre el campo `marcas` del config.toml.
    marcas = _parsear_marcas(os.environ.get("KENI_METRICAS_MARCAS") or datos.get("marcas"))

    return Config(
        fuente=fuente,
        cuentas=cuentas,
        credenciales=datos.get("credenciales", {}),
        marcas=marcas,
    )


class FuenteScoped:
    """Envoltorio que limita una FuenteMetricas a un subconjunto de marcas.

    `cuentas()` solo lista las marcas en alcance; `resumen`/`mejores_piezas`
    rechazan ids fuera de alcance con `CuentaNoEncontrada` (incluso si existen en
    la fuente subyacente). Aplica a CUALQUIER fuente (muestra o real), por lo que
    todo lo aguas abajo —reporte_consolidado, picos, etc.— queda acotado.
    """

    def __init__(self, fuente: FuenteMetricas, marcas: list[str]):
        self._fuente = fuente
        self._marcas = list(marcas)
        self._permitidas = set(marcas)

    @property
    def nombre(self) -> str:
        return self._fuente.nombre

    def _verificar(self, cuenta_id: str) -> None:
        if cuenta_id not in self._permitidas:
            disponibles = ", ".join(self._marcas) or "(ninguna en tu alcance)"
            raise CuentaNoEncontrada(
                f"Cuenta {cuenta_id!r} fuera de tu alcance. Disponibles: {disponibles}."
            )

    def cuentas(self) -> list[Cuenta]:
        return [c for c in self._fuente.cuentas() if c.id in self._permitidas]

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas:
        self._verificar(cuenta_id)
        return self._fuente.resumen(cuenta_id, rango)

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        self._verificar(cuenta_id)
        return self._fuente.mejores_piezas(cuenta_id, rango, n)


def construir_fuente(cfg: Config | None = None) -> FuenteMetricas:
    """Crea la fuente activa segun la configuracion.

    Si la persona declaro marcas (env `KENI_METRICAS_MARCAS` o campo `marcas` del
    config), envuelve la fuente para limitarla a esas marcas. Sin marcas, la
    fuente se devuelve tal cual (comportamiento historico: todas las marcas).
    """
    cfg = cfg or cargar_config()
    if cfg.fuente == "muestra":
        from .fuentes.muestra import FuenteMuestra

        fuente: FuenteMetricas = FuenteMuestra()
    else:
        from .agregador import FuenteCompuesta

        fuente = FuenteCompuesta.desde_config(cfg)

    if cfg.marcas:
        return FuenteScoped(fuente, cfg.marcas)
    return fuente
