import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

import { CLAVE_ESFUERZO, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

/**
 * Nivel de esfuerzo de razonamiento que la IA usa al generar (copy, RSS,
 * hashtags y agentes). Más esfuerzo = mejor calidad pero más lento; menos =
 * más rápido. El valor "" es el predeterminado del modelo. Se guarda local.
 */
export function SeccionEsfuerzo() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_ESFUERZO,
    queryFn: ({ signal }) => api.esfuerzo(signal),
  });

  const [esfuerzo, setEsfuerzo] = React.useState("");

  // Sincroniza el estado local con el nivel cargado del servidor.
  React.useEffect(() => {
    if (data) setEsfuerzo(data.esfuerzo);
  }, [data]);

  const guardar = useMutation({
    mutationFn: () => api.guardarEsfuerzo({ esfuerzo }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "Esfuerzo guardado.");
      void queryClient.invalidateQueries({ queryKey: CLAVE_ESFUERZO });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const hayCambios = data !== undefined && esfuerzo !== data.esfuerzo;

  return (
    <SeccionColapsable
      titulo="Esfuerzo de generación"
      contentClassName="space-y-2"
      descripcion={
        <>
          Define la velocidad vs. calidad. Se almacena localmente.
        </>
      }
    >
        {isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <BloqueError
            titulo="No se pudo cargar el esfuerzo"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : (
          <>
            {data.opciones.map((opcion) => {
              const seleccionada = esfuerzo === opcion.id;
              return (
                <label
                  key={opcion.id || "predeterminado"}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                    seleccionada ? "border-primary bg-primary/5" : "border-border hover:bg-accent",
                  )}
                >
                  <input
                    type="radio"
                    name="esfuerzo"
                    value={opcion.id}
                    checked={seleccionada}
                    onChange={() => setEsfuerzo(opcion.id)}
                    disabled={guardar.isPending}
                    className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                  />
                  <span className="space-y-0.5">
                    <span className="block text-sm font-medium">{opcion.etiqueta}</span>
                    <span className="block text-xs text-muted-foreground">{opcion.descripcion}</span>
                  </span>
                </label>
              );
            })}
            <div className="flex items-center gap-3 pt-1">
              <Button onClick={() => guardar.mutate()} disabled={guardar.isPending || !hayCambios}>
                <Save className={cn("h-4 w-4", guardar.isPending && "animate-pulse")} />
                {guardar.isPending ? "Guardando…" : "Guardar cambios"}
              </Button>
              {!hayCambios && !guardar.isPending && (
                <span className="text-xs text-muted-foreground">No hay cambios sin guardar.</span>
              )}
            </div>
          </>
        )}
    </SeccionColapsable>
  );
}
