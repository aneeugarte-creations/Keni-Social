"""Cliente de Google Analytics 4: OAuth de usuario + Data API + Admin API.

Modelo de auth: OAuth de usuario (la persona conecta SU cuenta Google con acceso a
las propiedades GA4). No requiere ser admin de la propiedad ni un service account:
basta con que la cuenta tenga lectura. Se usa el scope `analytics.readonly`, que
cubre tanto la Data API (runReport) como las lecturas de la Admin API
(accountSummaries).

Sin dependencias nuevas: el intercambio de código y el refresh son POST normales a
`oauth2.googleapis.com/token` (igual que `fuentes/youtube.py`); las llamadas a las
APIs van con `Authorization: Bearer <access_token>` sobre httpx. El access_token de
Google caduca en ~1h, así que se renueva con el refresh_token en cada operación.

Reparto de responsabilidades:
- Las funciones de OAuth (`url_autorizacion`, `intercambiar_codigo`) las usa la Consola
  durante el flujo de conexión (construir la URL y canjear el `code` del callback).
- `ClienteGA4` (refresh + Data/Admin API) lo usan tanto la Consola (probar conexión,
  listar propiedades) como, más adelante, el cruce de campañas con la web.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

import httpx

from .fuentes._http import cliente_http, get_json, log, post_json

# Endpoints de Google (OAuth + GA4 Data/Admin).
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DATA_API = "https://analyticsdata.googleapis.com/v1beta"
ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"

# Un único scope cubre la Data API (runReport) y las lecturas de la Admin API.
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


def url_autorizacion(client_id: str, redirect_uri: str, state: str) -> str:
    """URL de consentimiento de Google a la que mandar a la persona (popup).

    `access_type=offline` + `prompt=consent` fuerzan la entrega de un `refresh_token`
    (sin ellos, en una reautorización Google podría devolver solo un access_token). El
    `state` es el anti-CSRF que el callback verifica.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def intercambiar_codigo(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    cliente: httpx.Client | None = None,
) -> dict:
    """Canjea el `code` del callback por tokens. Devuelve el JSON de Google.

    El campo relevante es `refresh_token` (el que se persiste y permite leer GA4 sin
    que la persona vuelva a iniciar sesión). `redirect_uri` debe ser EXACTAMENTE el
    mismo registrado en el cliente OAuth y usado en `url_autorizacion`.
    """
    cli = cliente or cliente_http()
    return post_json(
        cli,
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )


def refrescar_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    cliente: httpx.Client | None = None,
) -> str:
    """Cambia el refresh_token por un access_token fresco (caduca en ~1h)."""
    cli = cliente or cliente_http()
    datos = post_json(
        cli,
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    token = datos.get("access_token")
    if not token:
        raise RuntimeError("Google no devolvió access_token al refrescar.")
    return str(token)


class ClienteGA4:
    """Lee GA4 con el refresh_token de una cuenta conectada.

    Mantiene client_id/client_secret/refresh_token y renueva el access_token bajo
    demanda. Las operaciones son de SOLO LECTURA (listar propiedades, runReport).
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        cliente: httpx.Client | None = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._cli = cliente or cliente_http()
        self._token: str | None = None

    def _headers(self, refrescar: bool = False) -> dict:
        if self._token is None or refrescar:
            self._token = refrescar_token(
                self._client_id, self._client_secret, self._refresh_token, self._cli
            )
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, url: str, params: dict | None = None) -> dict:
        """GET con un reintento tras 401 (token caducado) renovando el access_token."""
        try:
            return get_json(self._cli, url, params=params, headers=self._headers())
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 401:
                raise
            return get_json(self._cli, url, params=params, headers=self._headers(refrescar=True))

    def _post(self, url: str, cuerpo: dict) -> dict:
        try:
            return post_json(self._cli, url, json=cuerpo, headers=self._headers())
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 401:
                raise
            return post_json(self._cli, url, json=cuerpo, headers=self._headers(refrescar=True))

    def propiedades(self) -> list[dict]:
        """Propiedades GA4 que ve la cuenta conectada: `[{property_id, nombre, cuenta}]`.

        Vía Admin API `accountSummaries`. Devuelve el id NUMÉRICO (sin el prefijo
        `properties/`) para mapearlo a marcas. Pagina hasta agotar (`nextPageToken`).
        """
        salida: list[dict] = []
        page_token: str | None = None
        while True:
            params = {"pageSize": 200}
            if page_token:
                params["pageToken"] = page_token
            datos = self._get(f"{ADMIN_API}/accountSummaries", params=params)
            for cuenta in datos.get("accountSummaries", []):
                nombre_cuenta = cuenta.get("displayName", "")
                for p in cuenta.get("propertySummaries", []):
                    pid = str(p.get("property", "")).split("/")[-1]
                    if pid:
                        salida.append(
                            {
                                "property_id": pid,
                                "nombre": p.get("displayName", pid),
                                "cuenta": nombre_cuenta,
                            }
                        )
            page_token = datos.get("nextPageToken")
            if not page_token:
                return salida

    def reporte_paginas(
        self, property_id: str, desde: date, hasta: date, limite: int = 100
    ) -> list[dict]:
        """Tráfico por URL del periodo: `[{ruta, titulo, vistas, usuarios, visitas}]`.

        `vistas` = páginas vistas (screenPageViews), `usuarios` = navegadores únicos
        (totalUsers), `visitas` = sesiones (sessions). Es el dato base del cruce con
        campañas (notas web por etiqueta). Ordena por vistas desc y trunca a `limite`.
        """
        cuerpo = {
            "dateRanges": [{"startDate": desde.isoformat(), "endDate": hasta.isoformat()}],
            "dimensions": [{"name": "pagePath"}, {"name": "pageTitle"}],
            "metrics": [
                {"name": "screenPageViews"},
                {"name": "totalUsers"},
                {"name": "sessions"},
            ],
            "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
            "limit": str(limite),
        }
        datos = self._post(f"{DATA_API}/properties/{property_id}:runReport", cuerpo)
        filas: list[dict] = []
        for fila in datos.get("rows", []):
            dims = fila.get("dimensionValues", [])
            mets = fila.get("metricValues", [])

            def _m(i: int) -> int:
                return int(mets[i]["value"]) if len(mets) > i else 0

            filas.append(
                {
                    "ruta": dims[0]["value"] if len(dims) > 0 else "",
                    "titulo": dims[1]["value"] if len(dims) > 1 else "",
                    "vistas": _m(0),
                    "usuarios": _m(1),
                    "visitas": _m(2),
                }
            )
        return filas

    def total_evento(
        self, property_id: str, desde: date, hasta: date, nombre_evento: str
    ) -> int:
        """Nº de veces que ocurrió un evento GA4 en el periodo (p.ej. `video_start`).

        Para "inicios de video": `eventCount` filtrado a `eventName == video_start`. Solo
        devuelve > 0 si el sitio trackea ese evento (medición mejorada o evento propio);
        si no, 0 sin error.
        """
        cuerpo = {
            "dateRanges": [{"startDate": desde.isoformat(), "endDate": hasta.isoformat()}],
            "metrics": [{"name": "eventCount"}],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "eventName",
                    "stringFilter": {"value": nombre_evento},
                }
            },
        }
        datos = self._post(f"{DATA_API}/properties/{property_id}:runReport", cuerpo)
        total = 0
        for fila in datos.get("rows", []):
            mets = fila.get("metricValues", [])
            total += int(mets[0]["value"]) if mets else 0
        return total

    def probar(self, property_id: str, desde: date, hasta: date) -> dict:
        """Llamada barata de validación: cuenta filas del runReport de una propiedad.

        Degrada con honestidad: devuelve `{ok, filas, detalle}` sin lanzar, para que el
        endpoint de "probar conexión" reporte el resultado en lugar de un traceback.
        """
        try:
            filas = self.reporte_paginas(property_id, desde, hasta, limite=5)
            return {"ok": True, "filas": len(filas), "detalle": "ok", "muestra": filas[:5]}
        except httpx.HTTPStatusError as e:
            cuerpo = e.response.text[:300]
            log.warning("GA4 probar(%s) HTTP %s: %s", property_id, e.response.status_code, cuerpo)
            return {"ok": False, "filas": 0, "detalle": f"HTTP {e.response.status_code}: {cuerpo}"}
        except Exception as e:  # noqa: BLE001 -- reporta cualquier fallo de red/datos sin romper
            log.warning("GA4 probar(%s) falló: %s", property_id, e)
            return {"ok": False, "filas": 0, "detalle": str(e)}
