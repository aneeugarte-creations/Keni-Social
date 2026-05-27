# Sistema de automatización de redes — AMX Contenido (UnoTV / ClaroSports)
### Documento de arquitectura y decisión · Keni AI · keni-social

> **Doc-origen (histórico).** Esta es la exploración del 2026-05-23 que dio nacimiento a
> keni-social. Se conserva por el diagnóstico (el dolor central, el contexto editorial como
> activo, los límites de las APIs). Para el estado **vivo** ver: arquitectura actual en
> `docs/arquitectura.md`, credenciales en `docs/credenciales.md`, y la facilitación de la
> Sesión 4 en `03-entrega/unotv-clarosports/` (Drive). No es la fuente de verdad del producto.

- **Fecha:** 2026-05-23 · **Rev. 2** (corrige el diagnóstico del dolor central tras releer las entrevistas)
- **Para:** (1) decisión de dirección sobre el sistema centralizado, y (2) guía de Mikel para la Sesión 4, en la que **cada participante construye su propia automatización**.
- **Estado:** exploración — hipótesis bajo prueba dentro del piloto.
- **Fuentes:** entrevistas del equipo piloto (releídas en directo), transcripciones de selección, runbooks y transcripciones de sesiones 1-3, e investigación del panorama de herramientas/APIs/MCP 2025-26. Lo marcado con ⚠️ requiere verificación al cotizar.

---

## 0. TL;DR

1. **El dolor central NO es vídeo→copy ni los reportes de métricas** (esos son roles especializados y periféricos: un editor de vídeo, un coordinador de YouTube, una analista). El centro de gravedad del equipo son los **~4 community managers que rotan turnos haciendo lo mismo** + el copy + la pareja de redes UnoTV. Su dolor es **la talacha de copy + post, todo el día, en todas las plataformas**.

2. **El bloqueo que impide automatizar esa talacha es uno solo:** el copy que da la IA **no es publicable tal cual** — le falta jerga mexicana, línea editorial de redes y formato por plataforma, y mete errores (fechas, números, nombres). Por eso lo **reescriben todo**. Resolver eso = recuperar las horas.

3. **La automatización correcta no es "conectar redes y publicar". Es codificar el contexto editorial** (voz de marca + tropicalización + formato por plataforma + checklist de verificación) en Skills, para que el copy salga listo y el humano solo apruebe. Es exactamente la tesis que ya enseñáis (Bernardo: *IA diseña el proceso la primera vez → se vuelve software determinista*).

4. **Esto reencuadra la Sesión 4:** "cada uno hace su automatización" = cada community/copy construye **su Skill de producción de copy con su contexto editorial dentro**. El caso prioritario es el más repetitivo y de mayor volumen (el copy+post diario), y **Tescu** (el más resistente, se niega a usar IA para copy) es el make-or-break del piloto.

5. **El sistema centralizado (conectar redes, métricas, credenciales) sigue siendo un objetivo válido, pero es la ÚLTIMA MILLA**, no el dolor diario. Se decide comparando A vs B (§5) y se monta *después* de resolver la producción de copy. Aviso: la publicación 100% automática es frágil/limitada por las plataformas (§4), y ⚠️ el coste de la API de X puede ser la partida más cara.

---

## 1. El dolor central: la talacha de copy + post (corregido)

### Quién lo sufre (el centro de gravedad)
La masa operativa del equipo, no los especialistas:
- **Community managers Claro Sports** que se turnan en el mismo equipo: **Jorge "Tescu", Luis, Roger**.
- **Redes UnoTV** (pareja que rota turnos): **Ángel + Eduardo "Lalo"**.
- **Copy dedicado UnoTV:** **José**.
- **Community Fundación:** **Daiana**. **Editorial + canal WhatsApp UnoTV:** **Yustine**.

Bernardo lo dice explícito: *"tienes **cuatro community managers haciendo lo mismo en turnos**... cuando uno automatiza un proceso, otro va a tener dos horas más libres."* Y describe el trabajo: *"si nos ponemos a la parte operativa, usamos el 100% de nuestros minutos en IA... el trabajo operativo lo hacemos 100% con IA."* El problema es que **ese 100% no les libera**, porque el resultado hay que rehacerlo.

### Por qué no está ya automatizado: el copy no es publicable tal cual
Este es el hallazgo clave, y es **transversal a todos los que escriben**:

| Persona | Cita | Qué falla |
|---|---|---|
| **Ángel** | *"la tasajeo siempre... no tiene jerga mexicana... no tiene línea editorial... como contratar a alguien que no es mexicano"* | Tropicalización + voz editorial. **Es su petición entera.** |
| **Eduardo** | *"combinaba un lenguaje coloquial con las noticias duras de UnoTV... me jala los acentos de un sitio español"* | Registro/tono inconsistente; acentos de fuentes ES |
| **José** | el ideal: *"que solo sea revisar, ya se escucha bien, va con el tono de la empresa"* | Tono + fiabilidad de datos |
| **Yustine** | *"no respeta nº de caracteres ni formatos de noticiarios"* | Formato por plataforma |
| **Tescu** (🔴) | se niega a usar IA para copy: *"es mi toque final"* | No confía en que suene a él |

Y los errores que les obligan a verificar a mano (José): *"expresidente Trump"* sistemático, *"fechas y números de la nada"*, caracteres en árabe/hindi. Su norma: *"la responsabilidad sigue cayendo en manos humanas; no puedo decir 'es que ChatGPT lo puso mal'."*

> **Diagnóstico:** la talacha pesada que queda **es el copy** (redactar + adaptar por plataforma). El **post** ya está parcialmente resuelto — Echobox auto-publica FB/X desde la web (Eduardo: *"nos ha quitado una carga operativa bastante grande"*). Lo que falta automatizar del post es donde Echobox no llega (Instagram con diseño, YouTube, stories, tiempo real en cobertura).

### La tesis que ya enseñáis, aplicada aquí (Bernardo, charla 2)
> *"La IA no automatiza procesos repetitivos... empiezas con IA, diseñas el proceso, y la IA programa un software que lo automatiza y **deja de ser IA**."*

Aplicado: cada community usa la IA para **codificar su proceso de copy una vez** (su contexto editorial), y eso se vuelve una **Skill repetible** que produce copy listo con mínima intervención. Liberas horas → **se redistribuyen a lo creativo/calidad** (*"mucho volumen, pero con calidad"* — la diferenciación que busca Bernardo, y que coincide con el objetivo del director: que se centren en la parte creativa).

---

## 2. La pieza que lo desbloquea todo: el contexto editorial como activo

Antes de cualquier herramienta o conexión, el activo de mayor palanca es **codificar el contexto editorial** — y es 100% construible en Claude Code hoy, sin comprar ni conectar nada. Es la aplicación directa de la "idea 2" del piloto (*lo que la IA sabe de tu trabajo se lo dices tú*) y del trabajo de CLAUDE.md del Día 3.

**Qué contiene (jerarquía de carpetas = jerarquía editorial, como ya se enseñó en S3):**
- **Voz de marca por propiedad:** UnoTV (noticias, tono duro) vs Claro Sports (deportivo) vs Nación Gamer (gaming) vs Piso 15 (podcast) vs Fundación (social/sensible).
- **Tropicalización:** jerga mexicana, modismos, lo que funciona en redes ("no mames" ≠ "joder"; el ejemplo de Ángel).
- **Formato por plataforma:** longitud y estilo de copy para X vs IG vs FB vs TikTok vs YouTube; nº de caracteres (dolor de Yustine).
- **Reglas y restricciones legales:** prohibido usar la bandera con escudo nacional; tratamiento de menores en notas (workaround de José); línea roja de privacidad ya enseñada.
- **Checklist de verificación:** datos duros, fechas, nombres (Trump), fuentes — lo que cada uno verifica a mano hoy, convertido en paso automático del proceso.

**Por qué es lo primero:** todas las automatizaciones de copy del equipo dependen de esto. Sin contexto editorial, la Skill produce el mismo copy "que hay que tasajear". Con él, sale publicable. Es el cuello de botella real, y es transversal.

---

## 3. Mapa por persona para la Sesión 4 (cada uno construye lo suyo)

Reordenado por el diagnóstico corregido: **primero la masa operativa de copy+post** (el centro), después los casos especializados/adyacentes. Todo construible en Claude Code hoy.

### Grupo A — La masa operativa (PRIORIDAD): producción de copy publicable
La misma plantilla para casi todos, personalizada por persona/marca. Es la automatización de mayor impacto del piloto porque la repiten ~4 personas en turnos, todo el día.

| Persona | Su automatización en S4 | Énfasis personal |
|---|---|---|
| **Ángel** | Skill de copy con **su** contexto editorial UnoTV (ya tiene "robotitos" entrenados → migrarlos a Skill) | Tropicalización mexicana — su obsesión declarada |
| **Eduardo** | Skill de copy + síntesis de nota para UnoTV / Nación Gamer | Separar registro coloquial vs noticia dura; limpiar acentos ES |
| **José** | Empaquetar su flujo (ya muy definido) como Skill: síntesis multi-fuente + **checklist de verificación** + reglas anti-bloqueo | Fiabilidad de datos; investigación en idiomas que no domina sin caer en fuentes falsas |
| **Tescu** (🔴) | Skill de copy **en su voz** a partir del clip que ya catalogó con Magnifi. **Objetivo: que diga "esto sí suena a mí"** | Es el make-or-break. Empezar por un resultado inmediato y visible que le rompa el "es mi toque final" |
| **Luis** | Copy desde la entrevista/programa (transcribir → citas → copy tropicalizado) | Su dolor concreto, dentro de la misma lógica de copy |
| **Roger** | (sin entrevistar — mapear; previsiblemente misma Skill que Tescu/Luis) | — |
| **Daiana** | Skill de copy rápido para cobertura en vivo, con tono por departamento (deportivo vs social) | Tiempo real durante coberturas |
| **Yustine** | Skill de copy con formato/caracteres por plataforma + agenda del canal WhatsApp | Respeto de formato (su fricción) |

> **Para conducir la sesión:** la "automatización individual" de la mayoría es **la misma Skill de producción de copy**, alimentada por el contexto editorial (§2) y personalizada. Eso es lo que ya saben hacer tras las sesiones 1-3 y resuelve el dolor diario real. Si **Tescu** sale con una Skill cuyo copy acepta como suyo, el piloto está ganado.

### Grupo B — Especializados / adyacentes (valiosos, pero no el centro)
| Persona | Caso | Nota |
|---|---|---|
| **Lalo-YouTube** | Metadata de YouTube desde transcripción (descripción, capitulado, etiquetas) con validación por muestra | Especializado; útil pero no es el dolor de la masa |
| **Jonathan** | Metadata + SEO de Nación Gamer; reducir los ~20 clics de YouTube | La subida real es última milla (Capa 2) |
| **Maira** | Podcast Piso 15: copy + miniaturas + resumen desde transcripción | La más madura; puede ser monitora de pares |
| **Mariana** | Reporte de métricas: Skill sobre los CSV exportados (separar Reels/gráfico/vídeo, consolidar verticales) | Caso de "IA la 1ª vez → software después" de manual. Resuelve sus ~2 días/semana, pero es 1 persona |
| **Elías** | QA editorial (checklist) + resumen semanal "lo más visto" | Coordinación, no producción |
| **Ale** | Copy de evento; clasificación del archivo de 150 GB (proyecto aparte) | Adyacente |
| **César** | Orquestación / su app interna de horarios | Perfil dev; aliado técnico en sala |

---

## 4. La última milla: realidad de publicar y leer métricas por API

Esto define el techo del **sistema centralizado** (§5), no el dolor diario. El factor limitante no es el software ni la IA: son las APIs de las plataformas.

| Plataforma | Publicar por API | Límite duro | Notas |
|---|---|---|---|
| **FB / Instagram** (Meta Graph) | Sí: imágenes, carruseles, Reels (≤90s), Stories | **~25 posts/24h por cuenta IG**; cuenta Business obligatoria | **App Review (días-semanas)**. Música nativa no automatizable |
| **X / Twitter** | Sí | Tiers de pago | ⚠️ **El coste es el problema** (abajo) |
| **YouTube** (Data API v3) | Sí | **~6 vídeos/día** con cuota por defecto | Ampliación solicitable |
| **TikTok** (Content Posting) | Sí, **solo tras auditoría de TikTok** | ~15/día por creador | La auditoría es un trámite real |
| **Threads** | Sí | App Review 2-4 sem/permiso | ⚠️ El equipo no mencionó usar Threads |

**⚠️ El coste de X (decisión, no detalle):** en pago por uso, **un post con URL ≈ $0,20** — letal para un medio que enlaza notas todo el día. Tiers fijos: Basic $200/mes, Pro $5.000/mes, Enterprise ~$42.000/mes. Hay que cotizar el volumen real antes de comprometer arquitectura.

**Corrección de encuadre para la S4:** en S3 se dijo que publicar por API es "imposible salvo Metricool". Es impreciso — hay **API oficial con límites y App Review**, o herramienta que la envuelve. Y lo robusto (y lo que el propio equipo concluyó en el caso "muerte del Papa", donde la IA paró sola a pedir aprobación) es: **automatizar la producción, dejar el disparo con humano en el lazo**, sobre todo en breaking news y directo.

---

## 5. El sistema centralizado: Arquitectura A vs B (última milla, medio plazo)

Se monta **después** de resolver la producción de copy (§2-3). Ambas opciones: publicación con humano en el lazo, credenciales por OAuth (nunca contraseñas en crudo).

### Opción A — SaaS rápido (rampa de entrada)
**Stack:** gestor SaaS (**Metricool** por coste multi-marca, o **Sprout Social** por reporting) para publicación + bandeja + analítica, **+ MCP de copiloto** (Buffer/Ayrshare) conectado a Claude, **+ 1Password/Bitwarden**.

### Opción B — Híbrida ("software + MCP + IA" con control)
**Stack:** **Ayrshare** (publicación unificada a 13+ redes + **credenciales por marca** vía OAuth/JWT) **+ n8n** (orquesta: IA produce copy con contexto editorial → cola de aprobación → publica → recoge métricas) **+ Ayrshare MCP + Claude** **+ Metricool/Looker** para dashboard.

### Comparación a fondo

| Dimensión | **A — SaaS rápido** | **B — Híbrida** |
|---|---|---|
| **Coste mensual** ⚠️ | Metricool Advanced ~$67 (multi-marca) o Sprout $249-499/asiento + Listening $999 | Ayrshare $149-599 (50 perfiles ≈ $579) + n8n (self-host gratis) + dashboard. **X aparte en ambos** |
| **Tiempo a primer resultado** | **Días-semanas** | Semanas-meses (construir flujos) |
| **Encaje "software + MCP + IA"** | Parcial | **Completo** — lo que pediste |
| **Control de datos/credenciales** | Del proveedor | Mayor (Ayrshare abstrae tokens; n8n en infra de Keni) |
| **Mantenimiento** | Mínimo | Medio (Keni opera los flujos) |
| **Encaje restricciones AMX** (máquinas bloqueadas, sin admin, IT fuera) | Bueno (SaaS desde navegador) | Bueno **si Keni hospeda** (no depende de máquinas/IT de AMX) |
| **Multi-marca** (≈7 marcas × plataformas) | Buena | **Muy buena** (perfiles por marca) |
| **Integra el contexto editorial (§2)** | No directamente | **Sí** (n8n llama a la Skill de copy) |

**Veredicto:** entrar por **A** para validar rápido sin tocar máquinas bloqueadas; **evolucionar a B**, que es donde el contexto editorial (§2) se enchufa al flujo de publicación y se cumple la "mezcla software + MCP + IA". **C (self-hosted)** se aparca salvo que seguridad corporativa lo imponga y haya DevOps.

> **MCP, sin hype:** hoy estable para **redactar + programar + leer métricas** conversando (Ayrshare MCP el más maduro). **No** apto para publicar autónomo en vivo. Encaja con lo ya sembrado: *"el MCP tiene las claves, no la IA — un código temporal de tu casa, no la llave."*

---

## 6. Credenciales y seguridad (lo que pediste explícito)

**Regla base: nunca compartir contraseñas en crudo. Todo por delegación de acceso.**
1. **OAuth 2.0** en todo: la red emite *tokens*, nadie cede contraseña.
2. **FB/IG/Threads → Meta Business Manager:** roles por persona; **Keni entra como Partner**, no con login. SSO (Okta/Cerby) si América Móvil lo requiere.
3. **Ayrshare** abstrae tokens por marca (*User Profile* + JWT) → el equipo nunca toca credenciales.
4. **Lo irreducible** (API keys de X, Google Cloud) → **1Password/Bitwarden** con rotación.
5. **Rotación:** tokens long-lived de Meta caducan ~60 días → que lo gestione la herramienta.

Conecta con dos cosas ya instaladas: la **postura de privacidad de Keni** ("prohibido guardar en memoria"; "si dudas, no pegues") y el marco del **"psicópata"**. Resuelve además la preocupación real de José sobre la cuenta de empresa compartida. Hoy el equipo **no tiene gestor de contraseñas** y comparte cuentas → es un quick-win de seguridad por sí solo.

---

## 7. Cómo encaja con la Sesión 4 y el piloto

- **La sesión es la Capa 1, recentrada:** cada community/copy construye **su Skill de producción de copy** sobre el contexto editorial (§2). Resultado tangible el mismo día, sin conectar ni comprar nada.
- **El make-or-break es Tescu:** si su copy sale en su voz y lo acepta como suyo, se rompe la resistencia (*"es mi toque final"*) y el piloto demuestra valor con el caso más difícil.
- **Promesas pendientes que la S4 debe honrar:** (a) **simplificar el setup de terminal** (atasco #1 del grupo en S3); (b) explicar **MCP / "cómo dar permisos y contraseñas"** como puente a la última milla; (c) **tope de tokens** antes de flujos reales.
- **Coherencia con el estilo de Mikel:** demostrar primero, casos reales de ellos, analogías, honestidad sobre límites. Demostrar los límites de las APIs **en vivo**, no de memoria (en S3 hubo imprecisiones).
- **No dejar caer la idea 3** ("saber cuándo creerle"): va embebida en el **checklist de verificación** de cada Skill de copy (caso José). Automatizar la producción es el mejor terreno para enseñar cuándo creerle.
- **Lectura organizativa (Bernardo):** al liberar horas hay que **rediseñar el reparto hacia lo creativo/calidad**. Keni puede acompañar esa estrategia de transformación del departamento — es la conversación de mayor valor más allá del piloto.

---

## 8. Decisiones abiertas y qué verificar

1. **Cotizar el volumen real de X** y su coste (§4) — puede condicionar toda la estrategia en esa red. ⚠️
2. **¿Quién hospeda la Capa 2?** Si Keni (recomendado, evita el bloqueo de IT/máquinas de AMX), confirmarlo.
3. **Identificar "CCB"** (fuente de datos que Mariana cruza con Meta) — para automatizar su reporte sin la inconsistencia actual.
4. **Confirmar plataformas reales por marca** (¿Threads? ¿TikTok en todas?) y **nº de posts/día** por red — define topes de API y coste.
5. **Cuentas Business en Meta + estado de App Review** — sin Business no hay publicación por API; el App Review tarda, conviene iniciarlo pronto si se va a Capa 2.
6. **Mapear a Roger** (Claro Sports, no entrevistado) — previsiblemente misma Skill de copy que Tescu/Luis.

---

*Documento de exploración (Rev. 2). Siguiente paso natural: si se valida la dirección, (a) preparar el runbook de la Sesión 4 centrado en la Skill de producción de copy + contexto editorial, con el caso Tescu como prueba; y (b) un mini-piloto de la Opción A para la última milla.*
