"""Persistencia local del historico de lecturas (SQLite).

Cada vez que se consulta `metricas_resumen`, se guarda un snapshot. Con dos o mas
lecturas de periodos distintos se calcula la variacion REAL vs. el periodo
anterior, y la tool `tendencia_historica` devuelve la evolucion.

Vive en `~/.local/share/keni-metricas/historico.db` (o `KENI_METRICAS_DB`).
Es local por persona, como las credenciales.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .schema import ResumenMetricas

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS lecturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cuenta TEXT NOT NULL,
    rango TEXT NOT NULL,
    periodo_desde TEXT NOT NULL,
    periodo_hasta TEXT NOT NULL,
    visualizaciones INTEGER,
    alcance INTEGER,
    interacciones INTEGER,
    engagement_pct REAL,
    seguidores_netos INTEGER,
    fuente TEXT,
    por_plataforma TEXT
);
CREATE INDEX IF NOT EXISTS idx_lecturas_cuenta_rango
    ON lecturas(cuenta, rango, periodo_hasta);
"""


def ruta_db() -> Path:
    if (p := os.environ.get("KENI_METRICAS_DB")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "keni-metricas" / "historico.db"


def historico_activo() -> bool:
    return os.environ.get("KENI_METRICAS_HISTORICO", "1") not in ("0", "false", "no")


def variacion(actual: ResumenMetricas, vis_anterior: int, eng_anterior: float) -> dict[str, float]:
    """Delta vs. periodo anterior: visualizaciones en %, engagement en puntos."""
    return {
        "visualizaciones_pct": round((actual.visualizaciones - vis_anterior) / vis_anterior * 100, 1)
        if vis_anterior
        else 0.0,
        "engagement_pct": round(actual.engagement_pct - eng_anterior, 1),
    }


class Historico:
    def __init__(self, ruta: Path | str | None = None):
        self.ruta = Path(ruta) if ruta else ruta_db()
        if str(self.ruta) != ":memory:":
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self.ruta))
        self._con.row_factory = sqlite3.Row
        self._con.executescript(_ESQUEMA)

    def guardar(self, r: ResumenMetricas) -> None:
        self._con.execute(
            """INSERT INTO lecturas (ts, cuenta, rango, periodo_desde, periodo_hasta,
                   visualizaciones, alcance, interacciones, engagement_pct,
                   seguidores_netos, fuente, por_plataforma)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                r.cuenta,
                r.rango,
                r.periodo.desde.isoformat(),
                r.periodo.hasta.isoformat(),
                r.visualizaciones,
                r.alcance,
                r.interacciones,
                r.engagement_pct,
                r.seguidores_netos,
                r.fuente,
                json.dumps([m.model_dump(mode="json") for m in r.por_plataforma]),
            ),
        )
        self._con.commit()

    def periodo_anterior(
        self, cuenta: str, rango: str, antes_de: date
    ) -> sqlite3.Row | None:
        """Ultima lectura de un periodo estrictamente anterior (para la variacion)."""
        cur = self._con.execute(
            """SELECT * FROM lecturas
               WHERE cuenta=? AND rango=? AND periodo_hasta < ?
               ORDER BY periodo_hasta DESC, id DESC LIMIT 1""",
            (cuenta, rango, antes_de.isoformat()),
        )
        return cur.fetchone()

    def serie(self, cuenta: str, rango: str, n: int) -> list[dict]:
        """Ultimos n periodos (una lectura por periodo, la mas reciente), cronologico."""
        cur = self._con.execute(
            """SELECT periodo_hasta, visualizaciones, engagement_pct, fuente
               FROM lecturas
               WHERE cuenta=? AND rango=? AND id IN (
                   SELECT MAX(id) FROM lecturas WHERE cuenta=? AND rango=? GROUP BY periodo_hasta
               )
               ORDER BY periodo_hasta DESC LIMIT ?""",
            (cuenta, rango, cuenta, rango, n),
        )
        filas = [dict(row) for row in cur.fetchall()]
        filas.reverse()  # cronologico ascendente
        return filas

    def aplicar_variacion(self, r: ResumenMetricas) -> ResumenMetricas:
        """Si hay periodo anterior, sustituye variacion_vs_anterior por la real."""
        ant = self.periodo_anterior(r.cuenta, r.rango, r.periodo.hasta)
        if ant is not None:
            r.variacion_vs_anterior = variacion(r, ant["visualizaciones"], ant["engagement_pct"])
        return r

    def close(self) -> None:
        self._con.close()
