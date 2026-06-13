import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { UsuarioAdmin } from "@/types";

import { AvatarPersona } from "./AvatarPersona";
import { CLAVE_TAREAS } from "./claves";

/** Diálogo "Asignar a…" compartido (manager elige a quién encarga). */
export function DialogoAsignar({
  titulo,
  abierto,
  onOpenChange,
  usuarios,
  responsableActual,
  onElegir,
  enviando,
}: {
  titulo: string;
  abierto: boolean;
  onOpenChange: (v: boolean) => void;
  usuarios: { id: string; usuario: string }[];
  responsableActual: string;
  onElegir: (personaId: string) => void;
  enviando: boolean;
}) {
  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Asignar "{titulo}"</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Elige a quién se la encargas; se le avisa en la app.
        </p>
        <div className="max-h-72 space-y-1 overflow-y-auto py-1">
          {usuarios.length === 0 && (
            <p className="px-1 text-sm text-muted-foreground">No hay compañeros para asignar.</p>
          )}
          {usuarios.map((u) => {
            const yaEs = u.id === responsableActual;
            return (
              <button
                key={u.id}
                type="button"
                disabled={enviando || yaEs}
                onClick={() => onElegir(u.id)}
                className={cn(
                  "flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm disabled:opacity-100",
                  yaEs
                    ? "border-primary/50 bg-primary/5 text-primary"
                    : "border-border hover:border-foreground/30 hover:bg-accent",
                )}
              >
                <span className="truncate">{u.usuario}</span>
                {yaEs && <span className="ml-2 shrink-0 text-xs">la lleva ahora</span>}
              </button>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Diálogo «Añadir persona al equipo» de la MARCA activa (cada marca tiene su equipo). Lista los
 * usuarios de cobertura que aún no están en la marca y los suma con un PATCH a sus `marcas`
 * (sin pisar las otras). Crear personas nuevas vive en Usuarios (organigrama).
 */
export function DialogoAnadirPersona({
  marca,
  abierto,
  onOpenChange,
}: {
  marca: string;
  abierto: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const usuariosQ = useQuery({
    queryKey: ["usuarios-admin"],
    queryFn: ({ signal }) => api.usuarios(signal),
    enabled: abierto,
  });
  const candidatos = (usuariosQ.data?.usuarios ?? []).filter(
    (u) => u.cobertura && !(u.marcas ?? []).includes(marca),
  );
  const anadir = useMutation({
    mutationFn: (u: UsuarioAdmin) =>
      api.actualizarUsuario(u.id, { marcas: [...new Set([...(u.marcas ?? []), marca])] }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      void queryClient.invalidateQueries({ queryKey: ["usuarios-admin"] });
      onOpenChange(false);
      toast.success("Persona añadida al equipo.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Añadir persona al equipo</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Suma a quien cubrirá en esta marca. Para crear a alguien nuevo, ve a Usuarios.
        </p>
        <div className="max-h-72 space-y-1 overflow-y-auto py-1">
          {usuariosQ.isLoading && (
            <p className="px-1 text-sm text-muted-foreground">Cargando…</p>
          )}
          {!usuariosQ.isLoading && candidatos.length === 0 && (
            <p className="px-1 text-sm text-muted-foreground">No hay nadie más que añadir.</p>
          )}
          {candidatos.map((u) => (
            <button
              key={u.id}
              type="button"
              disabled={anadir.isPending}
              onClick={() => anadir.mutate(u)}
              className="flex w-full items-center gap-2 rounded-md border border-border px-3 py-2 text-left text-sm hover:border-foreground/30 hover:bg-accent"
            >
              <AvatarPersona id={u.id} nombre={u.nombre || u.usuario} size="sm" />
              <span className="truncate">{u.nombre || u.usuario}</span>
            </button>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
