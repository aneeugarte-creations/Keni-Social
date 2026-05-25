import * as React from "react";

import { type Tema, TemaContext, temaInicial } from "@/hooks/tema-contexto";

/**
 * Proveedor de tema. La consola sigue la preferencia de color del sistema
 * operativo (`prefers-color-scheme`) y reacciona EN VIVO si el usuario la cambia
 * en su SO. No hay toggle manual ni persistencia: claro u oscuro segun el SO.
 * El contexto y el hook `useTema` viven en `tema-contexto.ts`.
 */
export function TemaProvider({ children }: { children: React.ReactNode }) {
  const [tema, setTema] = React.useState<Tema>(temaInicial);

  // Sigue la preferencia del SO en vivo (escucha cambios de claro/oscuro).
  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const aplicar = (oscuro: boolean) => setTema(oscuro ? "oscuro" : "claro");
    aplicar(mq.matches);
    const onChange = (e: MediaQueryListEvent) => aplicar(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // Aplica/quita la clase `.dark` en <html>.
  React.useEffect(() => {
    document.documentElement.classList.toggle("dark", tema === "oscuro");
  }, [tema]);

  const valor = React.useMemo(
    () => ({
      tema: tema === "oscuro" ? ("dark" as const) : ("light" as const),
      esOscuro: tema === "oscuro",
      // Se mantienen por compatibilidad del contexto, pero ya no hay UI que las use.
      alternar: () => setTema((t) => (t === "oscuro" ? "claro" : "oscuro")),
      fijar: (t: Tema) => setTema(t),
    }),
    [tema],
  );

  return <TemaContext.Provider value={valor}>{children}</TemaContext.Provider>;
}
