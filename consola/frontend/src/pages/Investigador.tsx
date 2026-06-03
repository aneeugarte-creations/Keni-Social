import { Globe } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { PanelPlanDelDia } from "./ParrillaDia";
import { PanelTendencias } from "./Radar";

/**
 * Página "El Investigador": el hub unificado de Investigación. Antes "Plan del
 * día" (ParrillaDia) y "Descubrimiento" (Radar) eran dos páginas separadas, pero
 * son dos vistas del MISMO dataset — el plan ordenado del día vs. las señales
 * crudas de las que deriva. Aquí viven bajo una sola cabecera y un control
 * segmentado in-page (no rutas nuevas):
 *
 *   - "Plan de hoy" (por defecto, lo más importante): la lista jerarquizada de
 *     contenidos del día (reusa `PanelPlanDelDia` de ParrillaDia).
 *   - "Descubrimiento": lo viral del momento, crudo (reusa `PanelTendencias` de
 *     Radar). El panel "Auto" (admin) NO vive aquí.
 *
 * Cada panel conserva su propio fetch/estado (país + marca activa); no se
 * duplica esa lógica. El segmento activo es estado local (useState), no URL.
 */
export default function Investigador() {
  const [vista, setVista] = React.useState("plan");

  return (
    <>
      <PageHeader
        titulo="El Investigador"
        descripcion="Las noticias y tendencias del día por marca, listas para llevar a la parrilla — sin rastrear fuentes a mano."
        acciones={
          <Button asChild variant="outline" size="sm">
            <Link to="/datos/investigacion/termometro">
              <Globe className="h-4 w-4" />
              Termómetro mundial
            </Link>
          </Button>
        }
      />
      <Tabs value={vista} onValueChange={setVista} className="space-y-4">
        <TabsList>
          <TabsTrigger value="plan">Plan de hoy</TabsTrigger>
          <TabsTrigger value="descubrimiento">Descubrimiento</TabsTrigger>
        </TabsList>
        <TabsContent value="plan">
          <PanelPlanDelDia />
        </TabsContent>
        <TabsContent value="descubrimiento">
          <PanelTendencias />
        </TabsContent>
      </Tabs>
    </>
  );
}
