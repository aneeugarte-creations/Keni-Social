"""Adaptador Meta Graph API: Facebook Pages + Instagram (insights).

Requiere App Review de Meta (`pages_read_engagement`, `read_insights`,
`instagram_manage_insights`). Hasta entonces, `disponible()` es False salvo que
se configure un access token (p. ej. dev token sobre cuentas de prueba). Ver
docs/credenciales.md.
"""

from __future__ import annotations

from datetime import date

import httpx

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import cliente_http, get_json, log

BASE = "https://graph.facebook.com/v21.0"


def _suma_valores(datos: dict) -> dict[str, int]:
    """Suma los valores diarios de cada metrica de un payload de insights."""
    out: dict[str, int] = {}
    for serie in datos.get("data", []):
        nombre = serie.get("name")
        total = sum(int(v.get("value", 0) or 0) for v in serie.get("values", []))
        if nombre:
            out[nombre] = total
    return out


class AdaptadorMeta:
    def __init__(
        self,
        creds: dict,
        plataforma: Plataforma = Plataforma.facebook,
        cliente: httpx.Client | None = None,
    ):
        self.plataforma = plataforma
        self._token = creds.get("access_token")
        self._cli = cliente or cliente_http()

    def disponible(self) -> bool:
        return bool(self._token)

    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None:
        if not self.disponible():
            return None
        try:
            if self.plataforma is Plataforma.facebook:
                datos = get_json(
                    self._cli,
                    f"{BASE}/{handle}/insights",
                    params={
                        "metric": "page_impressions,page_impressions_unique,page_post_engagements",
                        "period": "day",
                        "since": desde.isoformat(),
                        "until": hasta.isoformat(),
                        "access_token": self._token,
                    },
                )
                m = _suma_valores(datos)
                vis = m.get("page_impressions", 0)
                alc = m.get("page_impressions_unique", 0)
                inter = m.get("page_post_engagements", 0)
            else:  # instagram
                datos = get_json(
                    self._cli,
                    f"{BASE}/{handle}/insights",
                    params={
                        "metric": "impressions,reach,accounts_engaged",
                        "period": "day",
                        "since": desde.isoformat(),
                        "until": hasta.isoformat(),
                        "access_token": self._token,
                    },
                )
                m = _suma_valores(datos)
                vis = m.get("impressions", 0)
                alc = m.get("reach", 0)
                inter = m.get("accounts_engaged", 0)

            eng = round(inter / vis * 100, 1) if vis else 0.0
            return MetricaPlataforma(
                plataforma=self.plataforma,
                visualizaciones=vis,
                alcance=alc,
                interacciones=inter,
                engagement_pct=eng,
            )
        except Exception as e:  # noqa: BLE001 - degradacion elegante
            log.warning("Meta %s fallo para %s: %s", self.plataforma.value, handle, e)
            return None

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        if not self.disponible():
            return []
        es_fb = self.plataforma is Plataforma.facebook
        edge = "posts" if es_fb else "media"
        metrica = "post_impressions" if es_fb else "impressions"
        engaged = "post_engaged_users" if es_fb else "total_interactions"
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/{handle}/{edge}",
                params={
                    "fields": f"id,message,caption,permalink_url,created_time,timestamp,"
                    f"insights.metric({metrica},{engaged})",
                    "since": desde.isoformat(),
                    "until": hasta.isoformat(),
                    "limit": max(n, 10),
                    "access_token": self._token,
                },
            )
            piezas: list[Pieza] = []
            for it in datos.get("data", []):
                ins = _suma_valores(it.get("insights", {}))
                vis = ins.get(metrica, 0)
                inter = ins.get(engaged, 0)
                if not vis:
                    continue
                fecha = (it.get("created_time") or it.get("timestamp") or "")[:10]
                piezas.append(
                    Pieza(
                        id=str(it.get("id", "")),
                        plataforma=self.plataforma,
                        titulo=(it.get("message") or it.get("caption") or "(sin texto)")[:120],
                        publicado=date.fromisoformat(fecha) if fecha else hasta,
                        visualizaciones=vis,
                        interacciones=inter,
                        engagement_pct=round(inter / vis * 100, 1) if vis else 0.0,
                        url=it.get("permalink_url"),
                    )
                )
            piezas.sort(key=lambda p: p.engagement_pct, reverse=True)
            return piezas[:n]
        except Exception as e:  # noqa: BLE001
            log.warning("Meta %s piezas fallo para %s: %s", self.plataforma.value, handle, e)
            return []
