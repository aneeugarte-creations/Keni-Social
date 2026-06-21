# ADR 0002 — Monolito modular + catálogo de apps, no microservicios

El servicio se descompone por dentro como un **monolito modular organizado como un
catálogo de apps**. No microservicios: un enjambre de servicios por feature produce el
mismo enredo que un monolito, solo que distribuido y más difícil de depurar. Se extrae a
proceso aparte **solo en costuras reales**, no por feature.

Complementa a [ADR 0001](0001-runtime-servicio-compartido.md) (que fija el runtime y el
despliegue). El **agrupamiento concreto** del catálogo por unidad de producto lo fija
[ADR 0005](0005-agrupamiento-catalogo-por-unidad-de-producto.md): este ADR define el
**mecanismo** (catálogo data-driven + fronteras), 0005 define **el contenido**.

## Principios

1. **Catálogo de apps como principio de organización.** Un shell/launcher + apps
   registradas por **manifest** (`apps/<app>.toml`: ruta, icono, permisos, módulos
   backend). El catálogo y la navegación se **generan desde los manifests**, no se
   mantienen a mano: añadir una app es declarar su manifest. Es un router de apps, no N
   despliegues.

2. **Cada app = módulo autocontenido.** Ruta frontend + router backend (`api/<app>.py`)
   + su dominio/almacenamiento. Depende **solo** de `keni-shared` y de los contratos del
   gateway. **Regla de oro: nunca `app → app`.** Una necesidad cruzada se resuelve por un
   contrato/seam explícito del gateway, jamás importando las tripas de otra app.

3. **Fronteras verificadas en CI.** La disciplina de fronteras —no la topología— es lo
   que evita el mastodonte. Un lint de imports (AST, sin red ni BD) mapea cada router a
   su app vía los manifests y **falla** si un módulo importa los internals de otra app.
   Los cruces legítimos viven en una **allowlist de seams** documentada y mínima; el
   shell es la capa transversal (auth, config, media, secretos) que todas las apps pueden
   consumir, análoga a `keni-shared`.

4. **Estado compartido por la capa de datos del gateway**, no una app leyendo las tablas
   de otra. Infra compartida (capa de datos, `keni-shared`, fachada de métricas) no
   pertenece a ninguna app.

5. **El módulo es la unidad de extracción.** Si una app crece a dominio pesado, su
   frontera de módulo es la línea por la que se separa a servicio, sin reescritura.

## Deployables

Tres procesos, no N microservicios:

- **Gateway + módulos de feature** — Starlette + SPA React; el grueso, modular por dentro.
- **Worker de generación** — un servicio aparte corre `claude -p` (stream-json); el
  gateway **encola** el job y el **worker** lo ejecuta. Es la única costura nueva fuerte
  (trabajo largo, streaming); reiniciar el gateway no mata los jobs en curso. Ver
  [ADR 0001](0001-runtime-servicio-compartido.md).
- **MCP de métricas** — proceso aparte con contrato propio (stdio/HTTP).

Más infra compartida: Postgres (estado), object storage (media) y transcripción por
whisper (nunca a una API de terceros), que en el stack hosted vive en su propio worker
(faster-whisper) y en local corre directamente en la máquina (`whisper.cpp`).

Dos modos de despliegue, no un enjambre: **local/privacidad** —cada persona corre el MCP
y la transcripción (`whisper.cpp`) en su máquina, sin exponer red ni sacar datos del
equipo— y **hosted/equipo** —el stack de `deploy/docker-compose.yml`: gateway (`front` +
`back`), `worker` de generación, `transcriptor` (whisper), MCP y Postgres tras un ingress
único—.
