/**
 * Burbuja Ralph: overlay GLOBAL naranja fijo abajo-derecha que gestiona el pool de
 * agentes de desarrollo (estilo Nolan v1). Se monta UNA sola vez cerca de la raíz
 * (lo cabla el orquestador en `main.tsx`) y se pinta en un portal sobre `<body>`,
 * así flota por encima de toda la app sin que ningún contenedor con overflow la recorte.
 *
 * Click en la burbuja → despliega el panel de bolitas (`PanelRalphs`). Click en una
 * bolita → abre el chat en vivo con ESE Ralph (`ChatRalph`). El botón [＋] abre el
 * lanzador (`LanzadorRalph`). El estado vive en `store/ralphStore.ts`.
 */
import { Bot, X } from "lucide-react";
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
  const alternarPanel = useRalphStore((s) => s.alternarPanel);
  const cerrarPanel = useRalphStore((s) => s.cerrarPanel);

  // Carga el pool al montar (una vez); si el carril no está disponible, queda inerte.
  React.useEffect(() => {
    cargar();
  }, [cargar]);

  // El carril Ralph no está disponible (worker-ralph abajo o sin permiso): sin burbuja.
  if (!disponible) return null;

  const activos = ralphs.filter((r) => r.estado === "activo").length;

  return createPortal(
    <div className="fixed bottom-6 right-6 z-40 flex flex-col items-end gap-3">
      {/* Chat o lanzador: un panel a la vez, anclado sobre la burbuja. */}
      {seleccionado && <ChatRalph id={seleccionado} />}
      {lanzadorAbierto && <LanzadorRalph />}

      {/* Columna de bolitas (un Ralph por bolita) + botón de lanzar. */}
      {panelAbierto && <PanelRalphs />}

      {/* La burbuja. Click alterna el panel de bolitas. */}
      <Tooltip label={panelAbierto ? "Cerrar Ralph" : "Ralph · agentes de desarrollo"} side="left">
        <button
          type="button"
          onClick={() => (panelAbierto ? cerrarPanel() : alternarPanel())}
          className={cn(
            "relative flex h-14 w-14 items-center justify-center rounded-full bg-keni text-white shadow-lg transition-colors hover:bg-keni-500",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-keni focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          )}
          aria-label="Ralph"
        >
          {panelAbierto ? <X className="h-6 w-6" /> : <Bot className="h-6 w-6" />}
          {!panelAbierto && activos > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-emerald-500 px-1 text-[11px] font-semibold text-white ring-2 ring-background">
              {activos}
            </span>
          )}
        </button>
      </Tooltip>
    </div>,
    document.body,
  );
}
