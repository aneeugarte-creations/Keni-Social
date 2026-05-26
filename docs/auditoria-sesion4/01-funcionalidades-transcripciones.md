# Auditoría Sesión 4 — Funcionalidades extraídas de transcripciones

> Documento producido por análisis de las transcripciones de la Sesión 4 (mañana y tarde, 25 may 2026).  
> Fuentes consultadas:
> - `Mikel-Sesion4-limpio.md` (transcripción editada, mañana)
> - `Mikel-Sesion4.txt` (raw, mañana — confirmación)
> - `Mikel-sesion-4-tarde.txt` (raw, tarde)
> - `Sesion4-guion.md` (guion planificado — contexto, no evidencia de ejecución)
>
> Metodología: cada funcionalidad se cita con la fuente y franja donde aparece. "Mencionada" = solo se habló de ella; "Demostrada en vivo" = Mikel la mostró funcionando en la consola durante la sesión; "Construida en sesión" = se pidió y Claude la generó en tiempo real dentro de la clase; "En guion / planificada" = aparece solo en el guion prospectivo, no se confirma en transcripción.

---

## MÓDULO: `consola/` (keni-consola)

### F-C-01 · Generador de copy multi-plataforma desde nota

**Descripción:** El usuario pega el texto de una nota periodística (o su URL). La consola construye automáticamente un prompt usando el skill `copy-desde-nota` y lanza `claude -p` en segundo plano. Devuelve copy listo para publicar en X/Twitter, Instagram, Facebook, TikTok y YouTube (metadatos). Cada red tiene su pestaña/vista con la pieza final.

**Estado según transcripción:** Demostrada en vivo (mañana).

**Sesión/franja:** Mañana — sección "Demo: generar copy desde una nota".

**Cita:** *"Vamos a generar una nota para todas las redes: X, Instagram, Facebook, TikTok, YouTube. En YouTube serán metadatos. Aquí podemos ver el prompt que genera: lo que hace el software es crear un prompt automático de la nota. Usa 'copy desde nota', que es un prompt específico."*

**Detalles y reglas:**
- Las redes soportadas en demo: X, Instagram, Facebook, TikTok, YouTube.
- La consola muestra tokens (entrada/salida) y turnos en tiempo real mientras genera.
- El resultado va a la pestaña "publicaciones", una subpestaña por red.
- Se puede elegir generar solo para algunas redes (ej. "solo Twitter e Instagram").
- El prompt puede incluir extras: "no uses emojis", "genera para todas las redes".
- Se puede pegar texto plano o URL; texto plano funciona sin limpiar basura (la IA filtra).

---

### F-C-02 · Vista previa de publicación por red

**Descripción:** Para cada red, la consola muestra un preview visual de cómo se verá la publicación (simulación del tweet, del post de Instagram, etc.) antes de publicar.

**Estado según transcripción:** Demostrada en vivo (mañana).

**Sesión/franja:** Mañana — sección "Demo: generar copy desde una nota".

**Cita:** *"En Twitter veo la vista previa de cómo se vería el tuit con ese copy. En TikTok vería cómo sería el copy del vídeo si tuviera uno para poner."*

**Detalles:** Una previsualización exacta del formato final por plataforma. Se menciona también para Facebook con imagen adjunta.

---

### F-C-03 · Generación de copy desde fuentes RSS / feed de noticias

**Descripción:** La consola está conectada a fuentes RSS externas (ej. El País). Al llegar una noticia, el usuario la selecciona del feed y con un clic genera copy para las redes que elija, con la voz de la marca correcta.

**Estado según transcripción:** Demostrada en vivo (mañana).

**Sesión/franja:** Mañana — sección "Software, workflows y agentes".

**Cita:** *"Desde 'fuentes', por ejemplo, le he conectado El País por RSS. Me voy a El País y esta mañana ha publicado: 'Sheinbaum aclara que...' Me gusta la noticia: 'genera copy para UnoTV, solo para Twitter; no quiero YouTube, solo Twitter e Instagram'. Le doy a generar y en dos minutos tengo la nota con nuestra voz."*

**Detalles:**
- Selector de marca destino (ej. UnoTV, Claro Sports).
- Selector de redes de destino.
- Fuentes configurables en "ajustes" (RSS, feeds de marca, feeds de país, AMX).
- Diseñado para el escenario de cobertura nocturna: "si a las 3 de la mañana surge una noticia y no podéis prestar atención, se genera con un clic."

---

### F-C-04 · Generación de imagen con IA integrada

**Descripción:** Desde la vista de publicación, el usuario puede solicitar que se genere una imagen para el post usando un proveedor de imagen IA conectado (OpenAI/DALL·E, Midjourney, u otros). La imagen se descarga y se coloca automáticamente en la publicación.

**Estado según transcripción:** Demostrada en vivo (mañana) — con reservas (requiere configurar el token del proveedor).

**Sesión/franja:** Mañana — sección "Imágenes, vídeo y publicar en las redes".

**Cita:** *"No: la genera, la descarga y la coloca automáticamente. Tú tienes que conectarlo todo previamente y darle al lápiz, al toque."*

**Detalles:**
- El proveedor se configura en "ajustes" con token (OpenAI en la demo).
- Posibilidad de conectar también la biblioteca de AFP: "coge la imagen de AFP; si no la encuentras, intenta generar una".
- Se menciona la posibilidad de insertar el logo de Claro Sports en PNG en esquina superior como overlay (ver F-C-06).

---

### F-C-05 · Nivel de esfuerzo de generación (effort level) configurable

**Descripción:** En la configuración, el usuario puede seleccionar el nivel de esfuerzo cognitivo que usa Claude al generar copy, hashtags y agentes: bajo, medio, alto, muy alto o máximo. Para copy rápido: bajo; para análisis estratégico: máximo.

**Estado según transcripción:** Construida en sesión en vivo (mañana).

**Sesión/franja:** Mañana — sección "Harness vs. LLM, agregadores y suscripciones".

**Cita:** *"Aquí está: 'esfuerzo de generación' (cuánto piensa la IA al generar copy, hashtags y agentes). Le puedo decir bajo, medio, alto, muy alto o máximo. Esta es una funcionalidad que me has pedido tú: a ver si la tenía... no la tenía, y ahora sí."*

**Detalles:** Permite "promptear al software en vez de promptear a la IA" cada vez. Equivalente al parámetro `--model` / thinking budget de la API de Claude.

---

### F-C-06 · Overlay de logo/marca en imágenes (determinista)

**Descripción:** En la generación de imágenes, se puede configurar que el logo de la marca (PNG) se inserte automáticamente en una posición fija (ej. esquina superior) de todas las imágenes, sin usar IA sino código determinista (librería Python tipo Pillow).

**Estado según transcripción:** Mencionada (mañana) + mostrada resultado en tarde (breaking de Guardiola).

**Sesión/franja:** Mañana — sección "Imágenes, vídeo y publicar en las redes" y "El breaking de Guardiola y por qué no se hace con IA".

**Cita (mañana):** *"Sí: una skill, un prompt. En las plantillas le puedes poner el logo de Claro Sports en PNG, que vaya siempre a la esquina superior."*

**Cita (tarde):** *"Ha usado Pillow, una librería de Python, un software capaz de acumular capas de fotos para crear la imagen: no ha utilizado IA para hacerla."*

**Detalles:**
- Distinción explícita: insertar PNG es proceso determinista (no IA); generar elementos creativos sí requiere IA.
- En demo del "breaking de Guardiola" se juntaron tres fotos (PNG + 2 JPG) en una imagen final.
- Se propone una pestaña específica de "generación de imágenes" donde gestionar todas las fuentes visuales y recursos.

---

### F-C-07 · Gestión de agentes por marca (multi-tenant)

**Descripción:** La consola permite crear agentes especializados por marca o unidad editorial. Cada agente es una carpeta con su `CLAUDE.md` propio, skills asignados y contexto diferenciado. Se pueden agregar sub-contextos (contratos, desarrollos en curso, etc.).

**Estado según transcripción:** Demostrada en vivo (tarde).

**Sesión/franja:** Tarde — sección final sobre agentes y arquitectura de carpetas.

**Cita:** *"Aquí es que puedas crear agentes que van... Un agente realmente es una carpeta con un contexto permanente. Entonces, yo puedo crear aquí el agente de Claro Sports Golf.tv que tenga un CLAUDE.md nuevo, específico de Golf.tv, que además puedo añadirle subcontexto, puedo añadirle más ficheros, más información de procesos."*

**Detalles:**
- Marcas mencionadas en demo: UnoTV, Nación Gamer, Claro Sports, Claro Sports Golf.tv, Piso 15.
- Agentes comparten skills/herramientas comunes pero tienen contexto editorial diferenciado.
- Las carpetas de agentes pueden vivir en Google Drive compartido para acceso de equipo.

---

### F-C-08 · Dashboard de consumo de tokens y ejecuciones de agentes

**Descripción:** Panel de control que muestra cuántos tokens han consumido los agentes, cuántas ejecuciones han realizado y con qué frecuencia, para monitorizar el gasto y la actividad del sistema.

**Estado según transcripción:** Mencionada y mostrada brevemente en demo (mañana).

**Sesión/franja:** Mañana — sección apertura de la demo.

**Cita:** *"Le hemos puesto también un dashboard de consumo de tokens, de ejecuciones, de cuántos agentes han ejecutado y cuántas veces, para revisar un poco lo que hacen todos nuestros agentes."*

**Detalles:** En la demo se muestran tokens en tiempo real (entrada/salida) durante la generación. El dashboard completo incluye histórico de ejecuciones.

---

### F-C-09 · Gestión de credenciales / tokens de acceso a redes

**Descripción:** Sección de configuración donde el usuario puede añadir, gestionar y revocar tokens de acceso a plataformas externas (Meta, X, TikTok, YouTube, Gmail, etc.) sin exponer la contraseña real. El sistema usa acceso delegado por token.

**Estado según transcripción:** Demostrada en vivo (tarde, explicación detallada del flujo OAuth/token).

**Sesión/franja:** Tarde — sección sobre tokens y acceso delegado.

**Cita:** *"En ajustes, busco tokens o accesos... aquí me puedo crear un token de acceso. Un token normalmente es un churro así de letras. Se le pega aquí y se le da a conectar y ese token es válido para hacerse pasar por ti en tu red social hasta que invalides el token sin tener que cambiar la contraseña."*

**Detalles:**
- Modelo explicado en sala: "acceso delegado" — no das contraseña, das código temporal.
- Se puede generar un token por marca (ej. UnoTV y Claro Sports son tokens distintos).
- Se demostró cómo obtener token de Gmail vía Google Cloud Console (paso a paso).
- La IA usa el token que ya está en el software; nunca ve la contraseña.
- Un token revocado obliga a generar uno nuevo.

---

### F-C-10 · Publicación automática en redes (con limitaciones de plataforma)

**Descripción:** Capacidad de publicar directamente en redes sociales desde la consola, sujeta a que la plataforma permita la publicación automática vía API (proceso de review de Meta, acuerdo con la red).

**Estado según transcripción:** Mencionada como objetivo futuro / semana 2, no disponible aún (mañana y tarde).

**Sesión/franja:** Mañana — sección "Imágenes, vídeo y publicar en las redes"; tarde — sección de publicación y Echobox.

**Cita (mañana):** *"Publicar tiene sus límites, porque las plataformas te limitan la publicación automática. [...] La idea sería que vosotros paséis la aplicación por el review de Meta para que os dejen publicar automáticamente."*

**Cita (tarde):** *"Que te avise, porque, de momento, el tema de publicar las redes sociales están un poco con las manos escondidas."*

**Detalles:**
- Metricool y Echobox ya tienen acuerdos con redes; se puede usar licencia existente de esas herramientas.
- Las cuentas de Piso 15 ya están en Metricool; se propone conectar la consola a Metricool.
- Posibilidad de "publicar con aprobación humana" como paso intermedio (mencionado para semana 2).

---

### F-C-11 · Buzón de sugerencias con auto-desarrollo

**Descripción:** Campo en la consola donde cualquier miembro del equipo puede escribir una sugerencia de funcionalidad. El buzón lanza automáticamente un prompt que hace que la aplicación se auto-desarrolle incorporando la sugerencia.

**Estado según transcripción:** Mencionada / en visión (mañana y tarde).

**Sesión/franja:** Mañana — sección "El breaking de Guardiola y por qué no se hace con IA"; tarde — sección final.

**Cita (mañana):** *"Tengo una aplicación con un cajón de sugerencias, y el cajón mismo lanza un prompt con esa sugerencia y se pone a hacerlo; para cuando te das cuenta, ya tiene implementada la sugerencia en la propia herramienta. Herramientas de autodesarrollo."*

**Cita (tarde):** *"Pongo un buzón de sugerencias en la aplicación y todo lo que escribáis en el buzón de sugerencias automáticamente se convierte en un prompt que pasa a diseñarse, que pasa a desarrollar la aplicación por sí misma."*

**Detalles:** Relacionado con la arquitectura de auto-mejora. No se demostró en vivo, solo se describió como funcionalidad existente en proyectos previos de Mikel.

---

### F-C-12 · Módulo de fuentes de noticias (agregador configurable)

**Descripción:** Sección de la consola para gestionar las fuentes de información que alimentan la generación de copy: RSS de medios externos, feeds de la marca, cuentas de redes sociales, tendencias de Google/X, etc.

**Estado según transcripción:** Demostrada en vivo (mañana — RSS El País).

**Sesión/franja:** Mañana — sección "Software, workflows y agentes".

**Cita:** *"Desde 'fuentes', por ejemplo, le he conectado El País por RSS."*

**Detalles:**
- Fuentes usadas o mencionadas: RSS de medios (El País, etc.), Google News, Google Trends MX, feeds de marca AMX, X (de pago — tier de pago), TikTok Trends (requiere auditoría TikTok).
- Se pueden añadir fuentes de la biblioteca interna de imágenes (AFP).
- Evaluación honesta de Mikel (vía Claude) en sala: feed gratis de noticias + trends es viable; curación social completa de X y TikTok no es totalmente automatizable aún.

---

### F-C-13 · Plantillas reutilizables de post (templates)

**Descripción:** La consola permite guardar y gestionar plantillas de publicación (artes, portadas, formatos) que se aplican automáticamente al generar el copy, para mantener consistencia visual por marca.

**Estado según transcripción:** Mencionada y mostrada brevemente en demo (mañana).

**Sesión/franja:** Mañana — sección "Demo: generar copy desde una nota".

**Cita:** *"Le puedo agregar templates o artes para que siempre salga con la portada, plantillas, fuentes, de todo. Como es tuyo, haces lo que quieras. Aquí tienes plantillas de post reutilizables."*

**Detalles:** Cada plantilla puede incluir recursos gráficos (PNG de logo, colores de marca, tipografías). Conectado con F-C-06 (overlay de logo).

---

### F-C-14 · Skill "Brief Matutino" (rastreo de tendencias + jerarquización)

**Descripción:** Skill que, dado un conjunto de parámetros (marca, temas a vigilar, ventana de frescura en horas, señales ya vistas en redes, agenda del día), busca noticias en Google News/Trends, las jerarquiza por relevancia y frescura, y devuelve una lista con título, tema y sugerencia de formato (carrusel, imagen, nota, vídeo) por pieza.

**Estado según transcripción:** Construida en sesión en vivo (mañana) y reutilizada en tarde.

**Sesión/franja:** Mañana — sección "'Carta a los Reyes' en directo (1 y 6)"; tarde — sección inicial.

**Cita (mañana):** *"'Buena carta a los Reyes, y muy aterrizada [...] Es viable: el skill 'resumen-tendencia' más la ingesta de redes sociales o de RSS desde la consola hace buena parte de lo que pides.' [...] 'Pieza por pieza, noticias web: propuesta concreta, un skill 'brief matutino'."*

**Parámetros de invocación (demo en vivo):**
- Marca: UnoTV
- Temas a vigilar: Sheinbaum, mundial
- Ventana de frescura: 6 horas
- Señales vistas en redes: Irán, Tijuana
- Agenda del día: no disponible

**Resultado demo:** Listado con 7-9 noticias jerarquizadas (Sheinbaum-Irán, Rusia-Ucrania, Gaza, Fidalgo+Quiñones, hoteleros/mundial, ciberataques/mundial, etc.) con marca de "fuera de marca" para piezas no relevantes (Switch 2, PlayStation 5 → Nación Gamer).

**Detalles:**
- Ventana de frescura configurable (se mencionó 6 horas en demo, 2 días en tarde).
- Evaluación de limitaciones: Google Trends MX viable; curación de X (de pago) y TikTok = "parte difícil y honesta"; vídeo = fuera de alcance automatizable.
- En tarde: misma skill usada para brief de UnoTV con Diana, con parámetros: todo tipo de temas, señales Irán/mundial, Gaza, Ucrania-Rusia, y al menos una nota nacional.

---

### F-C-15 · Skill "Termómetro Mundial" (resumen de noticias internacionales)

**Descripción:** Skill que genera automáticamente un post tipo "termómetro" con las 5-8 noticias internacionales más importantes del día, una por slide/sección, listo para publicar como carrusel. Incluye el copy armado de cada noticia.

**Estado según transcripción:** Construida en sesión en vivo (tarde).

**Sesión/franja:** Tarde — sección donde Diana describe el formato.

**Cita:** *"El termómetro es un posteo que hacemos que se llama 'termómetro mundial' porque abarcamos de cinco a ocho notas más importantes internacionales de coyuntura. [...] Se podría meter directamente en prompt para que diario a las siete de la mañana ya estén jerarquizadas las cinco noticias o las ocho noticias más importantes internacionales para un posteo, igual ya con el copy armado."*

**Detalles:**
- Formato: presentación/carrusel con un slide por noticia internacional.
- Horario objetivo: listo antes de las 7:00 AM.
- Copy armado por pieza (no solo link).
- Se mostró el resultado generado en la consola durante la tarde (sección "A ver si está ya el del deck").

---

### F-C-16 · Skill "Reporte Semanal Deportes" (deck/presentación)

**Descripción:** Genera automáticamente el reporte semanal de Claro Sports en formato presentación, con: mejores 3 publicaciones por plataforma (Instagram, TikTok, Facebook) por visualizaciones e interacciones, posteos de Claro Sports TV y Claro Sports Golf de esa semana, y agenda editorial de la siguiente semana (principales eventos deportivos + cómo se cubrirán).

**Estado según transcripción:** Construida en sesión en vivo (tarde).

**Sesión/franja:** Tarde — sección inicial "Carta a los Reyes" (reporte de Elías).

**Cita:** *"El reporte como tal lleva las mejores tres publicaciones de Instagram, las mejores tres de TikTok y las mejores tres de Facebook, basado en visualizaciones e interacciones. [...] Después vienen algunos posteos de Claro Sports TV y Claro Sports Golf [...] Y también los temas editoriales que vienen para esta semana."*

**Detalles:**
- Formato de salida: presentación (originalmente Canva; en demo se generó en la consola; se menciona posible exportación a PowerPoint).
- Fuentes de datos: Drive interno (métricas manuales del equipo) + métricas conectadas cuando estén disponibles.
- Eventos deportivos: fútbol, tenis, básquetbol, béisbol, transmisiones propias (no programas).
- Se mostró resultado parcial en sala (vista previa con datos de demo).

---

### F-C-17 · Skill "Rastreo de Virales"

**Descripción:** Skill específico para identificar contenido viral relevante en redes (que no necesariamente es nota periodística), antes de que se convierta en nota. Permite al CM capturarlo con ventaja frente a otros medios.

**Estado según transcripción:** Mencionada / pedida (tarde); no construida en sesión.

**Sesión/franja:** Tarde — sección de Diana complementando el brief matutino.

**Cita:** *"Rastreo de virales, sí. Porque hay muchos que no son nota. Entonces, nosotros los agarramos antes de que son nota."*

**Detalles:**
- Distinción de "brief matutino" (noticias formales) vs. "rastreo de virales" (contenido no-nota que está subiendo).
- No se construyó en sesión; Mikel confirmó que se haría "esta semana que viene, los siguientes cinco días".

---

### F-C-18 · Monitoreo de publicaciones comerciales / reportes de cliente

**Descripción:** Módulo separado (no mezclado con el rendimiento editorial general) para hacer seguimiento del rendimiento de publicaciones pagadas o de campañas de clientes específicos (Zucaritas, Chihuahua, etc.). Permite monitorear alcance e interacciones de una publicación específica, generar el reporte de cliente cuando se solicite, y detectar cuándo una publicación pagada ha alcanzado su KPI para pausarla.

**Estado según transcripción:** Pedida y especificada en detalle (tarde); Mikel confirmó viabilidad. No construida en sesión.

**Sesión/franja:** Tarde — sección de métricas comerciales.

**Cita:** *"Nosotros tenemos que estar monitoreando constantemente el rendimiento de una publicación comercial. [...] Creo que deben de ser apartados diferentes para que no se mezclen de información. [...] Por ejemplo, ahorita que empezamos un reporte que entregar de una publicación de Zucaritas, yo tengo que entregar específicamente el rendimiento de esa publicación."*

**Detalles:**
- Apartado propio, diferenciado del dashboard editorial general.
- Funciones: añadir manualmente el link de una publicación a monitorear; consultar en cualquier momento; generar reporte al pedirlo.
- Casos de uso: campañas de clientes con KPI determinado (pausar cuando alcanza alcance), y campañas sin KPI (monitoreo continuo para el reporte).
- Marcas/clientes mencionados: Zucaritas, campaña de Chihuahua.

---

### F-C-19 · Gestión de pendientes con barra de estatus

**Descripción:** Sistema de gestión de tareas del equipo donde se anotan los pendientes con estados (título pendiente, copy pendiente, enviado a diseño, enviado a editor de vídeo, publicado), para evitar duplicar trabajo entre turnos y eliminar la necesidad de emails de coordinación.

**Estado según transcripción:** Pedida y especificada (tarde); no construida en sesión.

**Sesión/franja:** Tarde — sección de Diana sobre coordinación de flujo.

**Cita:** *"Para que no se repita luego de la mañana, que se repita en la tarde, pero porque no checamos, porque no he tenido tiempo [...] Los pendientes anotarlos y que se puedan compartir entre los usuarios y poner un estatus de cómo va, en qué va, si ya tiene título, si ya tiene copy, a qué editor de vídeo se le pidió, a qué diseñador se le pidió."*

**Detalles:**
- "Un Monday también", en referencia a gestión de proyectos.
- Compartido entre usuarios del mismo equipo.
- Evita el "almacén de contexto" perdido cuando alguien no leyó el mail.

---

### F-C-20 · Skill "Predicción de tendencias / breaking anticipado"

**Descripción:** Herramienta que, a partir de contexto conocido (agenda pública, eventos programados, patrones históricos), genera predicciones de qué temas van a explotar en tendencia, con preparación previa de copy y materiales para publicar primero cuando ocurra.

**Estado según transcripción:** Mencionada/pedida (mañana y tarde); no construida.

**Sesión/franja:** Mañana — sección "'Carta a los Reyes' en directo (3)" y tarde — sección de predicción de contenido.

**Cita (mañana):** *"La mía era similar a la suya: que detectara, que hiciera una predicción de algún contenido que pudiera llegar a ser tendencia o viral, y que lo propusiera día con día."*

**Cita (tarde):** *"Que la guía ya sea capaz de predecir qué es lo que puede ir saliendo si de repente, pues eso, quien esté en el gobierno se junta con Trump. O cosas así, para que ya, o se va a juntar X día a X hora y tal, y ya pues prepare todo para ese día, para que seáis los primeros en lanzar."*

**Detalles:**
- Relacionado con "breaking express" (tener copy pre-preparado para eventos previsibles).
- La IA no es emocional, pero sí analiza patrones: "sabe que el mundial tiene más impacto que la liga mexicana."
- Precondición de calidad: alertas contextualizadas por marca (deporte ≠ política ≠ viral social).

---

### F-C-21 · Verificador de vídeos virales (fact-check de antigüedad)

**Descripción:** Skill / módulo que, dado el enlace de un vídeo en redes, determina si el vídeo es nuevo o ya circuló anteriormente (con fecha estimada), para evitar publicar contenido que ya es viejo disfrazado de nuevo.

**Estado según transcripción:** Construida en sesión en vivo (mañana), aunque con limitaciones de acceso detectadas en demo.

**Sesión/franja:** Mañana — sección "'Carta a los Reyes' en directo (4): verificar vídeos virales" y "Verificar el vídeo: el muro de la detección de IA".

**Cita:** *"Una aplicación que permita verificar si un vídeo viral es verdaderamente nuevo o ya circuló hace años. Frecuentemente nos pasan un vídeo viral de no sé qué y resulta que era de hace diez, cinco o tres años."*

**Detalles:**
- Invocación: pegar enlace del vídeo → devuelve si ya circuló y desde cuándo.
- En demo se intentó con un enlace de Instagram → falló por muro de login (Instagram requiere sesión iniciada).
- Herramientas de referencia investigadas en sesión: ClaimBuster, Misinfo Bot, Blocky, Open Fact Verification, Veracity, Open Fact Check.
- Plataformas más útiles para rastreo: YouTube (conserva metadata de fecha), Instagram, X, TikTok.
- Posibilidad de añadir detección de IA generativa, con advertencia explícita: "la IA solo puede predecir si está hecho con IA, no lo sabe a ciencia cierta."
- El skill existe en el catálogo del proyecto (`verifica-video`) pero en demo no fue encontrado automáticamente al primer intento.

---

### F-C-22 · Respuesta y moderación de comentarios

**Descripción:** Dos casos: (1) triaje de mensajes entrantes de la Fundación (clasificar intención: silla de ruedas, beca, torneo, etc.) y proponer respuesta en voz de marca; (2) moderación en vivo de comentarios de YouTube durante eventos en directo (detectar bots, groserías, tóxicos).

**Estado según transcripción:** Especificada y confirmada como "diseñada" (mañana); Mikel la envió a integrar en la consola durante la sesión.

**Sesión/franja:** Mañana — sección "'Carta a los Reyes' en directo (5)".

**Cita:** *"'Triaje de mensajes entrantes de la Fundación: llegan muchísimos y cada uno es una intención distinta —silla de ruedas, beca, inscripción a torneo—. Moderador en vivo de los comentarios de YouTube durante México Siglo XXI, el evento anual: tratar bots, groserías y tóxicos en el directo'. El caso 1: viabilidad alta. El caso 2: viabilidad media-alta."*

**Detalles:**
- Caso 2 (moderación en directo): avisos sobre cuota de API de YouTube y que YouTube ya hace parte nativa.
- Se requiere verificar fecha, canal, acceso, y volumen pico del evento antes de comprometer.
- Mikel envió a Claude que integre "una pequeña versión de eso en la aplicación".

---

### F-C-23 · Transcripción de vídeo/audio a copy (clip a copy)

**Descripción:** Skill que acepta un vídeo o audio (entrevista, declaración, podcast, cobertura, clip) y genera automáticamente: transcripción en local con Whisper, mejores citas con marca de tiempo, y copy listo para publicar en todas las redes con voz de marca, voz personal, tropicalización mexicana y auto-verificación.

**Estado según transcripción:** Demostrada en vivo (mañana) + mencionada/robustecida (tarde).

**Sesión/franja:** Mañana — sección "Skills: editar el prompt y la voz de marca"; tarde — sección de automatización de carpeta de vídeos.

**Cita (mañana):** *"El skill 'clip a copy' lo podemos ver aquí: convierte un vídeo o audio —entrevista, declaración, podcast, cobertura— en copy listo para publicar, por plataforma, para las marcas de AMX. Transcribe en local con Whisper."*

**Cita (tarde):** *"Con lo que dijiste, podríamos automatizar que cuando se cargue un vídeo a cierta carpeta, se transcriba, se procese toda esa información, y se generen copies y metadatas, para publicar en cada una de las redes, optimizado a SEO y optimizado a cada una de las plataformas sociales."*

**Detalles:**
- Whisper corre en local (audio no sale de la máquina).
- Extrae mejores citas con timecodes para cortar el clip.
- Optimización SEO por plataforma mencionada en tarde.
- Caso de uso específico: Piso 15 podcast → metadatos de YouTube de todos los clips.
- Propuesta tarde: trigger automático cuando se deposita un vídeo en una carpeta específica.

---

### F-C-24 · Generador de contenido Evergreen (calendario anual)

**Descripción:** Herramienta que genera contenido evergreen cruzando efemérides/datos históricos con el nicho de la marca, para fechas del año. Produce copy y sugiere formato de forma semi-automática.

**Estado según transcripción:** Mencionada/pedida (tarde); no construida.

**Sesión/franja:** Tarde — sección de contenidos alternativos Piso 15.

**Cita:** *"Lo que se le puede pedir es que haga como un tipo calendario anual, que cruce con efemérides o datos importantes históricos, que generen contenido Evergreen para esas fechas."*

**Detalles:**
- Casos de uso: Piso 15 (lucha libre, historia de la lucha), UnoTV (tecnología, ciencia, historia).
- Se puede hacer petición semanal o mensual en lugar de calendario completo.
- "Para Evergreen es muy fácil, porque no tienes que estar al día de tendencias."

---

### F-C-25 · Bot de ingestión vía Telegram/WhatsApp

**Descripción:** Bot que recibe material (vídeo, texto, audio) por Telegram o WhatsApp, lo pasa al flujo de procesamiento de la consola (monta pleca, genera copy, etc.) y devuelve el resultado listo para publicar.

**Estado según transcripción:** Mencionada (mañana); no construida.

**Sesión/franja:** Mañana — sección "Automatizar el flujo: pleca, bots y cobertura al momento".

**Cita:** *"Si te lo mandan por Telegram, por ejemplo, podrías tener un bot que lo pasa a tu proceso, lo hace automático y lo publica también automático. Puede llegar a recibirlo un bot, hacer el proceso y publicarlo sin que tú siquiera sepas que ha llegado la nota."*

**Detalles:**
- Telegram preferido sobre WhatsApp (WhatsApp requiere número de teléfono específico).
- Caso de uso: cobertura al momento, pleca de vídeo recibida del reportero.
- Flujo descrito: recibe material → aplica pleca → envía a revisión o publica directamente.

---

### F-C-26 · Procesamiento inteligente de imágenes para formato 4:5 y resize

**Descripción:** Herramienta para fotógrafos de campo que recibe una imagen original y produce: (a) versión en formato full con peso comprimido configurable (< 3 MB por defecto, seleccionable), y (b) versión en formato 4:5 para Instagram donde, si la imagen no cabe, extiende el fondo de forma inteligente (determinista para bandas uniformes —cielo, negro—; IA generativa solo si el borde es irregular), sin modificar sujetos ni elementos principales.

**Estado según transcripción:** Construida en sesión en vivo (tarde) — Mikel estaba haciendo las preguntas de especificación en tiempo real y generando la funcionalidad.

**Sesión/franja:** Tarde — sección de Ale (fotógrafa de campo).

**Cita:** *"Para que la foto quepa en 4:5 sin cortar al sujeto, ¿cómo prefieres extender el fondo? [...] Si es irregular, que use IA, ¿no? [...] Para el formato full, conservando el tamaño original, ¿a qué peso objetivo quieres que comprima cada imagen?"*

**Detalles:**
- Flujo de extensión de fondo: automático con preview; el usuario aprueba solo cuando es necesario.
- Peso configurable para formato full (default ~3 MB; seleccionable por caso).
- No modifica jugadores, retratos ni elementos principales.
- Extensión de cielo: clona/estira si es uniforme; IA solo si el borde no es uniforme.
- Tiempos de subida en eventos masivos (internet lento) justifican la compresión de peso.
- Caso de uso: Ale recibe fotos en RAW, las necesita en dos formatos.

---

### F-C-27 · Skill "Breaking Express" (pieza rápida con overlay desde foto)

**Descripción:** A partir de una o varias fotos + prompt de copy, genera una pieza visual de breaking news aplicando el overlay de marca (logo, texto) de forma determinista y rápida.

**Estado según transcripción:** Demostrada en vivo (mañana) — caso Guardiola.

**Sesión/franja:** Mañana — sección "El breaking de Guardiola y por qué no se hace con IA".

**Cita:** *"'El breaking express ya está en Keni Social.' [...] Le he dicho las tres fotos; él sabe cuál es cuál, porque puede leerlas. Ha usado Pillow, una librería de Python, un software capaz de acumular capas de fotos para crear la imagen."*

**Detalles:**
- Input: fotos (PNG + JPG) + brief de la noticia.
- Output: imagen compuesta con overlay de marca.
- No usa IA generativa para la composición; usa Pillow (Python) para la combinación de capas.
- Resultado actual: las tres fotos juntas. Pendiente de refinamiento: que saque el breaking con texto incrustado, portada bien compuesta.
- Tescu pidió ampliarlo: carrusel de varias fotos con textos adentro.

---

### F-C-28 · Integración con Adobe Photoshop / Premiere vía MCP

**Descripción:** Conectar la consola con Adobe Photoshop y/o Premiere Pro mediante servidores MCP de Adobe para automatizar edición de imagen y vídeo.

**Estado según transcripción:** Mencionada como posibilidad técnica (mañana).

**Sesión/franja:** Mañana — sección "Automatizar el flujo: pleca, bots y cobertura al momento".

**Cita:** *"Existen implementaciones de servidores MCP —conectores de IA— que permiten a asistentes como Claude integrarse con Adobe Photoshop y Premiere."*

**Detalles:** Solo mencionado como posibilidad. No se demostró ni construyó. Requiere la existencia del MCP oficial de Adobe.

---

### F-C-29 · Generador de titulares (múltiples versiones + votación)

**Descripción:** Para una nota o post, genera múltiples versiones de titular o cabecera, con diferentes ángulos, para que el equipo vote o un agente seleccione el mejor. Permite pruebas a escala imposible de hacer manualmente.

**Estado según transcripción:** Mencionada como capacidad del sistema (tarde).

**Sesión/franja:** Tarde — sección sobre titulares que "venden sin clickbait".

**Cita:** *"Puedes diseñar hasta sistemas de votación, donde cree 19 versiones o 20 y entre varios votéis y se coja la que más engancha, hacer pruebas. Si tú tienes el prompt que pide el copy o la cabecera para una nota, puedes pedirle que te genere 100 versiones y que luego lance agentes con diferentes ángulos como diferentes personas a votar."*

**Detalles:**
- Votación de equipo (humanos) o votación de agentes simulando perspectivas.
- Escenario final: de 100 generadas, 10 mejores → votan 10 personas reales.
- Criterio explícito de los CM: titulares que "vendan pero sin clickbait".

---

### F-C-30 · Reutilización de contenido de archivo (evergreen de virales)

**Descripción:** Herramienta que sugiere periódicamente retomar vídeos o piezas del archivo propio que fueron relevantes en su momento y pueden re-publicarse como contenido retro/de archivo.

**Estado según transcripción:** Mencionada (tarde).

**Sesión/franja:** Tarde.

**Cita:** *"En algún momento nos pidieron algo, un contenido de archivo, de videos virales, pero que ya tienen tiempo de retomarnos. O sea, como en otros medios que se tienen, 'te acuerdas de él y salen'."*

**Detalles:** Caso de uso: "Pasó con Fofo un martes." Reutilizar con frame de "se reviralizó" o "en este día de hace X años."

---

## MÓDULO: `skills-copy/`

### F-S-01 · Skill "copy-desde-nota" (skill central de copy editorial)

**Descripción:** Skill principal que convierte una o varias notas fuente, o una transcripción de clip, en copy listo para publicar. Define la voz de la marca, las reglas editoriales, los pasos de generación, las restricciones (no inventar datos, verificar fuentes, formato por red, etc.) y el checklist de auto-verificación final.

**Estado según transcripción:** Demostrada en vivo (mañana) + editada en sala.

**Sesión/franja:** Mañana — sección "Skills: editar el prompt y la voz de marca".

**Cita:** *"Aquí le dice: 'convierte una o varias notas fuente, o una transcripción de clip, en copy listo para publicar. Eres el redactor de redes de AMX Contenido...'. La salida siempre empieza por este bloque, arriba del todo, antes del copy."*

**Reglas explícitas en la skill (citadas en sesión):**
- "Nunca inventes datos, cifras ni fechas."
- "Si la voz personal está vacía, usa la de la marca y avísalo."
- "No simules una voz que no existe."
- "Respeta estrictamente el límite de caracteres."
- "Autoverifica todas las fuentes que referencias."
- "Cuando termines, no lo publiques, pídele al humano que lo apruebe."
- CTA específico por plataforma: Twitter (call to action), Instagram (carrusel de 7 fotos), YouTube (solo metadata).

**Detalles:**
- La skill es el "prompt que funciona del Día 3, empaquetado para no reescribirlo nunca más."
- Se puede editar completamente desde la consola (editor de skills inline).
- Se le pueden subir ejemplos: "estas son nuestras mejores notas, este es nuestro lenguaje."
- Estructura de la skill: instrucción + contexto editorial (CLAUDE.md) + recursos/ejemplos + checklist de verificación.

---

### F-S-02 · Skill "clip-a-copy" (de vídeo/audio a copy publicable)

**Descripción:** Skill que procesa vídeos, audios (entrevistas, podcasts, coberturas) y genera copy multi-plataforma con citas con timecodes. Ver también F-C-23. Aquí se documenta la skill en sí, no el flujo de la consola.

**Estado según transcripción:** Demostrada en vivo (mañana).

**Sesión/franja:** Mañana — sección "Skills: editar el prompt y la voz de marca".

**Cita:** *"'Clip a copy' [...] convierte un vídeo o audio —entrevista, declaración, podcast, cobertura— en copy listo para publicar, por plataforma, para las marcas de AMX. Transcribe en local con Whisper."*

**Detalles:**
- Whisper local → audio no sale de la máquina.
- Timecodes de mejores citas.
- Voz de marca + voz personal + tropicalización MX + auto-verificación.

---

### F-S-03 · Skill "resumen-tendencia" (skill de tendencias)

**Descripción:** Skill que resume tendencias del momento y las convierte en propuestas de contenido editorial. Base sobre la que se construyó "brief matutino".

**Estado según transcripción:** Mencionada como skill preexistente en el catálogo (mañana).

**Sesión/franja:** Mañana — respuesta de Claude al evaluar la "carta a los Reyes" de Lalo.

**Cita:** *"El skill 'resumen-tendencia' más la ingesta de redes sociales o de RSS desde la consola hace buena parte de lo que pides."*

**Detalles:** Skill base; "brief matutino" es una extensión natural de este.

---

### F-S-04 · Skill "nota-formato" (nota a formato de la casa)

**Descripción:** Skill que adapta una nota externa al formato y estilo de publicación propio de la marca. Parte de las skills precargadas de ejemplo.

**Estado según transcripción:** Mencionada como parte del catálogo de skills de ejemplo (mañana).

**Sesión/franja:** Mañana — sección de repositorio/backups.

**Cita:** *"Aquí están todas las skills (copy desde nota, nota-formato, etc.), guardadas en este repositorio externo."*

---

### F-S-05 · Skill "brief-matutino" (skill nueva construida en sesión)

**Descripción:** Ver F-C-14 para descripción completa. Aquí se documenta que existe como skill invocable con `/brief-matutino` (o similar).

**Estado según transcripción:** Construida en sesión en vivo (mañana).

**Sesión/franja:** Mañana — sección "'Carta a los Reyes' en directo (6)".

**Cita:** *"La tuya, 'brief matutino', en skills no existe; vamos a experimentar [...] Está aquí el skill."*

---

### F-S-06 · Skill "verifica-video"

**Descripción:** Ver F-C-21 para descripción completa. Skill que verifica si un vídeo viral ya circuló antes.

**Estado según transcripción:** Construida en sesión (mañana), con limitación de acceso a Instagram.

**Sesión/franja:** Mañana — sección "Verificar el vídeo".

**Cita:** *"Vamos a ver dónde he metido 'verificar vídeo'. Aquí está. Vamos a probar este skill, 'verificar vídeo', para UnoTV."*

---

### F-S-07 · Ingeniería inversa de voz de marca desde archivo de publicaciones

**Descripción:** Capacidad de alimentar a la skill con el historial de publicaciones de la marca (las últimas mil notas, por ejemplo) para que la IA analice patrones, extraiga la voz editorial y actualice automáticamente las skills con esos patrones.

**Estado según transcripción:** Mencionada como capacidad disponible (mañana).

**Sesión/franja:** Mañana — sección "Skills: editar el prompt y la voz de marca".

**Cita:** *"Se puede hacer ingeniería inversa: 'estas son las últimas mil notas que hemos publicado; revísalas, saca patrones y actualiza las skills con los patrones de nuestra voz y de nuestro formato de publicación'."*

**Detalles:** Los CM también pueden subir ejemplos de sus mejores notas directamente como recursos en la skill.

---

### F-S-08 · Skill "publica-meta" (skill existente en el catálogo de Claude Code)

**Descripción:** Skill ya existente en el catálogo del proyecto keni-social para publicar en Meta. Se menciona de forma incidental al explicar cómo funcionan los skills.

**Estado según transcripción:** Confirmada como existente en el catálogo (mañana).

**Sesión/franja:** Mañana — sección "Vídeos difíciles, y qué es un skill".

**Cita:** *"Si busco 'context', veis que aquí en skills solo tiene la de 'publica meta'."*

---

## MÓDULO: `mcp-metricas/`

### F-M-01 · Conexión de métricas multi-plataforma vía tokens

**Descripción:** El servidor MCP de métricas acepta tokens de acceso de múltiples plataformas (Meta/Instagram/Facebook, YouTube, X, TikTok) para leer métricas reales de las cuentas de las marcas sin exponer contraseñas.

**Estado según transcripción:** Mencionada como objetivo técnico inminente (mañana y tarde); métricas de demo usadas en la sesión.

**Sesión/franja:** Mañana — sección "Foto con IA, logo y procesos deterministas"; tarde — sección de tokens.

**Cita (mañana):** *"Las métricas igual: si las conectamos a todas las redes, nos podríamos descargar las métricas, y serían de verdad."*

**Cita (tarde):** *"Para las métricas de YouTube, Meta, X y TikTok, simplemente crea una funcionalidad de que yo te pueda pegar aquí un token, un token es una clave de acceso para sistemas."*

**Detalles:**
- Un token por marca (UnoTV ≠ Claro Sports).
- Plataformas: YouTube, Meta (Instagram/Facebook), X/Twitter, TikTok.
- Los datos de demo en la sesión son ficticios; la arquitectura está lista para conectar datos reales.

---

### F-M-02 · Tool `listar_cuentas`

**Descripción:** Tool del MCP que lista las cuentas/marcas conectadas y disponibles.

**Estado según transcripción:** Mencionada en el guion como una de las 2-3 tools mínimas del MCP; no se demostró invocación explícita en sala.

**Sesión/franja:** Guion (planificada) + inferida de la demo de la consola.

---

### F-M-03 · Tool `metricas_resumen(rango)`

**Descripción:** Tool del MCP que devuelve un resumen de métricas para una marca en un rango de fechas: alcance, engagement, impresiones, etc.

**Estado según transcripción:** En guion como tool mínima. En sesión de mañana se menciona que el sistema revisa métricas para aprender qué posts funcionan mejor.

**Sesión/franja:** Guion + mañana — sección "Demo: generar copy desde una nota".

**Cita (mañana):** *"También le tengo dicho que, si tiene las métricas de la marca, las revise para ver qué posts tienen mejores métricas e intente usar patrones similares."*

---

### F-M-04 · Tool `mejores_piezas(rango)`

**Descripción:** Tool del MCP que devuelve las piezas con mejor rendimiento en un periodo dado (para retroalimentar la generación de copy con patrones de éxito y para el reporte semanal).

**Estado según transcripción:** En guion + mencionada en reporte semanal (tarde).

**Sesión/franja:** Guion + tarde — sección de reporte semanal.

---

### F-M-05 · Métricas con aprendizaje para mejorar copy

**Descripción:** El sistema cruza las métricas de rendimiento de publicaciones anteriores con los patrones de copy para que el generador aprenda qué estilos, formatos y mensajes funcionan mejor y los incorpore en futuras generaciones.

**Estado según transcripción:** Mencionada (mañana).

**Sesión/franja:** Mañana — sección "Demo: generar copy desde una nota".

**Cita:** *"Es también un sistema que va aprendiendo: a medida que mejoran los posts, coge la información de esos posts y usa ese lenguaje, esa marca, lo que sea."*

**Detalles:** Este es el puente conceptual entre MCP de métricas y skills de copy (Skill + MCP = flujo completo del guion).

---

## MÓDULO: Transversal / Arquitectura

### F-T-01 · Control de límite de turnos (max-turns)

**Descripción:** Parámetro configurable que limita cuántas iteraciones (turnos) puede hacer un agente antes de detenerse, para evitar bucles y gasto excesivo.

**Estado según transcripción:** Explicada conceptualmente y mostrada en la consola (mañana).

**Sesión/franja:** Mañana — sección "Demo: generar copy desde una nota".

**Cita:** *"Los turnos no los hemos hablado: un turno es cada ida y venida de un modelo de lenguaje. [...] Le puedes poner un límite, para que no se vuelva loca y esté dos horas ejecutando: le dices que tiene diez turnos y en diez turnos tiene que sacar el resultado."*

---

### F-T-02 · Múltiples terminales / agentes paralelos

**Descripción:** La arquitectura permite tener múltiples sesiones de agente corriendo en paralelo (3, 6, 12+), cada una con su contexto y tarea, visibles simultáneamente.

**Estado según transcripción:** Demostrada en vivo (mañana — 3 agentes corriendo a la vez; tarde — referencia a múltiples pestañas).

**Sesión/franja:** Mañana — sección "La terminal frente a la aplicación; ficheros y memoria".

**Cita:** *"Veis que tengo tres a la vez; puedo tener 5, 6, 12."*

---

### F-T-03 · Contexto permanente vía CLAUDE.md (arquitectura de carpetas)

**Descripción:** Cada agente/marca tiene su propio `CLAUDE.md` en su carpeta. El contexto permanece entre sesiones sin necesidad de reexplicarlo cada vez.

**Estado según transcripción:** Explicada como arquitectura base (mañana y tarde).

**Sesión/franja:** Mañana — sección "La terminal frente a la aplicación; ficheros y memoria"; tarde — sección final.

**Cita (tarde):** *"En este caso, estoy lanzando agentes dentro de la carpeta Kenny Social, que es la carpeta donde define cuál es el proyecto [...] También lo ha creado él, pero es un contexto permanente entre sesiones."*

---

### F-T-04 · Integración con herramientas de vídeo externas vía MCP (Higgsfield, Kling, ElevenLabs)

**Descripción:** Conectar agentes con herramientas de generación de vídeo/audio (Higgsfield, Kling, ElevenLabs, Midjourney) mediante sus MCPs/skills, para generar vídeo de forma integrada en el flujo.

**Estado según transcripción:** Mencionada como posibilidad técnica futura (mañana).

**Sesión/franja:** Mañana — sección "'Carta a los Reyes' en directo (2)".

**Cita:** *"Están estos nuevos, Higgsfield, creo que se llama. Se conectan a todas las IAs: te dan la opción de usar Kling, ElevenLabs, Midjourney... todo. [...] Tiene unos skills concretos, 'Higgsfield AI skills'. Si se los inyecto a mi agente, aquí en 'skills', podría usarlo."*

**Detalles:** Generación de vídeo en sesión marcada como "fuera de alcance por ahora" (demasiados pasos, licencias, calidad insuficiente). El mecanismo de conexión vía MCP sí se mostró.

---

### F-T-05 · Integración con Gmail/Calendar vía OAuth token

**Descripción:** Conectar agentes con Gmail y Google Calendar mediante token OAuth para leer emails, resumirlos, crear agenda de la semana a partir de reuniones, y enviar correos programados.

**Estado según transcripción:** Mencionada y demostrada el proceso de generación del token (tarde).

**Sesión/franja:** Tarde — sección de tokens y acceso delegado.

**Cita:** *"Nosotros lo tenemos de hecho, lo tenemos con Gmail, con el calendar, con todo. Le podemos pedir que nos cree la agenda de la semana en función de las reuniones que hemos tenido, que nos lea todos los emails y nos resuma."*

**Detalles:** Se explicó paso a paso cómo generar el token en Google Cloud Console. No se integró en keni-social en la sesión.

---

### F-T-06 · Integración con asistente de voz / WhatsApp / Telegram

**Descripción:** Permitir que los agentes reciban instrucciones y ejecuten tareas a través de notas de voz o mensajes en canales de mensajería (WhatsApp, Telegram, Discord, Slack).

**Estado según transcripción:** Mencionada en cierre de sesión mañana.

**Sesión/franja:** Mañana — sección "Cierre: asistentes de voz".

**Cita:** *"Yo, por ejemplo, he tenido conexión en mi WhatsApp con mi Claude Code: mandarle notas de voz por WhatsApp y que se ejecuten tareas en el ordenador."*

**Detalles:** Herramientas mencionadas: OpenClaw, Hermes. No integrado en keni-social en la sesión.

---

### F-T-07 · Repositorio en GitHub (backup y distribución)

**Descripción:** El código de keni-social (consola, skills, CLAUDE.md de marcas) se almacena en GitHub para backup, versionado y distribución entre miembros del equipo.

**Estado según transcripción:** Mencionada como hecho establecido (mañana).

**Sesión/franja:** Mañana — sección "Backups y repositorios".

**Cita:** *"Se llaman repositorios. [...] Keni Social, la plataforma que estamos viendo, está guardada en GitHub [...] Aquí están todas las skills guardadas en este repositorio externo, además de la propia aplicación: la consola, con su frontend, con todo su código y su desarrollo."*

---

---

## Funcionalidades ambiguas / contradictorias

### A-01 · Publicación automática en redes: alcance real vs. aspiracional

**Descripción de la ambigüedad:** En la sesión de mañana, Mikel explicó que la publicación automática "tiene sus límites" porque las plataformas lo restringen, y que la idea sería pasar la aplicación por el review de Meta. En la tarde, se mencionó que las cuentas de Piso 15 ya están en Metricool y que sería posible conectar la consola a Metricool para publicar. No quedó claro si la publicación automática se considera en alcance para la semana 2 del piloto o es un objetivo a más largo plazo.

**Citas en tensión:**
- Mañana: *"La idea sería que vosotros paséis la aplicación por el review de Meta."*
- Tarde: *"Esta semana nos sentamos y lo revisamos para conectarlo [Metricool] y vemos si..."*

---

### A-02 · Generación de vídeo: "fuera de alcance" vs. "si compramos las licencias da igual"

**Descripción de la ambigüedad:** En la sesión de mañana, Claude evaluó la generación de vídeo como "en rojo, demasiados pasos, licencias y calidad insuficiente". Sin embargo, en la misma sesión un participante dijo: "Si logras hacerlo en vídeo, da igual: si tenemos que comprar dos, tres o cuatro licencias, da igual." No quedó cerrado si la generación de vídeo completo (con locución estilo José Minaya) está en alcance del piloto.

---

### A-03 · Skill "brief matutino": ¿es nueva o existía ya?

**Descripción de la ambigüedad:** Al principio de la demo en mañana, Mikel dice que "brief matutino en skills no existe; vamos a experimentar." Minutos después aparece el resultado como si la skill ya estuviera en el catálogo. En la tarde, se menciona que para el brief de Diana se usó "el brief matutino de Lalo" (de la mañana). Queda la duda de si la skill quedó persistida en el repositorio o solo existió como artefacto de sesión.

---

### A-04 · Verificador de vídeos virales: skill vs. integración de herramienta externa

**Descripción de la ambigüedad:** En la sesión, Mikel primero propone hacer un agente con los pasos de verificación, luego dice "busquemos herramientas open source que ya lo hagan y clonarla" (ClaimBuster, Open Fact Check, etc.), y finalmente dice "intégrala además en la aplicación principal." No quedó claro si el resultado final es un skill propio, una integración de ClaimBuster, o ambas.

---

### A-05 · Detección de vídeo generado con IA

**Descripción de la ambigüedad:** Un participante preguntó si al skill de verificación se le puede agregar detección de IA generativa. Mikel respondió que "se podría, sí, pero la IA solo es capaz de predecir." La conversación se extendió largamente sobre las limitaciones técnicas y terminó sin confirmar si se incluye o no en el skill `verifica-video`.

---

### A-06 · Dashboard de tokens: ¿módulo propio o parte de la configuración?

**Descripción de la ambigüedad:** En la apertura de la demo se menciona un "dashboard de consumo de tokens, de ejecuciones, de cuántos agentes han ejecutado". En la sección de effort level se muestra un contador de tokens en tiempo real durante la generación. No quedó claro si son el mismo componente o dos vistas distintas.

---

### A-07 · Reporte semanal: formato de salida (Canva vs. PowerPoint vs. presentación propia)

**Descripción de la ambigüedad:** El equipo trabaja el reporte en Canva actualmente. Mikel generó una versión del reporte en la consola. Al mostrarla, alguien preguntó "¿le puedes decir descarga un PowerPoint?". Mikel respondió que no tenía PowerPoint. No quedó definido el formato de salida objetivo: ¿presentación generada por la consola, exportación a PPTX, o integración con Canva?

---

*Documento generado el 2026-05-25. No audita código; solo extrae lo dicho en las transcripciones. El análisis de correspondencia entre estas funcionalidades y el código real del repositorio lo realiza un agente separado.*
