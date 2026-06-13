"""Andamiaje del JUEZ LLM y su CALIBRACIÓN (modo "live", FUERA de CI).

Los checks deterministas (`checks.py`) cazan lo MEDIBLE (longitud, emojis, hashtags, voz por
patrones, coherencia léxica, idioma). Lo que NO cazan es la calidad EDITORIAL fina: ¿el copy
es plano/genérico?, ¿tiene gancho real?, ¿la tropicalización MX suena natural?, ¿hay una
alucinación sutil? Eso lo juzga hoy un humano —y, opcionalmente, el crítico LLM de producción
(`dominio.critica_ia`, con visión, gateado por `KENI_CRITICA_IA`)—.

Este módulo NO corre en CI (cuesta dinero y no es determinista). Es el HOOK documentado para:

  1. EVALS LIVE: generar copy REAL con `claude -p` desde la nota de origen de un caso y luego
     pasarle los checks deterministas. Mide la regresión de extremo a extremo (prompt incluido),
     no solo de un copy fijo. Se invoca con un ejecutor inyectado (ver `generar_copy_live`).

  2. CALIBRACIÓN DEL JUEZ: medir cuánto COINCIDE el juez LLM con la etiqueta humana del caso
     (`espera`). Sin acuerdo medido, un "juez IA" es fe ciega. `acuerdo_con_humano` calcula ese
     acuerdo sobre un mini-set etiquetado (de momento, los propios casos semilla con su `espera`
     como proxy de etiqueta humana; cuando AMX aporte etiquetas finas se sustituyen).

Honestidad: hoy esto es ANDAMIAJE. El juez real (`critica_ia`) vota sobre una PUBLICACIÓN ya
en BD con su arte; reaprovecharlo aquí pide refactor para juzgar texto suelto. Se deja la
interfaz + el cálculo de acuerdo listos para enchufar ese juez (o un prompt de juez dedicado)
en cuanto haya etiquetas reales. NADA de esto se importa desde el runner determinista.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .modelo import FALLA, PASA, CasoEval

# Un juez: dado (caso) devuelve su veredicto ('pasa'/'falla'). Puede ser un wrapper de
# `claude -p`, del crítico de producción, o un fake en tests.
Juez = Callable[[CasoEval], str]

# Ejecutor de generación live: (prompt, dir_permitido) -> salida. MISMA firma que los
# ejecutores de `dominio.traduccion` / `clasificador_marca`, para reusar el subproceso real.
EjecutorLLM = Callable[[str, str], str]


@dataclass
class AcuerdoJuez:
    """Resultado de calibrar un juez contra las etiquetas humanas de un set de casos."""

    total: int
    aciertos: int
    falsos_positivos: int  # juez dijo 'pasa' donde el humano dijo 'falla' (lo PEOR: deja pasar basura)
    falsos_negativos: int  # juez dijo 'falla' donde el humano dijo 'pasa' (ruido: molesta al equipo)

    @property
    def acuerdo(self) -> float:
        return (self.aciertos / self.total) if self.total else 1.0


def acuerdo_con_humano(juez: Juez, casos: list[CasoEval]) -> AcuerdoJuez:
    """Mide el acuerdo de `juez` con la etiqueta humana (`caso.espera`) sobre `casos`.

    Es la pieza de CALIBRACIÓN: un juez solo es fiable si su acuerdo es alto y, sobre todo, si
    sus FALSOS POSITIVOS (deja pasar lo que el humano rechaza) son ~0. Con los casos semilla el
    número es orientativo (la etiqueta es la `espera` del propio caso); con etiquetas reales de
    AMX se vuelve una métrica de verdad. PURO: no llama al modelo, solo aplica el juez dado."""
    aciertos = fp = fn = 0
    for caso in casos:
        veredicto = (juez(caso) or "").strip().lower()
        humano = caso.espera
        if veredicto == humano:
            aciertos += 1
        elif veredicto == PASA and humano == FALLA:
            fp += 1
        elif veredicto == FALLA and humano == PASA:
            fn += 1
    return AcuerdoJuez(total=len(casos), aciertos=aciertos, falsos_positivos=fp, falsos_negativos=fn)


def generar_copy_live(caso: CasoEval, ejecutor: EjecutorLLM) -> str:
    """HOOK de evals LIVE: genera copy REAL para la nota de origen del caso con `ejecutor`.

    NO se implementa el ensamblado del prompt aquí para no duplicar `dominio.generar` /
    `biblioteca`: cuando se cablee, debe componer el prompt EXACTAMENTE como producción
    (Biblioteca de Prompts + contexto editorial de la marca) y devolver la salida cruda para
    pasarla por los checks deterministas. De momento es un punto de extensión explícito."""
    raise NotImplementedError(
        "evals live: cablear el ensamblado de prompt de producción (biblioteca + voz de marca) "
        "y reusar el ejecutor de claude -p. Ver consola/evals/README.md §Modo live."
    )
