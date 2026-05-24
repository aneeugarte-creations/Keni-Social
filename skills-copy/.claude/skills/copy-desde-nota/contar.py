#!/usr/bin/env python3
"""Cuenta caracteres (code points) del texto recibido por stdin.

Sirve para verificar límites con exactitud (X = 280, título de YouTube = 70,
cada tuit de un hilo = 280) en vez de contar a ojo.

Uso (con heredoc para no pelear con comillas/emojis):

    python3 contar.py <<'TXT'
    el texto de la variante
    TXT

Devuelve el nº de caracteres. Nota: cuenta code points; X pondera algunos emojis
y los enlaces como 23 — para esos casos trátalo como aproximación conservadora.
"""

import sys

texto = sys.stdin.read()
if texto.endswith("\n"):  # quita el salto final que añade el heredoc
    texto = texto[:-1]
print(len(texto))
