# ADR 0009 — Patrones editoriales derivados de métricas (perfil por marca + verificación de voz)

- **Estado:** Aceptado
- **Fecha:** 2026-06-10
- **Decisores:** equipo keni-social
- **Componente:** `keni-consola` (`patrones_marca.py`, `patrones_derivar.py`, `patrones_refresco.py`, `dominio/copy.py`, `texto_inicial/editorial/rrss/*/patrones.md`, `patrones_inicial/*.json`)
- **Relación:** consume la API de Metricool vía `keni_metricas` (ADR 0005 §B: B es la fuente única de métricas). Sigue el patrón inicial/store de la Prompts de Texto.

---

## Contexto

La línea editorial de cada marca (Voz/Reglas/Plataformas) nació de una lectura manual de
Metricool sobre UNA ventana (12-may→9-jun-2026). Funcionó —el copy sale más cerca de la voz
real— pero tenía tres carencias estructurales:

1. **No reproducible.** Los números de los docs (longitudes, % de mayúsculas, emojis) no
   tenían pipeline: nadie podía re-medirlos ni saber cuándo quedaban obsoletos.
2. **Solo prompt, sin verificación.** El único control de voz era la auto-verificación del
   propio modelo dentro del prompt; nada determinista contrastaba el copy GENERADO contra el
   patrón real de la marca antes de la revisión humana.
3. **Mezcla de capas.** El mismo doc mezclaba criterio humano estable ("no afirmar
   culpabilidades") con medición volátil ("las top miden 300-740"), así que refrescar datos
   implicaba editar a mano documentos de criterio.

Con 12 meses de historial disponible en Metricool (~70k piezas en las 3 marcas del piloto),
medimos además que parte de la intuición de la primera pasada NO aguanta la muestra (p. ej.
"la pregunta funciona en Nación Gamer": en 12 meses no distingue al cuartil top del fondo).

## Decisión

Separar el ciclo editorial en TRES artefactos con dueños distintos:

1. **Perfil de patrones por marca** (`patrones_inicial/<marca>.json` inicial en el paquete;
   override runtime en `<dir_config>/patrones/<marca>.json`, mismo principio inicial/store
   que la Texto). Lo deriva código determinista (`patrones_marca.derivar_perfil`): por
   marca×red, compara el cuartil TOP por engagement contra el FONDO en rasgos medibles
   (longitud, emojis, hashtags, gancho en MAYÚSCULAS, pregunta, formatos) y destila reglas
   de lint solo cuando el contraste es nítido. **Dueño: la máquina.**
2. **Doc editorial generado** `editorial/rrss/<marca>/patrones` (`pipelines: [copy]`): el
   render humano-legible del perfil, inyectado al prompt de copy junto a la Voz. Se regenera
   entero; NO se edita a mano. **Dueño: la máquina.** Voz/Reglas/Plataformas conservan el
   criterio cualitativo y dejan de llevar cifras volátiles. **Dueño: el humano.**
3. **Verificación de voz** en el post-procesado del copy (`dominio.copy.verificar_voz`):
   lint determinista de cada pieza generada contra el perfil. ADVISORY: nunca bloquea ni
   descarta; con avisos, un `listo` del modelo se degrada a `revisar` y los avisos viajan
   al revisor (resultado + nota en el tema). Sin perfil para la marca/red no se inventa
   (cero avisos). La galería (termómetro) queda fuera: formato de captions cortas por
   diseño, las bandas se midieron sobre el feed.

La **re-derivación** es un ciclo cerrado sin tocar git: CLI
(`python -m keni_consola.patrones_derivar --store`) y daemon (`patrones_refresco`, gateado
por `KENI_PATRONES_AUTO`, def OFF) que re-extraen de Metricool por ventanas mensuales,
recomputan el perfil y aplican JSON + doc del store. La frescura se decide con el campo
`generado` del propio perfil (sin estado extra; reinicios no re-derivan). Una extracción
vacía NUNCA pisa un perfil bueno.

## Alternativas consideradas

- **LLM que re-escribe la Voz periódicamente.** Rechazada: la voz es criterio humano (el
  principio del producto es "menos IA hacia fuera"); además un re-escrito total no es
  auditable. El LLM ya tiene su canal para PROPONER (sugerencias editoriales).
- **Lint con umbrales hardcodeados por marca.** Rechazada: vuelve a la intuición; el perfil
  JSON hace los umbrales auditables, regenerables y corregibles por humanos (el runtime
  gana a la inicial).
- **Persistir las piezas crudas en Postgres y derivar de ahí.** Rechazada por ahora:
  Metricool ya es el archivo histórico (12 meses disponibles); duplicarlo serían ~70k
  filas×texto sin un consumidor más allá de esta derivación. Si aparecen más consumidores,
  reabrir junto a ADR 0007.

## Consecuencias

- El prompt de copy recibe POR MARCA: Voz (humano) + Patrones medidos (máquina) — el modelo
  escribe dentro de las bandas reales a la primera, y el verificador comprueba que lo hizo.
- `derivar_verdicto` reconoce el veredicto EN PALABRAS del contrato del prompt de copy
  ("LISTO PARA APROBAR"…), no solo ✅/⚠️/❌: el veredicto del modelo ya no se pierde.
- Operación: activar el ciclo en hosted = `KENI_PATRONES_AUTO=1` en el servicio `daemons`
  (necesita las credenciales de Metricool del volumen `/data`). Sin el flag, el perfil se
  refresca con el CLI cuando se quiera.
- Los tests aíslan el dir de perfiles (`KENI_PATRONES_DIR`, autouse en conftest).
