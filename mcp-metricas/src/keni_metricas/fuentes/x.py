"""Adaptador X (API v2).

OJO: la lectura de métricas en X está en tier de pago (ver docs/credenciales.md);
`impression_count` solo llega con contexto de usuario/elevado. `handle` = user id.
- paginación: sigue `meta.next_token` (con tope MAX_PAGINAS) para cubrir el rango.
- el bearer token de app no caduca → no hay refresh.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import MAX_PAGINAS, get_json
from .base import AdaptadorBase, engagement_pct

BASE = "https://api.twitter.com/2"


def _iso_utc(d: date, fin: bool = False) -> str:
    t = time(23, 59, 59) if fin else time(0, 0, 0)
    return datetime.combine(d, t, tzinfo=UTC).isoformat().replace("+00:00", "Z")


class AdaptadorX(AdaptadorBase):
    plataforma = Plataforma.x
    # El bearer de X puede venir como `bearer_token` o `access_token`; no caduca,
    # por eso NO se sobreescribe `_refrescar` (el no-op de la base es correcto).
    claves_token = ("bearer_token", "access_token")

    def _tweets(self, handle: str, desde: date, hasta: date) -> list[dict]:
        """Todos los tweets del rango, paginando con next_token."""
        tweets: list[dict] = []
        params = {
            "max_results": 100,
            "start_time": _iso_utc(desde),
            "end_time": _iso_utc(hasta, fin=True),
            "tweet.fields": "public_metrics,created_at,text",
        }
        headers = self._headers_bearer()
        for _ in range(MAX_PAGINAS):
            datos = get_json(self._cli, f"{BASE}/users/{handle}/tweets", params=params, headers=headers)
            tweets.extend(datos.get("data", []))
            siguiente = (datos.get("meta") or {}).get("next_token")
            if not siguiente:
                break
            params = {**params, "pagination_token": siguiente}
        return tweets

    @staticmethod
    def _inter(pm: dict) -> int:
        return (
            int(pm.get("like_count", 0))
            + int(pm.get("reply_count", 0))
            + int(pm.get("retweet_count", 0))
            + int(pm.get("quote_count", 0))
        )

    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None:
        return self._intentar(
            lambda: self._metricas(handle, desde, hasta),
            defecto=None,
            contexto=f"X para {handle}",
        )

    def _metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma:
        tweets = self._tweets(handle, desde, hasta)
        vis = sum(int(t.get("public_metrics", {}).get("impression_count", 0)) for t in tweets)
        inter = sum(self._inter(t.get("public_metrics", {})) for t in tweets)
        return MetricaPlataforma(
            plataforma=self.plataforma,
            visualizaciones=vis,
            alcance=None,  # X no expone alcance/usuarios únicos: AUSENTE, no 0 (#138)
            interacciones=inter,
            engagement_pct=engagement_pct(inter, vis),
        )

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        return self._intentar(
            lambda: self._piezas(handle, desde, hasta, n),
            defecto=[],
            contexto=f"X piezas para {handle}",
        )

    def _piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
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
                    texto=str(t.get("text") or ""),
                    publicado=date.fromisoformat(fecha) if fecha else hasta,
                    visualizaciones=vis,
                    interacciones=inter,
                    engagement_pct=engagement_pct(inter, vis),
                    url=f"https://x.com/{handle}/status/{t.get('id', '')}",
                )
            )
        piezas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return piezas[:n]
