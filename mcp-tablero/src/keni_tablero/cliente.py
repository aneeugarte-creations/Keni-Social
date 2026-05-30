"""Cliente HTTP fino contra la API de la Consola (`/api/contenido`, `/api/webhooks`).

Encapsula la autenticacion (token por `Authorization: Bearer` y `X-Keni-Token`, ambas
admitidas por `seguridad.py` de la Consola) y la traduccion de errores HTTP a un dict
`{"error": "..."}` en espanol, de modo que las tools del MCP nunca propaguen tracebacks ni
status crudos al modelo. NO manda cabecera `Origin`: la Consola deja pasar las mutaciones
sin Origin (clientes no-navegador) apoyandose en el token (ver `seguridad._origen_mismo_host`).

Es la unica capa que toca la red; las tools (`tools.py`) la consumen.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Config

_TIMEOUT = 20.0


class ErrorConsola(RuntimeError):
    """Error ya en espanol, apto para devolver al modelo como `{"error": ...}`."""


class ClienteConsola:
    """Cliente de la API de la Consola. Una instancia por servidor MCP (reusa cabeceras)."""

    def __init__(self, cfg: Config):
        self._cfg = cfg

    def _cabeceras(self) -> dict[str, str]:
        cab = {"Content-Type": "application/json"}
        if self._cfg.token:
            cab["Authorization"] = f"Bearer {self._cfg.token}"
            cab["X-Keni-Token"] = self._cfg.token
        return cab

    def _peticion(self, metodo: str, ruta: str, *, json: Any = None) -> dict[str, Any]:
        url = f"{self._cfg.url_base}{ruta}"
        try:
            resp = httpx.request(
                metodo, url, json=json, headers=self._cabeceras(), timeout=_TIMEOUT
            )
        except httpx.TimeoutException as e:
            raise ErrorConsola(
                f"La Consola no respondio a tiempo ({self._cfg.url_base})."
            ) from e
        except httpx.HTTPError as e:
            raise ErrorConsola(
                f"No se pudo conectar con la Consola en {self._cfg.url_base}: {type(e).__name__}."
            ) from e

        if resp.status_code == 401:
            raise ErrorConsola(
                "La Consola rechazo la credencial (401). Revisa KENI_CONSOLA_TOKEN."
            )
        if resp.status_code == 403:
            raise ErrorConsola("La Consola denego la operacion (403): permisos insuficientes.")
        if resp.status_code >= 400:
            # Mensaje en espanol que da la propia API, si lo trae.
            try:
                cuerpo = resp.json()
            except ValueError:
                cuerpo = {}
            mensaje = cuerpo.get("error") if isinstance(cuerpo, dict) else None
            raise ErrorConsola(mensaje or f"La Consola devolvio un error (HTTP {resp.status_code}).")
        try:
            return resp.json()
        except ValueError as e:
            raise ErrorConsola("La Consola devolvio una respuesta no-JSON.") from e

    # --- Contenido (tablero) -------------------------------------------------- #

    def listar_contenido(self, params: dict[str, str] | None = None) -> dict[str, Any]:
        sufijo = ""
        if params:
            pares = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items() if v)
            sufijo = f"?{pares}" if pares else ""
        return self._peticion("GET", f"/api/contenido{sufijo}")

    def crear_contenido(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        return self._peticion("POST", "/api/contenido", json=cuerpo)

    def actualizar_contenido(self, contenido_id: str, cuerpo: dict[str, Any]) -> dict[str, Any]:
        return self._peticion("PATCH", f"/api/contenido/{contenido_id}", json=cuerpo)

    def actualizar_plataforma(
        self, contenido_id: str, plataforma_id: str, cuerpo: dict[str, Any]
    ) -> dict[str, Any]:
        return self._peticion(
            "PATCH",
            f"/api/contenido/{contenido_id}/plataformas/{plataforma_id}",
            json=cuerpo,
        )

    def agregar_plataforma(self, contenido_id: str, red: str) -> dict[str, Any]:
        return self._peticion(
            "POST", f"/api/contenido/{contenido_id}/plataformas", json={"red": red}
        )
