import { ScanSearch, ScanText } from "lucide-react";
import { Outlet } from "react-router-dom";

import { TabsHub, type ItemTabHub } from "@/components/layout/TabsHub";

const TABS: ItemTabHub[] = [
  { ruta: "/revision/editorial", etiqueta: "Editorial", icono: ScanText },
  { ruta: "/revision/verificacion", etiqueta: "Verificación", icono: ScanSearch },
];

/**
 * Hub de Revisión: agrupa los dos validadores previos a publicar (QA del copy
 * y verificación de autenticidad de imágenes/videos).
 */
export default function Revision() {
  return (
    <>
      <TabsHub items={TABS} etiquetaAria="Pestañas de Revisión" />
      <Outlet />
    </>
  );
}
