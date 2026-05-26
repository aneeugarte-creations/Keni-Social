"""Dominio de la consola: logica de negocio PURA, sin dependencia del transporte HTTP.

Aqui vive lo que antes mezclaban los handlers de `api/*.py`: parseo del stream de
`claude`, calculo del presupuesto, derivacion del verdicto, limpieza de copy y
serializacion de entidades. Es la capa que `api/` (HTTP) y `generaciones` (background)
consumen sin crear ciclos: el dominio NUNCA importa de `api/` ni de `generaciones`.
"""

from __future__ import annotations
