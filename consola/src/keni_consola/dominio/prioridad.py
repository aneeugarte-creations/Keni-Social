"""Gestor de prioridad de la cola de generacion: SOLO dos niveles.

Manual o automatico, y manual SIEMPRE gana. Nada mas: no hay niveles intermedios.

- MANUAL: lo lanza una PERSONA (API/MCP: copy, documentos, el boton "este primero" del
  Monitor, y cualquier accion humana). Se despacha SIEMPRE antes que lo automatico.
- AUTOMATICO: lo lanza la MAQUINA (pipeline de noticias, autogen, daemons, arte de fondo).

La prioridad viaja como un entero en `jobs.prioridad`; `reclamar_job` ordena por el (DESC), asi
que el trabajo manual salta al frente de lo automatico que espera, SIN tocar la mecanica de la
cola ni interrumpir lo que ya corre. A igual nivel, FIFO por antiguedad. A ojos de la economia
de tokens, AUTOMATICO es "fondo" (lo frena el corte `solo_manual`); MANUAL pasa hasta el margen.

Los valores (0 y 10) son los que ya viven en la columna `jobs.prioridad`, asi que no hace falta
migrar nada: lo automatico es `prioridad < MANUAL`, lo manual es `prioridad >= MANUAL`.
"""
from __future__ import annotations

AUTOMATICO = 0
MANUAL = 10


def nivel(*, manual: bool) -> int:
    """Nivel de despacho: MANUAL si lo lanza una persona, AUTOMATICO si lo lanza la maquina."""
    return MANUAL if manual else AUTOMATICO
