# Evals de calidad de la salida de IA

Red de regresión para la propuesta de valor de keni-social ("auto-verificación / más IA hacia
adentro"). Los prompts de la Biblioteca son **editables en vivo** sin red que los respalde: con
varios agentes (+ el humano) tocándolos en paralelo, un cambio que degrade voz/tono/formato se
despliega sin que nada lo cace. Este harness es esa red **en la capa medible**.

## Qué es

- Un set de **casos golden** versionados (`consola/evals/casos/*.yaml`): cada caso es un copy
  candidato + la marca/red + (opcional) su nota de origen + el veredicto esperado.
- Un **runner determinista** que contrasta cada copy contra la **misma maquinaria de
  verificación que corre en producción** (cero `claude -p`, barato, apto para CI):

  | Dimensión    | Qué mide                                           | Reutiliza |
  |--------------|----------------------------------------------------|-----------|
  | `limite_red` | tope técnico DURO de caracteres por red (por intervalo)| `keni_shared.limites_plataforma` + `dominio.copy._intervalos_publicables` |
  | `voz`        | longitud/emojis/hashtags/gancho/pregunta vs patrón real de la marca | `patrones_marca.verificar_pieza` (el MISMO lint del post-procesado) |
  | `coherencia` | solapamiento léxico copy↔nota (caza alucinación / pieza cruzada) | `pipeline_contenido._calidad.avisos_coherencia` |
  | `prohibidos` | términos vetados por la regla editorial de la marca | `dominio.dedup` (normalización) |
  | `idioma`     | tropicalización MX básica ("¿esto es español?")     | heurística conservadora propia |

## Cómo se ejecuta

```bash
# venv:  pip install -e ./keni-shared -e ./mcp-metricas -e ./consola
python -m keni_consola.evals              # reporte legible
python -m keni_consola.evals --verboso    # + dimensiones que pasan
python -m keni_consola.evals --json       # salida JSON (tooling)
python -m keni_consola.evals --estricto   # exit!=0 si algún caso ya no cuadra
```

La red de regresión vive en `consola/tests/test_evals_semilla.py` (corre en CI, sin Postgres):
falla si algún caso semilla cambia de veredicto.

## Cómo añadir un caso

Crea un `.yaml` en `consola/evals/casos/` (uno por escenario). Campos:

```yaml
id: marca-red-descripcion-corta      # único, slug
descripcion: "Qué prueba este caso."
marca: unotv                          # id canónico (slug-guion); validado contra el catálogo
red: facebook                         # x | instagram | facebook | tiktok | youtube
espera: pasa                          # pasa | falla
fuente: |                             # OPCIONAL: nota de origen (activa la dimensión coherencia)
  Texto de la nota/insumo del que salió el copy...
copy: |                               # el copy CANDIDATO a evaluar
  Texto del copy...
# --- refinamientos opcionales ---
prohibidos: ["culpable", "delincuente"]   # términos vetados; su presencia FALLA
falla_esperada_en: voz                    # si espera=falla, en qué dimensión DEBE cazarlo
dimensiones: [limite_red, voz]            # subconjunto a correr (def: todas las aplicables)
```

Buenas prácticas:
- Incluye casos que **deben pasar** y casos que **deben fallar** (un set sin fallos no prueba nada).
- Para un caso `falla`, fija `falla_esperada_en`: así no pasa por la razón equivocada.
- Usa copys **realistas** (longitudes y registro como en producción), no de juguete.

## Qué aporta y qué NO

**Aporta**: caza al instante (a) que alguien **debilite la maquinaria de verificación**
(lint de voz, gate de coherencia, límites de red) y (b) cambios en los **perfiles medidos**
de marca (`patrones_semilla/*.json`) que muevan las bandas. Es barato y determinista.

**NO sustituye la revisión humana.** El principio rector es "el humano decide qué se publica";
esto es el cinturón, no el conductor. Mide lo MEDIBLE; la calidad editorial fina (plano vs con
gancho, tropicalización natural, alucinación sutil) sigue siendo criterio humano.

**Limitación honesta — no ve ediciones del TEXTO del prompt.** El harness determinista evalúa
copys FIJOS, no copy recién generado; por eso una edición del prompt no cambia su resultado.
Para cazar regresiones del prompt hace falta el **modo live** (abajo), que sí genera copy real.

**Necesita datos reales de AMX para ser potente.** Los casos semilla son un arranque realista
pero NO son los "golden" definitivos: esos los aporta la mesa de AMX (UnoTV / Claro Sports) con
copys reales etiquetados (aprobado/rechazado y por qué). Con esas etiquetas, este harness pasa
de "no rompas lo medible" a "mide tu acuerdo con el criterio humano real".

## Modo live (fuera de CI) — hook documentado

`keni_consola.evals.juez` deja el andamiaje para dos extensiones que SÍ cuestan dinero y no son
deterministas (por eso no van en CI):

1. **Evals live**: `generar_copy_live(caso, ejecutor)` — generar copy REAL con `claude -p` desde
   la nota de origen del caso (componiendo el prompt EXACTAMENTE como producción: Biblioteca de
   Prompts + contexto editorial de la marca) y pasarlo por los checks deterministas. Mide la
   regresión de extremo a extremo, prompt incluido.
2. **Calibración del juez LLM**: `acuerdo_con_humano(juez, casos)` — mide cuánto coincide un juez
   LLM (p.ej. el crítico de producción `dominio.critica_ia`, o un prompt de juez dedicado) con la
   etiqueta humana. La métrica clave son los **falsos positivos** (el juez deja pasar lo que el
   humano rechaza): un juez solo es de fiar con falsos positivos ~0. Hoy se calibra con la
   `espera` de los casos semilla como proxy; se sustituye por etiquetas reales de AMX en cuanto
   las haya.
