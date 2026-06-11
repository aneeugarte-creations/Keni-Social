/**
 * Bandeja de SOLICITUDES de publicación (para admins): lista las solicitudes abiertas
 * con doc, autor, nota y fecha; el diff producción ↔ versión propuesta se despliega bajo
 * demanda (carga los cuerpos vía /version/{sha}), y cada solicitud se aprueba o rechaza
 * con un comentario opcional.
 *
 * Componente autónomo: listo para montarlo en una ruta o panel sin más cableado.
 */
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, ChevronRight, Inbox, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { DiffProsa } from "@/components/biblioteca/DiffProsa";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { claveSolicitudes, useSolicitudes } from "@/hooks/use-biblioteca";
import { api, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { SolicitudPublicacion } from "@/types";

/** Diff producción ↔ sha propuesto de UNA solicitud (solo se monta al desplegar). */
function DiffSolicitud({ solicitud }: { solicitud: SolicitudPublicacion }) {
  // El sha en producción sale del documento (puede ser null: primera publicación).
  const docQuery = useQuery({
    queryKey: ["texto-doc", solicitud.doc_id],
    queryFn: ({ signal }) => api.documento(solicitud.doc_id, signal),
  });
  const produccionSha = docQuery.data?.documento.produccion?.sha ?? null;

  const cuerpos = useQueries({
    queries: [
      {
        queryKey: ["texto-version", solicitud.doc_id, produccionSha],
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          api.versionTexto(solicitud.doc_id, produccionSha as string, signal),
        enabled: !!produccionSha,
      },
      {
        queryKey: ["texto-version", solicitud.doc_id, solicitud.sha_propuesto],
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          api.versionTexto(solicitud.doc_id, solicitud.sha_propuesto, signal),
      },
    ],
  });
  const [antesQuery, despuesQuery] = cuerpos;

  if (docQuery.isPending || (produccionSha && antesQuery.isPending) || despuesQuery.isPending) {
    return <Skeleton className="h-16 w-full" />;
  }
  return (
    <DiffProsa
      antes={produccionSha ? antesQuery.data?.documento.cuerpo ?? "" : ""}
      despues={despuesQuery.data?.documento.cuerpo ?? ""}
      soloCambios
    />
  );
}

function FilaSolicitud({ solicitud }: { solicitud: SolicitudPublicacion }) {
  const qc = useQueryClient();
  const [desplegada, setDesplegada] = React.useState(false);
  const [comentario, setComentario] = React.useState("");

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: claveSolicitudes("abierta") });
    qc.invalidateQueries({ queryKey: ["texto"] });
  };
  const aprobarMut = useMutation({
    mutationFn: () => api.aprobarSolicitudTexto(solicitud.id, { comentario: comentario.trim() || undefined }),
    onSuccess: () => {
      toast.success(`Solicitud aprobada: «${solicitud.titulo}» ya está en producción.`);
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const rechazarMut = useMutation({
    mutationFn: () => api.rechazarSolicitudTexto(solicitud.id, { comentario: comentario.trim() || undefined }),
    onSuccess: () => {
      toast.info("Solicitud rechazada. Producción no cambia.");
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const resolviendo = aprobarMut.isPending || rechazarMut.isPending;

  return (
    <li className="space-y-2 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{solicitud.titulo}</span>
          <span className="mt-0.5 block text-xs text-muted-foreground">
            {solicitud.autor} · {tiempoRelativo(solicitud.creado) || solicitud.creado.slice(0, 16).replace("T", " ")} ·{" "}
            <span className="font-mono">{solicitud.sha_propuesto.slice(0, 8)}</span>
          </span>
        </span>
        <Badge variant="aviso" className="shrink-0 rounded-full">pendiente</Badge>
      </div>
      {solicitud.nota ? (
        <p className="rounded-md bg-muted/50 px-2.5 py-1.5 text-xs leading-relaxed">
          {solicitud.nota}
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => setDesplegada((v) => !v)}
        className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        {desplegada ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        {desplegada ? "Ocultar cambios" : "Ver cambios"}
      </button>
      {desplegada ? (
        <div className="max-h-72 overflow-y-auto rounded-md border border-border p-3">
          <DiffSolicitud solicitud={solicitud} />
        </div>
      ) : null}

      <div className="flex flex-wrap items-end gap-2">
        <Textarea
          value={comentario}
          onChange={(e) => setComentario(e.target.value)}
          rows={1}
          placeholder="Comentario para quien solicitó (opcional)"
          className="min-h-9 flex-1 text-xs"
        />
        <Button
          size="sm"
          variant="outline"
          disabled={resolviendo}
          onClick={() => rechazarMut.mutate()}
          className="text-destructive hover:text-destructive"
        >
          <X className="mr-1 h-3.5 w-3.5" /> Rechazar
        </Button>
        <Button size="sm" variant="brand" disabled={resolviendo} onClick={() => aprobarMut.mutate()}>
          <Check className="mr-1 h-3.5 w-3.5" />
          {aprobarMut.isPending ? "Publicando…" : "Aprobar y publicar"}
        </Button>
      </div>
    </li>
  );
}

export interface BandejaSolicitudesProps {
  className?: string;
}

/** Lista de solicitudes ABIERTAS, con diff desplegable y aprobar/rechazar (admins). */
export function BandejaSolicitudes({ className }: BandejaSolicitudesProps) {
  const solicitudesQuery = useSolicitudes("abierta");
  const solicitudes = solicitudesQuery.data?.solicitudes ?? [];

  return (
    <section className={cn("overflow-hidden rounded-md border border-border", className)}>
      <header className="flex items-center gap-2 border-b border-border bg-muted/40 px-3 py-2 text-sm font-medium">
        <Inbox className="h-4 w-4 text-muted-foreground" />
        Solicitudes de publicación
        {solicitudes.length > 0 ? (
          <Badge variant="secondary" className="rounded-full">{solicitudes.length}</Badge>
        ) : null}
      </header>
      {solicitudesQuery.isPending ? (
        <div className="space-y-2 p-3">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : solicitudesQuery.isError ? (
        <p className="p-3 text-sm text-muted-foreground">
          {mensajeError(solicitudesQuery.error)}
        </p>
      ) : solicitudes.length === 0 ? (
        <p className="p-3 text-sm text-muted-foreground">
          No hay solicitudes pendientes. Cuando alguien del equipo proponga publicar un
          documento, aparecerá aquí.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {solicitudes.map((s) => (
            <FilaSolicitud key={s.id} solicitud={s} />
          ))}
        </ul>
      )}
    </section>
  );
}
