"""Adaptador TikTok (Display API).

Requiere auditoría de TikTok para acceso completo (ver docs/credenciales.md).
- paginación: sigue `data.cursor` mientras `data.has_more` (con tope MAX_PAGINAS).
- refresh: si hay client_key/client_secret/refresh_token, renueva el access_token
  ante un 401.
- TikTok no expone "alcance": se reporta AUSENTE (None), no 0 (#138). `handle` no
  se usa (va por el token).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from ..schema import MetricaPlataforma, Pieza, Plataforma
from ._http import MAX_PAGINAS, log, post_json
from .base import AdaptadorBase, engagement_pct

VIDEO_LIST = "https://open.tiktokapis.com/v2/video/list/"
TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
CAMPOS = "id,title,view_count,like_count,comment_count,share_count,create_time"


class AdaptadorTikTok(AdaptadorBase):
    plataforma = Plataforma.tiktok

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
                headers=self._headers_bearer(),
                json=cuerpo,
            )
            data = datos.get("data") or {}
            for v in data.get("videos", []):
                ct = v.get("create_time")
                if ct is None:
                    out.append(v)
                    continue
                d = datetime.fromtimestamp(int(ct), tz=UTC).date()
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
        return self._intentar(
            lambda: self._metricas(desde, hasta),
            defecto=None,
            contexto="TikTok",
        )

    def _metricas(self, desde: date, hasta: date) -> MetricaPlataforma:
        videos = self._videos(desde, hasta)
        vis = sum(int(v.get("view_count", 0)) for v in videos)
        inter = sum(self._inter(v) for v in videos)
        return MetricaPlataforma(
            plataforma=self.plataforma,
            visualizaciones=vis,
            alcance=None,  # TikTok Display API no expone alcance: AUSENTE, no 0 (#138)
            interacciones=inter,
            engagement_pct=engagement_pct(inter, vis),
        )

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]:
        return self._intentar(
            lambda: self._piezas(desde, hasta, n),
            defecto=[],
            contexto="TikTok piezas",
        )

    def _piezas(self, desde: date, hasta: date, n: int) -> list[Pieza]:
        piezas: list[Pieza] = []
        for v in self._videos(desde, hasta):
            vis = int(v.get("view_count", 0))
            inter = self._inter(v)
            ct = v.get("create_time")
            pub = datetime.fromtimestamp(int(ct), tz=UTC).date() if ct else hasta
            vid = str(v.get("id", ""))
            piezas.append(
                Pieza(
                    id=vid,
                    plataforma=self.plataforma,
                    titulo=(v.get("title") or "(sin titulo)")[:120],
                    texto=str(v.get("title") or ""),
                    publicado=pub,
                    visualizaciones=vis,
                    interacciones=inter,
                    engagement_pct=engagement_pct(inter, vis),
                    url=f"https://tiktok.com/video/{vid}",
                )
            )
        piezas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return piezas[:n]
