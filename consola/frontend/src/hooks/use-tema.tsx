import * as React from "react";

import { CLAVE_LS, type Tema, TemaContext, temaInicial } from "@/hooks/tema-contexto";

/**
 * Proveedor de tema. Aplica/quita la clase `.dark` en <html> y lo persiste en
 * localStorage para que el modo elegido sobreviva recargas. El contexto y el hook
 * `useTema` viven en `tema-contexto.ts` (modulo sin componentes).
 */
export function TemaProvider({ children }: { children: React.ReactNode }) {
  const [tema, setTema] = React.useState<Tema>(temaInicial);

  React.useEffect(() => {
    const raiz = document.documentElement;
    raiz.classList.toggle("dark", tema === "oscuro");
    window.localStorage.setItem(CLAVE_LS, tema);
  }, [tema]);

  const valor = React.useMemo(
    () => ({
      tema: tema === "oscuro" ? ("dark" as const) : ("light" as const),
      esOscuro: tema === "oscuro",
      alternar: () => setTema((t) => (t === "oscuro" ? "claro" : "oscuro")),
      fijar: (t: Tema) => setTema(t),
    }),
    [tema],
  );

  return <TemaContext.Provider value={valor}>{children}</TemaContext.Provider>;
}
