# Sesion — Termometro mundial + jerarquizacion automatica

Fecha: 2026-05-25
Origen: misma sesion del equipo de redes AMX que la nota de Elias ("mientras trabaja el
de Elias, pues va el otro generando alguien mas").
Esta nota es CONTEXTO/DECISION. La implementacion vive en el repo `~/projects/keni-social`.

## Que es el termometro mundial

Un posteo de GALERIA que el equipo hace a diario: abarca las **5 a 8 noticias
internacionales mas importantes** de coyuntura, **una por region** (si pasa algo en
China/Japon va un slide de Asia, otro de Europa, otro de America Latina, etc.). Hoy se
arma a mano. Idea: que "diario a las 7 de la manana ya esten jerarquizadas las 5-8 mas
importantes para el posteo, ya con el copy armado".

## La idea de fondo: jerarquizacion

Mas alla del termometro, en la sesion se hablo de **jerarquizar** la informacion del
rastreo diario para decidir **que formato funciona mejor** para cada nota (video, posteo,
galeria). Eso ya existe como skill (`nota-a-formato` / `brief-matutino`). El termometro es
un caso concreto de jerarquizacion: ordena internacionales y arma una galeria por region.

Cita clave de la sesion: "ya tiene disenado lo que tiene que hacer... si simplemente es en
la skill decirle: jerarquizalo con estos parametros/patrones". Es decir: el motor de
generacion ya existe; el termometro es una SKILL nueva + su disparador.

## Implementado en el repo (rama `feat/termometro-mundial`, CI local en verde)

Decision: hacerlo end-to-end reutilizando el motor de Skills que ya corre `claude -p`.

- **Skill `termometro-mundial`** (`skills-copy/`): salida tipo documento. Jerarquiza las
  notas que se le pasan (relevancia internacional + impacto + frescura + diversidad de
  regiones), elige el top 5-8, reparte por region en slides (portada + N slides) y cierra
  con el copy del posteo tropicalizado a MX + auto-verificacion. No inventa: solo trabaja
  con lo que se le da.
- **Pagina en la consola** (Trabajo -> "Termometro mundial"): configurar numero de slides,
  regiones, hora y marca; pegar las noticias (o "Traer del RSS" con un clic) y generar en
  segundo plano, con resultado guardable como publicacion. Endpoints `GET/PUT
  /api/termometro` y `POST /api/termometro/generar`.
- **Cron de las 7:00** (`keni-termometro`): sin servidor, reune las noticias de los feeds
  RSS activos (el "rastreo"), corre la skill y deja el termometro en el HISTORIAL para
  encontrarlo a primera hora. Plantilla launchd/cron en `docs/termometro-mundial.md`.

## Decisiones / pendientes

- **Formato de salida**: hoy es un documento (portada + slides + caption) que el community
  revisa y guarda. Falta decidir si conviene componer la galeria como imagenes
  (plantilla deterministica, ligado a la "linea visual" de la nota de Elias) o dejarla como
  guion para Canva.
- **Fuente de noticias internacionales**: el cron tira de los feeds RSS activos. Falta dar
  de alta buenos feeds internacionales por marca (hoy la curaduria es manual).
- **Validacion con el piloto**: la skill nace en grupo "experimentales"; pasa a "validadas"
  cuando el equipo confirme criterio (regiones, tono del caption, cuantos slides).
- **Merge a `main` + push**: pendiente de confirmacion (la rama queda lista, CI en verde).
