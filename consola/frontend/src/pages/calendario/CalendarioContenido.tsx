import { Gauge, Upload } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { DialogoImportarCalendario } from "@/pages/publicaciones/DialogoImportarCalendario";
import { GestionCadencia } from "@/pages/publicaciones/GestionCadencia";
import { GestionPublicaciones } from "@/pages/publicaciones/GestionPublicaciones";

const CABECERA = {
  titulo: "Programación",
  descripcion:
    "Las publicaciones programadas en una rejilla mensual. Respeta la marca activa del workspace.",
};

/**
 * Pestaña "Programación" del hub Calendario: la rejilla mensual de publicaciones programadas
 * (`GestionPublicaciones` en modo calendario). Desde la cabecera se gestiona la CADENCIA por
 * red (cada cuántos minutos puede salir un post, el reparto que alimenta este calendario) y se
 * importa un calendario externo. Un enlace `?cadencia=1` abre la cadencia directamente (lo usa
 * el aviso "sin cadencia" de la lista de contenido).
 */
export default function CalendarioContenido() {
  const [importarAbierto, setImportarAbierto] = React.useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const [cadenciaAbierto, setCadenciaAbierto] = React.useState(
    () => searchParams.get("cadencia") === "1",
  );

  // Catálogos para poblar los diálogos de importación (marcas) y cadencia (marcas + redes).
  const catalogosQuery = useQuery({
    queryKey: ["contenido", "catalogos"],
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  const marcas = catalogosQuery.data?.catalogos?.marcas ?? [];
  const redes = catalogosQuery.data?.catalogos?.redes ?? [];

  // Si se llega con ?cadencia=1, abre el diálogo y limpia el parámetro de la URL.
  React.useEffect(() => {
    if (searchParams.get("cadencia") === "1") {
      setCadenciaAbierto(true);
      const next = new URLSearchParams(searchParams);
      next.delete("cadencia");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCadenciaAbierto(true)}
              title="Define cada cuántos minutos puede salir un post por red (alimenta este calendario)"
            >
              <Gauge className="h-4 w-4" />
              Cadencia
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setImportarAbierto(true)}
              title="Importa publicaciones desde un calendario externo (CSV/ICS)"
            >
              <Upload className="h-4 w-4" />
              Importar calendario…
            </Button>
          </>
        }
      />

      <GestionPublicaciones modo="calendario" />

      <GestionCadencia
        abierto={cadenciaAbierto}
        onCerrar={() => setCadenciaAbierto(false)}
        marcas={marcas}
        redes={redes}
      />

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
