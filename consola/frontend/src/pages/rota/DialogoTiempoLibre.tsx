// «Tiempo libre» del gestor: registrar vacaciones/baja de cualquiera y ver QUIÉN está fuera, sin
// salir del calendario de Gestión. Reúne las piezas que ya existían (`NuevaAusencia` + lista de
// `TarjetaAusencia`) en un solo diálogo, accesible desde el menú ⋯ del gestor.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarOff } from "lucide-react";
import * as React from "react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { hoyCDMX } from "@/lib/fecha";

import { NuevaAusencia, TarjetaAusencia } from "./Ausencias";

export function DialogoTiempoLibre({
  abierto,
  onCerrar,
}: {
  abierto: boolean;
  onCerrar: () => void;
}) {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const miId = usuario?.id ?? "";
  const queryClient = useQueryClient();

  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
    enabled: abierto,
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"],
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
    enabled: abierto,
  });

  const equipo = equipoQ.data?.equipo ?? [];
  const hoy = hoyCDMX();
  // «Quién está fuera»: solo lo vigente o próximo (la ausencia aún no ha terminado), por fecha.
  const proximas = React.useMemo(() => {
    const lista = ausenciasQ.data?.ausencias ?? [];
    return [...lista]
      .filter((a) => a.hasta >= hoy)
      .sort((a, b) => a.desde.localeCompare(b.desde));
  }, [ausenciasQ.data, hoy]);

  // Cualquier alta/edición/baja de ausencia cambia capacidad y cobertura: invalida `["rota"]` para
  // que el calendario, el Panorama y el panel de coordinación se repinten.
  const refrescar = () => void queryClient.invalidateQueries({ queryKey: ["rota"] });

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Ausencias del equipo</DialogTitle>
        </DialogHeader>
        {/* Dos columnas en ancho: registrar a la izquierda, quién está fuera a la derecha, para
            ver todo de una sin scroll. En estrecho se apilan; solo la lista de la derecha scrollea
            cuando hay muchas ausencias, dejando el formulario siempre completo. */}
        <div className="grid gap-6 md:grid-cols-2 md:gap-8">
          <NuevaAusencia
            equipo={equipo}
            esAdmin={esAdmin}
            miId={miId}
            onCreada={refrescar}
          />
          <div className="space-y-2 md:border-l md:pl-8">
            <div className="px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground/60">
              Quién está fuera
            </div>
            <div className="max-h-[55vh] space-y-2 overflow-y-auto">
              {ausenciasQ.isPending ? (
                <Skeleton className="h-20 w-full rounded-lg" />
              ) : proximas.length === 0 ? (
                <EstadoVacio
                  icono={CalendarOff}
                  titulo="Nadie de vacaciones"
                  texto="No hay tiempo libre vigente ni próximo registrado."
                />
              ) : (
                proximas.map((a) => (
                  <TarjetaAusencia
                    key={a.id}
                    ausencia={a}
                    puedeGestionar={esAdmin || a.miembro_id === miId}
                    onCambio={refrescar}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
