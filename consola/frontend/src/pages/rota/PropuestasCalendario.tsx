/**
 * BANDEJA de propuestas de calendario (el "icono de notificaciones" del calendario de Turnos).
 *
 * Una TAREA con fecha (tarea suelta sin evento) es una PROPUESTA para el calendario: no entra
 * directa a la rejilla como un evento, sino que espera AQUÍ. El botón (campana + badge con el
 * número de propuestas) abre un cajón donde cada propuesta se puede ACEPTAR —se promueve a evento
 * de la rota y aparece en el calendario «Por cubrir»— o DESCARTAR (se borra sin crear evento).
 *
 * Misma arquitectura que un evento: la propuesta lleva título/fecha/hora/detalle; «Aceptar» es la
 * misma alta de evento que hace el import. Mientras está pendiente sigue visible en «Mis tareas».
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, Calendar, Check, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_TAREAS } from "@/pages/tareas/claves";
import type { Publicacion } from "@/types";

function Fila({
  propuesta,
  onAceptar,
  onDescartar,
  ocupada,
}: {
  propuesta: Publicacion;
  onAceptar: (p: Publicacion) => void;
  onDescartar: (p: Publicacion) => void;
  ocupada: boolean;
}) {
  const detalle = (propuesta.descripcion || "").trim();
  return (
    <div className="flex items-start gap-2.5 px-3 py-2.5 text-sm">
      <Calendar className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <span className="block break-words font-medium text-foreground">{propuesta.titulo}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground tabular-nums">
          {propuesta.fecha_objetivo}
          {propuesta.hora_objetivo ? ` · ${propuesta.hora_objetivo}` : ""}
        </span>
        {detalle && (
          <span className="mt-0.5 block break-words text-xs text-muted-foreground">{detalle}</span>
        )}
        <div className="mt-2 flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className="px-2"
            onClick={() => onAceptar(propuesta)}
            disabled={ocupada}
          >
            {ocupada ? (
              <Spinner className="mr-1 h-3.5 w-3.5" />
            ) : (
              <Check className="mr-1 h-3.5 w-3.5" />
            )}
            Aceptar
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="px-2 text-muted-foreground"
            onClick={() => onDescartar(propuesta)}
            disabled={ocupada}
          >
            <X className="mr-1 h-3.5 w-3.5" />
            Descartar
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * `propuestas`: tareas sueltas CON fecha (sin evento) — el llamador las deriva de la lista de
 * tareas ya cargada. Aceptar/descartar invalidan tanto la familia `["rota"]` (para que el evento
 * nuevo salga en la rejilla) como `CLAVE_TAREAS` (para que la propuesta deje la bandeja).
 */
export function PropuestasCalendario({ propuestas }: { propuestas: Publicacion[] }) {
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = React.useState(false);
  const contenedorRef = React.useRef<HTMLDivElement>(null);
  const n = propuestas.length;

  const refrescar = () => {
    void queryClient.invalidateQueries({ queryKey: ["rota"] });
    void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
  };

  const aceptar = useMutation({
    mutationFn: (id: string) => api.aceptarPublicacion(id),
    onSuccess: () => {
      toast.success("Aceptada: ya está en el calendario «Por cubrir».");
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const descartar = useMutation({
    mutationFn: (id: string) => api.eliminarPublicacion(id),
    onSuccess: () => {
      toast.success("Propuesta descartada.");
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const ocupadaId =
    aceptar.isPending ? aceptar.variables : descartar.isPending ? descartar.variables : null;

  // Cerrar al hacer clic fuera o con Escape (mismo patrón que la campana global y los menús del repo).
  React.useEffect(() => {
    if (!abierto) return;
    function fuera(e: MouseEvent) {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target as Node)) {
        setAbierto(false);
      }
    }
    function tecla(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", tecla);
    };
  }, [abierto]);

  // Sin propuestas no pintamos el icono: nada que notificar.
  if (n === 0) return null;

  return (
    <div ref={contenedorRef} className="relative">
      <Button
        variant="ghost"
        size="icon"
        className={cn(
          "relative h-8 w-8",
          abierto &&
            "bg-[hsl(var(--control-activo))] text-[hsl(var(--control-activo-foreground))]",
        )}
        onClick={() => setAbierto((v) => !v)}
        aria-label={`Propuestas de calendario (${n})`}
        aria-expanded={abierto}
        title="Tareas propuestas para el calendario"
      >
        <Bell className="h-4 w-4" />
        <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-none text-white tabular-nums">
          {n > 99 ? "99+" : n}
        </span>
      </Button>

      {abierto && (
        <div
          role="dialog"
          aria-label="Propuestas de calendario"
          className="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-border bg-popover shadow-lg"
        >
          <div className="border-b border-border px-3 py-2">
            <span className="text-sm font-medium">Propuestas de calendario</span>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Tareas con fecha esperando entrar al calendario.
            </p>
          </div>
          <div className="max-h-96 divide-y divide-border overflow-y-auto">
            {propuestas.map((p) => (
              <Fila
                key={p.id}
                propuesta={p}
                ocupada={ocupadaId === p.id}
                onAceptar={(x) => aceptar.mutate(x.id)}
                onDescartar={(x) => descartar.mutate(x.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
