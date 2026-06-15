"""Fuente offline `muestra`: datos representativos, creibles y deterministas.

No es codigo de usar-y-tirar: es el adaptador de prueba del sistema (lo usan los
tests) y la fuente con la que el MCP funciona desde el dia 1, como respaldo
offline cuando no hay credenciales reales configuradas (las metricas reales
llegan via Metricool, `fuentes.metricool`).

Cifras ancladas a la realidad del cliente (entrevista a la coordinadora operativa,
estrategia digital del cliente, 2026-05-18; ordenes de magnitud de followers
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

from ..formato import FUENTE_MUESTRA as _FUENTE_MUESTRA
from ..schema import (
    PLATAFORMAS_CON_ALCANCE,
    Cobertura,
    Cuenta,
    MetricaPieza,
    MetricaPlataforma,
    Periodo,
    Pieza,
    Plataforma,
    PuntoSerie,
    ResumenMetricas,
    agregar_alcance,
    resolver_rango,
)
from .base import CuentaNoEncontrada, engagement_pct

# PERFILES de muestra por cuenta: cifras creibles (visualizaciones/mes, plataformas,
# tema) ancladas a la realidad del cliente. Estan KEYED por `id_metricas` (guion_bajo).
#
# Las CUENTAS que sirve la muestra ya NO se hardcodean aqui: se DERIVAN del cliente
# activo (`keni_shared.marcas`/`keni_shared.cuentas`, externalizado a config en #135;
# por defecto, el cliente base). Este diccionario solo aporta el PERFIL de cada id; las cuentas de
# un cliente sin perfil propio caen a `_PERFIL_DEFECTO`. Asi, cambiar de cliente =
# cambiar el `.toml`, sin tocar este modulo, y la muestra sigue al catalogo.
#
# Para el cliente por defecto, los perfiles cubren exactamente las 5 marcas
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
# codigo, sin pretender ser tan realista como los perfiles calibrados del cliente.
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
# Cuentas hermanas de deportes (canal de TV + sub-vertical de golf): NO son
# marcas. Derivadas tambien de la fuente unica `keni_shared.cuentas`.
IDS_CUENTAS_HERMANAS: frozenset[str] = frozenset(_cuentas.CUENTAS_DEPORTES_HERMANAS)


def _construir_marcas() -> dict[str, tuple[str, int, list[Plataforma], str]]:
    """Cuentas que sirve la muestra: las del cliente activo + sus cuentas hermanas.

    Cada id toma su perfil de `_PERFILES` (cifras reales) o `_PERFIL_DEFECTO` si no lo
    tiene; el nombre humano sale de la etiqueta del catalogo. Para el cliente por
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
# Calibrado para que Claro Sports caiga en ~2-3% combinado (cifra de la coordinadora operativa) y
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


# Formato determinista por (cuenta, plataforma, semilla): plausible por red.
# IG/FB favorecen foto/reel/carrusel; YouTube vídeo; X texto/link; TikTok reel.
_FORMATOS_POR_PLAT: dict[Plataforma, tuple[str, ...]] = {
    Plataforma.facebook: ("foto", "video", "carrusel", "link"),
    Plataforma.instagram: ("reel", "foto", "carrusel"),
    Plataforma.x: ("texto", "foto", "link"),
    Plataforma.tiktok: ("reel", "video"),
    Plataforma.youtube: ("video", "reel"),
}

# Plataformas con concepto de vídeo (video_views + tiempo medio de visualización).
_PLAT_VIDEO: frozenset[Plataforma] = frozenset(
    {Plataforma.youtube, Plataforma.tiktok, Plataforma.instagram, Plataforma.facebook}
)


def _granulares_muestra(
    cuenta_id: str, plat: Plataforma, sem: str, vistas: int, inter: int
) -> dict:
    """Desglose granular DETERMINISTA y coherente con (vistas, interacciones).

    Reparte las `inter` (total homogéneo) entre likes/comentarios/compartidos/
    guardados con pesos sembrados que SIEMPRE suman <= inter (likes son la mayoría).
    Vídeo y clics se derivan de las vistas. Sin random ni fecha actual: el mismo
    (cuenta, plataforma, semilla) da siempre los mismos números.
    """
    formato_opts = _FORMATOS_POR_PLAT.get(plat, ("foto",))
    formato = formato_opts[int(_rand(cuenta_id, plat, sem, "fmt") * len(formato_opts))]

    # Reparto de interacciones: likes dominan; comentarios/compartidos/guardados
    # son fracciones menores. Se calculan sobre inter para que el desglose cierre.
    comentarios = int(inter * _entre(_rand(cuenta_id, plat, sem, "gc"), 0.04, 0.12))
    compartidos = int(inter * _entre(_rand(cuenta_id, plat, sem, "gs"), 0.03, 0.10))
    guardados = (
        int(inter * _entre(_rand(cuenta_id, plat, sem, "gg"), 0.02, 0.08))
        if plat in (Plataforma.instagram, Plataforma.tiktok)
        else None
    )
    likes = max(inter - comentarios - compartidos - (guardados or 0), 0)

    es_video = plat in _PLAT_VIDEO and formato in ("reel", "video")
    video_views = (
        int(vistas * _entre(_rand(cuenta_id, plat, sem, "gvv"), 0.6, 0.95))
        if es_video
        else None
    )
    tiempo_medio_vis_s = (
        int(_entre(_rand(cuenta_id, plat, sem, "gtv"), 8, 45)) if es_video else None
    )
    # Clics de enlace solo en formatos con enlace (link) o redes que los miden.
    clics_enlace = (
        int(vistas * _entre(_rand(cuenta_id, plat, sem, "gcl"), 0.002, 0.02))
        if formato == "link" or plat in (Plataforma.facebook, Plataforma.x)
        else None
    )
    return {
        "likes": likes,
        "comentarios": comentarios,
        "compartidos": compartidos,
        "guardados": guardados,
        "video_views": video_views,
        "tiempo_medio_vis_s": tiempo_medio_vis_s,
        "clics_enlace": clics_enlace,
        "formato": formato,
    }


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
        # sella la marca para estratificar/normalizar top/peores por grupo marca×red.
        cuenta=cuenta_id,
        **_granulares_muestra(cuenta_id, plat, f"{rango}:{idx}", vistas, inter),
    )


class FuenteMuestra:
    """Implementa FuenteMetricas con datos sembrados deterministas."""

    # UNICA fuente de verdad del nombre: `formato.FUENTE_MUESTRA`. Los renders
    # comparan `fuente.nombre` contra ese valor para anteponer el aviso de
    # datos de muestra (issue #131), en vez de buscar el literal "muestra".
    nombre = _FUENTE_MUESTRA

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
        # solo las plataformas que realmente miden alcance (Meta) lo traen; el
        # resto AUSENTE (None), igual que los adaptadores reales (#138).
        alcance = (
            int(vistas * _entre(_rand(cuenta_id, plat, rango, "a"), 0.55, 0.75))
            if plat in PLATAFORMAS_CON_ALCANCE
            else None
        )
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
        alc = agregar_alcance(por_plataforma)  # solo suma el alcance medido (#138)
        # engagement combinado: la muestra es una fuente única y determinista, su
        # modelo de engagement por marca es coherente (calibrado a la realidad del
        # cliente); a diferencia del agregado de fuentes reales heterogéneas, aquí
        # sí es un número con significado de demo. Ver `agregador.py` para el real.
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
            # El pool sintético se acota a un máximo razonable: el llamante de stats pide
            # n enorme ("todas"), pero generar cientos de miles de piezas falsas no aporta
            # (es demo). 240 cubre de sobra top/peores y una distribución representativa.
            for i in range(min(max(n, 12), 240))
        ]
        candidatas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return candidatas[:n]

    def metricas_de_post(
        self, cuenta_id: str, plat: Plataforma, id_post: str, *, dias: int = 90
    ) -> MetricaPieza | None:
        """Rendimiento sintetico y determinista de UN post (por id) para demo/tests offline.

        Como la muestra no tiene un "almacen" de posts reales por id, deriva cifras
        creibles y ESTABLES sembrando con (cuenta, red, id): el mismo id devuelve
        siempre los mismos numeros. Asi la tarjeta del tablero pinta rendimiento
        consistente sin fuente real. `dias` se ignora (no hay ventana real). Devuelve
        None si la cuenta no existe (la marca no esta en alcance), igual que el resto.
        """
        if not id_post:
            return None
        _, base_mes, plats, _ = self._marca(cuenta_id)
        if plat not in plats:
            # La red no es de esta marca: aun asi damos una cifra estable (el post
            # pudo crearse en una red que la muestra no perfila), con peso por defecto.
            peso = _PESO.get(plat, 0.1)
        else:
            peso = _PESO[plat]
        factor = _ENG_FACTOR.get(cuenta_id, 1.0)
        eng_min, eng_max = _ENG.get(plat, (1.0, 4.0))
        eng = round(
            _entre(_rand(cuenta_id, plat, id_post, "e"), eng_min, eng_max * 1.2) * factor, 1
        )
        # Visualizaciones de UN post: una fraccion pequena del volumen mensual de la red.
        vistas = int(
            base_mes * peso * _entre(_rand(cuenta_id, plat, id_post, "v"), 0.01, 0.10)
        )
        inter = int(vistas * eng / 100)
        dia = date.today() - timedelta(
            days=int(_rand(cuenta_id, plat, id_post, "d") * 14)
        )
        return MetricaPieza(
            id_post=str(id_post),
            plataforma=plat,
            encontrado=True,
            visualizaciones=vistas,
            interacciones=inter,
            engagement_pct=eng,
            url=_URL_BASE.get(plat, "https://example.com/{pid}").format(
                cuenta=cuenta_id, pid=id_post
            ),
            publicado=dia,
            fuente=self.nombre,
            **_granulares_muestra(cuenta_id, plat, f"post:{id_post}", vistas, inter),
            # La muestra no modela atribución de seguidores a un post concreto:
            # None (igual que Metricool, que tampoco lo da a nivel post).
            seguidores_netos_atribuidos=None,
        )

    def serie_diaria(self, cuenta_id: str, rango: str) -> list[PuntoSerie]:
        """Serie diaria sintetica y determinista para demo/tests offline.

        Reparte los totales del periodo (de `resumen`) sobre los dias con un jitter
        sembrado por (cuenta, fecha), de forma estable entre ejecuciones. Permite que la
        tendencia diaria pinte algo coherente sin fuente real.
        """
        res = self.resumen(cuenta_id, rango)
        desde, hasta, dias = resolver_rango(rango)
        if dias <= 0:
            return []
        vis_dia = res.visualizaciones / dias
        int_dia = res.interacciones / dias
        puntos: list[PuntoSerie] = []
        for i in range(dias):
            f = desde + timedelta(days=i)
            fv = _entre(_rand(cuenta_id, f.isoformat(), "sv"), 0.7, 1.3)
            fi = _entre(_rand(cuenta_id, f.isoformat(), "si"), 0.7, 1.3)
            puntos.append(
                PuntoSerie(
                    fecha=f,
                    visualizaciones=int(vis_dia * fv),
                    interacciones=int(int_dia * fi),
                )
            )
        return puntos

    def serie_seguidores(self, cuenta_id: str, rango: str) -> list[dict]:
        """Stock DIARIO de followers por red, determinista (demo/tests offline).

        Modela, por cada red de la marca, una BASE de comunidad sembrada por
        (cuenta, red) y un crecimiento neto del periodo (también sembrado) repartido
        de forma estable sobre los días, de modo que el stock crezca de forma
        plausible (monótono no estricto). Sin random ni fecha actual: el mismo
        (cuenta, red, día) da siempre el mismo valor. Devuelve:

            [{"fecha": "AAAA-MM-DD", "por_red": {"instagram": 1050, ...}}, ...]

        El `total` y el `neto` los calcula el llamante (`servicio`), igual que con
        Metricool, así la muestra no duplica esa lógica.
        """
        _, base_mes, plats, _ = self._marca(cuenta_id)
        desde, hasta, dias = resolver_rango(rango)
        if dias <= 0:
            return []
        puntos: list[dict] = []
        for i in range(dias):
            f = desde + timedelta(days=i)
            por_red: dict[str, int] = {}
            for plat in plats:
                # base de comunidad por red (orden de magnitud anclado al volumen).
                base = int(base_mes * _PESO[plat] * _entre(_rand(cuenta_id, plat, "segbase"), 0.004, 0.02))
                # crecimiento neto del periodo, sembrado por (cuenta, red, rango).
                neto = int(base * _entre(_rand(cuenta_id, plat, rango, "segneto"), 0.005, 0.04))
                # reparto lineal del neto sobre los días (estable, no decreciente).
                ganado = int(neto * (i / (dias - 1))) if dias > 1 else neto
                por_red[plat.value] = base + ganado
            puntos.append({"fecha": f.isoformat(), "por_red": por_red})
        return puntos

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
