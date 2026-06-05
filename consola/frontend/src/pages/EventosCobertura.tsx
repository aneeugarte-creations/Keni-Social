/**
 * Eventos y programas — hub de Fuentes/Investigación.
 *
 * Ola "Programas → Fuentes": el catálogo de programas de Claro Sports dejó
 * de vivir en la pestaña "Programas" del Calendario (que ahora es solo turnos) y
 * habita aquí, junto con los eventos a cubrir. Dos sub-pestañas:
 *
 *   • Eventos  — alta/filtrado/edición sobre `/api/rota/eventos` (`PanelEventos`).
 *   • Programas — catálogo evergreen de Claro Sports (`PanelProgramas`), antes en
 *                 la pestaña "Programas" de Turnos.
 *
 * NON-DESTRUCTIVO: los endpoints `/api/rota/eventos` y `/api/rota/programas` y su
 * lógica de backend permanecen intactos. La asignación de cobertura (qué turno
 * cubre cada evento) sigue en la rejilla de Turnos del Calendario.
 */
import { CalendarClock } from "lucide-react";
import { Link } from "react-router-dom";

import { PanelEventos } from "@/components/eventos/PanelEventos";
import { PanelProgramas } from "@/components/eventos/PanelProgramas";
import { MARCA_CLARO_SPORTS } from "@/components/layout/gating-marca";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";

export default function EventosCobertura() {
  const { marcaActiva } = useMarcaActiva();
  // La cobertura (asignación a turnos) es de Claro Sports: en su contexto (o en "Todas")
  // ofrecemos el atajo a la rejilla de Turnos del Calendario donde se asigna.
  const muestraCobertura = marcaActiva === null || marcaActiva === MARCA_CLARO_SPORTS;

  return (
    <>
      <PageHeader
        titulo="Eventos y programas"
        descripcion="Eventos a cubrir y catálogo de programas. Da de alta, filtra y prioriza; la asignación de cobertura se gestiona en los Turnos del Calendario (Claro Sports)."
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
      <Tabs defaultValue="eventos" className="space-y-4">
        <TabsList>
          <TabsTrigger value="eventos">Eventos</TabsTrigger>
          <TabsTrigger value="programas">Programas</TabsTrigger>
        </TabsList>
        <TabsContent value="eventos">
          <PanelEventos />
        </TabsContent>
        <TabsContent value="programas">
          <PanelProgramas />
        </TabsContent>
      </Tabs>
    </>
  );
}
