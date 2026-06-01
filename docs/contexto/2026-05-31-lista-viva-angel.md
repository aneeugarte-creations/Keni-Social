# Lista viva de contenidos — petición de Angel (evaluación + diseño)

> Fecha: 2026-05-31 · Origen: petición de Angel (equipo de redes AMX, piloto UnoTV / Claro Sports).
> Estado: evaluación de viabilidad + diseño de los huecos. Primera pieza en construcción
> (`feat/lista-viva-angel`): importador de calendario Excel/CSV.

## 1. Qué pidió Angel (textual, resumido)

Una **app web** que cada mañana (≈9:00) deje lista una **lista curada de contenidos a postear**.
Cada item con su **arte/imagen** y su **copy**, generados a partir de documentos y tablas
(PDF/Excel) que el equipo proporciona. La lista debe:

- Alimentarse del **máximo de fuentes posible**:
  - lista *green* de contenidos que el equipo quiere postear,
  - contenidos **obligatorios por compromiso**,
  - **RSS de unotv.com**,
  - **noticias virales**,
  - **radar de Google Trends**.
- Cada fuente con **su forma de ser alimentada**.
- **Re-ordenarse por prioridad cada vez que entra algo nuevo** (lista dinámica y "viva").
- Generar **copy y parte del arte a medida que entran los temas**, para que el equipo
  **revise y apruebe**, y luego se **programe y publique automáticamente**.

Y: evaluar qué tan viable es reutilizar lo ya construido en keni-social; adaptar o borrar lo
que en `docs/` no represente bien esto; y diseñar lo que falte por conectar.

## 2. Veredicto de viabilidad: ALTA (ensamblar, no construir desde cero)

La mayor parte de lo que pide Angel **ya existe como piezas en keni-social**, bastante más de
lo que sugerían los `docs/`. El trabajo real es **cablear y ensamblar** lo existente + cubrir
4-5 huecos concretos. No es un producto nuevo: es la **versión integrada** de capacidades que
hoy están sueltas.

### 2.1 Mapa: petición de Angel → lo que ya existe

| Lo que pide Angel | Estado | Dónde vive hoy |
|---|---|---|
| Lista viva priorizada (tablero) | ✅ Existe | Tabla `contenido` (`db.py`), `prioridad` alta/media/baja + `flujo` importante/evergreen/evento, ordenada al listar (`db.py` `listar_contenido`). Kanban real con piezas por plataforma (`contenido_plataforma`). |
| RSS de unotv.com | ✅ Existe | Pipeline de Fuentes RSS completo: `api/rss.py` (dedup `rss_items_vistos`, filtros incluir/excluir, guard SSRF, límites). Página `/investigacion/fuentes`. |
| Radar de Google Trends | ✅ Existe | `radar.py` jala el RSS oficial de Google Trends por país, con `señal` = tráfico aproximado real. `api/radar.py`. |
| Noticias virales | 🟡 Parcial | El Radar consolida Trends + feeds RSS del equipo. No hay API dedicada de "virales" más allá de eso. |
| Lista *green* (lo que el equipo quiere postear) | 🟡 Mapeable | Hoy = crear contenido a mano en el tablero. No está modelado como "green" explícito. |
| Obligatorios por compromiso | 🟡 Mapeable | No modelado como tal. Se aproxima con `prioridad='alta'` + `fecha_objetivo`, o con el módulo Comercial (campañas con objetivo). |
| Copy auto-generado al entrar un tema | 🟡 Parcial | La generación existe (worker + `claude -p` + 20 skills: nota→copy, url→copy, clip→copy, breaking, hilos, tropicalización MX, voz de marca, auto-verificación). **Pero NO se dispara sola** cuando entra un tema al tablero. |
| Arte auto-generado | 🟡 Parcial | Generación de imagen por IA real existe (`/api/media/generar`, OpenRouter → GPT-image/Gemini). **No está cableada** a la creación del borrador. |
| Revisión / aprobación humana | ✅ Existe | Flujo completo borrador→en_revisión→aprobado→programado→publicado + cola de revisión (`api/aprobacion.py`, `/revision/editorial`). "Otro par de ojos" (revisor ≠ autor). |
| Programado y publicado automáticamente | ✅ Existe (gated) | `programador.py` (barrido 60s) → publicación real a **Metricool** (`KENI_PUBLICAR_REAL`, hoy OFF por defecto; pendiente del App Review de Meta para algunas redes). |
| Re-priorización dinámica al entrar algo | 🟡 Parcial | Hoy ordena por prioridad fija (alta/media/baja) + fecha. No hay un **score** que mezcle señales (viralidad, compromiso, frescura) y re-ordene. |
| Entrega a las 9am | 🔴 No existe (decidido: Panel) | No hay email/digest/daemon de entrega. **Decisión:** la entrega es el **Panel listo** al entrar (reutiliza `/panel` + daemons). Sin email/SMTP. |
| Ingesta de PDF/Excel | 🔴 No existe | No hay importador del calendario/temas. **Es el primer hueco que se construye.** |

### 2.2 Infra que ya soporta "vivo y automático"

- **Cola + worker**: el back encola jobs (`cola.py`, tabla `jobs` Postgres) y `worker.py` los
  ejecuta con `claude -p` (escalable `--scale worker=N`, `FOR UPDATE SKIP LOCKED`). Generar copy
  en background **ya es producción**.
- **Daemons** (hilos en el back): `programador` (60s), refresco de métricas (4h), alertas de
  rendimiento (6h), captura comercial, scanner de vencimientos, y **`radar_auto`** (auto-promueve
  trending al tablero, gated `KENI_RADAR_AUTO`). El patrón "fuente → crea contenido" ya existe.
- **Modelo unificado**: una "publicación" del API legacy = una fila `contenido_plataforma`
  (`es_publicacion=1`) colgada de un `contenido` padre. **No hay dos modelos desconectados**:
  el tablero ES la verdad y las publicaciones son su vista programable/publicable.

## 3. Los huecos a construir (lo que falta conectar)

Ordenados por valor/dependencia:

### H1 — Ingesta de calendario (Excel/CSV) → tablero  ⭐ primero
No existe forma de subir el calendario/temas de Angel. **Se construye ahora** (ver §5):
parser puro (CSV + XLSX) → `repos.crear_contenido(...)` con `origen='import-calendario'`,
`prioridad`, `fecha_objetivo`, y etiqueta `compromiso` cuando la fila es obligatoria. Espeja
`radar_auto.promover_temas`. PDF se difiere (los PDF de calendario rara vez son tabla fiable;
el canon es Excel/CSV; PDF tabular = best-effort posterior).

### H2 — Cableado auto copy (+ arte) al entrar un tema  ⭐ corazón del producto
Cuando entra un tema al tablero (import, radar-auto, RSS elegido, o alta manual marcada
"generar"), **encolar automáticamente** una generación de copy (worker existente) que deje un
**borrador** colgado del contenido, listo para revisión. Fase 2: además encolar arte
(`/api/media/generar`) con un prompt derivado del copy/tema. Gated y con cap de concurrencia
(reutiliza `KENI_MAX_JOBS`) y un flag tipo `KENI_AUTOGEN=1` (conservador por defecto, como
`radar_auto`). Esto convierte "lista de temas" en "lista de borradores listos para aprobar".

### H3 — Score de prioridad dinámico (re-ordenar al entrar algo)
Hoy el orden es prioridad fija + fecha. Diseñar un **score** puro y testeable que combine:
señal de viralidad (Radar), compromiso (etiqueta + cercanía de `fecha_objetivo`), frescura, y
flujo. Se aplica al listar (no requiere reescribir filas) y hace que la lista se "re-acomode"
sola cuando entra algo nuevo. Empezar simple (función determinista) y afinar pesos con el equipo.

### H4 — Modelar "green" y "compromiso" como conceptos de primera clase
- **Compromiso**: primer paso = etiqueta `compromiso` + `fecha_objetivo` (lo construye H1, sin
  tocar enums). Follow-up limpio: promover a `flujo='compromiso'` (toca `FLUJOS_CONTENIDO` y la
  UI; hacerlo cuando se valide el modelo).
- **Green**: lista del equipo = contenido de alta manual; basta una etiqueta `green` o reusar
  `flujo='evergreen'`. Decisión menor; no bloquea.

### H5 — Panel "9am" (lista curada del día)
Vista del Panel que, al entrar a las 9, muestre **la lista viva ya ordenada por score**, con
contadores por fuente y por estado, y CTA a revisión. Reutiliza `/panel` + lectura del tablero.
**No** requiere email ni scheduler nuevo (decisión de producto: entrega = Panel).

## 4. Docs a adaptar / borrar (recomendación, no ejecutado aún)

La visión documentada hoy es "**asistente** de copy + consolidador de métricas; el humano lanza
cada paso". La visión de Angel es "**lista viva multi-fuente con auto-generación y publicación
programada; el humano valida checkpoints**". No se contradicen, pero varios docs asumen
asistencia manual y conviene adaptarlos:

| Doc | Acción | Motivo |
|---|---|---|
| `docs/ux-roadmap.md` (§ "norte de experiencia") | **Adaptar** | El principio "cada pantalla termina con el siguiente paso" supone asistencia; añadir el cierre de loop hacia auto-generación + scheduling. |
| `docs/estado-producto.md` (fases) | **Adaptar** | Redefinir Fase 0/1/2 si la auto-generación y el Panel-9am entran ya como producto. |
| `docs/go-to-market.md` | **Revisar** | Posiciona "programación/cola" como futuro de venta; alinear con que el tablero vivo ya existe. |
| `docs/contexto/2026-05-27-elias-spec-operativo.md` (clasif. OP/CR/MX; F7 radar) | **Adaptar** | Añadir clase "OP semiautomático con validación"; especificar que F7 (radar) **auto-popula** la cola, no solo informa. |
| `docs/plan-separacion-apps.md` (App C "Operación") | **Validar** | Si C incluye scheduling real + auto-gen ahora, suben de prioridad sus hitos. |
| ADRs 0001-0005, `README.md`, `docs/arquitectura.md`, `docs/guia-community-manager.md` | **Sin cambios** | Son arquitectura de ejecución / soporte; agnósticos a la visión operativa. |

Nada a **borrar** de raíz: todo es adaptable. (Pendiente de tu visto bueno para editar docs.)

## 5. Lo que se construye en esta rama (primer incremento)

`feat/lista-viva-angel` — **H1: importador de calendario Excel/CSV** (backend + tests):

- `consola/src/keni_consola/importador_calendario.py`: parsing **puro y testeable** de bytes
  `.csv` y `.xlsx` → filas normalizadas (`titulo`, `fecha`, `marca`, `redes`, `prioridad`,
  `compromiso`, `notas`), con mapeo flexible de columnas (sinónimos es/en) y validación honesta
  (filas inválidas se reportan, no rompen). Sin I/O en la parte pura.
- `importar_a_tablero(filas, ...)`: espeja `radar_auto.promover_temas` —
  `repos.crear_contenido(origen='import-calendario', ...)` + etiqueta `compromiso` cuando aplica,
  con dedup por (título normalizado + fecha).
- `POST /api/contenido/importar` (multipart) en `api/contenido.py`, espejo de `desde_radar`.
- Dependencia nueva: `openpyxl` en `consola/pyproject.toml`.
- Tests: `consola/tests/test_importador_calendario.py`.

Diferido (siguientes incrementos, ya diseñados arriba): frontend del importador (subir archivo
+ previsualizar + confirmar; requiere recompilar el bundle vendorizado), H2 (auto copy/arte),
H3 (score), H5 (Panel-9am).

## 6. Restricciones y decisiones tomadas

- **Entrega 9am = Panel** en la consola (no email). Decisión del 2026-05-31.
- **Obligatorios = ambos**: del Excel/CSV **y** a mano; se modelan como etiqueta `compromiso`
  + `fecha_objetivo` (sin tocar enums en el primer incremento).
- **Publicación automática** = vía Metricool (`programador.py`), gated por `KENI_PUBLICAR_REAL`;
  algunas redes dependen del **App Review de Meta** (gating externo, ver `docs/plataformas/`).
- **Conservador por defecto**: toda automatización nueva (auto-gen, etc.) detrás de un flag OFF
  por defecto, igual que `radar_auto`. El humano sigue aprobando antes de publicar.
