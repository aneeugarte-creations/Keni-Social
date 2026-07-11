/**
 * PanelFuentesStock — los TOGGLES de las fuentes de fotos de stock de UNA marca, contenido de la
 * subpágina de la etapa Stock (Contexto). Un Switch por proveedor (Pexels/Pixabay/Wikimedia/NASA/
 * Openverse) reflejando si está habilitado para la marca. Un proveedor de pago sin clave queda
 * DESHABILITADO con la pista de configurarla en Sistema → Proveedores.
 *
 * Backend: lista vacía o todos = sin filtro (todas las disponibles). Al togglear, se manda la lista
 * explícita de proveedores habilitados; la query se invalida tras guardar (el back es la verdad).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { mensajeError } from "@/pages/configuracion/lib";
import type { FuenteStock } from "@/types";

/** Clave de query del estado de fuentes de UNA marca (independiente del listado de Sistema). */
function claveMarca(marca: string): readonly string[] {
  return ["stock", "fuentes", marca];
}

export function PanelFuentesStock({ marca }: { marca: string | null }) {
  const queryClient = useQueryClient();

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: claveMarca(marca ?? ""),
    queryFn: ({ signal }) => api.estadoFuentesStockMarca(marca as string, signal),
    enabled: marca !== null,
  });

  const guardar = useMutation({
    mutationFn: (activas: string[]) => api.guardarFuentesStock(marca as string, activas),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: claveMarca(marca ?? "") });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // "Todas" (sin marca concreta): no hay una marca a la que aplicar los toggles.
  if (marca === null) {
    return (
      <p className="text-sm text-muted-foreground">
        Elige una marca concreta en la barra superior para configurar sus fuentes de fotos de stock.
      </p>
    );
  }

  if (isPending) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <BloqueError
        titulo="No se pudieron cargar las fuentes de stock"
        mensaje={mensajeError(error)}
        onReintentar={() => void refetch()}
        cargando={isFetching}
      />
    );
  }

  const fuentes = data.fuentes;
  const activasActuales = fuentes.filter((f) => f.activa).map((f) => f.proveedor);

  const alternar = (fuente: FuenteStock, valor: boolean) => {
    const activas = valor
      ? [...activasActuales, fuente.proveedor]
      : activasActuales.filter((p) => p !== fuente.proveedor);
    guardar.mutate(activas);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Elige de qué bancos saca fotos de stock <span className="font-medium text-foreground">{data.etiqueta}</span>.
          Si no habilitas ninguno, se usan todos los disponibles.
        </p>
      </div>

      <ul className="divide-y divide-border rounded-xl border bg-card">
        {fuentes.map((fuente) => {
          // Proveedor de pago sin clave global: no está disponible, el toggle queda inerte con su pista.
          const sinClave = fuente.requiere_clave && !fuente.disponible;
          return (
            <li key={fuente.proveedor} className="flex items-center justify-between gap-3 p-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">{fuente.nombre}</p>
                {sinClave ? (
                  <p className="text-xs text-muted-foreground">
                    {fuente.motivo || "Configúrala en Sistema → Proveedores."}
                  </p>
                ) : fuente.requiere_clave ? (
                  <p className="text-xs text-muted-foreground">Banco de pago (clave configurada).</p>
                ) : (
                  <p className="text-xs text-muted-foreground">Banco gratuito, sin clave.</p>
                )}
              </div>
              <Switch
                checked={fuente.activa}
                disabled={sinClave || guardar.isPending}
                onCheckedChange={(v) => alternar(fuente, v)}
                aria-label={`Fuente ${fuente.nombre}`}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
