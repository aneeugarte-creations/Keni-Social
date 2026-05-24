"""Adaptador TikTok (Display API).

Requiere auditoria de TikTok para acceso completo (ver docs/credenciales.md).
`handle` no se usa para el video/list propio (va por el token del usuario); se
acepta por consistencia de la interfaz. TikTok no expone "alcance": queda en 0.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import cliente_http, log

VIDEO_LIST = "https://open.tiktokapis.com/v2/video/list/"
CAMPOS = "id,title,view_count,like_count,comment_count,share_count,create_time"


class AdaptadorTikTok:
    plataforma = Plataforma.tiktok

    def __init__(self, creds: dict, cliente: httpx.Client | None = None):
        self._token = creds.get("access_token")
        self._cli = cliente or cliente_http()

    def disponible(self) -> bool:
        return bool(self._token)

    def _videos(self, desde: date, hasta: date) -> list[dict]:
        r = self._cli.post(
            VIDEO_LIST,
            params={"fields": CAMPOS},
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            json={"max_count": 20},
        )
        r.raise_for_status()
        videos = (r.json().get("data") or {}).get("videos", [])
        out = []
        for v in videos:
            ct = v.get("create_time")
            if ct is None:
                out.append(v)
                continue
            d = datetime.fromtimestamp(int(ct), tz=timezone.utc).date()
            if desde <= d <= hasta:
                out.append(v)
        return out

    @staticmethod
    def _inter(v: dict) -> int:
        return (
            int(v.get("like_count", 0))
            + int(v.get("comment_count", 0))
            + int(v.get("share_count", 0))
        )

    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None:
        if not self.disponible():
            return None
        try:
            videos = self._videos(desde, hasta)
            vis = sum(int(v.get("view_count", 0)) for v in videos)
            inter = sum(self._inter(v) for v in videos)
            return MetricaPlataforma(
                plataforma=self.plataforma,
                visualizaciones=vis,
                alcance=0,
                interacciones=inter,
                engagement_pct=round(inter / vis * 100, 1) if vis else 0.0,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("TikTok fallo: %s", e)
            return None

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        if not self.disponible():
            return []
        try:
            piezas: list[Pieza] = []
            for v in self._videos(desde, hasta):
                vis = int(v.get("view_count", 0))
                inter = self._inter(v)
                ct = v.get("create_time")
                pub = datetime.fromtimestamp(int(ct), tz=timezone.utc).date() if ct else hasta
                vid = str(v.get("id", ""))
                piezas.append(
                    Pieza(
                        id=vid,
                        plataforma=self.plataforma,
                        titulo=(v.get("title") or "(sin titulo)")[:120],
                        publicado=pub,
                        visualizaciones=vis,
                        interacciones=inter,
                        engagement_pct=round(inter / vis * 100, 1) if vis else 0.0,
                        url=f"https://tiktok.com/video/{vid}",
                    )
                )
            piezas.sort(key=lambda p: p.engagement_pct, reverse=True)
            return piezas[:n]
        except Exception as e:  # noqa: BLE001
            log.warning("TikTok piezas fallo: %s", e)
            return []
