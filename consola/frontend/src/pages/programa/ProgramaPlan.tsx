import { Tags } from "lucide-react";

import { TituloPagina } from "@/components/layout/encabezado";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { PanelPlan } from "@/pages/piezas/GestionPlan";

/**
 * Pestaña «Plan» del hub Programa (`/operacion/programa/plan`): la TAXONOMÍA de líneas de la
 * marca activa — cada línea con su hashtag (derivado del nombre, solo lectura), sus keywords del
 * clasificador, su cupo/día y sus horarios. Hermana de «Programación» (el calendario).
 *
 * El editor es POR MARCA (`key` por marca: remontar al cambiar evita arrastrar el plan de la
 * marca anterior). Con la vista «Todas» (sin marca activa) no hay un plan único que editar.
 */
export default function ProgramaPlan() {
  const { marcaActiva } = useMarcaActiva();
  return (
    <>
      <TituloPagina titulo="Plan" icono={Tags} />
      {marcaActiva ? (
        <PanelPlan key={marcaActiva} marca={marcaActiva} />
      ) : (
        <p className="py-6 text-sm text-muted-foreground">
          Elige una marca (arriba) para ver y editar su plan de líneas.
        </p>
      )}
    </>
  );
}
