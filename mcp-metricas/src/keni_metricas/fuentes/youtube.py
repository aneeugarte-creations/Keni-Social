"""Adaptador YouTube (Analytics API v2 + Data API v3).

Requiere OAuth con scope `yt-analytics.readonly`. `handle` = channel ID.
- refresh: si hay client_id/client_secret/refresh_token, renueva el access_token
  ante un 401 (los access tokens de Google caducan en ~1h).
- piezas: pide top-N por views (una sola consulta de Analytics; sin paginación).
- Analytics no expone "alcance": queda en 0.
"""

from __future__ import annotations

from datetime import date

import httpx

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import cliente_http, con_refresh, get_json, log, post_json

ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
DATA = "https://www.googleapis.com/youtube/v3/videos"
TOKEN = "https://oauth2.googleapis.com/token"


class AdaptadorYouTube:
    plataforma = Plataforma.youtube

    def __init__(self, creds: dict, cliente: httpx.Client | None = None):
        self._creds = creds
        self._token = creds.get("access_token")
        self._cli = cliente or cliente_http()

    def disponible(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def _refrescar(self) -> bool:
        cid, secret, rt = (
            self._creds.get("client_id"),
            self._creds.get("client_secret"),
            self._creds.get("refresh_token"),
        )
        if not (cid and secret and rt):
            return False
        try:
            datos = post_json(
                self._cli,
                TOKEN,
                data={
                    "client_id": cid,
                    "client_secret": secret,
                    "refresh_token": rt,
                    "grant_type": "refresh_token",
                },
            )
            if (nuevo := datos.get("access_token")):
                self._token = nuevo
                return True
        except Exception as e:  # noqa: BLE001
            log.warning("YouTube refresh falló: %s", e)
        return False

    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None:
        if not self.disponible():
            return None
        try:
            return con_refresh(lambda: self._metricas(handle, desde, hasta), self._refrescar)
        except Exception as e:  # noqa: BLE001
            log.warning("YouTube falló para %s: %s", handle, e)
            return None

    def _metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma:
        datos = get_json(
            self._cli,
            ANALYTICS,
            params={
                "ids": f"channel=={handle}",
                "startDate": desde.isoformat(),
                "endDate": hasta.isoformat(),
                "metrics": "views,likes,comments,shares",
            },
            headers=self._headers(),
        )
        filas = datos.get("rows") or [[0, 0, 0, 0]]
        vis, likes, coments, shares = (int(x) for x in filas[0][:4])
        inter = likes + coments + shares
        return MetricaPlataforma(
            plataforma=self.plataforma,
            visualizaciones=vis,
            alcance=0,
            interacciones=inter,
            engagement_pct=round(inter / vis * 100, 1) if vis else 0.0,
        )

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        if not self.disponible():
            return []
        try:
            return con_refresh(lambda: self._piezas(handle, desde, hasta, n), self._refrescar)
        except Exception as e:  # noqa: BLE001
            log.warning("YouTube piezas falló para %s: %s", handle, e)
            return []

    def _piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        rep = get_json(
            self._cli,
            ANALYTICS,
            params={
                "ids": f"channel=={handle}",
                "startDate": desde.isoformat(),
                "endDate": hasta.isoformat(),
                "metrics": "views,likes,comments,shares",
                "dimensions": "video",
                "sort": "-views",
                "maxResults": max(n, 10),
            },
            headers=self._headers(),
        )
        filas = rep.get("rows") or []
        titulos = self._titulos([f[0] for f in filas])
        piezas: list[Pieza] = []
        for f in filas:
            vid, vis, likes, coments, shares = f[0], int(f[1]), int(f[2]), int(f[3]), int(f[4])
            inter = likes + coments + shares
            piezas.append(
                Pieza(
                    id=vid,
                    plataforma=self.plataforma,
                    titulo=titulos.get(vid, vid),
                    publicado=hasta,
                    visualizaciones=vis,
                    interacciones=inter,
                    engagement_pct=round(inter / vis * 100, 1) if vis else 0.0,
                    url=f"https://youtube.com/watch?v={vid}",
                )
            )
        piezas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return piezas[:n]

    def _titulos(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        try:
            datos = get_json(
                self._cli,
                DATA,
                params={"part": "snippet", "id": ",".join(ids)},
                headers=self._headers(),
            )
            return {it["id"]: it.get("snippet", {}).get("title", it["id"]) for it in datos.get("items", [])}
        except Exception:  # noqa: BLE001
            return {}
