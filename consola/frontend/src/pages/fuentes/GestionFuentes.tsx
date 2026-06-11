import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleSlash,
  ExternalLink,
  Plus,
  Rss,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { FuenteRss, MarcaDisponible } from "@/types";

import { formatearFechaHora, tiempoRelativo } from "../publicaciones/meta";
import { DialogoFuente } from "./DialogoFuente";
import { CLAVE_FUENTES, CLAVE_ITEMS } from "./lib";

// --- Feeds (panel izquierdo) -----------------------------------------------

/** Panel izquierdo: alta + lista de feeds con salud, edición y activación. */
export function GestionFuentes({ marcas }: { marcas: MarcaDisponible[] }) {
  // Por marca: cada equipo gestiona los feeds de SU marca + los compartidos (sin marca).
  // El radar/plan de la marca lee exactamente este conjunto. Admin (sin marca activa) ve todo.
  const { marcaActiva } = useMarcaActiva();

  const query = useQuery({
    queryKey: [...CLAVE_FUENTES, marcaActiva ?? ""],
    queryFn: ({ signal }) => api.fuentesRss(marcaActiva ?? undefined, signal),
  });

  // null = sin diálogo; "nuevo" = creando; objeto = editando ese feed.
  const [editando, setEditando] = React.useState<FuenteRss | "nuevo" | null>(null);
  const todas = React.useMemo(() => query.data?.fuentes ?? [], [query.data]);
  const fuentes = React.useMemo(
    () => (marcaActiva ? todas.filter((f) => !f.marca || f.marca === marcaActiva) : todas),
    [todas, marcaActiva],
  );
  const compartidas = React.useMemo(
    () => fuentes.filter((f) => !f.marca).length,
    [fuentes],
  );

  return (
    <Card className="h-fit">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Rss className="h-4 w-4" />
          Feeds
        </CardTitle>
        <Button size="sm" variant="outline" onClick={() => setEditando("nuevo")}>
          <Plus className="h-4 w-4" />
          Añadir
        </Button>
      </CardHeader>
      {marcaActiva && (
        <div className="px-6 pb-1 text-xs text-muted-foreground">
          {compartidas > 0 ? compartidas + ' feed(s) compartida(s)' : ''}
        </div>
      )}
      <CardContent className="space-y-4">
        {query.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <p className="py-4 text-center text-sm text-muted-foreground">{mensajeError(query.error)}</p>
        ) : fuentes.length === 0 ? (
          <EstadoVacioTexto
            texto={
              marcaActiva
                ? "Añade el primer feed."
                : "Aún no hay feeds. Añade el primero con el botón de arriba."
            }
            className="py-4"
          />
        ) : (
          <div className="space-y-2">
            {fuentes.map((f) => (
              <FilaFuente key={f.id} fuente={f} onEditar={() => setEditando(f)} />
            ))}
          </div>
        )}
      </CardContent>

      <DialogoFuente
        abierto={editando !== null}
        fuente={editando === "nuevo" ? null : editando}
        marcas={marcas}
        onCerrar={() => setEditando(null)}
      />
    </Card>
  );
}

/** Una fila de feed con salud, toggle activo, editar y borrar. */
function FilaFuente({
  fuente,
  onEditar,
}: {
  fuente: FuenteRss;
  onEditar: () => void;
}) {
  const queryClient = useQueryClient();

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES });
    void queryClient.invalidateQueries({ queryKey: CLAVE_ITEMS });
    // La pestaña Salud lee otra query: activar/desactivar/borrar debe reflejarse allí YA
    // (sin esperar al refetch de 45 s).
    void queryClient.invalidateQueries({ queryKey: ["noticias", "salud"] });
  };

  const alternarActivo = useMutation({
    mutationFn: () => api.actualizarFuenteRss(fuente.id, { activo: !fuente.activo }),
    onSuccess: () => {
      invalidar();
      toast.success(fuente.activo ? "Feed desactivado" : "Feed activado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarFuenteRss(fuente.id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? "Feed borrado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Acción primaria = editar el feed. Activar/desactivar y borrar van al menú
  // contextual / kebab; el estado se comunica con la insignia "Inactivo" y la
  // opacidad de la fila, así que el icono de toggle persistente sobra.
  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: fuente.activo ? "Desactivar" : "Activar",
      icono: fuente.activo ? CircleSlash : CheckCircle2,
      onClick: () => alternarActivo.mutate(),
      activo: fuente.activo,
      deshabilitado: alternarActivo.isPending,
    },
    { separador: true },
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Borrar el feed "${fuente.nombre}"?`,
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        )
          borrar.mutate();
      },
      destructivo: true,
      deshabilitado: borrar.isPending,
    },
  ];

  return (
    <FilaConAcciones
      como="div"
      onPrimaria={onEditar}
      acciones={acciones}
      etiquetaAcciones={`Acciones de "${fuente.nombre}"`}
      kebab="hover"
      className={cn(
        "space-y-2 rounded-md border border-border p-3 pr-10",
        !fuente.activo && "opacity-60",
      )}
    >
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{fuente.nombre}</span>
          {fuente.marca && (
            <Badge variant="outline" className="font-normal">
              {fuente.marca_nombre || fuente.marca}
            </Badge>
          )}
          {fuente.categoria && (
            <Badge
              variant="secondary"
              className="font-normal"
              title="Cadencia de sondeo"
            >
              {fuente.categoria}
            </Badge>
          )}
          {!fuente.activo && (
            <Badge variant="secondary" className="font-normal">
              Inactivo
            </Badge>
          )}
        </div>
        <a
          href={fuente.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex max-w-full items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
          title={fuente.url}
        >
          <span className="truncate">{fuente.url}</span>
          <ExternalLink className="h-3 w-3 shrink-0" />
        </a>
      </div>
      <SaludFeed fuente={fuente} />
    </FilaConAcciones>
  );
}

/** Línea de salud de un feed: última actualización, conteo y error. */
function SaludFeed({ fuente }: { fuente: FuenteRss }) {
  const relativo = tiempoRelativo(fuente.ultima_actualizacion);
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      {fuente.ultimo_error ? (
        <span className="inline-flex items-center gap-1.5" title={fuente.ultimo_error}>
          <span className="h-2 w-2 shrink-0 rounded-full bg-red-500" aria-hidden />
          Error al refrescar
        </span>
      ) : (
        <span>
          {fuente.ultimo_conteo} {fuente.ultimo_conteo === 1 ? "item" : "items"}
        </span>
      )}
      <span className="text-muted-foreground/60">·</span>
      <span title={formatearFechaHora(fuente.ultima_actualizacion) || undefined}>
        {relativo ? `Actualizado ${relativo}` : "Sin actualizar aún"}
      </span>
    </div>
  );
}
