import { useQuery } from "@tanstack/react-query";
import { Bot, FileText, Play, RefreshCw, Send } from "lucide-react";
import { Link } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AgenteResumen } from "@/types";

/** Clave de React Query para el listado de agentes. */
export const CLAVE_AGENTES = ["agentes"] as const;

/** Texto legible del error de la API (o un fallback en español). */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/** Esqueleto de carga que imita la rejilla de agentes. */
function EsqueletoAgentes() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i}>
          <CardHeader className="pb-3">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-3 w-56" />
          </CardHeader>
          <CardContent className="flex gap-2 pt-0">
            <Skeleton className="h-5 w-28" />
            <Skeleton className="h-5 w-20" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/** Tarjeta de un agente (= una marca = su carpeta). Clic → detalle. */
function TarjetaAgente({ agente }: { agente: AgenteResumen }) {
  return (
    <Card className="transition-colors hover:border-primary/50">
      <Link to={`/agentes/${encodeURIComponent(agente.id)}`} className="block">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <CardTitle className="flex items-center gap-2 text-base">
                <Bot className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="truncate">{agente.nombre}</span>
              </CardTitle>
              <p
                className="truncate font-mono text-xs text-muted-foreground"
                title={agente.ruta}
              >
                {agente.ruta}
              </p>
            </div>
            <Badge variant={agente.tiene_claude_md ? "ok" : "aviso"} className="shrink-0">
              {agente.tiene_claude_md ? "Con CLAUDE.md" : "Sin CLAUDE.md"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-0 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Send className="h-4 w-4" aria-hidden="true" />
            {agente.n_publicaciones}{" "}
            {agente.n_publicaciones === 1 ? "publicación" : "publicaciones"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Play className="h-4 w-4" aria-hidden="true" />
            {agente.n_runs} {agente.n_runs === 1 ? "ejecución" : "ejecuciones"}
          </span>
        </CardContent>
      </Link>
    </Card>
  );
}

/**
 * Página de Agentes: lista las marcas (cada una es un agente con su carpeta,
 * CLAUDE.md, sub-contextos y runs). Unifica las antiguas Proyectos, Tareas y
 * Nueva carpeta. Al pulsar una tarjeta se abre su detalle.
 */
export default function Agentes() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_AGENTES,
    queryFn: ({ signal }) => api.agentes(signal),
  });

  const acciones = (
    <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
      <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
      Actualizar
    </Button>
  );

  return (
    <>
      <PageHeader
        titulo="Agentes"
        descripcion="Cada marca es un agente con su carpeta: contexto (CLAUDE.md), sub-contextos y ejecuciones."
        acciones={acciones}
      />

      {isPending ? (
        <EsqueletoAgentes />
      ) : isError ? (
        <BloqueError
          titulo="No se pudieron cargar los agentes"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      ) : data.agentes.length === 0 ? (
        <EstadoVacio
          icono={Bot}
          titulo="Aún no hay agentes"
          texto="Cada marca configurada aparecerá aquí como un agente con su propia carpeta y contexto."
          accion={
            <Button asChild variant="outline" size="sm">
              <Link to="/configuracion">
                <FileText className="h-4 w-4" />
                Configurar marcas
              </Link>
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.agentes.map((a) => (
            <TarjetaAgente key={a.id} agente={a} />
          ))}
        </div>
      )}
    </>
  );
}
