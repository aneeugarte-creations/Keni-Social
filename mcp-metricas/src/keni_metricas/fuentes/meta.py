"""Adaptador Meta Graph API: Facebook Pages + Instagram (insights).

Ruta directa opcional: la lectura habitual de metricas va via Metricool
(`fuentes.metricool`). Para la via directa usa `pages_read_engagement`,
`read_insights` e `instagram_manage_insights`; `disponible()` es False salvo que
se configure un access token. Ver docs/credenciales.md.

- piezas: pagina siguiendo `paging.next` (con tope MAX_PAGINAS).
- refresh: si hay app_id/app_secret, intercambia el token por uno de larga
  duración (fb_exchange_token) ante un 401. Meta no tiene refresh_token clásico.
- tipo_token: si las credenciales traen `tipo_token = "system_user"`, el token
  es de un System User de Business Manager y NO caduca; entonces el refresh es
  un no-op (no se intenta fb_exchange_token). Es la mitad "hosted" de la
  arquitectura híbrida. Ver docs/credenciales.md.
"""

from __future__ import annotations

from datetime import date

import httpx

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import MAX_PAGINAS, get_json, log
from .base import AdaptadorBase, engagement_pct

BASE = "https://graph.facebook.com/v21.0"

# Valor de `tipo_token` para tokens de System User (Business Manager): no caducan.
TIPO_SYSTEM_USER = "system_user"


def _suma_valores(datos: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for serie in datos.get("data", []):
        nombre = serie.get("name")
        total = sum(int(v.get("value", 0) or 0) for v in serie.get("values", []))
        if nombre:
            out[nombre] = total
    return out


class AdaptadorMeta(AdaptadorBase):
    def __init__(
        self,
        creds: dict,
        plataforma: Plataforma = Plataforma.facebook,
        cliente: httpx.Client | None = None,
    ):
        super().__init__(creds, cliente)
        self.plataforma = plataforma
        # System User tokens (Business Manager) no caducan: refresh es no-op.
        self._es_system_user = creds.get("tipo_token") == TIPO_SYSTEM_USER

    def _refrescar(self) -> bool:
        if self._es_system_user:
            # Token de System User: no caduca, no hay nada que renovar.
            return False
        cid, secret = self._creds.get("app_id"), self._creds.get("app_secret")
        if not (cid and secret and self._token):
            return False
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": cid,
                    "client_secret": secret,
                    "fb_exchange_token": self._token,
                },
            )
            if (nuevo := datos.get("access_token")):
                self._token = nuevo
                return True
        except Exception as e:  # noqa: BLE001
            log.warning("Meta refresh falló: %s", e)
        return False

    # --- métricas -----------------------------------------------------------
    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None:
        return self._intentar(
            lambda: self._metricas(handle, desde, hasta),
            defecto=None,
            contexto=f"Meta {self.plataforma.value} para {handle}",
        )

    def _metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma:
        if self.plataforma is Plataforma.facebook:
            metric = "page_impressions,page_impressions_unique,page_post_engagements"
            k_vis, k_alc, k_int = "page_impressions", "page_impressions_unique", "page_post_engagements"
        else:
            metric = "impressions,reach,accounts_engaged"
            k_vis, k_alc, k_int = "impressions", "reach", "accounts_engaged"
        datos = get_json(
            self._cli,
            f"{BASE}/{handle}/insights",
            params={
                "metric": metric,
                "period": "day",
                "since": desde.isoformat(),
                "until": hasta.isoformat(),
                "access_token": self._token,
            },
        )
        m = _suma_valores(datos)
        vis, alc, inter = m.get(k_vis, 0), m.get(k_alc, 0), m.get(k_int, 0)
        return MetricaPlataforma(
            plataforma=self.plataforma,
            visualizaciones=vis,
            alcance=alc,
            interacciones=inter,
            engagement_pct=engagement_pct(inter, vis),
        )

    # --- piezas (con paginación) -------------------------------------------
    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        return self._intentar(
            lambda: self._piezas(handle, desde, hasta, n),
            defecto=[],
            contexto=f"Meta {self.plataforma.value} piezas para {handle}",
        )

    def _piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        es_fb = self.plataforma is Plataforma.facebook
        edge = "posts" if es_fb else "media"
        metrica = "post_impressions" if es_fb else "impressions"
        engaged = "post_engaged_users" if es_fb else "total_interactions"

        # primera página
        url: str | None = f"{BASE}/{handle}/{edge}"
        params: dict | None = {
            "fields": f"id,message,caption,permalink_url,created_time,timestamp,"
            f"insights.metric({metrica},{engaged})",
            "since": desde.isoformat(),
            "until": hasta.isoformat(),
            "limit": max(n, 25),
            "access_token": self._token,
        }

        piezas: list[Pieza] = []
        for _ in range(MAX_PAGINAS):
            datos = get_json(self._cli, url, params=params)
            for it in datos.get("data", []):
                ins = _suma_valores(it.get("insights", {}))
                vis, inter = ins.get(metrica, 0), ins.get(engaged, 0)
                if not vis:
                    continue
                fecha = (it.get("created_time") or it.get("timestamp") or "")[:10]
                piezas.append(
                    Pieza(
                        id=str(it.get("id", "")),
                        plataforma=self.plataforma,
                        titulo=(it.get("message") or it.get("caption") or "(sin texto)")[:120],
                        texto=str(it.get("message") or it.get("caption") or ""),
                        publicado=date.fromisoformat(fecha) if fecha else hasta,
                        visualizaciones=vis,
                        interacciones=inter,
                        engagement_pct=engagement_pct(inter, vis),
                        url=it.get("permalink_url"),
                    )
                )
            url = (datos.get("paging") or {}).get("next")  # URL completa con cursor + token
            params = None
            if not url:
                break

        piezas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return piezas[:n]
