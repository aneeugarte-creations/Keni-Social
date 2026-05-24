# Arquitectura

Dos sistemas independientes que se complementan.

## 1. Sistema de copy (`skills-copy/`)

Agent Skills de Claude Code + contexto editorial versionado.

```
fuente (nota | clip)
   └─ copy-desde-nota
        ├─ carga: reglas-legales → tropicalizacion → plataformas → marca → voz
        ├─ produce: 1 variante por plataforma (con conteo de caracteres)
        └─ auto-verifica: fechas, nombres, cifras, legal, "¿suena mexicano?", límites
             └─ veredicto: LISTO PARA APROBAR / qué revisar
```

Separación clave: **marca** (línea editorial institucional, estable) vs **voz** (toque personal, lo rellena cada quien). La skill compone voz sobre marca sobre reglas globales.

## 2. MCP de métricas (`mcp-metricas/`)

Servidor MCP (Python/FastMCP, stdio) con una **fuente** activa:

```
tools (listar_cuentas, metricas_resumen, mejores_piezas, comparar_periodos, tendencia_historica)
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

- **Copy:** listo (sin dependencias externas).
- **MCP núcleo + fuente `muestra`:** listo y conectable.
- **Adaptadores reales:** el código está; el dato real por plataforma se habilita conforme caen los bloqueos externos — Meta App Review (semanas), auditoría de TikTok, decisión de coste de X. Ver `credenciales.md`.
