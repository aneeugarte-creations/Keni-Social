/**
 * Pestaña «Keywords» de Plan (hub Programa): por marca, cada CATEGORÍA con su HASHTAG
 * (derivado del nombre, 1:1, solo lectura — va siempre en sus piezas para medir por línea) y sus
 * PALABRAS CLAVE del clasificador (CSV, editable). El clasificador es determinista (0 tokens):
 * asigna una pieza a la línea cuyas keywords casen en su título+resumen.
 *
 * Las líneas se dan de alta/baja en la pestaña «Horarios»; aquí solo se editan sus keywords.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { api, mensajeError } from "@/lib/api";

export function PanelKeywords({ marca }: { marca: string }) {
  const queryClient = useQueryClient();
  const claveLineas = ["etiquetas", "categoria", marca] as const;
  const lineasQuery = useQuery({
    queryKey: claveLineas,
    queryFn: ({ signal }) =>
      api.etiquetas({ marca, clase: "categoria", activas: true }, signal),
  });

  // Borrador por línea: lo tecleado aún sin guardar (cae al valor del servidor si no hay).
  const [draft, setDraft] = React.useState<Record<string, string>>({});
  const guardar = useMutation({
    mutationFn: ({ id, keywords }: { id: string; keywords: string }) =>
      api.actualizarEtiqueta(id, { keywords }),
    onSuccess: (_data, { id }) => {
      setDraft((prev) => {
        const sig = { ...prev };
        delete sig[id];
        return sig;
      });
      void queryClient.invalidateQueries({ queryKey: claveLineas });
      toast.success("Palabras clave guardadas.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const lineas = lineasQuery.data?.etiquetas ?? [];

  return (
    <div>
      <p className="mb-3 text-xs text-muted-foreground">
        Cada línea con su hashtag (derivado del nombre, fijo) y las palabras clave con que el
        clasificador (determinista, sin IA) le asigna las piezas que las contengan.
      </p>
      {lineasQuery.isPending ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Spinner className="h-4 w-4" /> Cargando…
        </div>
      ) : lineas.length === 0 ? (
        <p className="py-6 text-sm text-muted-foreground">
          Esta marca no tiene líneas todavía. Añádelas en la pestaña «Horarios».
        </p>
      ) : (
        <div className="space-y-3">
          {lineas.map((l) => {
            const etiqueta = l.grupo ? `${l.grupo} · ${l.nombre}` : l.nombre;
            const valor = draft[l.id] ?? l.keywords ?? "";
            const cambiado = valor !== (l.keywords ?? "");
            return (
              <div key={l.id} className="space-y-2 rounded-md border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Label className="text-sm">{etiqueta}</Label>
                  {l.hashtags ? (
                    <span
                      className="font-mono text-xs text-muted-foreground"
                      title="Hashtag de la línea (derivado del nombre, no editable)"
                    >
                      #{l.hashtags}
                    </span>
                  ) : null}
                </div>
                <Textarea
                  value={valor}
                  onChange={(e) => setDraft((prev) => ({ ...prev, [l.id]: e.target.value }))}
                  rows={2}
                  placeholder="liga, gol, partido, jornada"
                  aria-label={`Palabras clave de ${etiqueta}`}
                />
                <div className="flex justify-end">
                  <Button
                    size="sm"
                    disabled={!cambiado || guardar.isPending}
                    onClick={() => guardar.mutate({ id: l.id, keywords: valor })}
                  >
                    {guardar.isPending && guardar.variables?.id === l.id ? (
                      <Spinner className="h-4 w-4" />
                    ) : (
                      <Save className="h-4 w-4" />
                    )}
                    Guardar
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
