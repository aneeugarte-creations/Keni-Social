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

## Principio

La IA produce; el humano aprueba. El copy sale con una **auto-verificación** que dice cuándo creerle, y las métricas se leen con **credenciales locales y revocables** (la llave vive en tu máquina, no en la IA).
