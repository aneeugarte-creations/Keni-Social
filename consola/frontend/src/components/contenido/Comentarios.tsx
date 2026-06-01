/**
 * Hilo de COMENTARIOS internos de una pieza (inspirado en Planable): discusión de redacción
 * del equipo por item, con opción de marcar hilos como resueltos. Los comentarios cuelgan del
 * `contenido` PADRE (el tema), no de la fila por red, así que solo necesita su `contenidoId`.
 *
 * Reutilizable por el editor de publicaciones (`DialogoEditar`) y cualquier superficie de
 * contenido. Antes vivía dentro de `PanelColaboracion`; se extrajo al fusionar Tablero y
 * Publicaciones (#fusion) para que el editor único lo monte como pestaña.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "No se pudo completar la acción.";
}

function fecha(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("es-MX", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function Comentarios({ contenidoId }: { contenidoId: string }) {
  const queryClient = useQueryClient();
  const clave = ["comentarios", contenidoId] as const;
  const [texto, setTexto] = React.useState("");

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.comentarios(contenidoId, undefined, signal),
    enabled: !!contenidoId,
  });
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: clave });

  const crear = useMutation({
    mutationFn: () => api.crearComentario(contenidoId, texto.trim()),
    onSuccess: () => {
      setTexto("");
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const resolver = useMutation({
    mutationFn: ({ id, resuelto }: { id: string; resuelto: boolean }) =>
      api.actualizarComentario(id, { resuelto }),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: (id: string) => api.eliminarComentario(id),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });

  const comentarios = query.data?.comentarios ?? [];

  if (!contenidoId) {
    return <EstadoVacio titulo="Sin tema" texto="Esta pieza no tiene un tema al que atar comentarios." />;
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-md border p-2">
        <Textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Escribe un comentario para el equipo…"
          rows={2}
          className="text-sm"
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={!texto.trim() || crear.isPending}
            onClick={() => crear.mutate()}
          >
            Comentar
          </Button>
        </div>
      </div>

      {comentarios.length === 0 ? (
        <EstadoVacio titulo="Sin comentarios" texto="Arranca la conversación del equipo." />
      ) : (
        <ul className="space-y-2">
          {comentarios.map((c) => {
            const acciones: EntradaMenuContextual[] = [
              {
                etiqueta: "Borrar comentario",
                icono: Trash2,
                onClick: async () => {
                  if (
                    await confirmar({
                      mensaje: "¿Borrar este comentario? No se puede deshacer.",
                      destructivo: true,
                      textoConfirmar: "Borrar",
                    })
                  )
                    borrar.mutate(c.id);
                },
                destructivo: true,
                deshabilitado: borrar.isPending,
              },
            ];
            return (
              <FilaConAcciones
                key={c.id}
                como="li"
                acciones={acciones}
                etiquetaAcciones="Acciones del comentario"
                kebab="hover"
                className={cn(
                  "rounded-md border p-2 pr-10 text-sm",
                  c.resuelto && "bg-muted/40 opacity-70",
                )}
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <Autor nombre={c.autor_nombre} className="text-xs" />
                  <span className="flex items-center gap-2 text-xs text-muted-foreground">
                    {fecha(c.creado)}
                    {c.resuelto && (
                      <Badge variant="ok" className="font-normal">
                        Resuelto
                      </Badge>
                    )}
                  </span>
                </div>
                <p className="whitespace-pre-wrap break-words">{c.texto}</p>
                <div className="mt-1.5 flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    onClick={() => resolver.mutate({ id: c.id, resuelto: !c.resuelto })}
                    disabled={resolver.isPending}
                  >
                    {c.resuelto ? "Reabrir" : "Marcar resuelto"}
                  </Button>
                </div>
              </FilaConAcciones>
            );
          })}
        </ul>
      )}
    </div>
  );
}
