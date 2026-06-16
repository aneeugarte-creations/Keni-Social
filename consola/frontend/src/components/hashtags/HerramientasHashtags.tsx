/**
 * Herramientas de hashtags para el compositor/editor de piezas.
 *
 * Una sola acción: **Insertar grupo** — elige un grupo guardado (`/api/hashtags`)
 * y se añaden sus hashtags al final del contenido. Solo se ofrecen los grupos de
 * la marca actual (más los generales sin marca); los de otras marcas no aparecen.
 *
 * También expone un acceso a la gestión de grupos. React Query + toasts; modo
 * claro/oscuro; texto es-MX.
 */
import { useQuery } from "@tanstack/react-query";
import { Hash, Settings2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";

import { agregarHashtags, CLAVE_HASHTAGS } from "../../pages/piezas/hashtags";

export interface HerramientasHashtagsProps {
  /** Publicacion actual (para detectar duplicados al insertar). */
  contenido: string;
  /** Inserta el contenido resultante (con hashtags añadidos). */
  onPublicacion: (nuevo: string) => void;
  marca: string;
  /** Abre la gestión de grupos (CRUD). */
  onGestionar: () => void;
}

export function HerramientasHashtags({
  contenido,
  onPublicacion,
  marca,
  onGestionar,
}: HerramientasHashtagsProps) {
  const gruposQuery = useQuery({
    queryKey: CLAVE_HASHTAGS,
    queryFn: ({ signal }) => api.hashtags(signal),
  });

  const grupos = React.useMemo(() => gruposQuery.data?.grupos ?? [], [gruposQuery.data]);
  // Solo los grupos de la marca actual (más los generales sin marca); los de otras
  // marcas no se muestran. Primero la marca, luego los generales.
  const gruposVisibles = React.useMemo(() => {
    return grupos
      .filter((g) => g.marca === marca || !g.marca)
      .sort((a, b) => (a.marca === marca ? 0 : 1) - (b.marca === marca ? 0 : 1));
  }, [grupos, marca]);

  function insertarGrupo(id: string) {
    const grupo = grupos.find((g) => g.id === id);
    if (!grupo) return;
    onPublicacion(agregarHashtags(contenido, grupo.hashtags));
    toast.success(`Insertado: ${grupo.nombre}`);
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
          disabled={gruposQuery.isPending || gruposVisibles.length === 0}
        >
          <SelectTrigger className="h-8 w-auto gap-1.5 text-xs" aria-label="Insertar grupo de hashtags">
            <SelectValue
              placeholder={
                gruposVisibles.length === 0 ? "Sin grupos guardados" : "Insertar grupo"
              }
            />
          </SelectTrigger>
          <SelectContent>
            {gruposVisibles.map((g) => (
              <SelectItem key={g.id} value={g.id}>
                {g.nombre} ({g.hashtags.length})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto text-muted-foreground"
          onClick={onGestionar}
        >
          <Settings2 className="h-4 w-4" />
          Gestionar grupos
        </Button>
      </div>
    </div>
  );
}
