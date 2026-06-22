/**
 * Vistas guardadas del dashboard de Analíticas: presets nombrados que recuperan de un clic
 * un corte completo (configuración de vista + marca + periodo), p. ej. "Claro Sports IG
 * dirección".
 *
 * Vive en el cluster de acciones de la cabecera (`Metricas.tsx`). Un botón "Vistas" despliega
 * la lista de presets compartidos del equipo: al elegir uno se aplica su `config` al store de
 * presentación (`vistaConfig`) y se delega marca+periodo al padre (que mueve el switch global
 * y la URL `?periodo=`). "Guardar vista actual" congela el estado vivo bajo un nombre.
 *
 * Las vistas son COMPARTIDAS (piloto AMX): cualquiera las ve, aplica y borra.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, Loader2, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { VistaGuardada } from "@/types";

import { useVistaConfig } from "./vistaConfig";

const CLAVE_VISTAS = ["metricas", "vistas"] as const;

interface VistasGuardadasProps {
  /** Marca activa actual (id canónico) o `null` = todas. Se congela al guardar. */
  marcaActual: string | null;
  /** Periodo actual (token de `?periodo=`). Se congela al guardar. */
  periodoActual: string;
  /** Aplica marca + periodo de una vista (el padre mueve el switch global y la URL). */
  onAplicar: (marca: string | null, periodo: string) => void;
}

export function VistasGuardadas({
  marcaActual,
  periodoActual,
  onAplicar,
}: VistasGuardadasProps) {
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = React.useState(false);
  const [dialogoGuardar, setDialogoGuardar] = React.useState(false);
  const [nombre, setNombre] = React.useState("");
  const ref = React.useRef<HTMLDivElement>(null);

  // Cierra el panel al clicar fuera o con Escape (mismo patrón que el menú "⋮").
  React.useEffect(() => {
    if (!abierto) return;
    const alClicFuera = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false);
    };
    const alEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierto(false);
    };
    document.addEventListener("mousedown", alClicFuera);
    document.addEventListener("keydown", alEscape);
    return () => {
      document.removeEventListener("mousedown", alClicFuera);
      document.removeEventListener("keydown", alEscape);
    };
  }, [abierto]);

  const listaQuery = useQuery({
    queryKey: CLAVE_VISTAS,
    queryFn: ({ signal }) => api.vistas({}, signal),
  });
  const vistas = listaQuery.data?.vistas ?? [];

  const crear = useMutation({
    mutationFn: () =>
      api.crearVista({
        nombre: nombre.trim(),
        marca: marcaActual ?? "",
        periodo: periodoActual,
        config: useVistaConfig.getState().exportar(),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_VISTAS });
      toast.success("Vista guardada");
      setDialogoGuardar(false);
      setNombre("");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => api.eliminarVista(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_VISTAS });
      toast.success("Vista borrada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const aplicar = (vista: VistaGuardada) => {
    useVistaConfig.getState().aplicar(vista.config);
    onAplicar(vista.marca || null, vista.periodo);
    setAbierto(false);
    toast.success(`Vista «${vista.nombre}» aplicada`);
  };

  return (
    <div ref={ref} className="relative">
      <Button
        variant="outline"
        size="sm"
        aria-haspopup="menu"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
      >
        <Bookmark className="h-4 w-4" />
        Vistas
      </Button>
      {abierto && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 w-64 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md"
        >
          {listaQuery.isPending ? (
            <p className="px-2 py-3 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : vistas.length === 0 ? (
            <p className="px-2 py-3 text-center text-sm text-muted-foreground">
              Aún no hay vistas guardadas.
            </p>
          ) : (
            <ul className="max-h-72 overflow-y-auto">
              {vistas.map((vista) => (
                <li key={vista.id} className="flex items-center gap-1">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => aplicar(vista)}
                    className="flex min-w-0 flex-1 flex-col rounded-sm px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    <span className="truncate font-medium">{vista.nombre}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {vista.marca_nombre || "Todas las marcas"}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Borrar vista ${vista.nombre}`}
                    disabled={eliminar.isPending}
                    onClick={() => eliminar.mutate(vista.id)}
                    className="shrink-0 rounded-sm p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-destructive disabled:pointer-events-none disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div role="separator" className="my-1 h-px bg-border" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setAbierto(false);
              setDialogoGuardar(true);
            }}
            className={cn(
              "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm transition-colors",
              "hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <Plus className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            Guardar vista actual
          </button>
        </div>
      )}

      <Dialog open={dialogoGuardar} onOpenChange={setDialogoGuardar}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Guardar vista</DialogTitle>
            <DialogDescription>
              Congela la configuración actual del dashboard (vista, marca y periodo) bajo un
              nombre para recuperarla de un clic.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (nombre.trim()) crear.mutate();
            }}
            className="space-y-3"
          >
            <div className="space-y-1.5">
              <Label htmlFor="nombre-vista">Nombre</Label>
              <Input
                id="nombre-vista"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Claro Sports IG dirección"
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setDialogoGuardar(false)}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={!nombre.trim() || crear.isPending}>
                {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Guardar
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
