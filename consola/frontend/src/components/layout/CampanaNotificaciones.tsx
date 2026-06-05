/**
 * CAMPANA de notificaciones (el "cajón"), en la barra superior junto al selector de marca.
 *
 * - Un botón con icono de campana y un badge con el número de NO LEÍDAS (sondeo cada 20 s,
 *   ver `use-notificaciones`). El cajón está ACOTADO a la marca activa.
 * - Al ABRIR el cajón se marcan todas como leídas (se limpia el badge), pero la lista
 *   recién traída conserva el resaltado de "nuevas" hasta la próxima apertura.
 * - Cada fila resume el evento (mención / comentario / OK / rechazo / publicación) y, al
 *   pulsarla, lleva al feed. Se cierra al hacer clic fuera o con Escape.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AtSign, Bell, Megaphone, MessageSquare, ThumbsUp, XCircle } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import {
  claveContadorNotificaciones,
  useContadorNotificaciones,
  useNotificaciones,
} from "@/hooks/use-notificaciones";
import { api } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { Notificacion, TipoNotificacion } from "@/types";

/** Icono por tipo de notificación (refuerza el resumen de un vistazo). */
const ICONO: Record<TipoNotificacion, React.ComponentType<{ className?: string }>> = {
  mencion: AtSign,
  comentario: MessageSquare,
  aprobacion: ThumbsUp,
  rechazo: XCircle,
  publicacion: Megaphone,
};

/** Ruta del feed: destino al pulsar una notificación (no hay deep-link por pieza aún). */
const RUTA_FEED = "/operacion/feed/feed";

function Fila({
  notificacion,
  onIr,
}: {
  notificacion: Notificacion;
  onIr: () => void;
}) {
  const Icono = ICONO[notificacion.tipo] ?? Bell;
  return (
    <button
      type="button"
      onClick={onIr}
      className={cn(
        "flex w-full items-start gap-2.5 px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted/60",
        !notificacion.leida && "bg-primary/5",
      )}
    >
      <Icono className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className="block break-words text-foreground">{notificacion.resumen}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground tabular-nums">
          {tiempoRelativo(notificacion.creada)}
        </span>
      </span>
      {!notificacion.leida && (
        <span
          className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary"
          aria-label="No leída"
        />
      )}
    </button>
  );
}

export function CampanaNotificaciones() {
  const { marcaActiva } = useMarcaActiva();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [abierto, setAbierto] = React.useState(false);
  const contenedorRef = React.useRef<HTMLDivElement>(null);

  const contadorQuery = useContadorNotificaciones();
  const listaQuery = useNotificaciones(abierto);
  const noLeidas = contadorQuery.data?.no_leidas ?? 0;
  const notificaciones = listaQuery.data?.notificaciones ?? [];

  // Marcar todas como leídas: limpia el badge. Solo invalida el CONTADOR, no la lista, para
  // que el cajón abierto conserve el resaltado de "nuevas" mientras se mira.
  const marcarLeidas = useMutation({
    mutationFn: () => api.marcarNotificacionesLeidas(marcaActiva ?? undefined),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: claveContadorNotificaciones(marcaActiva),
      }),
  });

  // Al abrir con no leídas, márcalas leídas una sola vez (limpia el badge).
  const abrir = () => {
    setAbierto(true);
    if (noLeidas > 0 && !marcarLeidas.isPending) marcarLeidas.mutate();
  };
  const alternar = () => (abierto ? setAbierto(false) : abrir());

  // Cerrar al hacer clic fuera o con Escape (mismo patrón que los menús flotantes del repo).
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

  const irAlFeed = () => {
    setAbierto(false);
    navigate(RUTA_FEED);
  };

  return (
    <div ref={contenedorRef} className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="relative h-8 w-8"
        onClick={alternar}
        aria-label={noLeidas > 0 ? `Notificaciones (${noLeidas} sin leer)` : "Notificaciones"}
        aria-expanded={abierto}
        title="Notificaciones"
      >
        <Bell className="h-4 w-4" />
        {noLeidas > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-none text-white tabular-nums">
            {noLeidas > 99 ? "99+" : noLeidas}
          </span>
        )}
      </Button>

      {abierto && (
        <div
          role="dialog"
          aria-label="Notificaciones"
          className="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-border bg-popover shadow-lg"
        >
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-sm font-medium">Notificaciones</span>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {listaQuery.isLoading ? (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">Cargando…</p>
            ) : notificaciones.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-muted-foreground">
                No tienes notificaciones.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {notificaciones.map((n) => (
                  <li key={n.id}>
                    <Fila notificacion={n} onIr={irAlFeed} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
