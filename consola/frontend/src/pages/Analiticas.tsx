import { BarChart3, Megaphone, Presentation } from "lucide-react";
import { Outlet } from "react-router-dom";

import { TabsHub, type ItemTabHub } from "@/components/layout/TabsHub";

const TABS: ItemTabHub[] = [
  { ruta: "/analiticas/metricas", etiqueta: "Métricas", icono: BarChart3 },
  { ruta: "/analiticas/comercial", etiqueta: "Comercial", icono: Megaphone },
  { ruta: "/analiticas/reporte-deportes", etiqueta: "Reporte deportes", icono: Presentation },
];

/**
 * Hub de Analíticas: reúne los tres puntos de medición y reporte (rendimiento
 * orgánico, seguimiento de comercial con KPI y deck semanal de Claro Sports).
 */
export default function Analiticas() {
  return (
    <>
      <TabsHub items={TABS} etiquetaAria="Pestañas de Analíticas" />
      <Outlet />
    </>
  );
}
