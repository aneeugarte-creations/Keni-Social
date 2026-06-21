# ADR 0003 — Cerrojo por rol sobre secretos y estado globales

El servicio hosted es multiusuario con atribución de autor, pero los secretos
(clave del proveedor de imagen, tokens de redes) y el estado operacional viven en
un único almacén compartido por despliegue. Sobre esa superficie sensible rige un
cerrojo por **rol**.

## Modelo de seguridad

El cerrojo por rol es **consecuencia** de cómo se guardan los secretos hoy —globales
por despliegue, compartidos por todo el equipo—, no un principio de que un editor
jamás deba tocar un secreto. Mientras esa premisa se mantenga, la superficie sensible
se cierra tras admin; si los secretos pasaran a ser por persona o por marca, este
modelo se reabre (ver "Revisar cuando").

- **Mientras los secretos sean globales por despliegue, se cierran tras el rol
  admin.** Todo `/api/conexiones/*` —lectura y mutación de la clave de imagen y de
  los tokens de redes— exige sesión de un usuario admin real. Bajo esa premisa un
  `editor` recibe 403 y no ve ni la presencia/pista del secreto: como el secreto es
  común a todo el despliegue, exponerlo a un rol cualquiera lo expondría a todos. Los
  consumen los servicios (la clave la usa la generación de imagen; los tokens, el MCP
  de métricas), no el editor.

- **La gestión de usuarios se cierra tras el flag `superadmin`.** Crear, editar o
  borrar cuentas exige el flag `superadmin`, ortogonal al rol: un admin normal
  conserva sus poderes pero no entra a Usuarios.

- **El token de mantenimiento no concede poder admin (decisión actual, revisable).**
  El token interino pasa la barrera de `/api` como credencial de mantenimiento, pero
  hoy no otorga poder admin sobre usuarios ni secretos: ahí también recibe 403. Es
  una elección deliberada para que la credencial de mantenimiento no sea una vía
  paralela a admin, no una línea roja eterna. La única excepción acotada es el
  bootstrap del primer admin con la base vacía.

- **Fuente única de la decisión de rol.** La pregunta "¿es admin?" / "¿es
  superadmin?" vive en `keni_consola.permisos`; `conexiones`, `usuarios` y `rota`
  comparten ese contrato. El helper solo **lee** el `request.state` que el
  middleware de seguridad ya fija (sesión + CSRF intactos); no abre ninguna vía de
  auth nueva.

- **Los secretos nunca salen al navegador.** La API reporta a lo sumo presencia y
  una pista con los últimos caracteres; la clave entera no se loguea ni se devuelve.
  El almacén local nace con permisos `0600`.

## Aislamiento por tenant

El estado compartido del equipo es el comportamiento deseado mientras cada cliente
va en su propio despliegue (un tenant por instancia). El aislamiento real por
tenant —secretos y estado **separados por cliente** en vez de un almacén global,
con filtro en la capa de datos para que ningún handler pueda saltárselo— es el
camino de crecimiento cuando convivan varios clientes en un mismo despliegue.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- Convivan dos o más clientes/marcas que requieran aislamiento real en un mismo despliegue (entonces retomar el aislamiento por tenant, hoy diferido).
- Se quiera que un editor gestione sus propias credenciales de red (rompería el supuesto "secretos globales → solo admin").
