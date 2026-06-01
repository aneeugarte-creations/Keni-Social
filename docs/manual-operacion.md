# Manual de operación

Guía del **operador** de keni-social: la persona de Keni que pone esto en marcha y lo
mantiene para el equipo de AMX (Bernardo, Mariana). No es un manual de uso diario
(eso es la [guía para community managers](guia-community-manager.md)) ni de
arquitectura (eso es [`arquitectura.md`](arquitectura.md)): es el **índice y la secuencia**
que enlaza el resto de la documentación, en orden, sin repetirla.

Dos piezas a operar: la **Consola** con su **Biblioteca de prompts** (generación de copy;
funciona sin credenciales) y el **MCP de métricas** (`keni-metricas`, opcional, necesita `uv`
y, para datos reales, credenciales).

Principio del producto: **la IA produce, el humano aprueba.** Nada se publica solo.

---

## 1. Puesta en marcha

Por cada persona del equipo, en este orden:

1. **Instalar el plugin** (dos comandos dentro de Claude Code, sin permisos de admin).
   El detalle —incluido que el repo es privado y hay que estar autenticado con `gh`—
   está en el [`README.md`](../README.md) (sección "Instalación como plugin"):

   ```
   /plugin marketplace add kenitech-io/keni-social
   /plugin install keni-social@keni
   ```

   El plugin declara el **MCP de métricas** (`keni-metricas`) y comandos `/` de apoyo. La
   **generación de copy** ya **no** son skills instalables: vive en la **Consola** (paso 3),
   en su **Biblioteca de prompts** (Copy desde nota, Clip a copy, Termómetro mundial…),
   lanzados con `claude -p`. **El copy se trabaja desde la Consola.**

2. **Conectar las métricas (opcional).** El servidor `keni-metricas` viene declarado en el
   plugin pero necesita `uv`/`uvx` para arrancar. Regístralo y compruébalo:

   ```bash
   claude mcp add keni-metricas -- uvx --from /ruta/a/keni-social/mcp-metricas keni-metricas
   claude mcp list          # debe aparecer keni-metricas
   ```

   En una sesión de Claude: `usa listar_cuentas` y `usa metricas_resumen con cuenta claro-sports y rango semana`.
   Por defecto corre con datos de **muestra** (no necesita credenciales); para datos reales,
   ver el paso 2 de credenciales más abajo. Detalle completo en
   [`despliegue-local.md`](despliegue-local.md).

   Para configurar marcas, scoping y credenciales **sin editar TOML a mano**, corre el asistente guiado:
   ```
   python -m keni_metricas.asistente          # crea/actualiza ~/.config/keni-metricas/config.toml
   python -m keni_metricas.asistente --solo-mostrar   # previsualiza sin escribir
   python -m keni_metricas.asistente --validar        # prueba la conexión si hay tokens
   ```

3. **Consola web (opcional, para quien prefiere botones a comandos).** Es una capa de
   gestión LOCAL (`127.0.0.1`) sobre Claude Code y las métricas; no la necesita quien
   trabaja por conversación. Qué es y su diseño: [`consola.md`](consola.md). Instalar y
   arrancar (`python -m keni_consola`, dependencias del monorepo): el README del paquete,
   [`../consola/README.md`](../consola/README.md); tocar la interfaz,
   [`../consola/frontend/README.md`](../consola/frontend/README.md).

4. **Elegir el modo de despliegue del MCP.** Conviven los dos (arquitectura híbrida):

   | Modo | Cuándo usarlo | Doc |
   |---|---|---|
   | **Local por persona** (stdio) | Por defecto. La persona puede instalar `uv` en su máquina. Máxima privacidad: las llaves nunca salen del equipo. | [`despliegue-local.md`](despliegue-local.md) |
   | **Alojado por Keni** (HTTP) | Máquinas corporativas muy bloqueadas, o para evitar la renovación de tokens. Keni hospeda el MCP con **System User tokens de Meta** (no caducan) tras TLS + bearer. | [`despliegue-hosted.md`](despliegue-hosted.md) |

   Para máquinas que no pueden instalar **nada**: Claude Code en la nube de Keni
   (opción 3 de [`despliegue-local.md`](despliegue-local.md)), con el MCP corriendo dentro
   del entorno de la propia persona.

---

## 2. Credenciales

Solo necesarias para **datos reales** de métricas (con `fuente = muestra` no hace falta nada).

- **Métricas reales = vía Metricool.** El camino recomendado de dato real es la API de
  Metricool (AMX en plan Advanced): un token por marca, sin submission externa. Tabla de
  tokens y configuración en [`credenciales.md`](credenciales.md).
- **Dónde viven:** en `~/.config/keni-metricas/config.toml` de cada persona (está en
  `.gitignore`, no se versiona). Se copia de `mcp-metricas/credenciales.ejemplo.toml`. Si falta
  un bloque, esa plataforma se omite con aviso (degradación elegante).
- **Meta — System User:** para evitar la renovación manual del token cada ~60 días (los tokens de
  usuario caducan), usa un token de **System User** de Business Manager, que **no caduca**.
  Cómo generarlo paso a paso y cómo marcarlo (`tipo_token = "system_user"`):
  [`credenciales.md`](credenciales.md), sección "Meta: token de System User". Es el token que usa
  el despliegue **alojado**.
- **Qué viaja y qué no** (audios, llaves y datos de audiencia se quedan en local; solo salen
  texto de copy y números agregados): [`flujo-de-datos-privacidad.md`](flujo-de-datos-privacidad.md).

---

## 3. Caja de transcripción (Clip a copy)

El flujo **Clip a copy** (video/audio → copy) transcribe **100% en local** con `whisper.cpp`:
el audio **no sale de la máquina**. Eso es por diseño, por privacidad (ver
[`flujo-de-datos-privacidad.md`](flujo-de-datos-privacidad.md)).

Decisión de operación: **no hace falta instalar whisper en todas las máquinas.** Designa **un
Mac** (Apple Silicon) como caja de transcripción compartida — el de la persona de datos, o el
**Mac Studio** del equipo. Las máquinas de community bloqueadas (sin Homebrew) mandan ahí el
material y redactan el copy a partir del `.txt`/`.srt` resultante.

Instalación de la caja (una sola vez): `brew install whisper-cpp ffmpeg` + descargar el modelo
`ggml-large-v3-turbo` (~1.6 GB). Pasos exactos, ruta del modelo y prueba de humo:
[`despliegue-local.md`](despliegue-local.md), sección "Transcripción local".

---

## 4. Operación diaria

El equipo no necesita este manual para el día a día: necesita la
**[guía para community managers](guia-community-manager.md)**, que tiene, en lenguaje normal,
exactamente qué escribirle a Claude para sacar copy de una nota, de un video, consultar métricas
y entender la **auto-verificación** (✅ / ⚠️ / ❌). Como operador, conviene que conozcas:

- **Prompts de copy (Biblioteca):** Copy desde nota, Clip a copy, Termómetro mundial, QA editorial.
  La separación **marca** (línea editorial estable) vs **voz** (toque personal) está en
  [`arquitectura.md`](arquitectura.md).
- **Métricas / dashboard.** Por conversación con las tools del MCP (`listar_cuentas`,
  `metricas_resumen`, `mejores_piezas`, `reporte_consolidado`, `picos`). Para una vista visual
  sin GUI, el dashboard HTML autocontenido (se abre con doble clic, sin red):

  ```bash
  python -m keni_metricas.dashboard --salida dashboard.html --rango mes
  ```

- **Reporte por cron.** Para entrega automática del informe consolidado + alertas, el wrapper
  `mcp-metricas/scripts/cron-reporte.sh` (lock anti-solape, log, **solo lectura**, no reintenta).
  Programa con launchd/cron; configurable por entorno:

  ```bash
  KENI_REPORTE_RANGO=semana KENI_REPORTE_DIR="$HOME/keni-reportes" \
    /ruta/a/keni-social/mcp-metricas/scripts/cron-reporte.sh
  ```

  El comando subyacente es `keni-reporte` (CLI). Detalle en
  [`mcp-metricas/README.md`](../mcp-metricas/README.md).

---

## 5. Publicación (estado)

Hoy el sistema **no publica solo** — y eso es a propósito (el humano aprueba).

- **Por defecto: preview en dry-run.** La skill `publica-meta` es el pre-vuelo final: muestra
  exactamente qué se publicaría en cada red (texto, conteo de caracteres, hashtags, carrusel/hilo,
  qué media acompaña) y cierra con una checklist. **No toca la red, no sube media.** También hay
  una CLI dry-run del payload: `python -m keni_metricas.publicacion ...` (solo imprime la
  petición exacta; no publica).
- **Publicación real: vía Metricool.** La publicación de verdad sale por el **scheduler de
  Metricool** (una sola integración cubre Facebook, Instagram, X, TikTok y YouTube; AMX ya
  tiene plan Advanced), sin submission externa por plataforma. Se enciende con el flag
  `KENI_PUBLICAR_REAL`; lo que queda es trabajo de código interno para cablear el camino real
  en el programador de la Consola (ver
  [`plataformas/publicacion-metricool.md`](plataformas/publicacion-metricool.md)).

---

## 6. Actualizaciones

- **Actualizar el plugin para el equipo.** Cuando Keni publique una versión nueva, cada persona
  corre dentro de Claude Code:

  ```
  /plugin marketplace update keni
  ```

  (Recordar recargar después.) Lo mismo en el [`README.md`](../README.md).
- **Las voces personales sobreviven a las actualizaciones.** La voz de cada quien vive en
  **`~/.config/keni-social/voces/tu-nombre.md`**, fuera del repo/plugin: una actualización **no**
  la pisa. Crear la carpeta una vez con `mkdir -p ~/.config/keni-social/voces`. (Hay un fallback
  versionado dentro del repo, pero la ubicación personal **gana** y es la recomendada.)
- **El histórico y las credenciales también son locales por persona** (`config.toml` y el SQLite
  `~/.local/share/keni-metricas/historico.db`): viven fuera del plugin, así que tampoco se pierden
  al actualizar.

---

## 7. Soporte y mantenimiento

- **Tokens — renovación / rotación.** Los tokens de Meta **de usuario** caducan ~60 días: o se
  renuevan a mano o se migra a **System User** (no caduca) — preferido, y obligatorio para el
  modo alojado. Para **revocar** acceso: borrar el token del `config.toml` local **y** revocarlo
  en la plataforma (Meta Business, Google, X, TikTok). Ver
  [`credenciales.md`](credenciales.md).
- **Contexto editorial.** La línea editorial (reglas legales, tropicalización, fichas de marca)
  vive versionada en el plugin; se actualiza publicando una versión nueva (paso 6). Las voces
  personales las mantiene cada quien en su carpeta de config.
- **Qué vigilar.**
  - **Caducidad de tokens** de usuario (la causa #1 de "se desconectó"): migrar a System User.
  - **Token de Metricool** (métricas y publicación reales): si falta o caduca, las métricas
    degradan a `muestra` y la publicación real no sale; renovarlo en el `config.toml`.
  - **`cron.log`** del reporte programado (en `KENI_REPORTE_DIR`): revisar `FALLO` (no reintenta
    solo). El reporte es solo lectura: un fallo nunca rompe nada, solo no entrega ese informe.
  - **Auto-verificación:** recordar al equipo que ⚠️ significa "revísalo tú" (típico en nombres y
    cifras sacados de un audio); no se publica con ⚠️ sin confirmar.

---

### Mapa de documentos

| Tema | Documento |
|---|---|
| Cómo encajan las piezas | [`arquitectura.md`](arquitectura.md) |
| Instalar el plugin | [`README.md`](../README.md) |
| Consola web (qué es) | [`consola.md`](consola.md) |
| Consola — instalar y arrancar | [`../consola/README.md`](../consola/README.md) |
| Despliegue local por persona | [`despliegue-local.md`](despliegue-local.md) |
| Despliegue alojado por Keni | [`despliegue-hosted.md`](despliegue-hosted.md) |
| Credenciales y tokens | [`credenciales.md`](credenciales.md) |
| Privacidad / flujo de datos | [`flujo-de-datos-privacidad.md`](flujo-de-datos-privacidad.md) |
| Uso diario del equipo | [`guia-community-manager.md`](guia-community-manager.md) |
| Resumen para dirección | [`resumen-para-direccion.md`](resumen-para-direccion.md) |
| Go-to-market y pricing | [`go-to-market.md`](go-to-market.md) |
