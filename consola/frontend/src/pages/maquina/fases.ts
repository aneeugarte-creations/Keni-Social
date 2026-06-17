/**
 * Las FASES de las dos máquinas (Investigación y Producción), en orden de flujo.
 *
 * Antes vivían inline en `FlujoInvestigacion` y `CockpitProduccion`; al consolidar todo en la
 * página «Contexto» (Máquina) se extraen aquí para que un único `PanelPipeline` las pinte como
 * el ESQUELETO de cada pestaña. Cada fase resuelve su switch por la PRIMERA de sus `claves`
 * presente en el catálogo; las que solo cuelgan del maestro virtual del proceso lo indican con
 * `heredada`.
 */
import type { FasePipeline } from "@/pages/monitor/PanelPipeline";

/** Slug estable de una fase para su subpágina (`/maquina/contexto/:proceso/:fase`). */
export function slugFase(nombre: string): string {
  return nombre
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/**
 * Una fase TIENE CONTENIDO propio (algo que mostrar en su subpágina Prompt · Contexto · Logs) si
 * tiene prompt (`doc`), contexto editorial de marca (`contextoMarca`), histórico de runs por etapa
 * (`etapa`) o cola viva (`queue`). Sin nada de esto la subpágina no aporta: no es navegable y, si
 * además no tiene toggle propio, NO es una etapa (no debe pintarse como fila).
 */
export function tieneContenido(fase: FasePipeline): boolean {
  return Boolean(fase.doc || fase.contextoMarca || fase.etapa || fase.queue);
}

/** Maestro VIRTUAL de Investigación: respaldo de las fases sin flag físico propio. */
export const MAESTRO_INVESTIGACION = "KENI_INVESTIGACION";
/** Maestro VIRTUAL de Producción: respaldo de las fases sin flag físico propio. */
export const MAESTRO_PRODUCCION = "KENI_PRODUCCION";

/** El flujo COMPLETO de Investigación (ADR 0011), de ENTRADA a SALIDA. */
export const FASES_INVESTIGACION: readonly FasePipeline[] = [
  {
    nombre: "Recolectar",
    es_ia: false,
    claves: ["KENI_PIPELINE_RECOLECTAR", MAESTRO_INVESTIGACION],
    ayuda: "Recolecta artículos de las fuentes y agrupa las notas parecidas del mismo evento",
    queue: "recolectar",
    excepciones: { base: MAESTRO_INVESTIGACION, nota: "Apaga Recolectar y Verificar juntas." },
  },
  {
    // Cotejo previo a la fusión: corre por grupo propuesto ANTES de fundir. Seguidora del flag de
    // Fusionar (solo el maestro en `claves`): no pinta switch propio, su recorrido lo gobierna Fusionar.
    nombre: "Cotejar",
    es_ia: true,
    claves: [MAESTRO_INVESTIGACION],
    ayuda: "Verifica cada grupo propuesto antes de fundir",
    doc: "prompt/fusionar-verificar",
  },
  {
    nombre: "Fusionar",
    es_ia: true,
    claves: ["KENI_PIPELINE_FUSIONAR", MAESTRO_INVESTIGACION],
    ayuda: "Funde las notas agrupadas en una sola historia",
    doc: "prompt/fusionar",
    etapa: "fusionar",
  },
  {
    // Etiqueta familias de un mismo gran evento (historias DISTINTAS, sin fundirlas) para sacarlas
    // como un carrusel. Corre dentro del paso de Fusionar; seguidora de su flag (solo el maestro en
    // `claves`): no pinta switch propio, su recorrido lo gobierna Fusionar.
    nombre: "Macro-evento",
    es_ia: true,
    claves: [MAESTRO_INVESTIGACION],
    ayuda: "Agrupa historias distintas de un mismo gran evento (carrusel)",
    doc: "prompt/fusionar-macroevento",
  },
  {
    nombre: "Traducir",
    es_ia: true,
    claves: [MAESTRO_INVESTIGACION],
    ayuda: "Adapta el texto al español de México",
    doc: "prompt/traducir",
  },
  {
    nombre: "Clasificar",
    es_ia: true,
    claves: ["KENI_CLASIFICAR_MARCA_IA", MAESTRO_INVESTIGACION],
    ayuda: "Asigna marca a las notas de últimas horas",
    doc: "prompt/clasificar-marca",
    contextoMarca: true,
  },
  {
    nombre: "Priorizar",
    es_ia: true,
    claves: ["KENI_PRIORIZAR_PERFIL_IA", MAESTRO_INVESTIGACION],
    ayuda: "Ordena por relevancia para tu marca",
    doc: "prompt/priorizar",
    contextoMarca: true,
    etapa: "priorizar",
  },
  {
    nombre: "Admitir",
    es_ia: false,
    claves: [MAESTRO_INVESTIGACION],
    ayuda: "Crea el tema admitido en la mesa de redacción",
    etapa: "admitir",
  },
  {
    nombre: "Verificar",
    es_ia: true,
    claves: ["KENI_PIPELINE_VERIFICAR", MAESTRO_INVESTIGACION],
    ayuda: "Contrasta las fuentes antes de pasar a la mesa",
    doc: "prompt/verificar",
    queue: "verificar",
    etapa: "verificar",
    excepciones: { base: MAESTRO_INVESTIGACION, nota: "Apaga Recolectar y Verificar juntas." },
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
    nombre: "Redactar",
    es_ia: true,
    claves: ["KENI_PIPELINE_REDACTAR", MAESTRO_PRODUCCION],
    ayuda:
      "Redacta el copy que convierte la noticia verificada en pieza y revisa su voz y calidad antes de avanzar",
    doc: "prompt/redactar",
    contextoMarca: true,
    queue: "redactar",
    etapa: "redactar",
    excepciones: {
      base: MAESTRO_PRODUCCION,
      nota: "Apagar «Producción» en una marca la deja sin copy automático.",
    },
    // Los envoltorios NO son agentes sueltos: son fragmentos que `generar.componer()` inyecta
    // en este prompt según las redes pedidas (una pieza por red / copy único / decisión de
    // carrusel). Cuelgan de Redactar para editarlos donde se usan.
    subPrompts: [
      { nombre: "Redes", doc: "prompt/envoltorios/redes", ayuda: "Una pieza por red" },
      { nombre: "Unificado", doc: "prompt/envoltorios/copy-unico", ayuda: "El mismo copy para todas las redes" },
      { nombre: "Carrusel", doc: "prompt/envoltorios/carrusel", ayuda: "Decisión de carrusel" },
    ],
  },
  {
    nombre: "Sugerir hashtags",
    es_ia: true,
    claves: ["KENI_PIPELINE_SUGERIR_HASHTAGS", MAESTRO_PRODUCCION],
    ayuda:
      "Saca del historial de la marca los hashtags habituales y, al revisar la pieza, sugiere en gris los más relevantes para aceptar o rechazar de un clic. Solo cuando al copy le faltan",
    doc: "prompt/sugerir-hashtags",
    contextoMarca: true,
    queue: "sugerir-hashtags",
    etapa: "sugerir_hashtags",
  },
  {
    nombre: "Ilustrar",
    es_ia: true,
    claves: ["KENI_PIPELINE_ILUSTRAR", MAESTRO_PRODUCCION],
    ayuda: "Genera imagen por IA para los temas con copy y sin imagen",
    doc: "prompt/ilustrar",
    queue: "ilustrar",
    etapa: "ilustrar",
    excepciones: {
      base: "KENI_PIPELINE_ILUSTRAR",
      nota: "Apagar «Ilustrar» en una marca la deja sin imagen por IA.",
    },
  },
  {
    // Nivel de revisión IA de la pieza terminada: corre DENTRO de la cadena de aprobación (tras
    // los OK humanos), no encola etapa propia. Switch propio (`KENI_CRITICA_IA`), OFF por defecto.
    nombre: "Crítica",
    es_ia: true,
    claves: ["KENI_CRITICA_IA", MAESTRO_PRODUCCION],
    ayuda: "Revisa con visión la pieza terminada en la cadena de aprobación, antes de auto-programar",
    doc: "prompt/critica",
  },
];

/** Tipo de job → fase con cola (Producción). */
export const QUEUE_PRODUCCION: Record<string, string> = {
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
];
