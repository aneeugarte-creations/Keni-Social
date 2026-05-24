# keni-social

Sistemas de producción de Keni para equipos de redes sociales. Dos componentes independientes pero complementarios:

| Carpeta | Qué es | Estado |
|---|---|---|
| [`mcp-metricas/`](mcp-metricas/) | Servidor **MCP** que lee métricas de redes (Meta FB/IG, YouTube, X, TikTok), multi-marca, y las expone a Claude. Corre **local por persona** con sus propias credenciales. | Núcleo + fuente `muestra` listos; adaptadores reales escalonados por App Review/auditoría. |
| [`skills-copy/`](skills-copy/) | **Agent Skills** de Claude Code + contexto editorial versionado, que convierten una nota o transcripción en copy publicable (voz de marca + tropicalización mexicana + formato por plataforma + auto-verificación). | Listo para usar. |

Diseñado primero para el equipo de **AMX Contenido** (UnoTV / Claro Sports) y reutilizable para otros clientes de Keni.

## Por dónde empezar

- **Generar copy:** ver [`skills-copy/README.md`](skills-copy/README.md).
- **Conectar métricas a Claude:** ver [`mcp-metricas/README.md`](mcp-metricas/README.md).
- **Credenciales y despliegue local:** ver [`docs/`](docs/).

## Instalación como plugin

La forma más sencilla de tener todo (las skills de copy + las métricas) es instalar `keni-social` como **plugin de Claude Code** desde el marketplace privado de Keni. Son **dos comandos**, dentro de Claude Code, sin permisos de administrador.

1. Añade el marketplace de Keni (solo la primera vez):

   ```
   /plugin marketplace add kenitech-io/keni-social
   ```

2. Instala el plugin:

   ```
   /plugin install keni-social@keni
   ```

Listo. Cierra y vuelve a abrir Claude Code (o ejecuta `/reload-plugins`). Después de instalarlo tendrás disponibles las cuatro skills de copy, con el nombre del plugin por delante:

- `/keni-social:copy-desde-nota` — de una o varias notas/cables (o una transcripción) a copy publicable por plataforma.
- `/keni-social:clip-a-copy` — de un video/audio a copy (transcribe en local).
- `/keni-social:resumen-tendencia` — brief corto de un tema: qué pasa, ángulo por marca y riesgos legales.
- `/keni-social:nota-a-formato` — normaliza una nota cruda al estilo editorial de la casa.

> Las skills de copy funcionan solas. El servidor de **métricas** (`keni-metricas`) viene declarado en el plugin pero necesita `uv`/`uvx` en la máquina para arrancar y, para datos reales, credenciales locales. Ver [`mcp-metricas/README.md`](mcp-metricas/README.md) y [`docs/credenciales.md`](docs/credenciales.md). El cableado de ejemplo del servidor está en [`.mcp.json`](.mcp.json).

### Actualizar

Cuando Keni publique una versión nueva, actualízala con:

```
/plugin marketplace update keni
```

### Repositorio privado

`kenitech-io/keni-social` es privado. Para que `/plugin marketplace add` funcione tienes que tener acceso al repo y estar autenticado con GitHub (por ejemplo `gh auth login`). Pídele acceso a Keni si el comando falla con un error de permisos.

## Principio

La IA produce; el humano aprueba. El copy sale con una **auto-verificación** que dice cuándo creerle, y las métricas se leen con **credenciales locales y revocables** (la llave vive en tu máquina, no en la IA).
