import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { PanelPlan } from "@/pages/piezas/GestionPlan";
import { PanelKeywords } from "@/pages/piezas/PanelKeywords";

/**
 * Pestaña «Plan» del hub Programa (`/operacion/programa/plan`): la TAXONOMÍA de líneas de la marca
 * activa, en dos sub-pestañas — «Horarios» (cuántas piezas/día por línea, sus horas, las redes del
 * plan y el alta/baja de líneas) y «Keywords» (el hashtag de cada línea y sus palabras clave del
 * clasificador). Hermana de «Programación» (el calendario).
 *
 * El título lo pinta la subnav del hub (pestaña «Plan»); aquí no se repite. El editor es POR MARCA
 * (`key` por marca: remontar al cambiar evita arrastrar el plan de la marca anterior). Con la vista
 * «Todas» (sin marca activa) no hay un plan único que editar.
 */
export default function ProgramaPlan() {
  const { marcaActiva } = useMarcaActiva();
  if (!marcaActiva) {
    return (
      <p className="py-6 text-sm text-muted-foreground">
        Elige una marca (arriba) para ver y editar su plan de líneas.
      </p>
    );
  }
  return (
    <Tabs defaultValue="horarios" className="space-y-4">
      <TabsList>
        <TabsTrigger value="horarios">Horarios</TabsTrigger>
        <TabsTrigger value="keywords">Keywords</TabsTrigger>
      </TabsList>
      <TabsContent value="horarios">
        <PanelPlan key={marcaActiva} marca={marcaActiva} />
      </TabsContent>
      <TabsContent value="keywords">
        <PanelKeywords key={marcaActiva} marca={marcaActiva} />
      </TabsContent>
    </Tabs>
  );
}
