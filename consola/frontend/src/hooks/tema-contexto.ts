import * as React from "react";

/**
 * Contexto y hook del tema (claro/oscuro). Vive en un modulo SIN componentes para
 * no romper el fast-refresh del proveedor (regla react-refresh/only-export-components):
 * el componente `TemaProvider` queda solo en `use-tema.tsx` y consume esto.
 */

export type Tema = "claro" | "oscuro";

export const CLAVE_LS = "keni-consola-tema";

export interface ContextoTema {
  tema: "light" | "dark";
  esOscuro: boolean;
  alternar: () => void;
  fijar: (t: Tema) => void;
}

export const TemaContext = React.createContext<ContextoTema | null>(null);

/** Lee el tema inicial: lo guardado en localStorage o, si no, la preferencia del SO. */
export function temaInicial(): Tema {
  if (typeof window === "undefined") return "oscuro";
  const guardado = window.localStorage.getItem(CLAVE_LS);
  if (guardado === "claro" || guardado === "oscuro") return guardado;
  const prefiereOscuro = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return prefiereOscuro ? "oscuro" : "claro";
}

export function useTema(): ContextoTema {
  const ctx = React.useContext(TemaContext);
  if (!ctx) {
    // Fallback seguro fuera del proveedor (p.ej. tests aislados).
    return { tema: "dark", esOscuro: true, alternar: () => {}, fijar: () => {} };
  }
  return ctx;
}
