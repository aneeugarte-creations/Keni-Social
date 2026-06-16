/**
 * FlujoInvestigacion — el pipeline de INVESTIGACIÓN consolidado: todas las fases del intervalo aguas
 * arriba (Recolectar · Agrupar · Fusionar · Traducir · Clasificar · Priorizar · Admitir · Verificar)
 * como tarjetas grandes en orden, con icono, switch (on/off), conteos de cola y «Editar prompt».
 *
 * Es una configuración del panel genérico `PanelPipeline` (la presentación —tarjetas, switches,
 * cola, maestro «Máquina», overlay de prompt, excepciones por marca— vive ahí y la comparte con
 * Producción). Aquí solo se declaran las FASES de Investigación y su reparto de cola.
 */
import { PanelPipeline, type FasePipeline } from "@/pages/monitor/PanelPipeline";
import { ChipInvestigacion } from "@/pages/noticias/ChipInvestigacion";
import type { ColaMonitor } from "@/types";

/** Maestro VIRTUAL de Investigación: respaldo de las fases sin flag físico propio. */
const MAESTRO = "KENI_INVESTIGACION";

// El flujo COMPLETO del intervalo antes (en el flujo) (ADR 0011), en orden de ENTRADA a SALIDA.
const FASES: readonly FasePipeline[] = [
  {
    nombre: "Recolectar",
    es_ia: false,
    claves: ["KENI_PIPELINE_RECOLECTAR", MAESTRO],
    ayuda: "Recolecta artículos de las fuentes",
    queue: "recolectar",
    excepciones: { base: MAESTRO, nota: "Apaga Recolectar y Verificar juntas." },
  },
  {
    nombre: "Agrupar",
    es_ia: false,
    claves: ["KENI_PIPELINE_RECOLECTAR", MAESTRO],
    ayuda: "Agrupa las notas parecidas del mismo evento",
    heredada: "junto con Recolectar",
  },
  {
    nombre: "Fusionar",
    es_ia: true,
    claves: ["KENI_PIPELINE_FUSIONAR", MAESTRO],
    ayuda: "Funde las notas agrupadas en una sola historia",
    doc: "prompt/fusionar",
  },
  {
    nombre: "Traducir",
    es_ia: true,
    claves: [MAESTRO],
    ayuda: "Adapta el texto al español de México",
    doc: "prompt/traducir",
    heredada: "con Investigación",
  },
  {
    nombre: "Clasificar",
    es_ia: true,
    claves: ["KENI_CLASIFICAR_MARCA_IA", MAESTRO],
    ayuda: "Asigna marca a las notas de últimas horas",
    doc: "prompt/clasificar-marca",
  },
  {
    nombre: "Priorizar",
    es_ia: true,
    claves: ["KENI_PRIORIZAR_PERFIL_IA", MAESTRO],
    ayuda: "Ordena por relevancia para tu marca",
    doc: "prompt/priorizar",
  },
  {
    nombre: "Admitir",
    es_ia: false,
    claves: [MAESTRO],
    ayuda: "Crea el tema admitido en la mesa de redacción",
    heredada: "con Investigación",
  },
  {
    nombre: "Verificar",
    es_ia: true,
    claves: ["KENI_PIPELINE_VERIFICAR", MAESTRO],
    ayuda: "Contrasta las fuentes antes de pasar a la mesa",
    doc: "prompt/verificar",
    queue: "verificar",
    excepciones: { base: MAESTRO, nota: "Apaga Recolectar y Verificar juntas." },
  },
];

/** Tipo de job → fase con cola. Recolectar agrupa el pool; Verificar la verificación de la fuente. */
const QUEUE_POR_TIPO: Record<string, string> = {
  rss: "recolectar",
  "noticias-ia": "recolectar",
  insumos: "recolectar",
  pipeline: "verificar",
  verificacion: "verificar",
  "revision": "verificar",
};

export function FlujoInvestigacion({
  cola,
  esAdmin = true,
}: {
  cola?: ColaMonitor;
  esAdmin?: boolean;
}) {
  return (
    <PanelPipeline
      titulo="Pipeline en vivo"
      fases={FASES}
      queuePorTipo={QUEUE_POR_TIPO}
      admisionEn="verificar"
      cola={cola}
      esAdmin={esAdmin}
      chip={<ChipInvestigacion />}
    />
  );
}
