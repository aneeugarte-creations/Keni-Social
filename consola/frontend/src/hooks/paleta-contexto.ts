import * as React from "react";

/**
 * Contexto y hook de la paleta de comandos (⌘K). Vive en un módulo SIN
 * componentes para no romper el fast-refresh del proveedor (regla
 * react-refresh/only-export-components): el `PaletaProvider` queda en
 * `components/layout/PaletaComandos.tsx` y consume esto.
 *
 * Expone `abrir()` para que cualquier parte del shell (p.ej. el trigger
 * "Buscar…" del sidebar) abra la paleta sin prop-drilling.
 */
export interface ValorPaleta {
  abrir: () => void;
}

export const PaletaContexto = React.createContext<ValorPaleta | null>(null);

/** Hook para abrir la paleta. Devuelve un no-op si no hay provider (tests aislados). */
export function usePaletaComandos(): ValorPaleta {
  return React.useContext(PaletaContexto) ?? { abrir: () => {} };
}
