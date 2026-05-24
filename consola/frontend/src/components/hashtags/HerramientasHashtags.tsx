/**
 * Herramientas de hashtags para el compositor/editor de publicaciones.
 *
 * Ofrece dos acciones que insertan hashtags al final del contenido:
 *  - **Insertar grupo**: elige un grupo guardado (`/api/hashtags`).
 *  - **Sugerir con IA**: pide sugerencias (`/api/hashtags/sugerir`) y muestra
 *    chips seleccionables que se insertan en bloque.
 *
 * También expone un acceso a la gestión de grupos. React Query + toasts; modo
 * claro/oscuro; texto es-MX.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { Hash, Loader2, Plus, Settings2, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { agregarHashtags, CLAVE_HASHTAGS } from "../../pages/publicaciones/hashtags";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

export interface HerramientasHashtagsProps {
  /** Contenido actual (para detectar duplicados y dar contexto a la IA). */
  contenido: string;
  /** Inserta el contenido resultante (con hashtags añadidos). */
  onContenido: (nuevo: string) => void;
  marca: string;
  red: string;
  /** Abre la gestión de grupos (CRUD). */
  onGestionar: () => void;
}

export function HerramientasHashtags({
  contenido,
  onContenido,
  marca,
  red,
  onGestionar,
}: HerramientasHashtagsProps) {
  // Chips sugeridos por IA pendientes de insertar.
  const [sugeridos, setSugeridos] = React.useState<string[]>([]);
  const [seleccion, setSeleccion] = React.useState<Set<string>>(new Set());

  const gruposQuery = useQuery({
    queryKey: CLAVE_HASHTAGS,
    queryFn: ({ signal }) => api.hashtags(signal),
  });

  const grupos = React.useMemo(() => gruposQuery.data?.grupos ?? [], [gruposQuery.data]);
  // Mostramos primero los grupos de la marca actual, luego los generales.
  const gruposOrdenados = React.useMemo(() => {
    return [...grupos].sort((a, b) => {
      const pa = a.marca === marca ? 0 : a.marca ? 2 : 1;
      const pb = b.marca === marca ? 0 : b.marca ? 2 : 1;
      return pa - pb;
    });
  }, [grupos, marca]);

  function insertarGrupo(id: string) {
    const grupo = grupos.find((g) => g.id === id);
    if (!grupo) return;
    onContenido(agregarHashtags(contenido, grupo.hashtags));
    toast.success(`Insertado: ${grupo.nombre}`);
  }

  const sugerir = useMutation({
    mutationFn: () =>
      api.sugerirHashtags({ texto: contenido, marca, red: red || undefined }),
    onSuccess: (data) => {
      const lista = data.hashtags ?? [];
      if (lista.length === 0) {
        toast.info("No se obtuvieron sugerencias.");
        return;
      }
      setSugeridos(lista);
      setSeleccion(new Set(lista));
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function alternar(h: string) {
    setSeleccion((prev) => {
      const sig = new Set(prev);
      if (sig.has(h)) sig.delete(h);
      else sig.add(h);
      return sig;
    });
  }

  function insertarSeleccionados() {
    const elegidos = sugeridos.filter((h) => seleccion.has(h));
    if (elegidos.length === 0) return;
    onContenido(agregarHashtags(contenido, elegidos));
    toast.success(
      `Insertados ${elegidos.length} ${elegidos.length === 1 ? "hashtag" : "hashtags"}`,
    );
    setSugeridos([]);
    setSeleccion(new Set());
  }

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Hash className="h-3.5 w-3.5" />
          Hashtags
        </span>

        <Select
          value=""
          onValueChange={insertarGrupo}
          disabled={gruposQuery.isPending || grupos.length === 0}
        >
          <SelectTrigger className="h-8 w-auto gap-1.5 text-xs" aria-label="Insertar grupo de hashtags">
            <SelectValue
              placeholder={
                grupos.length === 0 ? "Sin grupos guardados" : "Insertar grupo"
              }
            />
          </SelectTrigger>
          <SelectContent>
            {gruposOrdenados.map((g) => (
              <SelectItem key={g.id} value={g.id}>
                {g.nombre}
                {g.marca ? ` · ${g.marca_nombre || g.marca}` : ""} ({g.hashtags.length})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => sugerir.mutate()}
          disabled={sugerir.isPending || contenido.trim().length === 0}
        >
          {sugerir.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          Sugerir con IA
        </Button>

        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto text-muted-foreground"
          onClick={onGestionar}
          title="Gestionar grupos de hashtags"
        >
          <Settings2 className="h-4 w-4" />
          Gestionar grupos
        </Button>
      </div>

      {sugeridos.length > 0 && (
        <div className="space-y-2 border-t border-border pt-2">
          <p className="text-xs text-muted-foreground">
            Toca para seleccionar y luego inserta los elegidos:
          </p>
          <div className="flex flex-wrap gap-1.5">
            {sugeridos.map((h) => {
              const activo = seleccion.has(h);
              return (
                <button
                  key={h}
                  type="button"
                  onClick={() => alternar(h)}
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                    activo
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background text-foreground hover:bg-accent",
                  )}
                  aria-pressed={activo}
                >
                  {h}
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              onClick={insertarSeleccionados}
              disabled={seleccion.size === 0}
            >
              <Plus className="h-4 w-4" />
              Insertar seleccionados ({seleccion.size})
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setSugeridos([]);
                setSeleccion(new Set());
              }}
            >
              Descartar
            </Button>
          </div>
        </div>
      )}

      {sugeridos.length === 0 && grupos.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {gruposOrdenados.slice(0, 4).map((g) => (
            <Badge
              key={g.id}
              variant="secondary"
              className="cursor-pointer font-normal hover:bg-secondary/70"
              onClick={() => insertarGrupo(g.id)}
              title={`Insertar ${g.nombre}`}
            >
              {g.nombre}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
