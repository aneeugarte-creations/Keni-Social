"""Modelo de datos del harness de evals: CASO golden, RESULTADO por dimensión/caso, REPORTE.

Un CASO es un fichero YAML versionado bajo `consola/evals/casos/` (uno por escenario):

    id: unotv-fb-ok-detencion
    descripcion: "Nota policial sobria, dentro de patrón UnoTV en Facebook."
    marca: unotv            # id canónico (slug-guion), validado contra el catálogo
    red: facebook           # id de red canónico
    fuente: |               # OPCIONAL: nota/insumo de origen (para la coherencia léxica)
      La Fiscalía de Jalisco informó la detención de un presunto responsable...
    copy: |                 # copy CANDIDATO a evaluar
      El presunto responsable fue detenido, informó la Fiscalía de Jalisco...
    espera: pasa            # dictamen esperado del caso: pasa | falla
    # --- refinamientos OPCIONALES de la rúbrica ---
    prohibidos: ["culpable", "delincuente"]   # términos vetados (editorial); su presencia FALLA
    falla_esperada_en: voz                    # si espera=falla, qué dimensión DEBE cazarlo
    dimensiones: [limite_red, voz, coherencia, prohibidos, idioma]  # subconjunto a correr

La rúbrica se expresa con CHECKS DETERMINISTAS (sin coste de IA), uno por DIMENSIÓN
(`checks.DIMENSIONES`). El dictamen del caso es `falla` si CUALQUIER dimensión falla, si no
`pasa`. El runner compara ese dictamen con `espera`: un caso "cuadra" cuando coinciden.

PURO: este módulo solo parsea/valida YAML; no corre checks ni toca BD/red.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Dictámenes posibles de un caso (y de la expectativa declarada).
PASA = "pasa"
FALLA = "falla"

# Estados de una dimensión: ok (limpio), falla (avisos), na (no aplica a este caso).
ESTADO_OK = "ok"
ESTADO_FALLA = "falla"
ESTADO_NA = "na"


@dataclass(frozen=True)
class CasoEval:
    """Un caso golden cargado y validado. Inmutable (los casos no se mutan al correr)."""

    id: str
    marca: str
    red: str
    copy: str
    espera: str = PASA
    descripcion: str = ""
    fuente: str = ""
    prohibidos: tuple[str, ...] = ()
    falla_esperada_en: str = ""
    dimensiones: tuple[str, ...] = ()  # vacío = todas las aplicables
    ruta: str = ""  # fichero de origen (para mensajes de error)


@dataclass(frozen=True)
class ResultadoDimension:
    """Resultado de UNA dimensión sobre un caso: estado + avisos legibles."""

    nombre: str
    estado: str
    avisos: tuple[str, ...] = ()

    @property
    def fallo(self) -> bool:
        return self.estado == ESTADO_FALLA


@dataclass
class ResultadoCaso:
    """Resultado de un caso: dimensiones + dictamen efectivo + si cuadra con lo esperado."""

    caso: CasoEval
    dimensiones: list[ResultadoDimension] = field(default_factory=list)

    @property
    def dictamen(self) -> str:
        return FALLA if any(d.fallo for d in self.dimensiones) else PASA

    @property
    def dimensiones_fallidas(self) -> list[str]:
        return [d.nombre for d in self.dimensiones if d.fallo]

    @property
    def cuadra(self) -> bool:
        """True si el dictamen coincide con `espera` Y (si se declaró) lo cazó la dimensión
        esperada. Así un caso "debe fallar" no cuadra por casualidad si falla por otra razón."""
        if self.dictamen != self.caso.espera:
            return False
        objetivo = self.caso.falla_esperada_en
        if self.caso.espera == FALLA and objetivo:
            return objetivo in self.dimensiones_fallidas
        return True


@dataclass
class ReporteEvals:
    """Reporte agregado de una corrida del harness sobre un set de casos."""

    resultados: list[ResultadoCaso] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.resultados)

    @property
    def cuadran(self) -> int:
        return sum(1 for r in self.resultados if r.cuadra)

    @property
    def discrepancias(self) -> list[ResultadoCaso]:
        return [r for r in self.resultados if not r.cuadra]

    @property
    def score(self) -> float:
        """Fracción [0,1] de casos cuyo dictamen cuadra con la expectativa golden."""
        return (self.cuadran / self.total) if self.total else 1.0

    def a_dict(self) -> dict[str, Any]:
        """Forma serializable (para `--json` y para tests/CI)."""
        return {
            "total": self.total,
            "cuadran": self.cuadran,
            "score": round(self.score, 4),
            "casos": [
                {
                    "id": r.caso.id,
                    "marca": r.caso.marca,
                    "red": r.caso.red,
                    "espera": r.caso.espera,
                    "dictamen": r.dictamen,
                    "cuadra": r.cuadra,
                    "dimensiones": [
                        {"nombre": d.nombre, "estado": d.estado, "avisos": list(d.avisos)}
                        for d in r.dimensiones
                    ],
                }
                for r in self.resultados
            ],
        }


class ErrorCaso(ValueError):
    """Un caso YAML mal formado (campo obligatorio ausente, tipo inválido, etc.)."""


def dir_casos_por_defecto() -> Path:
    """Directorio de casos golden: `KENI_EVALS_DIR` si está, si no `consola/evals/casos`.

    Se resuelve relativo a este fichero (checkout de fuente), que es donde corre el harness
    (CI y local; los casos viajan en el repo, no en el wheel)."""
    env = os.environ.get("KENI_EVALS_DIR")
    if env:
        return Path(env).expanduser()
    # .../consola/src/keni_consola/evals/modelo.py -> parents[3] == consola/
    return Path(__file__).resolve().parents[3] / "evals" / "casos"


def _lista_str(valor: object) -> tuple[str, ...]:
    """Normaliza un campo de lista a tupla de strings no vacíos (tolerante: '' o None -> ())."""
    if valor is None:
        return ()
    if isinstance(valor, str):
        return (valor.strip(),) if valor.strip() else ()
    if isinstance(valor, (list, tuple)):
        return tuple(str(x).strip() for x in valor if str(x).strip())
    raise ErrorCaso(f"se esperaba lista o string, no {type(valor).__name__}")


def caso_de_dict(datos: dict[str, Any], *, ruta: str = "") -> CasoEval:
    """Construye y VALIDA un `CasoEval` desde el dict del YAML. Lanza `ErrorCaso` si falta
    un obligatorio o un tipo no cuadra (un typo en un caso debe romper, no pasar en silencio)."""
    if not isinstance(datos, dict):
        raise ErrorCaso(f"{ruta}: el caso debe ser un mapeo YAML, no {type(datos).__name__}")
    faltan = [k for k in ("id", "marca", "red", "copy") if not str(datos.get(k) or "").strip()]
    if faltan:
        raise ErrorCaso(f"{ruta}: faltan campos obligatorios: {', '.join(faltan)}")
    espera = str(datos.get("espera") or PASA).strip().lower()
    if espera not in (PASA, FALLA):
        raise ErrorCaso(f"{ruta}: 'espera' debe ser '{PASA}' o '{FALLA}', no {espera!r}")
    return CasoEval(
        id=str(datos["id"]).strip(),
        marca=str(datos["marca"]).strip(),
        red=str(datos["red"]).strip(),
        copy=str(datos["copy"]),
        espera=espera,
        descripcion=str(datos.get("descripcion") or "").strip(),
        fuente=str(datos.get("fuente") or ""),
        prohibidos=_lista_str(datos.get("prohibidos")),
        falla_esperada_en=str(datos.get("falla_esperada_en") or "").strip(),
        dimensiones=_lista_str(datos.get("dimensiones")),
        ruta=ruta,
    )


def cargar_casos(directorio: Path | str | None = None) -> list[CasoEval]:
    """Carga TODOS los casos `.yaml`/`.yml` de `directorio` (def `dir_casos_por_defecto`).

    Orden estable por id. Un fichero ilegible o un caso inválido LANZA `ErrorCaso` (el harness
    no se traga casos rotos: un caso que no carga es una regresión del set, no un caso que pasa).
    Soporta un fichero con UN caso (mapeo) o con VARIOS (lista de mapeos)."""
    base = Path(directorio) if directorio is not None else dir_casos_por_defecto()
    if not base.is_dir():
        raise ErrorCaso(f"directorio de casos inexistente: {base}")
    casos: list[CasoEval] = []
    vistos: set[str] = set()
    for ruta in sorted([*base.glob("*.yaml"), *base.glob("*.yml")]):
        try:
            cargado = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ErrorCaso(f"{ruta}: YAML ilegible: {exc}") from exc
        if cargado is None:
            continue
        documentos = cargado if isinstance(cargado, list) else [cargado]
        for doc in documentos:
            caso = caso_de_dict(doc, ruta=str(ruta))
            if caso.id in vistos:
                raise ErrorCaso(f"{ruta}: id de caso duplicado: {caso.id!r}")
            vistos.add(caso.id)
            casos.append(caso)
    return sorted(casos, key=lambda c: c.id)
