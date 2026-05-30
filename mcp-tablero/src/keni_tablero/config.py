"""Configuracion local por persona del MCP de tablero.

A diferencia de `keni-metricas` (que lleva su propio config.toml de credenciales de
Metricool), este MCP solo necesita saber DONDE esta la Consola y CON QUE token hablarle:

  - `KENI_CONSOLA_URL`   base de la Consola (def `http://127.0.0.1:8765`). En hosted,
                          `https://social.kenitech.io`.
  - `KENI_CONSOLA_TOKEN` token interino de la Consola (mismo que usa el back/SPA). Es la
                          credencial de la API; sin el, la Consola responde 401 (salvo que
                          corra SIN token, modo solo-sesion, en cuyo caso no aplica a un MCP).

Las credenciales NUNCA se hardcodean: salen del entorno (la maquina de cada persona / el
servicio). Sin URL configurada se asume el local por defecto, util para desarrollo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_URL = "KENI_CONSOLA_URL"
ENV_TOKEN = "KENI_CONSOLA_TOKEN"

URL_DEFECTO = "http://127.0.0.1:8765"


@dataclass(frozen=True)
class Config:
    url: str = URL_DEFECTO
    token: str = ""

    @property
    def url_base(self) -> str:
        """URL base sin barra final (para componer `/api/...`)."""
        return self.url.rstrip("/")


def cargar_config() -> Config:
    """Lee la configuracion del entorno (URL + token de la Consola)."""
    url = (os.environ.get(ENV_URL) or URL_DEFECTO).strip() or URL_DEFECTO
    token = (os.environ.get(ENV_TOKEN) or "").strip()
    return Config(url=url, token=token)
