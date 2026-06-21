"""Tools del MCP. Se registran contra una FuenteMetricas (muestra o real)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .fuentes.base import CuentaNoEncontrada, FuenteMetricas
from .historico import Historico


def registrar(mcp: FastMCP, fuente: FuenteMetricas, historico: Historico | None = None) -> None:
    @mcp.tool()
    def listar_cuentas() -> dict:
        """Lista las cuentas/marcas de redes disponibles (UnoTV, Claro Sports, etc.)
        y sus plataformas. Usala primero para saber que se puede consultar."""
        return {
            "cuentas": [c.model_dump(mode="json") for c in fuente.cuentas()],
            "fuente": fuente.nombre,
        }

    @mcp.tool()
    def metricas_resumen(cuenta: str, rango: str = "semana") -> dict:
        """Resumen de metricas de una cuenta para un rango ('semana', 'mes', '7d' o
        '30d'): visualizaciones, alcance, engagement y variacion vs. el periodo
        anterior, con desglose por plataforma. Responde '¿como van mis metricas?'."""
        try:
            r = fuente.resumen(cuenta, rango)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}
        if historico is not None:
            historico.aplicar_variacion(r)  # variacion REAL si hay periodo anterior
            # NOTA "v1 solo lectura": esto SI escribe, pero NO a plataformas externas:
            # es un snapshot en la cache LOCAL SQLite (historico.db, por persona) que
            # alimenta la variacion y `tendencia_historica`. Es OPT-IN, controlada por
            # el flag que ya existe (`KENI_METRICAS_HISTORICO`, ver historico.py): si
            # esta desactivado, `historico` es None y no se guarda nada. Las redes
            # siguen siendo solo lectura.
            historico.guardar(r)
        return r.model_dump(mode="json")

    @mcp.tool()
    def mejores_piezas(cuenta: str, rango: str = "semana", n: int = 3) -> dict:
        """Las N piezas (piezas) con mejor desempeno de una cuenta en el rango,
        ordenadas por engagement. Util para '¿que contenido funciono mejor?'."""
        n = max(1, min(int(n), 10))
        try:
            piezas = fuente.mejores_piezas(cuenta, rango, n)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}
        respuesta: dict = {
            "cuenta": cuenta,
            "rango": rango,
            "n": n,
            "piezas": [p.model_dump(mode="json") for p in piezas],
            "fuente": fuente.nombre,
        }
        # Degradacion EXPLICITA: si alguna plataforma configurada no
        # aporto piezas (API caida, sin credenciales, presupuesto), se adjunta la
        # cobertura (mismo modelo que metricas_resumen) y una nota legible. Capacidad
        # opcional de la fuente: muestra y dobles de test no la exponen (sin nota).
        cob_fn = getattr(fuente, "cobertura_piezas", None)
        cob = cob_fn() if callable(cob_fn) else None
        if cob is not None and cob.omitidas:
            from .formato import partes_cobertura

            respuesta["cobertura"] = cob.model_dump(mode="json")
            partes = partes_cobertura(cob) or []
            respuesta["nota"] = (
                "Resultado PARCIAL: sin piezas de " + ", ".join(partes) + "."
            )
        return respuesta

    @mcp.tool()
    def comparar_periodos(cuenta: str, rango_a: str = "semana", rango_b: str = "mes") -> dict:
        """Compara las metricas de una cuenta entre dos rangos (p. ej. 'semana' vs 'mes')."""
        try:
            a = fuente.resumen(cuenta, rango_a)
            b = fuente.resumen(cuenta, rango_b)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}

        diferencia: dict = {}
        # Sin baseline (b = 0 visualizaciones) no hay % defendible: se OMITE la clave
        # en vez de devolver 0.0 (que era indistinguible de "sin variacion real").
        # Mismo patron que engagement_pct justo debajo.
        if b.visualizaciones:
            diferencia["visualizaciones_pct"] = round(
                (a.visualizaciones - b.visualizaciones) / b.visualizaciones * 100, 1
            )
        # delta de engagement en PUNTOS. Misma clave que historico.variacion y
        # variacion_vs_anterior del esquema: una sola convencion en todo el MCP.
        # Si alguno de los engagement es None (no comparable entre plataformas)
        # no hay delta defendible: se omite la clave.
        if a.engagement_pct is not None and b.engagement_pct is not None:
            diferencia["engagement_pct"] = round(a.engagement_pct - b.engagement_pct, 1)

        return {
            "cuenta": cuenta,
            "a": a.model_dump(mode="json"),
            "b": b.model_dump(mode="json"),
            "diferencia": diferencia,
        }

    @mcp.tool()
    def tendencia_historica(cuenta: str, rango: str = "semana", n: int = 8) -> dict:
        """Evolucion historica de una cuenta: las ultimas n lecturas guardadas
        (visualizaciones y engagement por periodo). Util para ver si una cuenta
        sube o baja en el tiempo. Requiere haber consultado metricas_resumen antes."""
        if historico is None:
            return {"error": "El historico no esta activado (KENI_METRICAS_HISTORICO=0)."}
        n = max(1, min(int(n), 52))
        puntos = historico.serie(cuenta, rango, n)
        if not puntos:
            return {
                "cuenta": cuenta,
                "rango": rango,
                "puntos": [],
                "nota": "Aun no hay historico para esta cuenta/rango. Consulta metricas_resumen y vuelve mas tarde.",
            }
        return {"cuenta": cuenta, "rango": rango, "puntos": puntos}

    @mcp.tool()
    def reporte_consolidado(rango: str = "mes", top: int = 3) -> dict:
        """Reporte de TODAS las marcas/verticales en un rango: total + desglose por
        marca + mejores piezas + variacion. Es el informe periodico consolidado
        (lo que antes se hacia a mano). 'rango': semana|mes|7d|30d."""
        from .reporte import construir_reporte

        top = max(1, min(int(top), 10))
        try:
            return construir_reporte(fuente, rango, top, historico)
        except ValueError as e:
            return {"error": str(e)}

    @mcp.tool()
    def picos(rango: str = "semana", umbral_pct: int = 50) -> dict:
        """Alerta proactiva de anomalías: marca piezas que despuntan muy por encima
        del engagement medio de su cuenta, y cuentas que se desvían de su baseline
        histórico (>= umbral_pct). Responde '¿qué debería estar mirando AHORA?'."""
        from .picos import detectar_picos

        try:
            return detectar_picos(fuente, rango, max(1, int(umbral_pct)), historico)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}

    @mcp.tool()
    def serie_seguidores(rango: str = "mes") -> dict:
        """Crecimiento de SEGUIDORES por día y por red en el rango: stock diario de
        followers por plataforma, total del día y neto del periodo (último − primero).
        Responde '¿cómo crece la comunidad?'. Si la fuente no expone followers,
        devuelve puntos vacíos y neto 0 (sin inventar)."""
        from . import servicio

        try:
            return servicio.serie_seguidores_desde_fuente(fuente, rango)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}

    @mcp.tool()
    def desglose_interacciones(rango: str = "mes") -> dict:
        """Desglose de ENGAGEMENT por marca×red en el rango: likes, comentarios,
        compartidos, guardados y video_views agregados, más interacciones,
        visualizaciones y engagement_pct por celda, y los totales globales. Responde
        '¿de qué se compone la interacción de cada marca/red?'."""
        from . import servicio

        try:
            return servicio.desglose_interacciones_desde_fuente(fuente, rango)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}

    @mcp.tool()
    def crosstab(rango: str = "mes") -> dict:
        """Cruce MARCA×RED×FORMATO de las piezas del rango: nº de piezas,
        visualizaciones, interacciones, engagement_pct y rendimiento relativo medio
        (vs. la mediana de su grupo) por combinación. Responde '¿qué formato rinde
        mejor en cada red y marca?'."""
        from . import servicio

        try:
            return servicio.crosstab_desde_fuente(fuente, rango)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}

    @mcp.tool()
    def correlacion_seguidores(rango: str = "mes") -> dict:
        """Correlación (NO causalidad) entre crecimiento de seguidores y
        piezas: por marca×red×día, seguidores ganados, nº de posts,
        seguidores por post y la pieza estrella del día. Incluye un caveat de
        atribución. Si no hay serie de followers, items vacío y la nota lo explica."""
        from . import servicio

        try:
            return servicio.correlacion_seguidores_desde_fuente(fuente, rango)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}

    @mcp.tool()
    def analisis_diario(rango: str = "semana", marca: str = "") -> dict:
        """Lectura accionable del periodo: NO solo cifras, sino qué subió/bajó, la(s)
        pieza(s) que lo explican y el siguiente paso ("pide copy/clip de lo que
        rinde"). Ensambla comparar_periodos + picos + mejores_piezas en una
        narrativa corta. Marca cuando los datos son de muestra. Responde el día a
        día de '¿qué números tuvimos y por qué, y qué hago con eso?'."""
        from .analisis_diario import construir_analisis

        try:
            return construir_analisis(fuente, rango, marca or None, historico)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}
