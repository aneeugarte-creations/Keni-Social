// Barra de acciones de ALINEACIÓN / DISTRIBUCIÓN / ORDEN Z en la cabecera del panel de capas.
// Da acceso a estas acciones sin salir del panel (antes solo vivían en la píldora flotante del
// lienzo). No duplica lógica: cablea las MISMAS acciones del store (`alinear`/`alinearMulti`,
// `distribuir`, `ordenarMulti`, `traerAlFrente`/`enviarAlFondo`) según la selección.
//
// Con selección única: alinear al lienzo + traer al frente / enviar al fondo. Con multi-selección:
// alinear el grupo y, con ≥3 capas, distribuir y ordenar (tidy up). Sin selección no se renderiza.

import {
  AlignCenterHorizontal,
  AlignCenterVertical,
  AlignEndHorizontal,
  AlignEndVertical,
  AlignHorizontalDistributeCenter,
  AlignStartHorizontal,
  AlignStartVertical,
  AlignVerticalDistributeCenter,
  BringToFront,
  LayoutGrid,
  SendToBack,
} from "lucide-react";

import { Tooltip } from "@/components/ui/tooltip";

import type { StoreEditor } from "../store";

type Accion = {
  icono: typeof BringToFront;
  titulo: string;
  onClick: () => void;
};

export function BarraCapasAcciones({
  store,
  seleccion,
  seleccionMulti,
}: {
  store: StoreEditor;
  seleccion: string | null;
  seleccionMulti: string[];
}) {
  const multi = seleccionMulti.length > 1;
  const alinear = (modo: "izq" | "centroH" | "der" | "arriba" | "centroV" | "abajo") => {
    const st = store.getState();
    if (multi) st.alinearMulti(modo);
    else if (seleccion) st.alinear(seleccion, modo);
  };

  const acciones: Accion[] = [
    { icono: AlignStartVertical, titulo: "Alinear izquierda", onClick: () => alinear("izq") },
    { icono: AlignCenterVertical, titulo: "Centrar horizontal", onClick: () => alinear("centroH") },
    { icono: AlignEndVertical, titulo: "Alinear derecha", onClick: () => alinear("der") },
    { icono: AlignStartHorizontal, titulo: "Alinear arriba", onClick: () => alinear("arriba") },
    { icono: AlignCenterHorizontal, titulo: "Centrar vertical", onClick: () => alinear("centroV") },
    { icono: AlignEndHorizontal, titulo: "Alinear abajo", onClick: () => alinear("abajo") },
    ...(seleccionMulti.length > 2
      ? [
          { icono: AlignHorizontalDistributeCenter, titulo: "Distribuir horizontal", onClick: () => store.getState().distribuir("h") },
          { icono: AlignVerticalDistributeCenter, titulo: "Distribuir vertical", onClick: () => store.getState().distribuir("v") },
          { icono: LayoutGrid, titulo: "Ordenar", onClick: () => store.getState().ordenarMulti() },
        ]
      : []),
    ...(!multi && seleccion
      ? [
          { icono: BringToFront, titulo: "Traer al frente", onClick: () => store.getState().traerAlFrente(seleccion) },
          { icono: SendToBack, titulo: "Enviar al fondo", onClick: () => store.getState().enviarAlFondo(seleccion) },
        ]
      : []),
  ];

  return (
    <div
      role="toolbar"
      aria-label="Alinear y ordenar"
      className="flex flex-wrap items-center gap-0.5 border-b border-border px-2 py-1.5"
    >
      {acciones.map((a) => (
        <Tooltip key={a.titulo} label={a.titulo} side="bottom">
          <button
            onClick={a.onClick}
            aria-label={a.titulo}
            className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <a.icono className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
      ))}
    </div>
  );
}
