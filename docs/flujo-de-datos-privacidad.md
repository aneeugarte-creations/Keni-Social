# Flujo de datos y privacidad

Documento para una revisión de privacidad. Describe **qué dato vive dónde**, qué nunca sale de
la máquina, cuánto se retiene y quién es subprocesador. Sin tecnicismos.

## Resumen en una frase

El material sensible —audios, videos y las llaves de acceso a las redes— **nunca viaja a un
servicio de terceros**: a servicios externos (Anthropic) solo van **texto de copy** y **números
agregados de métricas**. Dónde se *procesa* ese material sensible depende del modo de despliegue:
en **modo local** se queda en la máquina del equipo; en **modo alojado**, en el **sandbox dedicado
de cada persona dentro de la infraestructura de Keni** (`code.kenitech.io`), no en un tercero.

## Arquitectura: híbrida

Tres piezas, cada una con un alcance de datos distinto:

1. **Copy** — corre con `claude -p` (Claude Code). El texto se procesa con la IA de Anthropic.
2. **Transcripción (video/audio → texto)** — corre con **whisper**, sin nube de terceros. El audio
   **no va a ninguna API externa**.
3. **Métricas** — se leen a través de un **MCP alojado por Keni** (un servicio en línea), usando
   tokens de Meta (System User). El servicio devuelve **solo números agregados**.

### Dos modos de despliegue (dónde se procesa lo sensible)

La diferencia de privacidad entre modos **no** es qué sale a terceros (es lo mismo: texto + números
agregados a Anthropic), sino **dónde se procesa el material sensible**:

- **Modo local (por persona).** `claude -p` y whisper corren en la **máquina de la persona**. El
  audio, el video y las credenciales **no salen del equipo**.
- **Modo alojado (sandbox por usuario, `code.kenitech.io`).** La persona entra por navegador; `claude -p`
  y whisper corren en su **sandbox dedicado en infraestructura de Keni**. El audio y las credenciales
  **salen del portátil hacia ese sandbox propio** (no a un tercero ni a una API externa). En este modo,
  **Keni procesa y custodia** ese material sensible dentro del sandbox de cada persona — algo que en
  modo local no ocurre (ver *Subprocesadores*). La decisión está en
  [ADR 0001](adr/0001-runtime-servicio-compartido.md).

En ambos modos, lo que llega a Anthropic es lo mismo: **texto** (notas y copy) y **números
agregados** de métricas.

## Tabla: qué dato vive dónde

La columna que importa para terceros es la última (¿va a Anthropic?). Dónde se *procesa* lo
sensible cambia entre modo local y modo alojado.

| Dato | Modo local (por persona) | Modo alojado (sandbox por usuario, Keni infra) | ¿Va a un tercero (Anthropic)? |
|---|---|---|---|
| **Audio y video originales** | En la máquina del equipo; se transcriben con whisper, sin nube. No salen del equipo. | Suben al **sandbox dedicado de la persona** en Keni infra; whisper corre ahí. Salen del portátil, pero **no a un tercero**. | **No.** |
| **Tokens y credenciales de las redes** (Meta System User, etc.) | Local, en archivos de configuración fuera del control de versiones. | En el sandbox / MCP alojado, dentro de Keni infra. | **No.** |
| **Transcripción (texto del audio)** | Se genera y guarda en local. | Se genera en el sandbox de la persona. | Solo el **texto**, si se usa como base de copy → Anthropic. El audio **no**. |
| **Texto del copy** (notas de entrada y borradores de salida) | Se procesa con Claude (`claude -p`). | Se procesa con Claude (`claude -p`, suscripción de Claude Code del sandbox). | **Sí**, a Anthropic. |
| **Métricas agregadas** (visualizaciones, alcance, engagement, piezas top) | Las lee el MCP y entran en la conversación con la IA. | Las lee el MCP alojado de Keni. | **Sí**, números agregados, a Keni (MCP) y Anthropic. |
| **Datos personales de seguidores / audiencia** | No se recogen ni se procesan. | No se recogen ni se procesan. | **No.** |

## Qué NUNCA va a un tercero

En **ningún modo** sale a un servicio de terceros (ni a Anthropic ni a otra nube externa):

- El **audio y el video** originales. La transcripción es con whisper, sin nube externa. *(En modo
  local se queda en tu máquina; en modo alojado se procesa en tu sandbox dedicado en Keni infra.)*
- Los **tokens y credenciales** de las redes sociales. *(Igual: en tu máquina, o en tu sandbox de
  Keni infra.)*
- Cualquier **dato personal de la audiencia** (no se recoge: solo se manejan números agregados).

## Qué sí sale, y a dónde

- **A la API de Anthropic (Claude):** el texto de las notas de entrada, el texto del copy
  generado y los números agregados de métricas que entren en la conversación.
- **Al MCP alojado de Keni:** solo números agregados de métricas (totales y desgloses por
  plataforma/marca, piezas top). **Sin datos personales.** Los tokens de las redes que el MCP
  usa para leer son de tipo Meta System User; las credenciales propias de la persona no se
  envían a la nube como parte del copy.

## Retención

- **Transcripciones:** en **modo local** quedan en disco, en la máquina (junto a los `.srt`/`.json`
  con marcas de tiempo); en **modo alojado**, en el sandbox de la persona en Keni infra. En ninguno
  se suben a un servicio de terceros. Su borrado se rige por la política interna del equipo (modo
  local) o por la política de retención del sandbox de Keni (modo alojado, *por definir*).
- **Audio y video:** en modo local los gestiona el equipo en su máquina; en modo alojado viven en el
  sandbox de la persona en Keni infra. El sistema no los copia a un tercero.
- **Métricas agregadas:** se usan para construir resúmenes e informes. No incluyen datos
  personales.
- **API de Anthropic:** lo enviado se trata según los términos de Anthropic (ver subprocesador).

## Subprocesadores

- **Anthropic** es subprocesador del texto que se le envía (notas, copy y números agregados de
  métricas) para que el modelo Claude procese la petición. **En ambos modos**, no recibe audio,
  video ni credenciales de las redes.
- **Keni (`code.kenitech.io`), solo en modo alojado.** El sandbox dedicado de cada persona —en
  infraestructura de Keni— procesa el audio/video y la transcripción y custodia las credenciales de
  las redes. No es un tercero externo, pero **es un cambio frente al modo local**, donde todo eso se
  queda en la máquina del equipo y Keni no lo procesa. (Aislamiento por persona vía sandbox; política
  de retención y acceso de Keni *por definir*.)

## Garantías de diseño

- **El humano aprueba.** El sistema prepara y previsualiza (modo borrador); **no publica solo**,
  no programa ni sube nada a las redes.
- **Verificación visible.** Cada copy llega con una auto-verificación que marca lo dudoso (✅ / ⚠️
  / ❌), de modo que nombres y cifras sin confirmar quedan señalados antes de publicar.
- **Mínimo necesario.** A servicios externos solo viaja lo imprescindible para redactar (texto)
  y para medir (números agregados); lo sensible **no va a un tercero** (se queda en tu máquina en
  modo local, o en tu sandbox de Keni en modo alojado).
