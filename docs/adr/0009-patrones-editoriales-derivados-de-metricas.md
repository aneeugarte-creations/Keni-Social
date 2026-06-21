# ADR 0009 — Patrones editoriales derivados de métricas

Cada marca tiene un perfil de patrones editoriales DERIVADO de sus métricas medidas,
y el copy generado se VERIFICA contra ese perfil antes de la revisión humana.

## Principio

El ciclo editorial separa tres artefactos con dueños distintos:

1. **Perfil de patrones por marca (máquina).** Código determinista lo deriva por
   marca×red comparando el cuartil TOP por engagement contra el FONDO en rasgos medibles
   (longitud, emojis, hashtags, gancho en mayúsculas, pregunta, formatos). Destila reglas
   de lint SOLO cuando el contraste entre top y fondo es nítido; conservador ante la duda.
   Se persiste como dato regenerable (inicial en el paquete, override en runtime), nunca
   como criterio escrito a mano.

2. **Criterio editorial cualitativo (humano).** Voz, Reglas y Plataformas son criterio
   humano estable y no llevan cifras volátiles. La voz es del humano: no se reescribe
   automáticamente. El principio del producto es menos IA hacia fuera.

3. **Verificación de voz (máquina).** En el post-procesado, cada pieza generada se contrasta
   contra el perfil de su marca. Es ADVISORY: nunca bloquea ni descarta. Si hay avisos y el
   modelo dijo `listo`, el veredicto se degrada a `revisar` y los avisos viajan al revisor.
   Sin perfil para la marca/red no se inventan avisos.

## Invariantes

- Los umbrales viven en el perfil derivado (auditables, regenerables, corregibles), no
  hardcodeados por marca.
- La re-derivación es un ciclo cerrado que no toca git: re-extrae de métricas, recomputa el
  perfil y lo persiste en el store. La frescura se decide por el propio perfil; los reinicios
  no re-derivan. Una extracción vacía nunca pisa un perfil bueno.
- El prompt de copy recibe por marca la Voz (humano) + los patrones medidos (máquina): el
  modelo escribe dentro de las bandas reales y el verificador comprueba que lo hizo.
