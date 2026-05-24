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


def cargar_config() -> Config:
    datos: dict = {}
    ruta = ruta_config()
    if ruta.exists():
        datos = tomllib.loads(ruta.read_text(encoding="utf-8"))

    fuente = os.environ.get("KENI_METRICAS_FUENTE") or datos.get("fuente", "muestra")

    cuentas: list[CuentaConfig] = []
    for c in datos.get("cuenta", []):
        plataformas = {
            Plataforma(k): str(v) for k, v in (c.get("plataformas") or {}).items()
        }
        cuentas.append(CuentaConfig(id=c["id"], nombre=c["nombre"], plataformas=plataformas))

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
