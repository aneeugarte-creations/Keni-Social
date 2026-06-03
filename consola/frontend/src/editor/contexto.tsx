// Provider del store del editor. Los hooks/contexto viven en `usarEditor.ts` (sin componentes)
// para no romper el fast-refresh de Vite.

import type { ReactNode } from "react";

import { CtxEditor } from "./usarEditor";
import type { StoreEditor } from "./store";

export function ProveedorEditor({ store, children }: { store: StoreEditor; children: ReactNode }) {
  return <CtxEditor.Provider value={store}>{children}</CtxEditor.Provider>;
}
