/**
 * Burbuja Ralph: overlay GLOBAL fijo abajo-derecha que gestiona el pool de agentes de
 * desarrollo (estilo Nolan v1). Se monta UNA sola vez cerca de la raíz (lo cabla el
 * orquestador en `main.tsx`) y se pinta en un portal sobre `<body>`, así flota por encima
 * de toda la app sin que ningún contenedor con overflow la recorte.
 *
 * La burbuja principal es el isotipo de Keni (pétalos). El PRIMER click abre directamente el
 * lanzador para arrancar un Ralph (no hay que pulsar un [＋] antes). Los Ralphs existentes
 * aparecen como bolitas en una barra HORIZONTAL a la izquierda de la burbuja; click en una
 * bolita abre su chat en vivo. El estado vive en `store/ralphStore.ts`.
 */
import * as React from "react";
import { createPortal } from "react-dom";

import { ChatRalph } from "./ChatRalph";
import { LanzadorRalph } from "./LanzadorRalph";
import { PanelRalphs } from "./PanelRalphs";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useRalphStore } from "@/store/ralphStore";

export function BurbujaRalph() {
  const cargar = useRalphStore((s) => s.cargar);
  const disponible = useRalphStore((s) => s.disponible);
  const panelAbierto = useRalphStore((s) => s.panelAbierto);
  const lanzadorAbierto = useRalphStore((s) => s.lanzadorAbierto);
  const seleccionado = useRalphStore((s) => s.seleccionado);
  const ralphs = useRalphStore((s) => s.ralphs);
  const abrirPanel = useRalphStore((s) => s.abrirPanel);
  const abrirLanzador = useRalphStore((s) => s.abrirLanzador);
  const cerrarPanel = useRalphStore((s) => s.cerrarPanel);

  // Carga el pool al montar (una vez); si el carril no está disponible, queda inerte.
  React.useEffect(() => {
    cargar();
  }, [cargar]);

  // El carril Ralph no está disponible (worker-ralph abajo o sin permiso): sin burbuja.
  if (!disponible) return null;

  const activos = ralphs.filter((r) => r.estado === "activo").length;

  // Click en la burbuja: si está cerrada, abre el panel y el lanzador (un Ralph nuevo, listo
  // para escribir); si está abierta, lo cierra todo.
  const alClicarBurbuja = () => {
    if (panelAbierto) {
      cerrarPanel();
    } else {
      abrirPanel();
      abrirLanzador();
    }
  };

  return createPortal(
    <div className="fixed bottom-6 right-6 z-40 flex flex-col items-end gap-3">
      {/* Chat o lanzador: un panel a la vez, anclado sobre la burbuja. */}
      {seleccionado && <ChatRalph id={seleccionado} />}
      {lanzadorAbierto && <LanzadorRalph />}

      {/* Barra HORIZONTAL: bolitas de los Ralphs (a la izquierda) + la burbuja principal. */}
      <div className="flex flex-row items-center gap-2">
        {panelAbierto && <PanelRalphs />}

        <Tooltip
          label={panelAbierto ? "Cerrar Ralph" : "Ralph · tu asistente"}
          side="left"
        >
          <button
            type="button"
            onClick={alClicarBurbuja}
            className={cn(
              "relative flex h-14 w-14 items-center justify-center rounded-full transition-transform hover:scale-105",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-keni focus-visible:ring-offset-2 focus-visible:ring-offset-background",
            )}
            aria-label="Ralph"
          >
            <img
              src="/favicon.png"
              alt="Keni"
              className="h-14 w-14 select-none drop-shadow-md"
              draggable={false}
            />
            {!panelAbierto && activos > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-emerald-500 px-1 text-[11px] font-semibold text-white ring-2 ring-background">
                {activos}
              </span>
            )}
          </button>
        </Tooltip>
      </div>
    </div>,
    document.body,
  );
}
