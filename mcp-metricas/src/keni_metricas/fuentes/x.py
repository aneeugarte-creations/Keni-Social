"""Adaptador X (API v2).

OJO: la lectura de metricas en X esta en tier de pago (ver docs/credenciales.md);
`impression_count` solo llega con contexto de usuario/elevado. `handle` = user id.
Sin token, `disponible()` es False y el agregador omite X.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import httpx

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import cliente_http, get_json, log

BASE = "https://api.twitter.com/2"


def _iso_utc(d: date, fin: bool = False) -> str:
    t = time(23, 59, 59) if fin else time(0, 0, 0)
    return datetime.combine(d, t, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class AdaptadorX:
    plataforma = Plataforma.x

    def __init__(self, creds: dict, cliente: httpx.Client | None = None):
        self._token = creds.get("bearer_token") or creds.get("access_token")
        self._cli = cliente or cliente_http()

    def disponible(self) -> bool:
        return bool(self._token)

    def _tweets(self, handle: str, desde: date, hasta: date) -> list[dict]:
        datos = get_json(
            self._cli,
            f"{BASE}/users/{handle}/tweets",
            params={
                "max_results": 100,
                "start_time": _iso_utc(desde),
                "end_time": _iso_utc(hasta, fin=True),
                "tweet.fields": "public_metrics,created_at,text",
            },
            headers={"Authorization": f"Bearer {self._token}"},
        )
        return datos.get("data", [])

    @staticmethod
    def _inter(pm: dict) -> int:
        return (
            int(pm.get("like_count", 0))
            + int(pm.get("reply_count", 0))
            + int(pm.get("retweet_count", 0))
            + int(pm.get("quote_count", 0))
        )

    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None:
        if not self.disponible():
            return None
        try:
            tweets = self._tweets(handle, desde, hasta)
            vis = sum(int(t.get("public_metrics", {}).get("impression_count", 0)) for t in tweets)
            inter = sum(self._inter(t.get("public_metrics", {})) for t in tweets)
            return MetricaPlataforma(
                plataforma=self.plataforma,
                visualizaciones=vis,
                alcance=0,
                interacciones=inter,
                engagement_pct=round(inter / vis * 100, 1) if vis else 0.0,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("X fallo para %s: %s", handle, e)
            return None

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        if not self.disponible():
            return []
        try:
            piezas: list[Pieza] = []
            for t in self._tweets(handle, desde, hasta):
                pm = t.get("public_metrics", {})
                vis = int(pm.get("impression_count", 0))
                inter = self._inter(pm)
                fecha = (t.get("created_at") or "")[:10]
                piezas.append(
                    Pieza(
                        id=str(t.get("id", "")),
                        plataforma=self.plataforma,
                        titulo=(t.get("text") or "")[:120],
                        publicado=date.fromisoformat(fecha) if fecha else hasta,
                        visualizaciones=vis,
                        interacciones=inter,
                        engagement_pct=round(inter / vis * 100, 1) if vis else 0.0,
                        url=f"https://x.com/{handle}/status/{t.get('id', '')}",
                    )
                )
            piezas.sort(key=lambda p: p.engagement_pct, reverse=True)
            return piezas[:n]
        except Exception as e:  # noqa: BLE001
            log.warning("X piezas fallo para %s: %s", handle, e)
            return []
