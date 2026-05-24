# Arquitectura

Dos sistemas independientes que se complementan.

## 1. Sistema de copy (`skills-copy/`)

Agent Skills de Claude Code + contexto editorial versionado.

```
fuente (nota escrita)            fuente (video | audio)
   └─ copy-desde-nota                └─ clip-a-copy
        │                                  ├─ transcribe en LOCAL (whisper.cpp; el audio no sale de la máquina)
        │                                  ├─ saca citas con marca de tiempo (puntos de corte del clip)
        │                                  └─ ↓ (mismo contexto editorial y verificación)
        ├─ carga: reglas-legales → tropicalizacion → plataformas → marca → voz
        ├─ produce: 1 variante por plataforma (con conteo de caracteres)
        └─ auto-verifica: fechas, nombres, cifras, legal, "¿suena mexicano?", límites
             └─ veredicto: LISTO PARA APROBAR / qué revisar
```

Separación clave: **marca** (línea editorial institucional, estable) vs **voz** (toque personal, lo rellena cada quien). La skill compone voz sobre marca sobre reglas globales.

`clip-a-copy` añade el caso "mete el video y dame el copy": transcribe el material en local y trata el texto de ASR como **no verificado** (nombres, cifras y citas se marcan para confirmar contra el audio). Comparte el mismo contexto editorial y la misma auto-verificación que `copy-desde-nota`.

## 2. MCP de métricas (`mcp-metricas/`)

Servidor MCP (Python/FastMCP, stdio) con una **fuente** activa:

```
tools (listar_cuentas, metricas_resumen, mejores_piezas, comparar_periodos,
       tendencia_historica, reporte_consolidado, picos)
   ├─ FuenteMetricas
   │    ├─ FuenteMuestra        (datos offline deterministas; default)
   │    └─ FuenteCompuesta      (real)
   │         └─ un AdaptadorPlataforma por red, tras una interfaz común:
   │            meta · youtube · x · tiktok   (degradan si no hay credenciales)
   └─ Historico (SQLite local)  guarda cada lectura → variación real vs. periodo
        anterior + serie temporal (tendencia_historica). Local por persona.
```

Añadir una plataforma = un adaptador nuevo, sin tocar las tools. El esquema (`schema.py`) normaliza todas las redes a la misma forma.

Ejecución **local por persona**, credenciales en la máquina de cada quien (ver `credenciales.md`).

## Cómo encajan

`copy-desde-nota` puede consultar `mejores_piezas` del MCP para ajustar el tono a lo que funcionó (paso opcional con degradación: si el MCP no está, se omite). Así el sistema que **produce** aprende del que **mide**, sin acoplarse: cada uno funciona solo.

## Estado / hitos

- **Copy (texto):** listo (sin dependencias externas).
- **Copy desde video/audio (`clip-a-copy`):** listo; requiere whisper.cpp + ffmpeg + modelo en local (Mac Apple Silicon), todo gratis y sin nube. Ver `despliegue-local.md`.
- **MCP núcleo + fuente `muestra`:** listo y conectable. Cifras de `muestra` ancladas a la entrevista de estrategia (Claro Sports ~80M vis/mes 2-3%; UnoTV alto alcance, bajo engagement).
- **Adaptadores reales:** el código está; el dato real por plataforma se habilita conforme caen los bloqueos externos — Meta App Review (semanas), auditoría de TikTok, decisión de coste de X. Ver `credenciales.md`.
