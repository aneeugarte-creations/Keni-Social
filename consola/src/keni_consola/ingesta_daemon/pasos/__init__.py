"""Pasos del barrido de ingesta (cada uno independiente y best-effort).

El orquestador (`ingesta_daemon._bucle.ejecutar_barrido`) los invoca a través del facade
(`ingesta_daemon.paso_*`) para que el parcheo en tests siga surtiendo efecto.
"""
