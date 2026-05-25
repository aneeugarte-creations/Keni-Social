import { Construction } from "lucide-react";

import { EstadoMensaje } from "@/components/layout/EstadoMensaje";
import { PageHeader } from "@/components/layout/PageHeader";

/**
 * Placeholder reutilizable para las paginas que aun no se implementan. Cada stub
 * lo renderiza con su propio titulo.
 */
export function EnConstruccion({
  titulo,
  descripcion,
}: {
  titulo: string;
  descripcion?: string;
}) {
  return (
    <>
      <PageHeader titulo={titulo} descripcion={descripcion} />
      <EstadoMensaje
        icono={Construction}
        titulo="En construcción"
        mensaje="Esta sección estará disponible pronto. Estamos trabajando en ella."
      />
    </>
  );
}
