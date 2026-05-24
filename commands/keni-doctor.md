---
description: Corre el autodiagnóstico del entorno de métricas y explica en claro cada ❌ y cómo arreglarlo. Solo lectura.
allowed-tools: Bash(uvx *) Bash(uv *) Bash(python -m keni_metricas.doctor *) Bash(python -m keni_metricas.asistente --validar *) Bash(python -m keni_metricas.asistente --solo-mostrar *) Bash(uv --version) Bash(uvx --version) Bash(python --version)
---

# Autodiagnóstico del entorno (keni-metricas)

Comprueba que el entorno de **métricas** está listo (intérprete, `uv`/`uvx`,
configuración y conectividad), y traduce cada fallo a una frase entendible con el
paso para arreglarlo.

Esto es **solo lectura**: no escribe configuración, no toca la red salvo una llamada
de prueba de conectividad, y nunca publica.

## Qué hacer

1. Intenta el autodiagnóstico dedicado si existe en este entorno:

   ```
   python -m keni_metricas.doctor
   ```

2. Si ese módulo no existe (error de import), haz el chequeo equivalente, sin
   escribir nada:
   - Versión de Python: `python --version`
   - `uv`/`uvx` disponibles: `uv --version` y `uvx --version`
   - Configuración y conectividad (prueba de lectura por plataforma con token):
     `python -m keni_metricas.asistente --validar`
     (si el usuario aún no tiene config, usa `--solo-mostrar` para no escribir nada).

3. Resume el resultado como una lista de checks. Para cada **❌**:
   - Di en una frase qué falta o falla.
   - Da el paso exacto para arreglarlo (instalar `uv`, correr
     `/keni-social:keni-doctor` de nuevo, o lanzar el asistente de configuración
     con `python -m keni_metricas.asistente`).

No ejecutes acciones correctivas tú; solo diagnostica y explica.
