// Construcción de la píldora de ACCIONES de la capa seleccionada (alinear / distribuir / orden /
// duplicar / borrar), extraída como hook. Owns el cálculo del array de acciones según la selección
// (única o múltiple); el componente solo lo pasa a `BarraAcciones`. Mismas reglas que antes: con
// multi-selección se alinea el grupo y se habilita distribuir/ordenar (≥3); con selección única se
// añade traer al frente / enviar al fondo.

import {
  AlignCenterHorizontal,
  AlignCenterVertical,
  AlignEndHorizontal,
  AlignEndVertical,
  AlignHorizontalDistributeCenter,
  AlignVerticalDistributeCenter,
  AlignStartHorizontal,
  AlignStartVertical,
  BringToFront,
  Copy,
  LayoutGrid,
  SendToBack,
  Trash2,
} from "lucide-react";

import type { StoreEditor } from "../store";
import type { AccionLienzo } from "./BarraAcciones";

export function useAccionesLienzo({
  store,
  seleccion,
  seleccionMulti,
}: {
  store: StoreEditor;
  seleccion: string | null;
  seleccionMulti: string[];
}): AccionLienzo[] {
  const multi = seleccionMulti.length > 1;
  const alinearFn = (modo: "izq" | "centroH" | "der" | "arriba" | "centroV" | "abajo") => {
    const st = store.getState();
    if (multi) st.alinearMulti(modo);
    else if (seleccion) st.alinear(seleccion, modo);
  };
  const acciones: AccionLienzo[] =
    seleccionMulti.length > 0
      ? [
          { icono: AlignStartVertical, titulo: "Alinear izquierda", onClick: () => alinearFn("izq") },
          { icono: AlignCenterVertical, titulo: "Centrar horizontal", onClick: () => alinearFn("centroH") },
          { icono: AlignEndVertical, titulo: "Alinear derecha", onClick: () => alinearFn("der") },
          { icono: AlignStartHorizontal, titulo: "Alinear arriba", onClick: () => alinearFn("arriba") },
          { icono: AlignCenterHorizontal, titulo: "Centrar vertical", onClick: () => alinearFn("centroV") },
          { icono: AlignEndHorizontal, titulo: "Alinear abajo", onClick: () => alinearFn("abajo") },
          ...(seleccionMulti.length > 2
            ? [
                { icono: AlignHorizontalDistributeCenter, titulo: "Distribuir horizontal", onClick: () => store.getState().distribuir("h") },
                { icono: AlignVerticalDistributeCenter, titulo: "Distribuir vertical", onClick: () => store.getState().distribuir("v") },
                // «Ordenar» (tidy up): espaciado uniforme en el eje dominante + centros alineados.
                { icono: LayoutGrid, titulo: "Ordenar", atajo: "⌥⇧T", onClick: () => store.getState().ordenarMulti() },
              ]
            : []),
          ...(!multi && seleccion
            ? [
                { icono: BringToFront, titulo: "Traer al frente", atajo: "⌘]", onClick: () => store.getState().traerAlFrente(seleccion) },
                { icono: SendToBack, titulo: "Enviar al fondo", atajo: "⌘[", onClick: () => store.getState().enviarAlFondo(seleccion) },
              ]
            : []),
          { icono: Copy, titulo: "Duplicar", atajo: "⌘D", onClick: () => store.getState().duplicarMulti() },
          { icono: Trash2, titulo: "Borrar", atajo: "Supr", onClick: () => store.getState().quitarMulti() },
        ]
      : [];

  return acciones;
}
