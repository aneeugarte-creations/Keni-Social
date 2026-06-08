"""FuenteCompuesta: combina los adaptadores reales por plataforma en metricas
multi-marca/multi-plataforma. Implementa FuenteMetricas a partir de la config.

FALLBACK HISTÓRICO, NO la fuente única
--------------------------------------
La fuente única de métricas de keni-social es **Metricool** (`fuentes.metricool`):
dashboard por marca/cuenta Y rendimiento por pieza salen del MISMO camino, sin
desfase. `FuenteCompuesta` queda como capacidad histórica (ADR 0005 §B) y está
DESACTIVADA por defecto: `config.construir_fuente` solo la instancia con el flag
opt-in `KENI_METRICAS_PERMITIR_REAL=1`. Razón del gate: solo cubre el dashboard
agregado (resumen + mejores piezas); NO implementa `metricas_de_post` ni
`serie_diaria`, así que conviviría con el tablero leyendo cero en el rendimiento por
pieza — exactamente el desfase entre fuentes que la consolidación elimina. No la
selecciones para producción: usa `metricool`.

Semántica de agregación entre plataformas (#138)
-------------------------------------------------
Las redes NO miden lo mismo, así que no todo se puede sumar entre ellas. La regla
explícita que aplica el agregador (ver `agregar_resumen`):

- `interacciones`  → SE SUMA. Es la única magnitud homogénea (likes + comentarios
  + compartidos + …): la misma cuenta en todas las plataformas.
- `visualizaciones`→ se suma solo como TOTAL INFORMATIVO. Mezcla impresiones
  (FB/IG/X) con reproducciones (YouTube/TikTok), que no son lo mismo; el desglose
  fiable está en `por_plataforma`. No se usa como base del engagement global.
- `alcance`        → se suma SOLO entre las plataformas que lo miden (Meta). Las
  que no lo miden lo reportan AUSENTE (`None`), no 0, y quedan EXCLUIDAS. Si
  ninguna lo mide, el total es `None` (ausencia de dato, no 0 real).
- `engagement_pct` → NO se divide sobre la suma de visualizaciones heterogéneas.
  Si el resumen combina más de una plataforma con bases distintas, el engagement
  global es `None` (no comparable); con una sola plataforma se conserva el suyo.
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
    agregar_alcance,
    agregar_engagement,
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

        # Agregación según la semántica de #138 (ver módulo): interacciones se
        # suman; visualizaciones solo como total informativo; alcance solo entre
        # plataformas que lo miden; engagement no se divide sobre bases mixtas.
        vis = sum(m.visualizaciones for m in por_plataforma)
        inter = sum(m.interacciones for m in por_plataforma)
        # Seguidores NETOS del periodo: suma, sobre las plataformas que respondieron,
        # del neto que aporte cada adaptador SI expone la capacidad. Los adaptadores
        # directos por red NO tienen serie de followers (a diferencia de Metricool, la
        # fuente única), así que esto degrada honestamente a 0 salvo que un adaptador
        # implemente `seguidores_netos(handle, desde, hasta)`. No se inventa.
        seguidores_netos = 0
        for plat, handle in cc.plataformas.items():
            if plat not in cobertura.ok:
                continue
            ad = self._adaptadores.get(plat)
            seg_fn = getattr(ad, "seguidores_netos", None)
            if seg_fn is None:
                continue
            try:
                neto = seg_fn(handle, desde, hasta)
            except Exception:  # noqa: BLE001 — degrada a 0, nunca inventa
                neto = None
            if isinstance(neto, int):
                seguidores_netos += neto
        return ResumenMetricas(
            cuenta=cuenta_id,
            rango=rango,
            periodo=Periodo(desde=desde, hasta=hasta),
            visualizaciones=vis,
            alcance=agregar_alcance(por_plataforma),
            interacciones=inter,
            engagement_pct=agregar_engagement(por_plataforma, inter),
            seguidores_netos=seguidores_netos,
            variacion_vs_anterior={},  # requiere historico; no se calcula en v1
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
