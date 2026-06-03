// Contexto + hooks del store del editor (sin componentes, para no romper el fast-refresh:
// el provider vive aparte en `contexto.tsx`). Un store Zustand por documento abierto.

import { createContext, useContext } from "react";
import { useStore } from "zustand";

import type { EstadoEditor, StoreEditor } from "./store";

export const CtxEditor = createContext<StoreEditor | null>(null);

export function useStoreEditor(): StoreEditor {
  const store = useContext(CtxEditor);
  if (!store) throw new Error("useStoreEditor fuera de <ProveedorEditor>");
  return store;
}

// Selector tipado sobre el store del documento actual.
export function useEditor<T>(selector: (s: EstadoEditor) => T): T {
  return useStore(useStoreEditor(), selector);
}
