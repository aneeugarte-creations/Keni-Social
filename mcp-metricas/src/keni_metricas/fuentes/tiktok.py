"""Adaptador TikTok (Display API).

Requiere auditoría de TikTok para acceso completo (ver docs/credenciales.md).
- paginación: sigue `data.cursor` mientras `data.has_more` (con tope MAX_PAGINAS).
- refresh: si hay client_key/client_secret/refresh_token, renueva el access_token
  ante un 401.
- TikTok no expone "alcance": queda en 0. `handle` no se usa (va por el token).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import MAX_PAGINAS, cliente_http, con_refresh, log, post_json

VIDEO_LIST = "https://open.tiktokapis.com/v2/video/list/"
TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
CAMPOS = "id,title,view_count,like_count,comment_count,share_count,create_time"


class AdaptadorTikTok:
    plataforma = Plataforma.tiktok

    def __init__(self, creds: dict, cliente: httpx.Client | None = None):
        self._creds = creds
        self._token = creds.get("access_token")
        self._cli = cliente or cliente_http()

    def disponible(self) -> bool:
        return bool(self._token)

    def _refrescar(self) -> bool:
        ck, secret, rt = (
            self._creds.get("client_key"),
            self._creds.get("client_secret"),
            self._creds.get("refresh_token"),
        )
        if not (ck and secret and rt):
            return False
        try:
            datos = post_json(
                self._cli,
                TOKEN,
                data={
                    "client_key": ck,
                    "client_secret": secret,
                    "grant_type": "refresh_token",
                    "refresh_token": rt,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if (nuevo := datos.get("access_token")):
                self._token = nuevo
                return True
        except Exception as e:  # noqa: BLE001
            log.warning("TikTok refresh falló: %s", e)
        return False

    def _videos(self, desde: date, hasta: date) -> list[dict]:
        """Vídeos del rango, paginando con cursor/has_more."""
        out: list[dict] = []
        cursor: int | None = None
        for _ in range(MAX_PAGINAS):
            cuerpo: dict = {"max_count": 20}
            if cursor is not None:
                cuerpo["cursor"] = cursor
            datos = post_json(
                self._cli,
                VIDEO_LIST,
                params={"fields": CAMPOS},
                headers={"Authorization": f"Bearer {self._token}"},
                json=cuerpo,
            )
            data = datos.get("data") or {}
            for v in data.get("videos", []):
                ct = v.get("create_time")
                if ct is None:
                    out.append(v)
                    continue
                d = datetime.fromtimestamp(int(ct), tz=timezone.utc).date()
                if desde <= d <= hasta:
                    out.append(v)
            if not data.get("has_more"):
                break
            cursor = data.get("cursor")
        return out

    @staticmethod
    def _inter(v: dict) -> int:
        return int(v.get("like_count", 0)) + int(v.get("comment_count", 0)) + int(v.get("share_count", 0))

    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None:
        if not self.disponible():
            return None
        try:
            videos = con_refresh(lambda: self._videos(desde, hasta), self._refrescar)
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
            log.warning("TikTok falló: %s", e)
            return None

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        if not self.disponible():
            return []
        try:
            videos = con_refresh(lambda: self._videos(desde, hasta), self._refrescar)
            piezas: list[Pieza] = []
            for v in videos:
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
            log.warning("TikTok piezas falló: %s", e)
            return []
