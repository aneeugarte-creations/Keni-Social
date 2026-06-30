/**
 * Las FASES de las dos máquinas (Investigación y Producción), en orden de flujo.
 *
 * Centralizadas aquí como el ESQUELETO de cada proceso: alimentan las subpáginas por fase
 * (`DetalleFase`) y el cálculo de qué daemons son «servicios» aparte (`ServiciosMaquina`, por
 * `claves`). La vista Pipeline (`PipelineUnificado`) tiene su propia tabla de etapas con la
 * criticidad y la cascada.
 */
import type { FasePipeline } from "@/pages/monitor/PanelPipeline";

/** Slug estable de una fase para su subpágina (`/maquina/contexto/:proceso/:fase`). */
export function slugFase(nombre: string): string {
  return nombre
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "-");
}

/**
 * Una fase TIENE CONTENIDO propio (algo que mostrar en su subpágina Prompt · Contexto · Logs) si
 * tiene prompt (`doc`), contexto editorial de marca (`contextoMarca`), histórico de runs por etapa
 * (`etapa`), cola viva (`queue`) o un daemon cuyos barridos son sus logs (`daemon`). Sin nada de
 * esto la subpágina no aporta: no es navegable y, si además no tiene toggle propio, NO es una etapa
 * (no debe pintarse como fila).
 */
export function tieneContenido(fase: FasePipeline): boolean {
  return Boolean(
    fase.doc || fase.contextoMarca || fase.etapa || fase.queue || fase.daemon || fase.panel,
  );
}

/** El flujo COMPLETO de Investigación (ADR 0011), de ENTRADA a SALIDA. */
export const FASES_INVESTIGACION: readonly FasePipeline[] = [
  {
    nombre: "Recolectar",
    es_ia: false,
    claves: ["KENI_PIPELINE_RECOLECTAR"],
    ayuda: "Recolecta artículos de las fuentes y agrupa las notas idénticas (misma url o titular)",
    queue: "recolectar",
    paralelo: "ingesta",
  },
  {
    // Fuente de ingesta PARALELA a las RSS: un daemon propio descarga las tendencias de Google
    // y las mete al pool. Global (no per-marca), con su switch propio (`KENI_TRENDS`); sin cola
    // ni histórico de jobs (solo añade material, no ejecuta IA). Su subpágina muestra el log por
    // barrido del daemon `trends`.
    nombre: "Google Trends",
    es_ia: false,
    claves: ["KENI_TRENDS"],
    ayuda: "Ingiere las tendencias de Google al pool, como fuente extra junto a las fuentes RSS",
    daemon: "trends",
    paralelo: "ingesta",
  },
  {
    nombre: "Fusionar",
    es_ia: true,
    claves: ["KENI_PIPELINE_FUSIONAR"],
    ayuda: "Propone qué notas son del mismo hecho y qué familias forman un mismo gran evento",
    doc: "prompt/fusionar",
    etapa: "fusionar",
  },
  {
    // Cotejar y Subtema son las dos SUB-LLAMADAS del job de Fusionar: corren DESPUÉS de la pasada
    // principal (por eso van aquí, no antes), una por grupo / por familia. Seguidoras de Fusionar
    // (sin flag propio, `claves: []`): su recorrido lo gobierna Fusionar. Cada una deja su propia
    // línea en la economía «por etapa» (`gasto_ia.etapa` = «Cotejar» / «Subtema»).
    nombre: "Cotejar",
    es_ia: true,
    claves: [],
    ayuda: "Verifica cada grupo propuesto antes de fundir las notas del mismo hecho",
    doc: "prompt/fusionar-verificar",
  },
  {
    nombre: "Subtema",
    es_ia: true,
    claves: [],
    ayuda: "Parte un macro-evento en subtemas coherentes (un carrusel por faceta)",
    doc: "prompt/fusionar-subtema",
  },
  {
    nombre: "Traducir",
    es_ia: true,
    claves: [],
    ayuda: "Adapta el texto al español de México",
    doc: "prompt/traducir",
  },
  {
    nombre: "Priorizar",
    es_ia: true,
    claves: ["KENI_PRIORIZAR_PERFIL_IA"],
    ayuda: "Ordena por relevancia para tu marca",
    doc: "prompt/priorizar",
    contextoMarca: true,
    etapa: "priorizar",
  },
  {
    nombre: "Admitir",
    es_ia: false,
    claves: [],
    ayuda: "Crea el tema admitido en la mesa de redacción",
    etapa: "admitir",
  },
  {
    nombre: "Verificar",
    es_ia: true,
    claves: ["KENI_PIPELINE_VERIFICAR"],
    ayuda: "Contrasta las fuentes antes de pasar a la mesa",
    doc: "prompt/verificar",
    queue: "verificar",
    etapa: "verificar",
    // Verificar (noticias) e Investigar evergreen son las dos vías de INVESTIGACIÓN —contrastar la
    // fuente de una historia vs. investigar una idea propia—: comparten fila horizontal (mismo `paralelo`).
    paralelo: "investigacion",
  },
  {
    // Rama PARALELA de Verificar: investiga una IDEA EVERGREEN aprobada (con web) y produce material
    // verificado que entra a producción como un tema más. No es un daemon (lo dispara aprobar la idea,
    // no un barrido): sin flag propio (`claves: []`). Su prompt es editable aquí.
    nombre: "Investigar evergreen",
    es_ia: true,
    claves: [],
    ayuda: "Investiga una idea evergreen aprobada con web y produce material verificado para producción",
    doc: "prompt/investigar-evergreen",
    contextoMarca: true,
    paralelo: "investigacion",
  },
];

/** Tipo de job → fase con cola (Investigación). */
export const QUEUE_INVESTIGACION: Record<string, string> = {
  rss: "recolectar",
  "noticias-ia": "recolectar",
  insumos: "recolectar",
  pipeline: "verificar",
  verificacion: "verificar",
  revision: "verificar",
};

/** Las fases del MOTOR de auto-producción, en orden de flujo. */
export const FASES_PRODUCCION: readonly FasePipeline[] = [
  {
    // Decisor de FORMATO: agente barato (Haiku) que, ANTES de Redactar, elige el camino del tema
    // —foto o carrusel— sobre señales ligeras (titulares, nº de notas/fuentes, evento, marca). El
    // camino elegido dirige a Redactar (foto) o a Carrusel. OFF por defecto: sin él, Redactar
    // decide el formato dentro de su propio prompt.
    nombre: "Decisor",
    es_ia: true,
    claves: ["KENI_PIPELINE_DECISOR"],
    ayuda: "Elige el camino de la pieza —foto o carrusel— antes de redactarla",
    doc: "prompt/decisor",
    contextoMarca: true,
    queue: "decisor",
    etapa: "decisor",
  },
  {
    nombre: "Redactar",
    es_ia: true,
    claves: ["KENI_PIPELINE_REDACTAR"],
    ayuda:
      "Redacta el copy que convierte la noticia verificada en pieza y revisa su voz y calidad antes de avanzar",
    doc: "prompt/redactar",
    contextoMarca: true,
    queue: "redactar",
    etapa: "redactar",
    // RAMA del Decisor: Redactar (foto) y Carrusel son los dos caminos PARALELOS entre los que el
    // Decisor enruta; comparten fila horizontal (como Recolectar + Google Trends en ingesta).
    paralelo: "redactar",
    // Los envoltorios NO son agentes sueltos: son fragmentos que `generar.componer()` inyecta
    // en este prompt según las redes pedidas (una pieza por red / copy único). La DECISIÓN de
    // formato ya no vive aquí: la toma el Decisor (fase previa) y el camino carrusel es su rama
    // paralela. Cuelgan de Redactar para editarlos donde se usan.
    subPrompts: [
      { nombre: "Redes", doc: "prompt/envoltorios/redes", ayuda: "Una pieza por red" },
      { nombre: "Unificado", doc: "prompt/envoltorios/copy-unico", ayuda: "El mismo copy para todas las redes" },
    ],
  },
  {
    // Camino CARRUSEL de Redactar: RAMA PARALELA a Redactar (mismo `paralelo` id → comparten fila).
    // Cuando el Decisor elige carrusel, el copy se redacta con este prompt (panel editorial: portada
    // paraguas + un slide por sub-historia) en vez del de foto. Comparte el motor de copy de Redactar
    // (su flag/cola); por eso no tiene flag propio (`claves: []`). Su prompt es editable aquí.
    nombre: "Carrusel",
    es_ia: true,
    claves: [],
    ayuda: "Redacta el copy como carrusel (panel de tarjetas) cuando el Decisor elige ese camino",
    doc: "prompt/redactar-carrusel",
    contextoMarca: true,
    paralelo: "redactar",
  },
  {
    nombre: "Keywords",
    es_ia: true,
    claves: ["KENI_PIPELINE_SUGERIR_HASHTAGS"],
    ayuda:
      "Propone los hashtags habituales de la marca (en gris, para aceptar o rechazar de un clic al revisar) y una imagen clave (keyword del sujeto visual) que alimenta el buscador de fotos de stock. Solo cuando al copy le faltan",
    doc: "prompt/sugerir-hashtags",
    contextoMarca: true,
    queue: "sugerir-hashtags",
    etapa: "sugerir_hashtags",
  },
  {
    nombre: "Ilustrar",
    es_ia: true,
    claves: ["KENI_PIPELINE_ILUSTRAR"],
    ayuda: "Genera imagen por IA para los temas con copy y sin imagen",
    doc: "prompt/ilustrar",
    queue: "ilustrar",
    etapa: "ilustrar",
  },
  {
    // Respaldo de imagen cuando Ilustrar no aplica: descarga inline una foto de stock (banco
    // gratuito) como ayuda visual SIN LICENCIA, no publicable hasta autorizarla. Es determinista
    // (no lanza `claude -p`): no encola jobs ni deja runs, por eso no tiene `queue` ni `etapa`.
    nombre: "Stock",
    es_ia: false,
    claves: ["KENI_PIPELINE_STOCK"],
    ayuda: "Adjunta una foto de stock como referencia sin licencia para los temas sin imagen",
    // Su subpágina son los TOGGLES de fuentes de stock por marca (no Prompt · Contexto · Logs).
    panel: "stock",
  },
  {
    // Nivel de revisión IA de la pieza terminada: corre DENTRO de la cadena de aprobación (tras
    // los OK humanos, NO justo tras Ilustrar), no encola etapa propia. Switch propio
    // (`KENI_CRITICA_IA`), OFF por defecto. `seccion` la separa de la secuencia automática anterior.
    nombre: "Crítica",
    es_ia: true,
    claves: ["KENI_CRITICA_IA"],
    ayuda: "Tras los dos OK humanos, revisa con visión la pieza terminada antes de auto-programar",
    doc: "prompt/critica",
    seccion: "Cadena de aprobación",
  },
];

/** Tipo de job → fase con cola (Producción). */
export const QUEUE_PRODUCCION: Record<string, string> = {
  decisor: "decisor",
  copy: "redactar",
  autogen: "redactar",
  "sugerir-hashtags": "sugerir-hashtags",
  imagen: "ilustrar",
};

/**
 * Un GRUPO de agentes INDEPENDIENTES (pestaña Herramientas): prompts que se lanzan a mano y NO
 * forman un pipeline. Se pintan como una CAJA por tipo (`PanelAgentes`), no como una secuencia con
 * conectores: cada caja agrupa los agentes de un mismo tipo y deja claro que son autónomos.
 */
export interface GrupoAgentes {
  /** El TIPO de agente (título de la caja). */
  titulo: string;
  /** Subtítulo de la caja: qué cubre el tipo. */
  descripcion: string;
  /** Los agentes del tipo; cada uno abre su prompt (su descripción vive en su subpágina). */
  fases: readonly FasePipeline[];
}

/**
 * HERRAMIENTAS — los agentes/prompts INDEPENDIENTES que NO son una etapa de la máquina ni un
 * fragmento inyectado en otra fase: el material que llega del equipo («Recibir», «Importar») y la
 * ideación evergreen. Cada uno se dispara desde su propio flujo (cajones del día, importación de
 * archivo, taller evergreen) y aquí se edita su prompt.
 *
 * Lo que NO vive aquí porque pertenece a una fase: la «Crítica» (nivel IA de la cadena de
 * aprobación, fase seguidora de Producción) y los «Envoltorios» de red (fragmentos que Redactar
 * inyecta en su prompt: cuelgan de esa fase como `subPrompts`).
 */
export const GRUPOS_HERRAMIENTAS: readonly GrupoAgentes[] = [
  {
    titulo: "Recibir",
    descripcion: "Material que llega del equipo, portales y corresponsales",
    fases: [
      { nombre: "Contexto", es_ia: true, claves: [], ayuda: "Indicaciones y correcciones del equipo", doc: "prompt/recibir/contexto" },
      { nombre: "Notas", es_ia: true, claves: [], ayuda: "Notas y links de Claro Sports", doc: "prompt/recibir/notas" },
      { nombre: "Portal", es_ia: true, claves: [], ayuda: "Material recibido por portal/SMS", doc: "prompt/recibir/portal" },
      { nombre: "Corresponsales", es_ia: true, claves: [], ayuda: "Aportes de corresponsales", doc: "prompt/recibir/corresponsales" },
      { nombre: "Reporteros", es_ia: true, claves: [], ayuda: "Aportes de reporteros", doc: "prompt/recibir/reporteros" },
      { nombre: "Eventos", es_ia: true, claves: [], ayuda: "Eventos de Claro Sports", doc: "prompt/recibir/eventos-claro" },
    ],
  },
  {
    titulo: "Importar",
    descripcion: "Calendarios y parrillas a la mesa de eventos",
    fases: [
      { nombre: "Calendario", es_ia: true, claves: [], ayuda: "Importa un calendario de contenido", doc: "prompt/importar/calendario" },
      { nombre: "Parrilla", es_ia: true, claves: [], ayuda: "Importa una rota/parrilla a eventos", doc: "prompt/importar/parrilla" },
    ],
  },
  {
    titulo: "Ideación",
    descripcion: "Propone contenido evergreen para la marca",
    fases: [{ nombre: "Idear", es_ia: true, claves: [], ayuda: "Propone ideas de contenido evergreen para la marca", doc: "prompt/idear" }],
  },
  {
    titulo: "Audio",
    descripcion: "Agentes que trabajan las transcripciones del gestor de audio→texto",
    fases: [
      { nombre: "Limpiar", es_ia: true, claves: [], ayuda: "Quita silencios, loops, frases repetidas y muletillas conservando el sentido", doc: "prompt/audio/limpiar" },
      { nombre: "Resumir", es_ia: true, claves: [], ayuda: "Resume la transcripción: idea central, puntos clave y citas", doc: "prompt/audio/resumir" },
      { nombre: "Aclarar", es_ia: true, claves: [], ayuda: "Detecta fragmentos dudosos y pregunta al equipo para corregirlos", doc: "prompt/audio/aclarar" },
      { nombre: "Corregir", es_ia: true, claves: [], ayuda: "Aplica las respuestas del equipo a la transcripción", doc: "prompt/audio/corregir" },
      { nombre: "Ideas", es_ia: true, claves: [], ayuda: "Extrae ideas de todo tipo (software, contenido, negocio, operación) agrupadas por categoría", doc: "prompt/audio/ideas" },
      { nombre: "Clips", es_ia: true, claves: [], ayuda: "Detecta los momentos clipeables y su hook, con el minuto para recortarlos", doc: "prompt/audio/clips" },
      { nombre: "Capítulos", es_ia: true, claves: [], ayuda: "Genera los capítulos de YouTube (SEO) listos para pegar en la descripción", doc: "prompt/audio/capitulado" },
    ],
  },
];

/**
 * DESARROLLO — el contexto de los agentes de AUTO-DESARROLLO (clase editorial `desarrollo`). Igual
 * que Herramientas: NO es un pipeline con interruptor, son prompts autónomos que se editan a mano,
 * agrupados en CAJAS por tipo (el carril del kanban de Sugerencias y los Ralph que conversan con el
 * equipo). Cada agente abre su subpágina (Prompt · Acerca); su nombre es de 1-2 palabras y la
 * descripción larga vive dentro, en su «Acerca».
 */
export const GRUPOS_DESARROLLO: readonly GrupoAgentes[] = [
  {
    titulo: "Carril",
    descripcion: "Las fases del kanban de auto-desarrollo, de explorar a revisar",
    fases: [
      { nombre: "Analyze", es_ia: true, claves: [], ayuda: "Explora el repo antes de tocar nada", doc: "editorial/desarrollo/analyze" },
      { nombre: "Plan", es_ia: true, claves: [], ayuda: "Diseña el cambio: alcance, seams y tests", doc: "editorial/desarrollo/plan" },
      { nombre: "Build", es_ia: true, claves: [], ayuda: "Implementa siguiendo el estilo del repo", doc: "editorial/desarrollo/build" },
      { nombre: "Review", es_ia: true, claves: [], ayuda: "Checklist final antes de promover a main", doc: "editorial/desarrollo/review" },
    ],
  },
  {
    titulo: "Ralph",
    descripcion: "El contexto base de los agentes Ralph que conversan con el equipo",
    fases: [
      { nombre: "Desarrollo", es_ia: true, claves: [], ayuda: "Ralph de auto-desarrollo: trabaja el repo en su worktree", doc: "editorial/desarrollo/ralph" },
      { nombre: "Operativo", es_ia: true, claves: [], ayuda: "Ralph operativo: asistente del equipo de redes (MCP)", doc: "editorial/desarrollo/ralph-operativo" },
    ],
  },
];

/** Agentes de una pestaña-catálogo (Herramientas o Desarrollo) aplanados: para resolver su
 *  subpágina por slug (`/maquina/contexto/:proceso/:fase`). */
export function agentesDe(proceso: "herramientas" | "desarrollo"): readonly FasePipeline[] {
  const grupos = proceso === "desarrollo" ? GRUPOS_DESARROLLO : GRUPOS_HERRAMIENTAS;
  return grupos.flatMap((g) => g.fases);
}
