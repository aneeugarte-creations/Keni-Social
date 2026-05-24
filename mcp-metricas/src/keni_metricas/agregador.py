"""FuenteCompuesta: combina los adaptadores reales por plataforma en metricas
multi-marca/multi-plataforma. Implementa FuenteMetricas a partir de la config.
"""

from __future__ import annotations

from .config import Config, CuentaConfig
from .fuentes.base import AdaptadorPlataforma, CuentaNoEncontrada
from .schema import Cuenta, MetricaPlataforma, Periodo, Pieza, Plataforma, ResumenMetricas, resolver_rango


class FuenteCompuesta:
    nombre = "real"

    def __init__(
        self,
        cuentas: list[CuentaConfig],
        adaptadores: dict[Plataforma, AdaptadorPlataforma],
    ):
        self._cuentas = cuentas
        self._adaptadores = adaptadores

    @classmethod
    def desde_config(cls, cfg: Config) -> "FuenteCompuesta":
        from .fuentes.meta import AdaptadorMeta
        from .fuentes.tiktok import AdaptadorTikTok
        from .fuentes.x import AdaptadorX
        from .fuentes.youtube import AdaptadorYouTube

        creds = cfg.credenciales
        posibles: dict[Plataforma, AdaptadorPlataforma] = {
            Plataforma.facebook: AdaptadorMeta(creds.get("meta", {}), Plataforma.facebook),
            Plataforma.instagram: AdaptadorMeta(creds.get("meta", {}), Plataforma.instagram),
            Plataforma.youtube: AdaptadorYouTube(creds.get("youtube", {})),
            Plataforma.x: AdaptadorX(creds.get("x", {})),
            Plataforma.tiktok: AdaptadorTikTok(creds.get("tiktok", {})),
        }
        # solo conserva los adaptadores con credenciales suficientes
        adaptadores = {p: a for p, a in posibles.items() if a.disponible()}
        return cls(cfg.cuentas, adaptadores)

    def _buscar(self, cuenta_id: str) -> CuentaConfig:
        for c in self._cuentas:
            if c.id == cuenta_id:
                return c
        disponibles = ", ".join(c.id for c in self._cuentas) or "(ninguna configurada)"
        raise CuentaNoEncontrada(
            f"Cuenta {cuenta_id!r} no encontrada. Disponibles: {disponibles}."
        )

    def cuentas(self) -> list[Cuenta]:
        return [
            Cuenta(
                id=c.id,
                nombre=c.nombre,
                plataformas=[p for p in c.plataformas if p in self._adaptadores],
            )
            for c in self._cuentas
        ]

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas:
        cc = self._buscar(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)

        por_plataforma: list[MetricaPlataforma] = []
        for plat, handle in cc.plataformas.items():
            ad = self._adaptadores.get(plat)
            if ad is None:
                continue
            m = ad.metricas(handle, desde, hasta)
            if m is not None:
                por_plataforma.append(m)

        vis = sum(m.visualizaciones for m in por_plataforma)
        inter = sum(m.interacciones for m in por_plataforma)
        alc = sum(m.alcance for m in por_plataforma)
        return ResumenMetricas(
            cuenta=cuenta_id,
            rango=rango,
            periodo=Periodo(desde=desde, hasta=hasta),
            visualizaciones=vis,
            alcance=alc,
            interacciones=inter,
            engagement_pct=round(inter / vis * 100, 1) if vis else 0.0,
            seguidores_netos=0,  # requiere historico; no se calcula en v1
            variacion_vs_anterior={},  # idem
            por_plataforma=por_plataforma,
            fuente=self.nombre,
        )

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        cc = self._buscar(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        todas: list[Pieza] = []
        for plat, handle in cc.plataformas.items():
            ad = self._adaptadores.get(plat)
            if ad is None:
                continue
            todas.extend(ad.piezas(handle, desde, hasta, n))
        todas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return todas[:n]
