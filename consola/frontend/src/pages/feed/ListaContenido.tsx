import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { GestionPublicaciones } from "@/pages/publicaciones/GestionPublicaciones";
import { PanelReciclaje } from "@/pages/publicaciones/PanelReciclaje";

const CABECERA = {
  titulo: "Contenido",
  descripcion:
    "El contenido del equipo en lista: cada pieza con su estado y checklist por plataforma.",
};

/** Workspace "todas las marcas" (sin aislar): coincide con el centinela global de marca. */
const WORKSPACE_TODAS = "__todas__";

/**
 * Pestaña "Lista" del hub Feed: la SUPERFICIE de contenido en lista.
 *
 * Solo pinta el contenido (panel de reciclaje + `GestionPublicaciones` en modo lista). La
 * configuración editorial que antes colgaba del menú "Gestionar" se mudó a su sitio: la
 * CADENCIA al hub Calendario (Programación) y las ETIQUETAS / HASHTAGS a Biblioteca ›
 * Estrategia de marcas; las franjas y las plantillas quedaron obsoletas. Por eso esta
 * pestaña ya no lleva acciones de cabecera. La marca del workspace ES la marca activa
 * global (sin selector local).
 */
export default function ListaContenido() {
  const navigate = useNavigate();
  // El workspace ES la marca activa global (switch de la topbar). No hay estado ni
  // persistencia local de marca aquí.
  const { marcaActiva } = useMarcaActiva();
  const workspace = marcaActiva ?? WORKSPACE_TODAS;

  // Encolar/reciclar sin cadencia ni franjas devuelve 400: llevamos al usuario a configurar
  // la cadencia (ahora en el calendario de Programación), que es el camino vigente.
  const irAConfigurarCadencia = () =>
    navigate("/operacion/calendario/calendario?cadencia=1");

  return (
    <>
      <PageHeader {...CABECERA} />

      {/* Sugerencias proactivas de reciclaje (#110): se ocultan solas si no hay candidatas.
          Respetan el workspace activo. */}
      <PanelReciclaje
        filtros={{ marca: workspace === WORKSPACE_TODAS ? undefined : workspace }}
        onConfigurarCadencia={irAConfigurarCadencia}
      />

      <GestionPublicaciones modo="lista" onConfigurarCadencia={irAConfigurarCadencia} />
    </>
  );
}
