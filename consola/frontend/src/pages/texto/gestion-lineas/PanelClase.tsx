import { useQuery } from "@tanstack/react-query";
import { Plus, Tags } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";

import { FilaLinea } from "./FilaLinea";
import { FormularioLinea } from "./FormularioLinea";
import { CLASE_AYUDA, CLASE_LABEL, CLAVE_ETIQUETAS } from "./lib";
import type { ClaseLinea } from "./tipos";

/** Un panel CRUD para una clase concreta (líneas o orígenes). */
export function PanelClase({ clase }: { clase: ClaseLinea }) {
  const query = useQuery({
    queryKey: [...CLAVE_ETIQUETAS, clase],
    queryFn: ({ signal }) => api.etiquetas({ clase }, signal),
  });

  const etiquetas = React.useMemo(
    () => query.data?.etiquetas ?? [],
    [query.data],
  );
  const marcas = query.data?.marcas ?? [];

  const { marcaActiva } = useMarcaActiva();
  const [creando, setCreando] = React.useState(false);

  // El filtro de marca lo manda SIEMPRE el switch global de la barra superior
  // (`useMarcaActiva`); esta vista no tiene selector propio. Con una marca activa
  // concreta se muestran sus etiquetas + las globales (`marca === ""`); con la vista
  // agregada (`marcaActiva == null`, "Todas") se muestran todas.
  const visibles = React.useMemo(
    () =>
      etiquetas.filter(
        (e) => !e.marca || marcaActiva == null || e.marca === marcaActiva,
      ),
    [etiquetas, marcaActiva],
  );

  return (
    <Card className="h-fit">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Tags className="h-4 w-4" />
          {clase === "vertical" ? "Líneas de contenido" : "Orígenes"}
          <Badge variant="secondary" className="ml-1">
            {visibles.length}
          </Badge>
        </CardTitle>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setCreando((v) => !v)}
          aria-expanded={creando}
        >
          <Plus className="h-4 w-4" />
          Añadir
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{CLASE_AYUDA[clase]}</p>

        {creando && (
          <FormularioLinea
            clase={clase}
            marcas={marcas}
            onListo={() => setCreando(false)}
          />
        )}

        {query.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <BloqueError
            titulo={`No se pudieron cargar ${CLASE_LABEL[clase].toLowerCase()}s`}
            mensaje={mensajeError(query.error)}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        ) : visibles.length === 0 ? (
          <EstadoVacioTexto
            texto={
              etiquetas.length === 0
                ? `Aún no hay ${
                    clase === "vertical" ? "líneas" : "orígenes"
                  }. Crea el primero con el botón de arriba.`
                : "No hay nada para esta marca. Cambia de marca en el selector de arriba o crea una."
            }
            className="py-4"
          />
        ) : (
          <div className="space-y-2">
            {visibles.map((e) => (
              <FilaLinea key={e.id} etiqueta={e} clase={clase} marcas={marcas} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
