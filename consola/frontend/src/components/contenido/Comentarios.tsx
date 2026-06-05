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
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, ApiError } from "@/lib/api";
import { formatearFechaHoraCorta } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { MencionCandidato } from "@/types";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "No se pudo completar la acción.";
}

// Fecha+hora en CDMX (el instante del backend es UTC).
const fecha = (iso: string): string => formatearFechaHoraCorta(iso);

// El "token" de una mención en el texto: `@usuario` (handle sin espacios). Se usa para
// detectar el disparador `@…` mientras se escribe y para saber qué menciones siguen en pie.
const TOKEN_MENCION = /@([\w.-]*)$/;

export function Comentarios({ contenidoId }: { contenidoId: string }) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const clave = ["comentarios", contenidoId] as const;
  const [texto, setTexto] = React.useState("");
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  // Menciones (@): candidatos de la marca, los que el usuario ya eligió, y el estado del
  // menú flotante (consulta tras la @ + item resaltado para teclado).
  const [seleccionadas, setSeleccionadas] = React.useState<Map<string, MencionCandidato>>(
    () => new Map(),
  );
  const [menu, setMenu] = React.useState<{ consulta: string; activo: number } | null>(null);

  const candidatosQuery = useQuery({
    queryKey: ["menciones-candidatos", marcaActiva ?? "__todas__"],
    queryFn: ({ signal }) => api.mencionesCandidatos(marcaActiva ?? undefined, signal),
    staleTime: 5 * 60_000,
  });
  const candidatos = candidatosQuery.data?.usuarios ?? [];

  // Sugerencias filtradas por lo escrito tras la @ (por handle o por nombre). Tope visual.
  const sugerencias = React.useMemo(() => {
    if (menu === null) return [];
    const q = menu.consulta.toLowerCase();
    return candidatos
      .filter((c) => c.usuario.toLowerCase().includes(q) || c.nombre.toLowerCase().includes(q))
      .slice(0, 6);
  }, [menu, candidatos]);

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.comentarios(contenidoId, undefined, signal),
    enabled: !!contenidoId,
  });
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: clave });

  // Al cambiar el texto: actualízalo y detecta si el cursor está sobre un disparador `@…`.
  const alEscribir = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const valor = e.target.value;
    setTexto(valor);
    const antesDelCursor = valor.slice(0, e.target.selectionStart ?? valor.length);
    const m = antesDelCursor.match(TOKEN_MENCION);
    setMenu(m ? { consulta: m[1], activo: 0 } : null);
  };

  // Inserta `@usuario ` reemplazando el disparador `@…` y recuerda el id mencionado.
  const elegirMencion = (c: MencionCandidato) => {
    const ta = textareaRef.current;
    const cursor = ta?.selectionStart ?? texto.length;
    const antes = texto.slice(0, cursor).replace(TOKEN_MENCION, `@${c.usuario} `);
    const nuevo = antes + texto.slice(cursor);
    setTexto(nuevo);
    setSeleccionadas((prev) => new Map(prev).set(c.id, c));
    setMenu(null);
    requestAnimationFrame(() => {
      ta?.focus();
      const pos = antes.length;
      ta?.setSelectionRange(pos, pos);
    });
  };

  // Teclas con el menú abierto: ↑/↓ navegan, Enter/Tab eligen, Escape cierra (sin tocar el texto).
  const alTeclear = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (menu === null || sugerencias.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setMenu({ ...menu, activo: (menu.activo + 1) % sugerencias.length });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setMenu({ ...menu, activo: (menu.activo - 1 + sugerencias.length) % sugerencias.length });
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      const elegido = sugerencias[menu.activo] ?? sugerencias[0];
      if (elegido) elegirMencion(elegido);
    } else if (e.key === "Escape") {
      setMenu(null);
    }
  };

  // Solo se mandan como menciones los ids cuyo `@usuario` SIGUE en el texto (si lo borró, fuera).
  const mencionesVigentes = (): string[] =>
    [...seleccionadas.values()]
      .filter((c) => texto.includes(`@${c.usuario}`))
      .map((c) => c.id);

  const crear = useMutation({
    mutationFn: () =>
      api.crearComentario(contenidoId, texto.trim(), undefined, mencionesVigentes()),
    onSuccess: () => {
      setTexto("");
      setSeleccionadas(new Map());
      setMenu(null);
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
        <div className="relative">
          <Textarea
            ref={textareaRef}
            value={texto}
            onChange={alEscribir}
            onKeyDown={alTeclear}
            onBlur={() => setMenu(null)}
            placeholder="Escribe un comentario… usa @ para mencionar a alguien"
            rows={2}
            className="text-sm"
          />
          {/* Menú flotante de menciones: aparece al escribir `@…`. `onMouseDown` (no click)
              para no perder el foco/selección del textarea antes de insertar. */}
          {menu !== null && sugerencias.length > 0 && (
            <ul className="absolute left-0 right-0 top-full z-50 mt-1 max-h-56 overflow-y-auto rounded-md border border-border bg-popover py-1 shadow-lg">
              {sugerencias.map((c, i) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      elegirMencion(c);
                    }}
                    className={cn(
                      "flex w-full flex-col items-start px-3 py-1.5 text-left text-sm hover:bg-muted/60",
                      i === menu.activo && "bg-muted/60",
                    )}
                  >
                    <span className="text-foreground">{c.nombre}</span>
                    <span className="text-xs text-muted-foreground">@{c.usuario}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
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

      {comentarios.length === 0 ? null : (
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
