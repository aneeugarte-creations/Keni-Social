/**
 * NoticiasHub — pieza «Noticias» del hub Investigación e ÍNDICE del hub.
 *
 * Noticias = items informativos/temporales a publicar (agencias, RSS ajenos,
 * reporteros, corresponsales). Caducan. Su única superficie es el POOL persistente
 * del motor de ingesta (`Cobertura`): el flujo continuo de noticias, donde las
 * Historias ya vienen ordenadas por señal/breaking — eso ES el descubrimiento. El
 * antiguo "Descubrimiento" en vivo (Radar v1: Google Trends + plan del día) se
 * retiró; el pool persistente es la única fuente de verdad de la ingesta.
 *
 * AQUÍ YA NO HAY AJUSTES (Fase 3: UN solo sitio para los ajustes de la máquina): el
 * motor de noticias (maestro de Investigación, excepciones por marca y todos los
 * grupos `noticias_*`) se edita en el drawer de ajustes del Monitor, sección
 * «Investigación». El riel del proceso sigue siendo informativo, y el antiguo panel
 * «Monitor de investigación» embebido es ahora un chip compacto que enlaza al
 * Monitor prefiltrado (`?proceso=investigacion`).
 */
import Cobertura from "./Cobertura";
import { ChipInvestigacion } from "./noticias/ChipInvestigacion";
import { RielInvestigacion } from "./noticias/RielInvestigacion";

export default function NoticiasHub() {
  return (
    <div className="space-y-4">
      <RielInvestigacion />
      <ChipInvestigacion />
      <Cobertura />
    </div>
  );
}
