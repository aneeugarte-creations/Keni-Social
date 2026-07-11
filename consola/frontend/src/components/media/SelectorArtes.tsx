/**
 * Galería para elegir un ARTE ya guardado en la galería (objeto de media catalogado).
 *
 * Lista las artes (`GET /api/artes`) acotadas a la `marca` de la pieza y con búsqueda por
 * título/etiqueta. Al elegir una, devuelve su `{objeto, url}` al padre (el editor de imagen
 * la usa como FONDO y compone la placa encima). Permite quitar un arte de la galería.
 *
 * No persiste nada por sí mismo: solo selecciona. Guardar artes se hace desde el Estudio o
 * tras componer en el editor de imagen.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageOff, Search, Trash2 } from "lucide-react";
import * as React from "react";
import { useEffect } from "react";
import { toast } from "sonner";

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { confirmar } from "@/components/comunes/confirmar";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError, urlMedia } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Arte, TipoArte } from "@/types";

/** Carpetas de la prompts (filtro por `tipo`). "" = todas. */
const CARPETAS: ReadonlyArray<{ id: TipoArte | ""; etiqueta: string }> = [
  { id: "", etiqueta: "Todas" },
  { id: "original", etiqueta: "Originales" },
  { id: "subida", etiqueta: "Subidas" },
  { id: "ia", etiqueta: "IA" },
  { id: "estudio", etiqueta: "Estudio" },
];

export interface SelectorArtesProps {
  open: boolean;
  onCerrar: () => void;
  /** Devuelve el arte elegido (su `objeto` se usará como fondo). */
  onSeleccionar: (arte: Arte) => void;
  /** Acota la galería a una marca (recomendado: la marca de la pieza). */
  marca?: string;
}

export function SelectorArtes({ open, onCerrar, onSeleccionar, marca }: SelectorArtesProps) {
  const queryClient = useQueryClient();
  const [q, setQ] = React.useState("");
  const [qDebounced, setQDebounced] = React.useState("");
  // Carpeta activa (filtro por `tipo`). "" = todas.
  const [tipo, setTipo] = React.useState<TipoArte | "">("");

  // Debounce de 250ms para la búsqueda: evita lanzar queries en cada pulsación.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQDebounced(q.trim());
    }, 250);
    return () => clearTimeout(timer);
  }, [q]);

  const clave = ["artes", marca ?? "", tipo, qDebounced] as const;
  const { data, isLoading, isError, error } = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) =>
      api.listarArtes(
        { marca: marca || undefined, tipo: tipo || undefined, q: qDebounced || undefined },
        signal,
      ),
    enabled: open,
  });

  const borrar = useMutation({
    mutationFn: (id: string) => api.borrarArte(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["artes"] });
      toast.success("Arte quitado de la galería");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const artes = data?.artes ?? [];

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Galería de artes</DialogTitle>
          <DialogDescription>
            Elige una imagen como fondo.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-1.5">
          {CARPETAS.map((c) => {
            const activo = tipo === c.id;
            return (
              <button
                key={c.id || "todas"}
                type="button"
                aria-pressed={activo}
                className={cn(
                  "shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  activo
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
                onClick={() => setTipo(c.id)}
              >
                {c.etiqueta}
              </button>
            );
          })}
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar…"
            className="h-9 rounded-lg border-transparent bg-muted/60 pl-8 placeholder:text-muted-foreground focus-visible:border-border"
            aria-label="Buscar artes"
          />
        </div>

        <div className="max-h-[55vh] min-h-[12rem] overflow-y-auto">
          {isLoading ? (
            <div className="flex h-48 items-center justify-center text-muted-foreground">
              <Spinner className="h-5 w-5" />
            </div>
          ) : isError ? (
            <p className="flex h-48 items-center justify-center text-sm text-destructive">
              {mensajeError(error)}
            </p>
          ) : artes.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
              <ImageOff className="h-6 w-6" />
              <p className="text-sm">Sin artes aún.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {artes.map((arte) => {
                const acciones: EntradaMenuContextual[] = [
                  {
                    etiqueta: "Quitar",
                    icono: Trash2,
                    destructivo: true,
                    onClick: async () => {
                      if (
                        await confirmar({
                          titulo: "Quitar de la galería",
                          mensaje: `¿Quitar «${arte.titulo || "sin nombre"}» de la galería?`,
                          destructivo: true,
                          textoConfirmar: "Quitar",
                        })
                      ) {
                        borrar.mutate(arte.id);
                      }
                    },
                    deshabilitado: borrar.isPending,
                  },
                ];
                return (
                  <FilaConAcciones
                    key={arte.id}
                    como="div"
                    kebab="nunca"
                    realce
                    onPrimaria={() => {
                      onSeleccionar(arte);
                      onCerrar();
                    }}
                    acciones={acciones}
                  >
                    <div className="block w-full overflow-hidden rounded-xl border bg-card transition-shadow hover:shadow-sm hover:ring-1 hover:ring-foreground/20 focus-within:ring-1 focus-within:ring-foreground/20">
                      <img
                        src={urlMedia(arte.objeto)}
                        alt={arte.titulo || "Arte de la galería"}
                        loading="lazy"
                        className="aspect-square w-full object-cover"
                      />
                      {arte.titulo && (
                        <span className="block truncate px-2 py-1 text-left text-xs text-muted-foreground">
                          {arte.titulo}
                        </span>
                      )}
                    </div>
                  </FilaConAcciones>
                );
              })}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
