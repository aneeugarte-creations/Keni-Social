# Flujo de datos y privacidad

Documento para una revisión de privacidad. Describe **qué dato vive dónde**, qué nunca sale de
la máquina, cuánto se retiene y quién es subprocesador. Sin tecnicismos.

> **Cómo leer este documento.** Marcamos en cada punto el **estado ACTUAL** (lo que hoy hace el
> sistema en producción) frente al **OBJETIVO** (lo que el diseño quiere alcanzar pero **aún no
> está implementado**). El objetivo de esta distinción es no afirmar garantías que el despliegue
> todavía no cumple. Cuando algo está *por definir* o *no verificado*, lo decimos.

## Resumen en una frase

Las **llaves de acceso a las redes** y el **audio/vídeo originales del flujo clip→copy** no se
envían a un servicio de terceros. **Sí** salen a terceros, en cambio: **texto** (notas y copy) y
**números agregados** de métricas hacia **Anthropic**, y —cuando se usa la generación de
imágenes— **prompts de imagen y, en el modo de extensión de fondo, la propia foto** hacia
**OpenRouter/OpenAI**. En modo alojado, ese procesamiento ocurre en la **infraestructura
compartida de Keni** (no en un servicio por persona): un único servicio de generación, una base
de datos Postgres compartida y almacenamiento de objetos compartido.

> **ACTUAL vs OBJETIVO (lo más importante de este documento).**
> - **ACTUAL:** en modo alojado **no existe un sandbox dedicado por persona**. La generación corre
>   en un **servicio compartido** de Keni (un contenedor `worker` común que ejecuta `claude -p`),
>   con un **único token de Claude compartido por todo el equipo**, y el estado vive en una base de
>   datos **compartida**. No hay aislamiento técnico de datos ni credenciales entre personas dentro
>   del servicio alojado.
> - **OBJETIVO:** aislamiento por persona (sandbox dedicado en `code.kenitech.io`), descrito en la
>   **Fase 2 del [ADR 0001](adr/0001-runtime-servicio-compartido.md)**. **Aún no está
>   implementado.** No debe presentarse como garantía actual ante AMX.

## Arquitectura: híbrida

Tres piezas, cada una con un alcance de datos distinto:

1. **Copy** — corre con `claude -p` (Claude Code). El texto se procesa con la IA de Anthropic.
2. **Transcripción (vídeo/audio → texto)** — corre con **whisper**, sin nube de terceros. El audio
   **no va a ninguna API externa**. *(ACTUAL: la transcripción es del **perfil local**; el gateway
   alojado **no transcribe** — ver más abajo.)*
3. **Métricas** — se leen a través de un **MCP alojado por Keni** (un servicio en línea), usando
   tokens de Meta (System User). El servicio devuelve **solo números agregados**.
4. **Imágenes (Estudio de imagen)** — operaciones deterministas (logo, recorte, peso…) en local y
   sin terceros; pero la **generación/expansión por IA** (ilustraciones, fondos, *outpaint*) va a un
   modelo de imagen **a través de OpenRouter** (gateway compatible con OpenAI). *(ACTUAL: en uso en
   fase beta dentro del piloto AMX — ver [`estudio-imagen.md`](estudio-imagen.md).)*

### Dos modos de despliegue (dónde se procesa lo sensible)

- **Modo local (por persona).** `claude -p`, whisper y los scripts de imagen corren en la **máquina
  de la persona**. El audio, el vídeo y las credenciales **no salen del equipo** (salvo lo que se
  envíe explícitamente a terceros: ver *Qué sí sale, y a dónde*).

- **Modo alojado (servicio compartido de Keni).** La persona entra por navegador. **ACTUAL:** la
  generación de copy **no** corre en un sandbox propio de cada persona, sino en un **servicio
  compartido**: el gateway (`back`) **encola** la petición y un **contenedor `worker` común a todo
  el equipo** ejecuta `claude -p` (con un **único token de Claude compartido**). El estado
  (borradores, historial, tareas, usuarios) vive en una **base de datos Postgres compartida** y la
  media en **almacenamiento de objetos compartido** (Garage/S3), todo dentro de la infraestructura
  de Keni. **No hay separación técnica de datos ni credenciales entre personas** dentro de ese
  servicio. **OBJETIVO:** sandbox dedicado por persona en `code.kenitech.io` (Fase 2 del
  [ADR 0001](adr/0001-runtime-servicio-compartido.md)), **no implementado todavía**.

  - **whisper en alojado (ACTUAL): no está.** Por privacidad, la transcripción clip→copy es del
    **perfil local** (el audio no sale de la máquina del equipo). El gateway alojado **no
    transcribe**. Así que, hoy, el caso "subo un audio/vídeo al servicio alojado y se transcribe
    allí" **no ocurre**.

En lo que llega a Anthropic, ambos modos coinciden: **texto** (notas y copy) y **números agregados**
de métricas. Lo que cambia en alojado es **dónde y con qué aislamiento** se procesa: hoy, en
infraestructura **compartida** de Keni, sin separación por persona.

## Tabla: qué dato vive dónde

| Dato | Modo local (por persona) | Modo alojado — **ACTUAL** (servicio compartido, Keni infra) | ¿Va a un tercero? |
|---|---|---|---|
| **Audio y vídeo originales** (flujo clip→copy) | En la máquina del equipo; se transcriben con whisper, sin nube. No salen del equipo. | **No aplica:** el alojado **no transcribe** (whisper es solo local). El audio/vídeo no se sube al servicio alojado. | **No** (no se envían a terceros). |
| **Tokens y credenciales de las redes** (Meta System User, etc.) | Local, en archivos de configuración fuera del control de versiones. | En el almacén de secretos del servicio compartido / MCP alojado, dentro de Keni infra. **Compartido a nivel de servicio, no aislado por persona.** | **No.** |
| **Transcripción (texto del audio)** | Se genera y guarda en local. | No se genera en alojado (whisper es local). Si se pega su texto como base de copy, ese **texto** viaja como cualquier otro texto de copy. | Solo el **texto**, si se usa como base de copy → Anthropic. El audio **no**. |
| **Texto del copy** (notas de entrada y borradores de salida) | Se procesa con Claude (`claude -p`). | Se procesa con `claude -p` en el **worker compartido**, con **token de Claude compartido**. | **Sí**, a Anthropic. |
| **Prompts de imagen** (descripción para generar/expandir; pueden describir contenido editorial de AMX) | Si se usa el motor generativo, salen a OpenRouter/OpenAI. | Igual: el worker compartido los envía a OpenRouter/OpenAI. | **Sí**, a **OpenRouter/OpenAI** (motor generativo). |
| **Foto original** (solo en *extender fondo con IA* / outpaint) | Se envía a OpenRouter/OpenAI como imagen de entrada. | Igual. | **Sí**, a **OpenRouter/OpenAI** (solo en outpaint generativo). |
| **Métricas agregadas** (visualizaciones, alcance, engagement, piezas top) | Las lee el MCP y entran en la conversación con la IA. | Las lee el MCP alojado de Keni (compartido). | **Sí**, números agregados, a Keni (MCP) y Anthropic. |
| **Datos personales de seguidores / audiencia** | No se recogen ni se procesan. | No se recogen ni se procesan. | **No.** |

> **Nota sobre el modo alojado OBJETIVO:** la columna "alojado" describe el **estado ACTUAL**
> (compartido). El objetivo de aislamiento por persona (sandbox dedicado) **aún no existe**; cuando
> se implemente, esta tabla deberá actualizarse.

## Qué NO se envía a un tercero

En **ningún modo** se envían a un servicio de terceros:

- El **audio y el vídeo** originales del flujo clip→copy. La transcripción es con whisper, sin nube
  externa. *(En local se queda en tu máquina; en alojado, hoy, ese flujo no se ofrece — whisper es
  solo local.)*
- Los **tokens y credenciales** de las redes sociales. *(En local: en tu máquina. En alojado: en el
  almacén de secretos del servicio compartido de Keni — no a un tercero externo, pero **no aislado
  por persona**; ver* Subprocesadores*.)*
- Cualquier **dato personal de la audiencia** (no se recoge: solo se manejan números agregados).

> **Importante:** las **imágenes** (prompts y, en outpaint, la foto) **sí** salen a un tercero
> (OpenRouter/OpenAI) cuando se usa el motor generativo. No están en esta lista.

## Qué sí sale, y a dónde

- **A la API de Anthropic (Claude):** el texto de las notas de entrada, el texto del copy generado
  y los números agregados de métricas que entren en la conversación. *(En alojado, vía un **único
  token de Claude compartido** por el equipo.)*
- **A OpenRouter/OpenAI (generación de imágenes, ACTUAL en beta):** cuando se usa el motor
  generativo del Estudio de imagen, salen los **prompts de imagen** (texto que describe la pieza, y
  que **puede describir contenido editorial de AMX**) y, en la operación de **extender fondo con IA**
  (*outpaint*), también la **foto de entrada** (enviada como imagen). Endpoint:
  `openrouter.ai/api/v1/chat/completions`; el modelo es **configurable** (selector de Ajustes /
  variable `OPENROUTER_IMAGE_MODEL`) y por defecto es un modelo de imagen de **OpenAI** servido a
  través de OpenRouter. Las operaciones **deterministas** (logo, pleca, recorte, peso, extender un
  fondo uniforme) **no** usan IA y **no** salen a terceros.
- **Al MCP alojado de Keni:** solo números agregados de métricas (totales y desgloses por
  plataforma/marca, piezas top). **Sin datos personales.** Los tokens que el MCP usa para leer son
  de tipo Meta System User; las credenciales propias de la persona no se envían a la nube como parte
  del copy.

## Retención

- **Transcripciones:** son del **perfil local**; quedan en disco en la máquina (junto a los
  `.srt`/`.json` con marcas de tiempo). No se suben a un servicio de terceros. Su borrado se rige
  por la política interna del equipo. *(En alojado no se generan: whisper es solo local.)*
- **Audio y vídeo:** en local los gestiona el equipo en su máquina. *(El alojado no los recibe.)*
- **Borradores, historial, tareas y media (modo alojado):** viven en la **base de datos Postgres
  compartida** y el **almacenamiento de objetos compartido** (Garage/S3) de Keni — **compartidos a
  nivel de servicio**, sin separación por persona (ACTUAL). Política de retención y de acceso de
  Keni: **por definir**.
- **Métricas agregadas:** se usan para construir resúmenes e informes. No incluyen datos personales.
- **API de Anthropic:** lo enviado se trata según los términos de Anthropic (ver subprocesador).
- **OpenRouter/OpenAI:** los prompts y, en outpaint, la imagen enviada se tratan según los términos
  de OpenRouter y del proveedor del modelo (OpenAI) (ver subprocesador). Retención por su parte:
  **no verificada por nosotros**; debe confirmarse en sus términos antes de la revisión con AMX.

## Subprocesadores

- **Anthropic** — subprocesador del **texto** que se le envía (notas, copy y números agregados de
  métricas) para que el modelo Claude procese la petición. **En ambos modos**, no recibe audio,
  vídeo ni credenciales de las redes. *(En alojado, vía un único token de Claude compartido por el
  equipo, no por persona.)*
- **OpenRouter** (y, a través de él, **OpenAI** como proveedor del modelo de imagen por defecto) —
  subprocesador de la **generación de imágenes** (ACTUAL, beta). Recibe los **prompts de imagen**
  (que pueden describir contenido editorial de AMX) y, en la operación de **extender fondo con IA**
  (*outpaint*), también la **foto de entrada**. No recibe audio, vídeo de clips, transcripciones ni
  credenciales de las redes. El proveedor concreto del modelo depende del modelo configurado.
- **Keni (infraestructura de servicio compartido), solo en modo alojado.** El servicio de Keni
  ejecuta `claude -p` (worker compartido), aloja el MCP de métricas, custodia los secretos
  (incluido el token de Claude y, en su caso, la clave de imagen) y persiste el estado en Postgres y
  object storage **compartidos**. **No es un tercero externo**, pero **es un cambio frente al modo
  local** (donde todo eso se queda en la máquina del equipo) y, hoy, **sin aislamiento por persona**.
  - **ACTUAL:** servicio y datos **compartidos** entre todas las personas del equipo; un único token
    de Claude para todos; política de retención y acceso de Keni **por definir**.
  - **OBJETIVO (no implementado):** aislamiento por persona vía sandbox dedicado en
    `code.kenitech.io` (Fase 2 del [ADR 0001](adr/0001-runtime-servicio-compartido.md)).

## Garantías de diseño

- **El humano aprueba.** El sistema prepara y previsualiza (modo borrador); **no publica solo**,
  no programa ni sube nada a las redes.
- **Verificación visible.** Cada copy llega con una auto-verificación que marca lo dudoso (✅ / ⚠️
  / ❌), de modo que nombres y cifras sin confirmar quedan señalados antes de publicar. El mismo
  revisor legal/editorial se aplica a las imágenes generadas.
- **Mínimo necesario a terceros.** A Anthropic solo viaja texto (notas y copy) y números agregados;
  a OpenRouter/OpenAI solo lo necesario para generar imágenes (prompt y, en outpaint, la foto). El
  audio/vídeo de clips y las credenciales de las redes **no van a un tercero**.
- **Pendiente para cumplir las garantías de aislamiento (ACTUAL → OBJETIVO).** El aislamiento por
  persona (sandbox dedicado) **no está implementado**: hoy el servicio alojado es compartido (un
  worker común, un token de Claude común, datos compartidos). Mientras no se ejecute la Fase 2 del
  [ADR 0001](adr/0001-runtime-servicio-compartido.md), **no debe afirmarse** ante AMX un aislamiento
  de datos o credenciales entre personas/clientes en el modo alojado.
