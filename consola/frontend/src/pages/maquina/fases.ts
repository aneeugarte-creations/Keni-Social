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
    nombre: "Aprobar",
    es_ia: false,
    claves: ["KENI_AUTO_PREAPROBACION"],
    ayuda: "El OK humano antes de programar la pieza",
    heredada: "el switch auto-aprueba las de bajo riesgo",
    etapa: "aprobar",
  },
  {
    nombre: "Publicar",
    es_ia: false,
    claves: ["KENI_PUBLICAR_REAL"],
    ayuda: "Postea de verdad en el programador (apagado: simulación)",
    precaucion: "Publica de verdad",
    excepciones: {
      base: "KENI_PUBLICAR_REAL",
      nota: "Apagar «Publicar» en una marca la deja en simulación (sin postear).",
    },
  },
];

/** Tipo de job → fase con cola (Producción). */
export const QUEUE_PRODUCCION: Record<string, string> = {
  copy: "redactar",
  autogen: "redactar",
  imagen: "ilustrar",
};

/**
 * IMPORTACIÓN — las herramientas de material recibido del equipo (recibir/* + importar/*). No son
 * un flujo de daemon: son prompts que se lanzan a mano sobre lo que llega. Se listan con el MISMO
 * diseño que Investigación/Producción (filas que abren su prompt); sin switches ni colas.
 */
export const FASES_IMPORTACION: readonly FasePipeline[] = [
  { nombre: "Contexto", es_ia: true, claves: [], ayuda: "Indicaciones y correcciones del equipo", doc: "prompt/recibir/contexto" },
  { nombre: "Notas", es_ia: true, claves: [], ayuda: "Notas y links de Claro Sports", doc: "prompt/recibir/notas" },
  { nombre: "Portal", es_ia: true, claves: [], ayuda: "Material recibido por portal/SMS", doc: "prompt/recibir/portal" },
  { nombre: "Corresponsales", es_ia: true, claves: [], ayuda: "Aportes de corresponsales", doc: "prompt/recibir/corresponsales" },
  { nombre: "Reporteros", es_ia: true, claves: [], ayuda: "Aportes de reporteros", doc: "prompt/recibir/reporteros" },
  { nombre: "Eventos", es_ia: true, claves: [], ayuda: "Eventos de Claro Sports", doc: "prompt/recibir/eventos-claro" },
  { nombre: "Calendario", es_ia: true, claves: [], ayuda: "Importa un calendario de contenido", doc: "prompt/importar/calendario" },
  { nombre: "Parrilla", es_ia: true, claves: [], ayuda: "Importa una rota/parrilla a eventos", doc: "prompt/importar/parrilla" },
];

/**
 * HERRAMIENTAS — prompts independientes que NO son una etapa de la máquina: la ideación evergreen,
 * la crítica IA, los hashtags, los envoltorios del copy y el asistente de copy (resumir/variantes,
 * que dispara el agente vía la tool MCP `keni_generar_copy`). Mismo diseño; abren su prompt.
 */
export const FASES_HERRAMIENTAS: readonly FasePipeline[] = [
  { nombre: "Idear", es_ia: true, claves: [], ayuda: "Propone ideas de contenido evergreen para la marca", doc: "prompt/idear" },
  { nombre: "Crítica", es_ia: true, claves: [], ayuda: "Crítica con visión antes de publicar", doc: "prompt/critica" },
  { nombre: "Hashtags", es_ia: true, claves: [], ayuda: "Sugerencias de hashtags por marca/red", doc: "prompt/hashtags" },
  { nombre: "Redes", es_ia: true, claves: [], ayuda: "Envoltorio: una pieza por red", doc: "prompt/envoltorios/redes" },
  { nombre: "Unificado", es_ia: true, claves: [], ayuda: "Envoltorio: el mismo copy para todas las redes", doc: "prompt/envoltorios/copy-unico" },
  { nombre: "Carrusel", es_ia: true, claves: [], ayuda: "Envoltorio: decisión de carrusel", doc: "prompt/envoltorios/carrusel" },
  { nombre: "Resumir", es_ia: true, claves: [], ayuda: "Asistente de copy IA (modo resumir) · vía agente/MCP", doc: "prompt/asistente/resumir" },
  { nombre: "Variantes", es_ia: true, claves: [], ayuda: "Asistente de copy IA (modo variantes) · vía agente/MCP", doc: "prompt/asistente/variantes" },
];

/** Las herramientas no tienen colas de daemon: el mapa va vacío (sin conteos por fila). */
export const QUEUE_VACIA: Record<string, string> = {};
