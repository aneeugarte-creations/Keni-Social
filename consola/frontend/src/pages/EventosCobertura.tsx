/**
 * Eventos (a cubrir) — hub de Fuentes/Investigación.
 *
 * Ola "Calendario = turnos / Fuentes = eventos": la gestión de los EVENTOS a cubrir
 * dejó de vivir en el Calendario (que ahora es solo turnos) y habita aquí, en el hub de
 * Fuentes. Reutiliza `PanelEventos` (alta/filtrado/edición sobre `/api/rota/eventos`),
 * que también consumen los cajones (Excel → cajón → evento, ola "crear evento").
 *
 * La ASIGNACIÓN de cobertura (qué turno cubre cada evento) sigue siendo específica de
 * Claro Sports y vive en la rejilla de Turnos del Calendario (no destructivo: la lógica
 * de cobertura está intacta allí). Aquí solo damos de alta y gestionamos los eventos;
 * para Claro Sports añadimos un enlace a esa rejilla. La lista de eventos en sí es
 * general (cualquier marca puede consultarla), pero hoy la rota solo cubre Claro Sports.
 */
import { CalendarClock } from "lucide-react";
import { Link } from "react-router-dom";

import { PanelEventos } from "@/components/eventos/PanelEventos";
import { MARCA_CLARO_SPORTS } from "@/components/layout/gating-marca";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";

export default function EventosCobertura() {
  const { marcaActiva } = useMarcaActiva();
  // La cobertura (asignación a turnos) es de Claro Sports: en su contexto (o en "Todas")
  // ofrecemos el atajo a la rejilla de Turnos del Calendario donde se asigna.
  const muestraCobertura = marcaActiva === null || marcaActiva === MARCA_CLARO_SPORTS;

  return (
    <>
      <PageHeader
        titulo="Eventos"
        descripcion="Eventos y transmisiones a cubrir. Da de alta, filtra y prioriza; la asignación de cobertura se gestiona en los Turnos del Calendario (Claro Sports)."
        acciones={
          muestraCobertura ? (
            <Button asChild variant="outline" size="sm">
              <Link to="/operacion/calendario/turnos">
                <CalendarClock className="h-4 w-4" /> Cobertura en Turnos
              </Link>
            </Button>
          ) : undefined
        }
      />
      <PanelEventos />
    </>
  );
}
