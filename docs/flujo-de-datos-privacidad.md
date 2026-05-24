# Flujo de datos y privacidad

Documento para una revisión de privacidad. Describe **qué dato vive dónde**, qué nunca sale de
la máquina, cuánto se retiene y quién es subprocesador. Sin tecnicismos.

## Resumen en una frase

El material sensible —audios, videos y las llaves de acceso a las redes— **se queda en la
máquina del equipo**. A servicios externos solo viajan **texto de copy** y **números agregados
de métricas**; nunca el audio original ni las credenciales.

## Arquitectura: híbrida

Tres piezas, cada una con un alcance de datos distinto:

1. **Copy** — corre en Claude Code, en la máquina de la persona. El texto se procesa con la IA
   de Anthropic.
2. **Transcripción (video/audio → texto)** — corre **100% en local** en un Mac designado del
   equipo. El audio **no sale del equipo**.
3. **Métricas** — se leen a través de un **MCP alojado por Keni** (un servicio en línea), usando
   tokens de Meta (System User). El servicio devuelve **solo números agregados**.

## Tabla: qué dato vive dónde

| Dato | Dónde vive / se procesa | ¿Sale de la máquina? | Quién lo ve |
|---|---|---|---|
| **Audio y video originales** | Local (Mac designado del equipo). Se transcriben con whisper.cpp, sin nube. | **No.** Nunca sale. | Solo el equipo, en su máquina. |
| **Tokens y credenciales de las redes** (Meta System User, etc.) | Local, en la máquina; en archivos de configuración fuera del control de versiones. | **No.** Nunca salen. | Solo el equipo. |
| **Transcripción (texto del audio)** | Se genera y guarda en local (disco de la máquina). | Solo si se usa como base del copy: entonces ese **texto** viaja a Anthropic. El audio no. | Equipo en local; Anthropic solo si se redacta copy a partir de ella. |
| **Texto del copy** (notas de entrada y borradores de salida) | Se procesa con la IA de Anthropic. | **Sí**, a la API de Anthropic. | Equipo y Anthropic (como subprocesador). |
| **Métricas agregadas** (visualizaciones, alcance, engagement, piezas top) | Las lee el MCP alojado de Keni y se usan en la conversación con la IA. | **Sí**, números agregados: al MCP alojado de Keni y a la API de Anthropic. | Equipo, Keni (MCP) y Anthropic. |
| **Datos personales de seguidores / audiencia** | No se recogen ni se procesan. | **No.** | Nadie por esta vía. |

## Qué NUNCA sale de la máquina

- El **audio y el video** originales. La transcripción es local, por diseño.
- Los **tokens y credenciales** de las redes sociales.
- Cualquier **dato personal de la audiencia** (no se recoge: solo se manejan números agregados).

## Qué sí sale, y a dónde

- **A la API de Anthropic (Claude):** el texto de las notas de entrada, el texto del copy
  generado y los números agregados de métricas que entren en la conversación.
- **Al MCP alojado de Keni:** solo números agregados de métricas (totales y desgloses por
  plataforma/marca, piezas top). **Sin datos personales.** Los tokens de las redes que el MCP
  usa para leer son de tipo Meta System User; las credenciales propias de la persona no se
  envían a la nube como parte del copy.

## Retención

- **Transcripciones:** quedan **en disco, en la máquina** (junto a los archivos `.srt`/`.json`
  con marcas de tiempo). Su borrado es responsabilidad del equipo, según su política interna; no
  se suben a ningún servicio externo.
- **Audio y video:** los gestiona el equipo en su máquina; el sistema no los copia fuera.
- **Métricas agregadas:** se usan para construir resúmenes e informes. No incluyen datos
  personales.
- **API de Anthropic:** lo enviado se trata según los términos de Anthropic (ver subprocesador).

## Subprocesador

- **Anthropic** es subprocesador del texto que se le envía (notas, copy y números agregados de
  métricas) para que el modelo Claude procese la petición. No recibe audio, video ni
  credenciales de las redes.

## Garantías de diseño

- **El humano aprueba.** El sistema prepara y previsualiza (modo borrador); **no publica solo**,
  no programa ni sube nada a las redes.
- **Verificación visible.** Cada copy llega con una auto-verificación que marca lo dudoso (✅ / ⚠️
  / ❌), de modo que nombres y cifras sin confirmar quedan señalados antes de publicar.
- **Mínimo necesario.** A servicios externos solo viaja lo imprescindible para redactar (texto)
  y para medir (números agregados); lo sensible se queda en local.
