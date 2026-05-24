"""FuenteCompuesta: combina los adaptadores reales por plataforma en metricas
multi-marca/multi-plataforma. Implementa FuenteMetricas a partir de la config.
"""

from __future__ import annotations

import logging

from .config import Config, CuentaConfig
from .fuentes.base import AdaptadorPlataforma, CuentaNoEncontrada
from .presupuesto import Presupuesto, PresupuestoExcedido
from .schema import (
    Cobertura,
    Cuenta,
    MetricaPlataforma,
    MotivoOmision,
    Periodo,
    Pieza,
    Plataforma,
    ResumenMetricas,
    resolver_rango,
)

log = logging.getLogger("keni_metricas")


class FuenteCompuesta:
    nombre = "real"

    def __init__(
        self,
        cuentas: list[CuentaConfig],
        adaptadores: dict[Plataforma, AdaptadorPlataforma],
        presupuesto: Presupuesto | None = None,
    ):
        self._cuentas = cuentas
        self._adaptadores = adaptadores
        self._presupuesto = presupuesto

    def _consumir(self, plat: Plataforma) -> bool:
        """True si hay presupuesto para consultar la plataforma; si no, avisa y False."""
        if self._presupuesto is None:
            return True
        try:
            self._presupuesto.consumir(plat)
            return True
        except PresupuestoExcedido as e:
            log.warning("%s", e)
            return False

    @classmethod
    def desde_config(cls, cfg: Config) -> FuenteCompuesta:
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
        return cls(cfg.cuentas, adaptadores, Presupuesto())

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
        cobertura = Cobertura()
        for plat, handle in cc.plataformas.items():
            ad = self._adaptadores.get(plat)
            if ad is None:
                # plataforma configurada pero sin adaptador: faltan credenciales
                self._omitir(cobertura, plat, MotivoOmision.sin_credenciales)
                continue
            if not self._consumir(plat):
                self._omitir(cobertura, plat, MotivoOmision.presupuesto_agotado)
                continue
            m = ad.metricas(handle, desde, hasta)
            if m is None:
                # el adaptador devolvio None: la API fallo (ver log.warning del adaptador)
                self._omitir(cobertura, plat, MotivoOmision.error_api)
                continue
            por_plataforma.append(m)
            cobertura.ok.append(plat)

        if cobertura.omitidas:
            detalle = ", ".join(f"{p.value}={cobertura.motivo[p.value].value}" for p in cobertura.omitidas)
            log.warning(
                "cobertura parcial en %s/%s: %d/%d plataformas omitidas (%s)",
                cuenta_id,
                rango,
                len(cobertura.omitidas),
                len(cc.plataformas),
                detalle,
            )

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
            cobertura=cobertura,
        )

    @staticmethod
    def _omitir(cobertura: Cobertura, plat: Plataforma, motivo: MotivoOmision) -> None:
        cobertura.omitidas.append(plat)
        cobertura.motivo[plat.value] = motivo

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        cc = self._buscar(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        todas: list[Pieza] = []
        for plat, handle in cc.plataformas.items():
            ad = self._adaptadores.get(plat)
            if ad is None or not self._consumir(plat):
                continue
            todas.extend(ad.piezas(handle, desde, hasta, n))
        todas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return todas[:n]
