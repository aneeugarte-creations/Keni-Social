import { useNavigate } from "react-router-dom";

import { GestionPiezas } from "@/pages/piezas/GestionPiezas";

/** Workspace "todas las marcas" (sin aislar): coincide con el centinela global de marca. */

/**
 * Pestaña "Lista" del hub Feed: la SUPERFICIE de contenido en lista.
 *
 * Solo pinta el contenido (panel de reciclaje + `GestionPiezas` en modo lista). La
 * configuración editorial que antes colgaba del menú "Gestionar" se mudó a su sitio: los
 * HORARIOS al hub Calendario (Programación) y las ETIQUETAS / HASHTAGS a Texto ›
 * Estrategia de marcas. Por eso esta pestaña ya no lleva acciones de cabecera. La marca del
 * workspace ES la marca activa global (sin selector local).
 */
export default function ListaPublicacion() {
  const navigate = useNavigate();

  // Encolar sin franjas de horario devuelve 400: llevamos al usuario a configurar
  // los horarios (en el calendario de Programación), que es el camino vigente.
  const irAConfigurarHorarios = () =>
    navigate("/operacion/programacion?horarios=1");

  return (
    <>
      <GestionPiezas modo="lista" onConfigurarHorarios={irAConfigurarHorarios} />
    </>
  );
}
