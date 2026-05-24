"""Adaptador YouTube (Analytics API v2 + Data API v3).

Requiere OAuth con scope `yt-analytics.readonly`. `handle` = channel ID.
Nota: la API de Analytics no expone "alcance"; se deja en 0.
"""

from __future__ import annotations

from datetime import date

import httpx

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import cliente_http, get_json, log

ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
DATA = "https://www.googleapis.com/youtube/v3/videos"


class AdaptadorYouTube:
    plataforma = Plataforma.youtube

    def __init__(self, creds: dict, cliente: httpx.Client | None = None):
        self._token = creds.get("access_token")
        self._cli = cliente or cliente_http()

    def disponible(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None:
        if not self.disponible():
            return None
        try:
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
        except Exception as e:  # noqa: BLE001
            log.warning("YouTube fallo para %s: %s", handle, e)
            return None

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        if not self.disponible():
            return []
        try:
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
            ids = [f[0] for f in filas]
            titulos = self._titulos(ids)
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
        except Exception as e:  # noqa: BLE001
            log.warning("YouTube piezas fallo para %s: %s", handle, e)
            return []

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
            return {
                it["id"]: it.get("snippet", {}).get("title", it["id"])
                for it in datos.get("items", [])
            }
        except Exception:  # noqa: BLE001
            return {}
