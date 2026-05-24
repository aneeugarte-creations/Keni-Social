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

from .fuentes.base import FuenteMetricas
from .schema import Plataforma


def ruta_config() -> Path:
    if (p := os.environ.get("KENI_METRICAS_CONFIG")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-metricas" / "config.toml"


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

    return Config(fuente=fuente, cuentas=cuentas, credenciales=datos.get("credenciales", {}))


def construir_fuente(cfg: Config | None = None) -> FuenteMetricas:
    """Crea la fuente activa segun la configuracion."""
    cfg = cfg or cargar_config()
    if cfg.fuente == "muestra":
        from .fuentes.muestra import FuenteMuestra

        return FuenteMuestra()

    from .agregador import FuenteCompuesta

    return FuenteCompuesta.desde_config(cfg)
