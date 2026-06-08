"""Dominio de la consola: logica de negocio PURA, sin dependencia del transporte HTTP.

Aqui vive lo que antes mezclaban los handlers de `api/*.py`: parseo del stream de
`claude`, calculo del presupuesto, derivacion del verdicto, limpieza de copy y
serializacion de entidades. Es la capa que `api/` (HTTP) y `generaciones` (background)
consumen sin crear ciclos: el dominio NUNCA importa de `api/`, y evita importar
`generaciones` salvo donde encolar una generación es intrínseco al módulo
(`generar.py` y `estudio_imagen.py`, que SON la fachada de generación del dominio).
El resto (p.ej. `copy.py`) solo lo referencia en anotaciones, bajo `TYPE_CHECKING`.
"""

from __future__ import annotations
