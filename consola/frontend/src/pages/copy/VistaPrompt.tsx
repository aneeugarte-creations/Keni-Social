/**
 * Panel colapsable "Ver prompt que se enviará".
 *
 * Llama (con debounce ~400 ms) a `POST /api/skills/catalogo/{id}/vista-prompt`
 * con los valores actuales del formulario y muestra, en solo lectura, el prompt
 * exacto que recibiría Claude. NO ejecuta nada: es una previsualización viva que
 * se actualiza conforme el usuario escribe.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Code2, Loader2 } from "lucide-react";
import * as React from "react";

import { api } from "@/lib/api";

/** Debounce simple de un valor (para no llamar a la API en cada tecla). */
function useDebounce<T>(valor: T, ms: number): T {
  const [diferido, setDiferido] = React.useState(valor);
  React.useEffect(() => {
    const t = window.setTimeout(() => setDiferido(valor), ms);
    return () => window.clearTimeout(t);
  }, [valor, ms]);
  return diferido;
}

export function VistaPrompt({
  skillId,
  marca,
  valores,
  redes,
}: {
  skillId: string;
  marca: string;
  valores: Record<string, string>;
  redes: string[];
}) {
  const [abierto, setAbierto] = React.useState(false);

  // Clave estable y serializable de las entradas, para el debounce y la query.
  const entradas = React.useMemo(
    () => ({ marca, valores, redes }),
    [marca, valores, redes],
  );
  const clave = useDebounce(JSON.stringify(entradas), 400);

  const { data, isFetching, isError, error } = useQuery({
    queryKey: ["skills", "vista-prompt", skillId, clave],
    queryFn: ({ signal }) =>
      api
        .vistaPromptSkill(
          skillId,
          { marca: entradas.marca, valores: entradas.valores, redes: entradas.redes },
          signal,
        )
        .then((r) => r.prompt),
    // Solo cuando el panel está abierto y hay una skill seleccionada.
    enabled: abierto && skillId !== "",
    // El prompt depende solo de las entradas; no es necesario reintentar agresivamente.
    retry: false,
  });

  return (
    <div className="rounded-md border border-border">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm font-medium transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <Code2 className="h-4 w-4 text-muted-foreground" />
        Ver prompt que se enviará
        {isFetching && abierto && (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden />
        )}
        <ChevronDown
          className={`ml-auto h-4 w-4 text-muted-foreground transition-transform ${abierto ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>
      {abierto && (
        <div className="border-t border-border p-3">
          {isError ? (
            <p className="text-sm text-muted-foreground">
              {error instanceof Error
                ? error.message
                : "No se pudo cargar la vista previa del prompt."}
            </p>
          ) : data === undefined ? (
            <p className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Cargando vista previa…
            </p>
          ) : (
            <pre className="max-h-[24rem] overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-xs leading-relaxed text-foreground">
              {data}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
