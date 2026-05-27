"""Fuente offline `muestra`: datos representativos, creibles y deterministas.

No es codigo de usar-y-tirar: es el adaptador de prueba del sistema (lo usan los
tests) y la fuente con la que el MCP funciona desde el dia 1, mientras los
adaptadores reales pasan App Review (Meta), auditoria (TikTok) o se decide el
coste (X).

Cifras ancladas a la realidad del cliente (entrevista a Mariana de Leon,
estrategia digital de AMX, 2026-05-18; ordenes de magnitud de followers
contrastados en redes publicas):
- Claro Sports Mexico: ~80M visualizaciones/mes, engagement 2-3% (audiencia muy
  futbolera). Picos: Olimpicos Milano-Cortina ~150M/3%; proyeccion Mundial 2026
  ~120-150M con engagement esperado 5-6%.
- UnoTV: prioriza alcance/distribucion sobre engagement (noticias = poca
  interaccion), por eso su factor de engagement es el mas bajo.
- Nacion Gamer, Piso 15 y Fundacion: verticales menores en crecimiento.
- Claro Sports TV y Csport Golf: cuentas hermanas de Claro Sports (canal de TV y
  vertical de golf) que el equipo promociona aparte; ordenes de magnitud menores.
El engagement por marca se modula con `_ENG_FACTOR` (no todas interactuan igual).
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from keni_shared import cuentas as _cuentas
from keni_shared import marcas as _marcas

from ..schema import (
    Cobertura,
    Cuenta,
    MetricaPlataforma,
    Periodo,
    Pieza,
    Plataforma,
    ResumenMetricas,
    resolver_rango,
)
from .base import CuentaNoEncontrada, engagement_pct

# PERFILES de muestra por cuenta: cifras creibles (visualizaciones/mes, plataformas,
# tema) ancladas a la realidad de AMX. Estan KEYED por `id_metricas` (guion_bajo).
#
# Las CUENTAS que sirve la muestra ya NO se hardcodean aqui: se DERIVAN del cliente
# activo (`keni_shared.marcas`/`keni_shared.cuentas`, externalizado a config en #135;
# por defecto AMX). Este diccionario solo aporta el PERFIL de cada id; las cuentas de
# un cliente sin perfil propio caen a `_PERFIL_DEFECTO`. Asi, cambiar de cliente =
# cambiar el `.toml`, sin tocar este modulo, y la muestra sigue al catalogo.
#
# Para el cliente AMX por defecto, los perfiles cubren exactamente las 5 marcas
# editoriales (unotv, claro_sports, nacion_gamer, piso_15, fundacion) MAS las 2
# cuentas hermanas de Claro Sports (claro_sports_tv, csport_golf; el golf es un
# sub-vertical, no una marca). El guard `tests/test_muestra.py` ancla esto al catalogo.
#
# id_metricas -> (nombre, visualizaciones/mes, plataformas, tema)
_PERFILES: dict[str, tuple[str, int, list[Plataforma], str]] = {
    "claro_sports": (
        "Claro Sports",
        80_000_000,
        [Plataforma.facebook, Plataforma.instagram, Plataforma.x, Plataforma.tiktok, Plataforma.youtube],
        "deportes",
    ),
    "unotv": (
        "UnoTV",
        120_000_000,
        [Plataforma.facebook, Plataforma.instagram, Plataforma.x, Plataforma.tiktok, Plataforma.youtube],
        "noticias",
    ),
    "nacion_gamer": (
        "Nacion Gamer",
        14_000_000,
        [Plataforma.facebook, Plataforma.instagram, Plataforma.x, Plataforma.tiktok, Plataforma.youtube],
        "gaming",
    ),
    "piso_15": (
        "Piso 15",
        4_000_000,
        [Plataforma.instagram, Plataforma.x, Plataforma.tiktok, Plataforma.youtube],
        "podcast",
    ),
    "fundacion": (
        "Fundacion",
        2_500_000,
        [Plataforma.facebook, Plataforma.instagram, Plataforma.x],
        "social",
    ),
    # Cuentas hermanas de Claro Sports (el equipo de redes las promociona en su
    # reporte semanal). El canal de TV reparte parecido a Claro Sports; el
    # vertical de golf es de nicho (pocas visualizaciones, audiencia fiel).
    "claro_sports_tv": (
        "Claro Sports TV",
        12_000_000,
        [Plataforma.facebook, Plataforma.instagram, Plataforma.tiktok, Plataforma.youtube],
        "deportes",
    ),
    "csport_golf": (
        "Csport Golf",
        3_000_000,
        [Plataforma.facebook, Plataforma.instagram, Plataforma.x, Plataforma.youtube],
        "deportes",
    ),
}

# Perfil por defecto para cuentas de un cliente sin perfil propio en `_PERFILES`
# (p.ej. un cliente nuevo cargado por config): cifras medias y todas las plataformas,
# tema "social". Garantiza que la muestra responda para CUALQUIER cliente sin tocar
# codigo, sin pretender ser tan realista como los perfiles calibrados de AMX.
_PERFIL_DEFECTO: tuple[str, int, list[Plataforma], str] = (
    "",  # el nombre real lo pone la etiqueta del catalogo (ver `_MARCAS`)
    10_000_000,
    [Plataforma.facebook, Plataforma.instagram, Plataforma.x, Plataforma.tiktok, Plataforma.youtube],
    "social",
)

# `id_metricas` de las MARCAS editoriales del CLIENTE ACTIVO (sin las cuentas
# hermanas de deportes). Se DERIVA de `keni_shared.marcas` (fuente unica, ahora
# cargada de config en #135): la muestra sigue al cliente seleccionado.
IDS_METRICAS_MARCAS: frozenset[str] = frozenset(m.id_metricas for m in _marcas.MARCAS)
# Cuentas hermanas de deportes (canal de TV + sub-vertical de golf en AMX): NO son
# marcas. Derivadas tambien de la fuente unica `keni_shared.cuentas`.
IDS_CUENTAS_HERMANAS: frozenset[str] = frozenset(_cuentas.CUENTAS_DEPORTES_HERMANAS)


def _construir_marcas() -> dict[str, tuple[str, int, list[Plataforma], str]]:
    """Cuentas que sirve la muestra: las del cliente activo + sus cuentas hermanas.

    Cada id toma su perfil de `_PERFILES` (cifras AMX) o `_PERFIL_DEFECTO` si no lo
    tiene; el nombre humano sale de la etiqueta del catalogo. Para el cliente AMX por
    defecto coincide exactamente con los perfiles, asi que el comportamiento historico
    (5 marcas + 2 hermanas, con sus cifras) no cambia.

    ORDEN: primero los ids del cliente que tienen perfil curado, en el ORDEN de
    `_PERFILES` (preserva la ordenacion historica que esperaba la API, p.ej. Claro
    Sports antes que UnoTV); luego el resto de ids del cliente (sin perfil), en orden
    de catalogo. Asi cambiar de cliente no exige re-hardcodear orden en codigo.
    """
    del_cliente = {m.id_metricas for m in _marcas.MARCAS} | set(_cuentas.CUENTAS_DEPORTES_HERMANAS)
    ids: list[str] = [cid for cid in _PERFILES if cid in del_cliente]
    ids += [
        m.id_metricas for m in _marcas.MARCAS if m.id_metricas not in _PERFILES
    ]
    ids += [c for c in _cuentas.CUENTAS_DEPORTES_HERMANAS if c not in _PERFILES]

    marcas_muestra: dict[str, tuple[str, int, list[Plataforma], str]] = {}
    for cid in ids:
        if cid in marcas_muestra:
            continue
        perfil = _PERFILES.get(cid, _PERFIL_DEFECTO)
        nombre = perfil[0] or _marcas.etiqueta_por_id_metricas(cid)
        marcas_muestra[cid] = (nombre, perfil[1], list(perfil[2]), perfil[3])
    return marcas_muestra


# Cuentas servidas por la muestra (derivadas del cliente activo). Reemplaza al antiguo
# `_MARCAS` hardcodeado; se mantiene el nombre `_MARCAS` por compatibilidad con el
# resto del modulo y sus tests.
_MARCAS: dict[str, tuple[str, int, list[Plataforma], str]] = _construir_marcas()

# peso de cada plataforma en el reparto de visualizaciones
_PESO = {
    Plataforma.tiktok: 0.34,
    Plataforma.facebook: 0.24,
    Plataforma.youtube: 0.20,
    Plataforma.instagram: 0.16,
    Plataforma.x: 0.06,
}

# perfil de engagement (min%, max%) por plataforma
_ENG = {
    Plataforma.facebook: (1.0, 2.2),
    Plataforma.instagram: (3.0, 5.2),
    Plataforma.x: (0.6, 1.6),
    Plataforma.tiktok: (4.5, 9.0),
    Plataforma.youtube: (3.0, 6.0),
}

# factor de engagement por marca: no todas las audiencias interactuan igual.
# Calibrado para que Claro Sports caiga en ~2-3% combinado (cifra de Mariana) y
# UnoTV mucho mas abajo (noticias = mucho alcance, poca interaccion).
_ENG_FACTOR: dict[str, float] = {
    "claro_sports": 0.62,
    "unotv": 0.30,
    "nacion_gamer": 0.85,
    "piso_15": 0.90,
    "fundacion": 0.55,
    "claro_sports_tv": 0.60,  # misma audiencia deportiva que Claro Sports
    "csport_golf": 0.90,  # nicho de golf: pocas vistas pero audiencia fiel
}

_TITULOS: dict[str, list[str]] = {
    "deportes": [
        "Gol agónico en el último minuto",
        "El crack que rompió las redes",
        "Resumen: la jugada que nadie vio venir",
        "Polémica en el VAR: lo que dice el reglamento",
        "La declaración que incendió al vestuario",
        "Así se vivió la remontada histórica",
        "El golazo de media cancha que es viral",
        "Lo mejor de la jornada en un minuto",
    ],
    "noticias": [
        "Lo que tienes que saber esta mañana",
        "Así quedó tras el operativo",
        "La cifra que cambia todo el panorama",
        "Claves para entender la nueva medida",
        "El momento que se hizo viral",
        "Esto fue lo que pasó anoche",
        "El dato que nadie esperaba",
        "Reacción en cadena: las consecuencias",
    ],
    "gaming": [
        "El tráiler que rompió internet",
        "Lo nuevo que cambia el meta",
        "Filtración: lo que viene en el parche",
        "Reacción en vivo al gameplay",
        "El easter egg que nadie había visto",
        "Top jugadas de la semana",
        "La actualización más esperada ya tiene fecha",
        "Así se ve corriendo al máximo",
    ],
    "podcast": [
        "El momento más comentado del episodio",
        "Lo que confesó nuestro invitado",
        "El clip que se volvió tendencia",
        "La pregunta incómoda que nadie hace",
        "Un minuto que resume el episodio",
        "La anécdota que nos dejó helados",
    ],
    "social": [
        "Así cambiamos una comunidad",
        "Una historia que vale la pena contar",
        "Lo que logramos juntos este mes",
        "Voces que merecen ser escuchadas",
        "Detrás de cámaras de la jornada",
        "El antes y el después que emociona",
    ],
}

_URL_BASE = {
    Plataforma.facebook: "https://facebook.com/{cuenta}/posts/{pid}",
    Plataforma.instagram: "https://instagram.com/p/{pid}",
    Plataforma.x: "https://x.com/{cuenta}/status/{pid}",
    Plataforma.tiktok: "https://tiktok.com/@{cuenta}/video/{pid}",
    Plataforma.youtube: "https://youtube.com/watch?v={pid}",
}


def _rand(*parts) -> float:
    h = hashlib.sha256("::".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _entre(r: float, a: float, b: float) -> float:
    return a + (b - a) * r


def _pieza(
    cuenta_id: str,
    rango: str,
    plat: Plataforma,
    idx: int,
    base_mes: int,
    dias: int,
    desde: date,
    titulo: str,
) -> Pieza:
    """Construye una pieza sembrada y determinista para (cuenta, rango, plataforma, idx).

    Las "mejores piezas" baten la media de engagement de su plataforma. La semilla
    incluye la plataforma para que dos piezas con el mismo idx en plataformas
    distintas no compartan cifras.
    """
    factor = _ENG_FACTOR.get(cuenta_id, 1.0)
    eng_min, eng_max = _ENG[plat]
    eng = round(
        _entre(_rand(cuenta_id, rango, "pe", plat, idx), (eng_min + eng_max) / 2, eng_max * 1.4) * factor, 1
    )
    vistas = int(base_mes * _PESO[plat] * (dias / 30) * _entre(_rand(cuenta_id, rango, "pv", plat, idx), 0.04, 0.22))
    inter = int(vistas * eng / 100)
    dia = desde + timedelta(days=int(_rand(cuenta_id, rango, "pd", plat, idx) * dias))
    pid = hashlib.sha256(f"{cuenta_id}{rango}{plat}{idx}".encode()).hexdigest()[:11]
    return Pieza(
        id=f"p_{pid}",
        plataforma=plat,
        titulo=titulo,
        publicado=dia,
        visualizaciones=vistas,
        interacciones=inter,
        engagement_pct=eng,
        url=_URL_BASE[plat].format(cuenta=cuenta_id, pid=pid),
    )


class FuenteMuestra:
    """Implementa FuenteMetricas con datos sembrados deterministas."""

    nombre = "muestra"

    def cuentas(self) -> list[Cuenta]:
        return [
            Cuenta(id=cid, nombre=nombre, plataformas=plats)
            for cid, (nombre, _, plats, _) in _MARCAS.items()
        ]

    def _marca(self, cuenta_id: str):
        if cuenta_id not in _MARCAS:
            disponibles = ", ".join(_MARCAS)
            raise CuentaNoEncontrada(
                f"Cuenta {cuenta_id!r} no encontrada. Disponibles: {disponibles}."
            )
        return _MARCAS[cuenta_id]

    def _metrica_plataforma(
        self, cuenta_id: str, plat: Plataforma, base_mes: int, dias: int, rango: str
    ) -> MetricaPlataforma:
        # reparto entre plataformas presentes (renormalizado mas abajo por el llamador)
        vistas_mes = base_mes * _PESO[plat]
        vistas = int(vistas_mes * (dias / 30) * _entre(_rand(cuenta_id, plat, rango, "v"), 0.85, 1.15))
        eng_min, eng_max = _ENG[plat]
        factor = _ENG_FACTOR.get(cuenta_id, 1.0)
        eng = round(_entre(_rand(cuenta_id, plat, rango, "e"), eng_min, eng_max) * factor, 1)
        interacciones = int(vistas * eng / 100)
        alcance = int(vistas * _entre(_rand(cuenta_id, plat, rango, "a"), 0.55, 0.75))
        return MetricaPlataforma(
            plataforma=plat,
            visualizaciones=vistas,
            alcance=alcance,
            interacciones=interacciones,
            engagement_pct=eng,
        )

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas:
        _, base_mes, plats, _ = self._marca(cuenta_id)
        desde, hasta, dias = resolver_rango(rango)

        # renormaliza pesos entre las plataformas presentes: cada plataforma recibe
        # base_mes * (_PESO[p] / suma_pesos). Como _metrica_plataforma multiplica por
        # _PESO[p], le pasamos base_mes / suma_pesos.
        suma_pesos = sum(_PESO[p] for p in plats)
        base_norm = int(base_mes / suma_pesos)
        por_plataforma = [
            self._metrica_plataforma(cuenta_id, p, base_norm, dias, rango) for p in plats
        ]

        vis = sum(m.visualizaciones for m in por_plataforma)
        inter = sum(m.interacciones for m in por_plataforma)
        alc = sum(m.alcance for m in por_plataforma)
        eng = engagement_pct(inter, vis)
        seg = int(vis * _entre(_rand(cuenta_id, rango, "seg"), 0.0006, 0.0012))

        return ResumenMetricas(
            cuenta=cuenta_id,
            rango=rango,
            periodo=Periodo(desde=desde, hasta=hasta),
            visualizaciones=vis,
            alcance=alc,
            interacciones=inter,
            engagement_pct=eng,
            seguidores_netos=seg,
            variacion_vs_anterior={
                "visualizaciones_pct": round(_entre(_rand(cuenta_id, rango, "dv"), -8, 12), 1),
                "engagement_pct": round(_entre(_rand(cuenta_id, rango, "de"), -0.6, 0.6), 1),
            },
            por_plataforma=por_plataforma,
            fuente=self.nombre,
            # la muestra siempre "responde" en todas las plataformas de la marca:
            # cobertura completa, sin omisiones.
            cobertura=Cobertura(ok=list(plats)),
        )

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        # n negativo no tiene sentido y haria slicing raro abajo (candidatas[:n]
        # con n<0 devolveria casi todas las candidatas): lo acotamos a 0.
        n = max(n, 0)
        _, base_mes, plats, tema = self._marca(cuenta_id)
        desde, _hasta, dias = resolver_rango(rango)
        titulos = _TITULOS[tema]
        # genera un pool amplio (plataforma elegida al azar por candidata) y se
        # queda con las n mejores por engagement.
        candidatas = [
            _pieza(
                cuenta_id,
                rango,
                plats[int(_rand(cuenta_id, rango, "p", i) * len(plats))],
                i,
                base_mes,
                dias,
                desde,
                titulos[i % len(titulos)],
            )
            for i in range(max(n, 12))
        ]
        candidatas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return candidatas[:n]

    def mejores_por_plataforma(
        self, cuenta_id: str, rango: str, plataformas: list[Plataforma], n: int
    ) -> dict[Plataforma, list[Pieza]]:
        """Las n mejores piezas de CADA plataforma pedida, ordenadas por
        visualizaciones + interacciones (el criterio del reporte semanal de deportes).

        A diferencia de `mejores_piezas` (top-N global por engagement), garantiza
        hasta n piezas POR plataforma. Solo considera plataformas que la cuenta
        tiene configuradas; las demas salen con lista vacia.
        """
        n = max(n, 0)
        _, base_mes, plats, tema = self._marca(cuenta_id)
        desde, _hasta, dias = resolver_rango(rango)
        titulos = _TITULOS[tema]
        activas = set(plats)
        resultado: dict[Plataforma, list[Pieza]] = {}
        for plat in plataformas:
            if plat not in activas:
                resultado[plat] = []
                continue
            pool = [
                _pieza(cuenta_id, rango, plat, i, base_mes, dias, desde, titulos[i % len(titulos)])
                for i in range(max(n, 6))
            ]
            pool.sort(key=lambda p: p.visualizaciones + p.interacciones, reverse=True)
            resultado[plat] = pool[:n]
        return resultado
