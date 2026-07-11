/**
 * SaludFeeds — estado de salud del motor de ingesta de feeds.
 *
 * Vive en FUENTES, no en Noticias: monitorizar los canales (feeds activos, en
 * error, stale, huecos de cobertura, reactivación) es configuración/observabilidad
 * de las fuentes, no curación del pool de noticias. Autónomo: toma la marca activa
 * del contexto, así Fuentes lo compone sin props.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Newspaper, Radio, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import type { BadgeProps } from "@/components/ui/badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";

const REFETCH_INTERVAL_MS = 45_000;
const CLAVE_SALUD = (marcaActiva: string | null) =>
  ["noticias", "salud", marcaActiva ?? ""] as const;

export function SaludFeeds() {
  const { marcaActiva } = useMarcaActiva();
  const queryClient = useQueryClient();
  const clave = CLAVE_SALUD(marcaActiva);

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.noticias.salud(marcaActiva ?? undefined, signal),
    staleTime: 30_000,
    refetchInterval: REFETCH_INTERVAL_MS,
  });

  const reactivarMut = useMutation({
    mutationFn: (id: string) => api.fuentes.reactivar(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: clave });
      toast.success("Feed reactivado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo cargar el estado de cobertura"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
      />
    );
  }

  if (query.isPending) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-8 w-32 rounded-full" />
          ))}
        </div>
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>
    );
  }

  const resumen = query.data?.resumen;
  const feeds = query.data?.feeds ?? [];

  /** Frescura en texto legible. */
  function frescuraTexto(min: number | null): string {
    if (min === null || min === undefined) return "—";
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60);
    if (h < 24) return `${h} h`;
    return `${Math.floor(h / 24)} día${Math.floor(h / 24) !== 1 ? "s" : ""}`;
  }

  /** Etiqueta, variante de Badge, SEVERIDAD (0 = peor) y tinte de fila para el estado de un feed. */
  function estadoFeed(feed: (typeof feeds)[number]): {
    label: string;
    variant: BadgeProps["variant"];
    className?: string;
    severidad: number;
    fila: string;
  } {
    if (feed.desactivado_auto === 1) {
      return { label: "Auto-desactivado", variant: "error", severidad: 0, fila: "bg-destructive/10" };
    }
    const slaMin = 180; // KENI_FEED_SLA_MIN por defecto
    if (feed.activo && feed.errores_seguidos > 0) {
      return { label: "Con error", variant: "error", severidad: 1, fila: "bg-amber-50/60 dark:bg-amber-950/20" };
    }
    if (feed.activo && feed.frescura_min !== null && feed.frescura_min > slaMin) {
      return { label: "Stale", variant: "aviso", severidad: 2, fila: "bg-amber-50/40 dark:bg-amber-950/15" };
    }
    if (!feed.activo) {
      return {
        label: "Inactivo", variant: "outline", className: "text-muted-foreground",
        severidad: 3, fila: "opacity-60",
      };
    }
    return {
      label: "Activo", variant: "outline",
      className: "border-emerald-500 text-emerald-700 dark:text-emerald-300",
      severidad: 4, fila: "",
    };
  }

  // PROBLEMAS PRIMERO: esta tabla es un monitor, no un listado — lo roto debe verse arriba
  // sin buscarlo. A igual severidad, los de menos items en 24 h antes (los que menos aportan).
  const feedsOrdenados = [...feeds]
    .map((f) => ({ feed: f, est: estadoFeed(f) }))
    .sort((a, b) => a.est.severidad - b.est.severidad || a.feed.items_24h - b.feed.items_24h);

  return (
    <div className="space-y-6">
      {/* Chips de resumen */}
      {resumen && (
        <div className="flex flex-wrap items-center gap-2" data-testid="salud-resumen">
          <Badge variant="outline" className="gap-1 text-xs border-emerald-500 text-emerald-700 dark:text-emerald-300">
            <Radio className="h-3 w-3" />
            {resumen.activos} activo{resumen.activos !== 1 ? "s" : ""}
          </Badge>
          {resumen.fallando > 0 && (
            <Badge variant="aviso" className="gap-1 text-xs">
              <AlertTriangle className="h-3 w-3" />
              {resumen.fallando} fallando
            </Badge>
          )}
          {resumen.auto_desactivados > 0 && (
            <Badge variant="error" className="gap-1 text-xs">
              <AlertTriangle className="h-3 w-3" />
              {resumen.auto_desactivados} auto-desactivado{resumen.auto_desactivados !== 1 ? "s" : ""}
            </Badge>
          )}
          {resumen.stale > 0 && (
            <Badge variant="aviso" className="gap-1 text-xs">
              <AlertTriangle className="h-3 w-3" />
              {resumen.stale} stale
            </Badge>
          )}
          <Badge variant="secondary" className="gap-1 text-xs">
            <Newspaper className="h-3 w-3" />
            {resumen.items_24h.toLocaleString("es-MX")} en 24 h
          </Badge>
          {resumen.frescura_global_min != null && (
            <Badge variant="outline" className="text-xs">
              Frescura: {frescuraTexto(resumen.frescura_global_min)}
            </Badge>
          )}
          {query.isFetching && (
            <Spinner className="h-3 w-3 text-muted-foreground" label="Actualizando" />
          )}
        </div>
      )}

      {/* Huecos de cobertura */}
      {resumen && resumen.huecos.length > 0 && (
        <Aviso>
          <p className="font-semibold mb-2" data-testid="salud-huecos-titulo">
            Huecos de cobertura ({resumen.huecos.length})
          </p>
          <ul className="space-y-1" data-testid="salud-huecos-lista">
            {resumen.huecos.map((hueco) => (
              <li key={hueco}>{hueco}</li>
            ))}
          </ul>
        </Aviso>
      )}

      {/* Tabla de feeds */}
      {feeds.length === 0 ? (
        <EstadoVacio
          icono={Radio}
          titulo="Sin feeds registrados"
        />
      ) : (
        <div data-testid="salud-tabla-feeds">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nombre</TableHead>
                <TableHead>Categoría</TableHead>
                <TableHead>Marca</TableHead>
                <TableHead className="text-right">Items 24 h</TableHead>
                <TableHead className="text-right" title="Artículos filtrados (no casan agenda)">
                  Filtrados
                </TableHead>
                <TableHead className="text-right">Frescura</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Último error</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {feedsOrdenados.map(({ feed, est }) => {
                // La mutación es de tabla (una para todas las filas): aísla disabled/spinner a la
                // fila en curso por sus `variables` para no girar el spinner de TODOS los feeds.
                const reactivando = reactivarMut.isPending && reactivarMut.variables === feed.id;
                return (
                  <TableRow key={feed.id} className={est.fila}>
                    <TableCell className="font-medium text-xs">{feed.nombre}</TableCell>
                    <TableCell className="text-xs">{feed.categoria || "—"}</TableCell>
                    <TableCell className="text-xs">{feed.marca_nombre || feed.marca || "—"}</TableCell>
                    <TableCell className="text-right text-xs">{feed.items_24h}</TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {feed.ultimo_filtrados ?? "—"}
                    </TableCell>
                    <TableCell className="text-right text-xs">{frescuraTexto(feed.frescura_min)}</TableCell>
                    <TableCell>
                      <Badge variant={est.variant} className={cn("text-xs", est.className)}>
                        {est.label}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">
                      {feed.ultimo_error || "—"}
                    </TableCell>
                    <TableCell>
                      {feed.desactivado_auto === 1 && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1 px-2"
                          disabled={reactivando}
                          onClick={() => reactivarMut.mutate(feed.id)}
                          data-testid={`btn-reactivar-${feed.id}`}
                          aria-label={`Reactivar feed ${feed.nombre}`}
                        >
                          {reactivando ? (
                            <Spinner className="h-3 w-3" />
                          ) : (
                            <RefreshCw className="h-3 w-3" />
                          )}
                          Reactivar
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
