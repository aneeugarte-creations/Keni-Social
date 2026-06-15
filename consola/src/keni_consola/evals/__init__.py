"""Harness de EVALS de calidad de la salida de IA (la red de regresión que faltaba).

PROBLEMA QUE CIERRA
===================
La propuesta de valor de keni-social es "auto-verificación / más IA hacia adentro": el
sistema genera copy y lo filtra para que el humano solo DECIDA. Pero los prompts de la
Biblioteca son EDITABLES EN VIVO (pestaña «Prompts», `libtexto`) sin ninguna red de
regresión: con varios agentes (+ el humano) tocándolos en paralelo, un cambio que degrade
voz / tono / formato se despliega sin que NADA lo cace. Este paquete es esa red: un set de
CASOS GOLDEN versionados + un RUNNER determinista que contrasta cada copy candidato contra
la MISMA maquinaria de verificación que corre en producción.

QUÉ ES Y QUÉ NO ES
==================
- ES: infraestructura ejecutable + casos SEMILLA realistas, barata y apta para CI (cero
  `claude -p`: reutiliza el lint determinista de `patrones_marca`, el gate de calidad
  advisory de `pipeline_contenido._revisar` y los límites técnicos de `keni_shared`).
- NO ES: un juez de calidad EDITORIAL definitivo. Los casos "de oro" definitivos los
  aporta la mesa del cliente; aquí van casos semilla para que el harness
  sea ejecutable y útil desde ya. NO sustituye la revisión humana (el principio rector es
  precisamente "humano decide qué se publica"); es el cinturón que evita que una edición de
  prompt rompa lo medible sin avisar.

CAPAS / REUSO (no se reinventa la verificación, se ENVUELVE)
===========================================================
- `patrones_marca.verificar_pieza`  -> dimensión VOZ (longitud/emojis/hashtags/gancho/
  pregunta contra el perfil real medido de la marca). El MISMO lint del post-procesado.
- `pipeline_contenido._revisar.avisos_coherencia` -> dimensión COHERENCIA (solapamiento
  léxico copy↔nota de origen; caza alucinaciones / pieza cruzada).
- `keni_shared.limites_plataforma.limite_de` + `dominio.copy._tramos_publicables` ->
  dimensión LÍMITE (tope técnico duro por red, por tramo de hilo/carrusel).
- `redes.es_red` / `marcas.es_marca` -> validación del catálogo de cada caso.

El runner es PURO y determinista (no toca BD ni red; el perfil de patrones se lee de disco).
Hook `evals.juez` documentado para evals "live" (generar copy real con el modelo / juez LLM),
FUERA de CI. Ver `consola/evals/README.md`.
"""

from __future__ import annotations

from .modelo import (
    CasoEval,
    ReporteEvals,
    ResultadoCaso,
    ResultadoDimension,
    cargar_casos,
    dir_casos_por_defecto,
)
from .runner import correr_casos, correr_directorio

__all__ = [
    "CasoEval",
    "ResultadoDimension",
    "ResultadoCaso",
    "ReporteEvals",
    "cargar_casos",
    "dir_casos_por_defecto",
    "correr_casos",
    "correr_directorio",
]
