# ADR 0009 — Patrones editoriales derivados de métricas

Cada marca tiene un perfil de patrones editoriales DERIVADO de sus métricas medidas,
y el copy generado se VERIFICA contra ese perfil antes de la revisión humana.

## Principio

Derivar de datos medidos lo que cada marca publica con éxito y reinyectarlo al ciclo
editorial como guía ADVISORY que lintea la FORMA del copy (longitud, densidad de emojis,
hashtags, registro), nunca el contenido, el tema ni la creatividad. El verificador
SOLO anota y degrada `listo` -> `revisar`; nunca bloquea ni descarta. Esto vale para
cualquier método estadístico y cualquier señal: lo permanente es el bucle medir →
destilar forma → reinyectar como aviso, con la voz cualitativa siempre en manos humanas
(menos IA hacia fuera). El método y la señal concretos son MECANISMO, no principio.

El ciclo separa tres artefactos con dueños distintos:

1. **Perfil de patrones por marca (máquina).** Código determinista lo deriva por
   marca×red sobre rasgos medibles y destila reglas de lint SOLO cuando el contraste es
   nítido; conservador ante la duda. Se persiste como dato regenerable (inicial en el
   paquete, override en runtime), nunca como criterio escrito a mano.

2. **Criterio editorial cualitativo (humano).** Voz, Reglas y Plataformas son criterio
   humano estable y no llevan cifras volátiles. La voz es del humano: no se reescribe
   automáticamente.

3. **Verificación de voz (máquina).** En el post-procesado, cada pieza generada se contrasta
   contra el perfil de su marca. Es ADVISORY: nunca bloquea ni descarta. Si hay avisos y el
   modelo dijo `listo`, el veredicto se degrada a `revisar` y los avisos viajan al revisor.
   Sin perfil para la marca/red no se inventan avisos.

## Mecanismo v1 (implementación actual, revisable)

Hoy el perfil se deriva así (`consola/src/keni_consola/patrones_marca.py`):

- **Señal:** `engagement_pct` de cada pieza publicada (Metricool).
- **Método:** por marca×red, ordenar por engagement y comparar el cuartil TOP contra el
  FONDO sobre estos rasgos: longitud, emojis, hashtags, gancho en mayúsculas de apertura,
  pregunta, multilínea, formato. La banda recomendada (p25-p75 del top) viaja en el doc
  generado; las reglas de lint avisan cuando una pieza se sale de p5-p95 del top o pisa una
  firma del fondo.

Tanto la señal como el método son la primera implementación, atada al piloto, y se espera
que cambien con más datos. NO son el principio.

## Invariantes

- Los umbrales POR MARCA (longitud máx/mín, emojis máx, hashtags máx, gancho/pregunta
  esperado/evitar por red) viven en el perfil derivado: auditables, regenerables y
  corregibles re-derivando, no escritos a mano marca por marca.
- La re-derivación es un ciclo cerrado que no toca git: re-extrae de métricas, recomputa el
  perfil y lo persiste en el store. La frescura se decide por el propio perfil; los reinicios
  no re-derivan. Una extracción vacía nunca pisa un perfil bueno.
- El prompt de copy recibe por marca la Voz (humano) + los patrones medidos (máquina): el
  modelo escribe dentro de las bandas reales y el verificador comprueba que lo hizo.

## Auditabilidad: alcance real

La auditabilidad es PARCIAL y conviene no exagerarla. Hay dos niveles de umbral:

- **Umbrales por marca** (los del perfil): auditables y regenerables, como dice el invariante.
- **META-umbrales** que deciden qué contraste top-vs-fondo cuenta como "nítido" y por tanto
  emite regla: están HARDCODEADOS en `_reglas_lint` (y constantes vecinas) — factores como
  `1.5×`/`1.2×` de longitud, `0.5×` para el mínimo, `60%`/`25%`/`30%`/`2.5×` del gancho,
  `12%`/`15%` de la pregunta, además del tamaño mínimo de muestra y el corte de cuartil.
  Están tuneados al piloto AMX, no derivados de datos, y son los primeros candidatos a
  cambiar cuando haya más volumen. Cambiarlos hoy exige editar código, no regenerar un perfil.

## Límite causal

El engagement está dominado por el tema, el timing y el boost de pauta, no por la
redacción del copy. Las bandas del perfil son CORRELACIÓN observada en lo publicado, no
causalidad de "esta forma funciona". Por eso el mecanismo es advisory y no bloqueante: un
aviso señala que una pieza se aparta de lo que la marca suele publicar con buen resultado,
no que vaya a rendir mal. La decisión sigue siendo del humano.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- Cierre el piloto AMX (con más datos, revisar método y meta-umbrales).
- Se detecte homogeneización de la voz (el bucle empujando hacia la media).
- Aparezca una señal mejor que el engagement (conversión, retención, señal curada por el humano).
