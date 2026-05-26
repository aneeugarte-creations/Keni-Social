"""Adaptador YouTube (Analytics API v2 + Data API v3).

Requiere OAuth con scope `yt-analytics.readonly`. `handle` = channel ID.
- refresh: si hay client_id/client_secret/refresh_token, renueva el access_token
  ante un 401 (los access tokens de Google caducan en ~1h).
- piezas: pide top-N por views (una sola consulta de Analytics; sin paginación).
- Analytics no expone "alcance": queda en 0.
"""

from __future__ import annotations

from datetime import date

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import get_json, log, post_json
from .base import AdaptadorBase, engagement_pct

ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
DATA = "https://www.googleapis.com/youtube/v3/videos"
TOKEN = "https://oauth2.googleapis.com/token"


class AdaptadorYouTube(AdaptadorBase):
    plataforma = Plataforma.youtube

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
        return self._intentar(
            lambda: self._metricas(handle, desde, hasta),
            defecto=None,
            contexto=f"YouTube para {handle}",
        )

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
            headers=self._headers_bearer(),
        )
        filas = datos.get("rows") or [[0, 0, 0, 0]]
        vis, likes, coments, shares = (int(x) for x in filas[0][:4])
        inter = likes + coments + shares
        return MetricaPlataforma(
            plataforma=self.plataforma,
            visualizaciones=vis,
            alcance=0,
            interacciones=inter,
            engagement_pct=engagement_pct(inter, vis),
        )

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        return self._intentar(
            lambda: self._piezas(handle, desde, hasta, n),
            defecto=[],
            contexto=f"YouTube piezas para {handle}",
        )

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
            headers=self._headers_bearer(),
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
                    engagement_pct=engagement_pct(inter, vis),
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
                headers=self._headers_bearer(),
            )
            return {it["id"]: it.get("snippet", {}).get("title", it["id"]) for it in datos.get("items", [])}
        except Exception:  # noqa: BLE001
            return {}
