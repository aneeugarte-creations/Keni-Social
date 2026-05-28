# ADR 0003 — Estado y secretos por tenant: cerrojo por rol ahora, aislamiento multi-tenant diferido

- **Estado:** Propuesto (borrador para revisar) — solo el cerrojo por rol está implementado
- **Fecha:** 2026-05-27
- **Decisores:** equipo keni-social (auditoría de arquitectura, épica #140)
- **Issues:** #153 (este ADR) · #130 (multiusuario, ADR 0001) · #145 (acotado por marca/proyecto) · #135 (multi-tenant)
- **Componente:** `consola/` — auth/permisos, almacén de secretos (`secretos.py`), tokens de redes (`api/conexiones.py`), estado operacional (`db.py`)
- **Relación:** **complementa** a [ADR 0001](0001-runtime-servicio-compartido.md) (runtime multiusuario) y a [ADR 0002](0002-descomposicion-monolito-modular-catalogo-apps.md) (riesgo multi-tenant §Riesgos). No los supersede.

> Mismo criterio de ADR que en este repo: solo decisiones aceptadas, sin alternativas en conflicto; la
> traza fina vive en git. Este ADR registra una decisión **parcialmente aceptada** (el cerrojo por rol,
> ya implementado en #153) y una decisión **diferida y propuesta** (el aislamiento por tenant), separadas
> con claridad para que quien lo lea sepa qué está hecho y qué no.

---

## Contexto

El servicio hosted (`social.kenitech.io`) es multiusuario (#130 Fase 1): hay login user/pass, roles
`admin`/`editor`, sesiones server-side y **atribución de autor** en el estado que se crea. Pero la
auditoría de arquitectura (#153) detectó que el **estado** y los **secretos** son **globales y
compartidos**, sin acotar por usuario, permiso ni cliente:

- **Secretos globales en un único fichero por despliegue:**
  - La clave del proveedor de imagen IA vive en `secretos.toml` (`secretos.ruta_secretos()`),
    colgada de la raíz de estado única del despliegue.
  - Los tokens de redes sociales (Meta/YouTube/X/TikTok) viven en el `config.toml` de métricas
    (`keni_metricas.config.ruta_config()`), también único.
  - Antes de #153, **cualquier usuario autenticado** (incluido un `editor`) podía leer la presencia/pista
    y **mutar/borrar** esos secretos vía `/api/conexiones/*`.

- **Estado sin acotar por permiso:** el tablero de tareas (#145), las generaciones, el seguimiento
  comercial y la rota tienen autor atribuido pero el modelo de roles es **binario** (`admin`/`editor`)
  y **sin dimensión de tenant ni de marca/proyecto en la cuenta**: una cuenta no "pertenece" a un cliente
  ni a un subconjunto de marcas. Por eso no hay todavía sobre qué acotar el estado por tenant.

### Por qué importa

Hoy el piloto es **single-tenant** (AMX): un solo equipo comparte un tablero, una clave de imagen y unos
tokens de redes. Para AMX, "todo el equipo ve el tablero" es **deseado** (#145 lo diseña así). El riesgo
es a futuro: en cuanto entre un **segundo cliente** en el mismo despliegue, los secretos y el estado del
cliente A serían visibles/mutables por usuarios del cliente B. Es el riesgo multi-tenant que el ADR 0002
ya anotó (§Riesgos, #135).

---

## Decisión

Separamos en dos lo que es **achacable ya** de lo que es un **cambio de arquitectura mayor**.

### 1) ACEPTADO e IMPLEMENTADO (#153): cerrojo por ROL sobre los secretos globales

Los secretos globales (clave de imagen + tokens de redes) son la superficie sensible más clara. Mientras
no exista aislamiento por tenant, se cierran detrás del **rol admin**:

- **TODOS** los endpoints de `/api/conexiones/*` (lectura **y** mutación) exigen rol `admin`. Un `editor`
  recibe **403** y ni siquiera ve la presencia/pista del secreto. El acceso por **token interino** de
  mantenimiento/despliegue (sin usuario) cuenta como plenos permisos (no rompe el modo local ni el
  bootstrap del servicio).
- El gate se decide en una **fuente única**: `keni_consola.permisos.es_admin(request)` /
  `rechazo_solo_admin(...)`. Ese helper centraliza la pregunta "¿es admin?" que antes estaba **duplicada**
  inline en `api/usuarios.py` y `api/rota.py` (mismo cuerpo); ahora las tres áreas
  (`conexiones`/`usuarios`/`rota`) comparten el mismo contrato. No se inventa ninguna vía de auth nueva:
  el helper solo **lee** el `request.state` que el middleware `SeguridadConsola` ya fija (sesión + CSRF
  intactos).

**Límite explícito (positivo):** el cerrojo es "solo admin", **no** un acotamiento por tenant. Con un solo
cliente (AMX) esto es suficiente: el admin del equipo gestiona las conexiones y los editores trabajan con
ellas indirectamente (la clave la consume `media.py`; los tokens los consume el MCP de métricas) sin poder
leerlas ni cambiarlas. El estado compartido (tablero #145, etc.) **se conserva tal cual**: sigue siendo del
equipo, acotable por `?proyecto=<id>` como hasta ahora.

### 2) DIFERIDO y PROPUESTO: aislamiento por TENANT (Fase 2 de #130)

El **aislamiento real por tenant** —un almacén de secretos y un estado **separados por cliente**, no un
fichero/tabla global— es un cambio de arquitectura mayor y **no** se construye en #153. Se difiere a la
Fase 2 de #130 / la épica multi-tenant (#135). Modelo **propuesto** (a ratificar cuando entre el 2.º
cliente):

- **Entidad `tenant` (cliente) de primera clase.** Una tabla `tenants` y una columna `tenant_id` en
  `usuarios`. Cada cuenta pertenece a exactamente un tenant. El `admin` pasa a ser **admin _de su tenant_**
  (no del despliegue); se añade un rol/flag `owner`/superadmin de plataforma para operaciones
  cross-tenant (alta de tenants, mantenimiento).
- **Permisos por marca/proyecto dentro del tenant (#145).** Tabla de asignación
  `usuario_marca`/`usuario_proyecto` (o un campo de "marcas visibles" por cuenta). El estado operacional
  (`tareas`, `comercial_publicaciones`, generaciones, rota) se **filtra en la capa de datos** por
  `tenant_id` + las marcas/proyectos visibles del usuario, no en cada handler. `listar_tareas` y hermanos
  reciben el contexto del solicitante (no un `None` que devuelve "todo").
- **Secretos por tenant, no un fichero global.** El almacén de la clave de imagen (`secretos.py`) y los
  tokens de redes pasan a estar **namespaced por `tenant_id`** (p. ej. una fila/registro por tenant en
  Postgres con valores cifrados en reposo, o un sub-árbol por tenant en disco). `obtener_clave_imagen()` /
  `ruta_config()` dejan de ser globales y reciben el tenant del contexto de la petición. Provisionado pero
  aún no consumido: el `postgres`/`garage` del stack `deploy/` es el sustrato natural para esto (hoy el
  back persiste en SQLite + disco).
- **Enforcement en la capa de datos, no por convención.** Coherente con el ADR 0002 ("estado compartido
  por la capa de datos del gateway, no una app leyendo tablas a mano"): el filtro por tenant/permiso vive
  en el repositorio/gateway para que ningún módulo de `api/` pueda saltárselo.

**Criterios de aceptación de la fase diferida** (cuando se aborde):

- Un usuario del tenant A nunca lee ni muta secretos, tokens ni estado del tenant B (test cross-tenant).
- Un `editor` solo ve el estado de las marcas/proyectos que tiene asignados (test por permiso).
- El piloto AMX sigue funcionando sin migración manual: un único tenant por defecto al que se adscriben las
  cuentas y los datos existentes (retrocompatible).

---

## Consecuencias

### Lo que se conserva (no se toca)

- La sesión + CSRF del middleware (#134/#130) y el token interino de mantenimiento.
- El tablero de tareas compartido del equipo (#145) y su filtro por `?proyecto=<id>`: para single-tenant
  es el comportamiento deseado.
- La regla de oro de los secretos: nunca salen al navegador (solo presencia/pista `····last4`).

### Lo que se añade ahora (#153)

- `keni_consola/permisos.py`: helper único de rol (`es_admin`, `rechazo_solo_admin`, `usuario_actual`),
  reusado por `conexiones`/`usuarios`/`rota`.
- Cerrojo `admin` en los 8 endpoints de `/api/conexiones/*` (imagen + redes), lectura y mutación.

### Riesgos / deuda asumida

- **Granularidad gruesa hasta la Fase 2.** Con "solo admin" sobre las conexiones, un editor no puede
  gestionar tokens aunque legítimamente trabaje con esas redes; es aceptable para AMX (un admin del equipo
  los gestiona) y se afina cuando llegue el modelo por tenant/permiso.
- **El aislamiento multi-tenant sigue pendiente.** Hasta que se implemente la Fase 2, **no** se debe
  meter un segundo cliente en el mismo despliegue compartiendo el almacén global; mientras tanto cada
  cliente va en su propio despliegue (un tenant por instancia).
