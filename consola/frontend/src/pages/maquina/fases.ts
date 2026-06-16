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
    ayuda: "Recolecta artículos de las fuentes",
    queue: "recolectar",
    excepciones: { base: MAESTRO_INVESTIGACION, nota: "Apaga Recolectar y Verificar juntas." },
  },
  {
    nombre: "Agrupar",
    es_ia: false,
    claves: ["KENI_PIPELINE_RECOLECTAR", MAESTRO_INVESTIGACION],
    ayuda: "Agrupa las notas parecidas del mismo evento",
    heredada: "junto con Recolectar",
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
    heredada: "con Investigación",
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
    heredada: "con Investigación",
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
    ayuda: "Redacta el copy que convierte la noticia verificada en pieza",
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
    nombre: "Revisar",
    es_ia: false,
    claves: ["KENI_PIPELINE_REVISAR", MAESTRO_PRODUCCION],
    ayuda: "Verifica la voz y la calidad del copy antes de avanzar",
    heredada: "con Producción",
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
