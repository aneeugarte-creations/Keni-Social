"""Cliente HTTP fino contra la API de la Consola (`/api/publicaciones`, `/api/webhooks`).

Encapsula la autenticacion (token por `Authorization: Bearer` y `X-Keni-Token`, ambas
admitidas por `seguridad.py` de la Consola) y la traduccion de errores HTTP a un dict
`{"error": "..."}` en espanol, de modo que las tools del MCP nunca propaguen tracebacks ni
status crudos al modelo. NO manda cabecera `Origin`: la Consola deja pasar las mutaciones
sin Origin (clientes no-navegador) apoyandose en el token (ver `seguridad._origen_mismo_host`).

Es la unica capa que toca la red; las tools (`tools.py`) la consumen. Usa UN
`httpx.Client` persistente por instancia (keep-alive: una conexion reusada por sesion
MCP, no una por peticion) y reintenta SOLO los GET ante fallos de transporte (los GET
son idempotentes; un POST/PATCH reintentado a ciegas podria duplicar la mutacion).
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .config import Config

_TIMEOUT = 20.0

# Reintentos de TRANSPORTE solo para GET (idempotente): n intentos con backoff lineal
# corto. Mismo espiritu que los reintentos de keni-metricas, en bucle simple.
_INTENTOS_GET = 3
_ESPERA_BASE = 0.2  # segundos; crece linealmente (0.2, 0.4)


class ErrorConsola(RuntimeError):
    """Error ya en espanol, apto para devolver al modelo como `{"error": ...}`."""


class ClienteConsola:
    """Cliente de la API de la Consola. Una instancia por servidor MCP (reusa conexion)."""

    def __init__(self, cfg: Config, cliente: httpx.Client | None = None):
        self._cfg = cfg
        # Cliente PERSISTENTE (keep-alive). Inyectable en tests (respx/MockTransport).
        self._cli = cliente or httpx.Client(timeout=_TIMEOUT)

    def _cabeceras(self) -> dict[str, str]:
        cab = {"Content-Type": "application/json"}
        if self._cfg.token:
            cab["Authorization"] = f"Bearer {self._cfg.token}"
            cab["X-Keni-Token"] = self._cfg.token
        return cab

    def _enviar(
        self, metodo: str, url: str, *, json: Any, params: dict[str, str] | None
    ) -> httpx.Response:
        """Una peticion con reintentos de transporte SOLO si es GET (idempotente)."""
        intentos = _INTENTOS_GET if metodo == "GET" else 1
        for intento in range(1, intentos + 1):
            try:
                return self._cli.request(
                    metodo, url, json=json, params=params, headers=self._cabeceras()
                )
            except httpx.TimeoutException as e:
                if intento < intentos:
                    time.sleep(_ESPERA_BASE * intento)
                    continue
                raise ErrorConsola(
                    f"La Consola no respondio a tiempo ({self._cfg.url_base})."
                ) from e
            except httpx.HTTPError as e:
                if intento < intentos:
                    time.sleep(_ESPERA_BASE * intento)
                    continue
                raise ErrorConsola(
                    f"No se pudo conectar con la Consola en {self._cfg.url_base}: {type(e).__name__}."
                ) from e
        raise AssertionError("inalcanzable")  # pragma: no cover

    def _peticion(
        self,
        metodo: str,
        ruta: str,
        *,
        json: Any = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        resp = self._enviar(metodo, f"{self._cfg.url_base}{ruta}", json=json, params=params)

        if resp.status_code == 401:
            raise ErrorConsola(
                "La Consola rechazo la credencial (401). Revisa KENI_CONSOLA_TOKEN."
            )
        if resp.status_code == 403:
            raise ErrorConsola("La Consola denego la operacion (403): permisos insuficientes.")
        if resp.status_code >= 400:
            # Mensaje en espanol que da la propia API, si lo trae: las respuestas de error
            # usan `error`, pero algunos endpoints responden con `mensaje`.
            try:
                cuerpo = resp.json()
            except ValueError:
                cuerpo = {}
            mensaje = None
            if isinstance(cuerpo, dict):
                mensaje = cuerpo.get("error") or cuerpo.get("mensaje")
            raise ErrorConsola(mensaje or f"La Consola devolvio un error (HTTP {resp.status_code}).")
        try:
            return resp.json()
        except ValueError as e:
            raise ErrorConsola("La Consola devolvio una respuesta no-JSON.") from e

    # --- Contenido (tablero) -------------------------------------------------- #

    def listar_publicacion(self, params: dict[str, str] | None = None) -> dict[str, Any]:
        # `params=` de httpx url-encodea los valores.
        filtrados = {k: v for k, v in (params or {}).items() if v}
        return self._peticion("GET", "/api/publicaciones", params=filtrados or None)

    def crear_publicacion(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        return self._peticion("POST", "/api/publicaciones", json=cuerpo)

    def actualizar_publicacion(self, publicacion_id: str, cuerpo: dict[str, Any]) -> dict[str, Any]:
        return self._peticion("PATCH", f"/api/publicaciones/{publicacion_id}", json=cuerpo)

    def actualizar_plataforma(
        self, publicacion_id: str, pieza_id: str, cuerpo: dict[str, Any]
    ) -> dict[str, Any]:
        return self._peticion(
            "PATCH",
            f"/api/publicaciones/{publicacion_id}/plataformas/{pieza_id}",
            json=cuerpo,
        )

    def agregar_plataforma(self, publicacion_id: str, red: str) -> dict[str, Any]:
        return self._peticion(
            "POST", f"/api/publicaciones/{publicacion_id}/plataformas", json={"red": red}
        )
