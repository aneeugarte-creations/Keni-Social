# golden — outputs de referencia de voz/tropicalización (#139)

Conjunto pequeño de **golden outputs**: copy de referencia, escrito a mano y
revisado, que representa cómo "suena bien" cada marca en es-MX. Son la base
determinista para evaluar **consistencia de voz** y **tropicalización** sin
llamar al modelo ni a la red.

> No son la verdad absoluta de estilo (eso lo aprueba un humano). Son un **ancla**:
> si un cambio de skill/contexto rompe una propiedad que estos ejemplos sí
> cumplen, algo se degradó.

## Qué NO son
- No reemplazan el gate local con modelo (`run.sh`): ese genera copy nuevo.
- No juzgan estilo subjetivo. Comprueban **propiedades deterministas** que un buen
  copy de esa marca debe cumplir: límites por plataforma, bloque de
  auto-verificación, fidelidad a la fuente y **ausencia de españolismos
  (incluidas flexiones)**.

## Estructura

```
golden/
  README.md            # este archivo
  manifest.json        # índice máquina-legible: cada golden -> marca/plataforma/fuente/notas
  fuentes/             # la nota/fuente de cada golden (para el check de fidelidad)
    fichaje-delantero.md
    sismo-cdmx.md
    beca-comunidad.md
  claro-sports/        # marca deportiva: coloquial pero correcto
    x.md
    tiktok.md
  unotv/               # noticias: es-MX neutro profesional, sin jerga
    x.md
    carrusel.md
  fundacion/           # social: sobria, cálida, sin jerga ni humor
    facebook.md
```

Cada golden lleva:
- un encabezado de plataforma reconocible por `checks.extraer_secciones`
  (`## X`, `## TikTok`, `## Carrusel`, …),
- el copy de esa plataforma respetando su formato/límite,
- el bloque de **auto-verificación** (✅/⚠️/❌ + veredicto), igual que produce la
  skill.

El `manifest.json` enlaza cada golden con su `marca`, `plataforma`, la `fuente`
de `fuentes/` (para fidelidad) y `voz_notas` (qué rasgos de voz ilustra: léxico
coloquial vs. neutro, tono sobrio, etc.).

## Cómo se evalúan

`test_golden.py` (CI-safe, sin modelo) recorre el `manifest.json` y, por cada
golden, comprueba que:

1. Pasa **todas** las propiedades de `checks.evaluar_copy` contra su fuente
   (límites, verificación, fidelidad, bandera con escudo).
2. **No** contiene españolismos ni sus flexiones (`tropicalizacion.detecta_flexiones_es_es`).
3. Trae el bloque de auto-verificación.

Si añades un golden nuevo, agrégalo al `manifest.json` y `test_golden.py` lo
recoge automáticamente.

## Por qué por marca/plataforma

La petición #1 del piloto AMX es que "suene mexicano" y que **cada sub-marca**
mantenga su registro (Claro Sports coloquial ≠ UnoTV neutro ≠ Fundación sobria).
Tener un ejemplo dorado por marca/plataforma fija ese contrato de voz como
referencia revisada, no como intuición.
