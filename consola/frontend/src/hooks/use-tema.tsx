import * as React from "react";

export type Tema = "claro" | "oscuro";

const CLAVE_LS = "keni-consola-tema";

interface ContextoTema {
  tema: "light" | "dark";
  esOscuro: boolean;
  alternar: () => void;
  fijar: (t: Tema) => void;
}

const TemaContext = React.createContext<ContextoTema | null>(null);

/** Lee el tema inicial: lo guardado en localStorage o, si no, la preferencia del SO. */
function temaInicial(): Tema {
  if (typeof window === "undefined") return "oscuro";
  const guardado = window.localStorage.getItem(CLAVE_LS);
  if (guardado === "claro" || guardado === "oscuro") return guardado;
  const prefiereOscuro = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return prefiereOscuro ? "oscuro" : "claro";
}

/**
 * Proveedor de tema. Aplica/quita la clase `.dark` en <html> y lo persiste en
 * localStorage para que el modo elegido sobreviva recargas.
 */
export function TemaProvider({ children }: { children: React.ReactNode }) {
  const [tema, setTema] = React.useState<Tema>(temaInicial);

  React.useEffect(() => {
    const raiz = document.documentElement;
    raiz.classList.toggle("dark", tema === "oscuro");
    window.localStorage.setItem(CLAVE_LS, tema);
  }, [tema]);

  const valor = React.useMemo<ContextoTema>(
    () => ({
      tema: tema === "oscuro" ? "dark" : "light",
      esOscuro: tema === "oscuro",
      alternar: () => setTema((t) => (t === "oscuro" ? "claro" : "oscuro")),
      fijar: (t: Tema) => setTema(t),
    }),
    [tema],
  );

  return <TemaContext.Provider value={valor}>{children}</TemaContext.Provider>;
}

export function useTema(): ContextoTema {
  const ctx = React.useContext(TemaContext);
  if (!ctx) {
    // Fallback seguro fuera del proveedor (p.ej. tests aislados).
    return { tema: "dark", esOscuro: true, alternar: () => {}, fijar: () => {} };
  }
  return ctx;
}
