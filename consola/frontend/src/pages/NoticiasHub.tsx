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
 * El armado MANUAL del Termómetro (galería internacional) también se retiró: la
 * galería se genera sola por el pipeline. Las acciones de página que queden las
 * portaliza `Cobertura` a su menú "⋮"; aquí solo viven los AJUSTES del motor (admin).
 */
import { AjustesPagina } from "@/components/layout/AjustesPagina";
import { AccionesPagina } from "@/components/layout/encabezado";
import { useSesion } from "@/hooks/sesion-contexto";
import { SeccionesAjustes } from "@/pages/configuracion/SeccionFuncionalidad";

import Cobertura from "./Cobertura";

// Grupos del catálogo que gobiernan el motor de noticias (espejan
// `ajustes_catalogo.GRUPOS_NOTICIAS` del backend), en lenguaje editorial:
// qué entra → orden → rendimiento → última hora → producción + bloque técnico.
const GRUPOS_NOTICIAS = new Set([
  "noticias_entrada",
  "noticias_orden",
  "noticias_rendimiento",
  "noticias_breaking",
  "noticias_produccion",
  "noticias_produccion_marca",
  "noticias_tecnico",
]);

export default function NoticiasHub() {
  const { usuario } = useSesion();
  const esAdmin = usuario === null || usuario.rol === "admin";
  return (
    <div className="space-y-4">
      {/* Reparto canónico de cabecera: los AJUSTES del motor de noticias al panel lateral
          (solo admin). Las ACCIONES de página (p. ej. «Borrar todo») las aporta `Cobertura`
          al mismo hueco, en su menú "⋮". */}
      {esAdmin && (
        <AccionesPagina>
          <AjustesPagina
            titulo="Ajustes del motor de noticias"
            descripcion="Controlan qué noticias entran al pool, en qué orden se muestran y cuáles disparan producción automática. Los cambios aplican al momento (hasta ~1 minuto)."
          >
            <SeccionesAjustes ids={GRUPOS_NOTICIAS} />
          </AjustesPagina>
        </AccionesPagina>
      )}
      <Cobertura />
    </div>
  );
}
