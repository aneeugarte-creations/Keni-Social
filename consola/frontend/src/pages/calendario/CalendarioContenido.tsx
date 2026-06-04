import { Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { DialogoImportarCalendario } from "@/pages/publicaciones/DialogoImportarCalendario";
import { GestionPublicaciones } from "@/pages/publicaciones/GestionPublicaciones";

const CABECERA = {
  titulo: "Programación",
  descripcion:
    "Las publicaciones programadas en una rejilla mensual. Respeta la marca activa del workspace.",
};

/**
 * Pestaña "Programación" del hub Calendario: la rejilla mensual de publicaciones programadas
 * (`GestionPublicaciones` en modo calendario). Permite importar un calendario externo.
 */
export default function CalendarioContenido() {
  const [importarAbierto, setImportarAbierto] = React.useState(false);

  // Catálogos solo para poblar el diálogo de importación (marcas).
  const catalogosQuery = useQuery({
    queryKey: ["contenido", "catalogos"],
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  const marcas = catalogosQuery.data?.catalogos?.marcas ?? [];

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          <Button
            variant="outline"
            size="sm"
            onClick={() => setImportarAbierto(true)}
            title="Importa publicaciones desde un calendario externo (CSV/ICS)"
          >
            <Upload className="h-4 w-4" />
            Importar calendario…
          </Button>
        }
      />

      <GestionPublicaciones modo="calendario" />

      <DialogoImportarCalendario
        abierto={importarAbierto}
        onCerrar={() => setImportarAbierto(false)}
        marcas={marcas}
        onImportado={(creados) => {
          toast.success(
            creados === 1
              ? "1 contenido importado."
              : `${creados} contenidos importados.`,
          );
          void catalogosQuery.refetch();
        }}
      />
    </>
  );
}
