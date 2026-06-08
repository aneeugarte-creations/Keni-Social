/**
 * Carril Rápido — Breaking (Claro Sports).
 *
 * Superficie de urgencia: muestra los temas del Radar con señal ACELERANDO (breaking)
 * para que el equipo prepare un borrador de copy con un tap y lo apruebe en segundos.
 *
 * Principios:
 *   - SÓLO PROPONE. El botón "Preparar borrador" crea un DRAFT; nunca publica.
 *   - Visible sólo para Claro Sports (y la vista "Todas" del admin).
 *   - Auto-refresca la lista cada 30 s para capturar nuevos breakings.
 *   - Sondea la generación en curso (use-generacion) hasta que el copy esté listo.
 */

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock, ExternalLink, Loader2, Zap } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, mensajeError } from "@/lib/api";
import { MARCA_CLARO_SPORTS } from "@/components/layout/gating-marca";
import type { BreakingItem } from "@/types";

const CABECERA = {
  titulo: "Carril rápido — Breaking",
  descripcion:
    "Temas con señal ACELERANDO AHORA. Prepara un borrador con un tap y apruébalo antes de que lo cubra la competencia. Nunca publica solo.",
};

/** Cada cuánto (ms) se refresca automáticamente la lista de breaking. */
const REFETCH_INTERVAL_MS = 30_000;

/** Badge de estado del borrador. */
function BadgeEstadoBorrador({ estado }: { estado: BreakingItem["estado_borrador"] }) {
  if (estado === "generando") {
    return (
      <Badge variant="outline" className="gap-1 border-amber-400 text-amber-600">
        <Loader2 className="h-3 w-3 animate-spin" />
        Generando copy…
      </Badge>
    );
  }
  if (estado === "listo") {
    return (
      <Badge variant="outline" className="gap-1 border-evergreen-500 text-evergreen-600">
        <CheckCircle2 className="h-3 w-3" />
        Borrador listo
      </Badge>
    );
  }
  return null;
}

/** Tarjeta de un tema breaking individual. */
function TarjetaBreaking({ item, marca }: { item: BreakingItem; marca: string }) {
  const queryClient = useQueryClient();
  const { generacion, ejecutando, iniciar } = useGeneracion();

  // Si hay una generación en curso de una preparación previa, arrancamos el sondeo.
  React.useEffect(() => {
    if (
      item.estado_borrador === "generando" &&
      item.generacion_id &&
      !generacion
    ) {
      // Arranca el sondeo desde el id ya conocido.
      iniciar({ id: item.generacion_id, estado: "ejecutando" } as Parameters<typeof iniciar>[0]);
    }
  }, [item.estado_borrador, item.generacion_id, generacion, iniciar]);

  // Cuando la generación en curso termina, refresca la lista.
  React.useEffect(() => {
    if (!ejecutando && generacion?.estado === "completado") {
      void queryClient.invalidateQueries({ queryKey: ["breaking", marca] });
    }
  }, [ejecutando, generacion?.estado, marca, queryClient]);

  const preparar = useMutation({
    mutationFn: () =>
      api.breaking.preparar({ titulo: item.titulo, marca }),
    onSuccess: (data) => {
      if (data.generacion_id) {
        iniciar({ id: data.generacion_id, estado: "ejecutando" } as Parameters<typeof iniciar>[0]);
      }
      void queryClient.invalidateQueries({ queryKey: ["breaking", marca] });
      toast.success("Borrador creado — generando copy en segundo plano.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const enCurso = preparar.isPending || ejecutando || item.estado_borrador === "generando";
  const hayBorrador = item.estado_borrador !== "ninguno";

  return (
    <Card className="border-l-4 border-l-red-500">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base leading-snug">{item.titulo}</CardTitle>
          <div className="flex shrink-0 items-center gap-1.5">
            {item.senal_texto && (
              <Badge variant="secondary" className="gap-1 text-xs">
                <Zap className="h-3 w-3 text-red-500" />
                {item.senal_texto}
              </Badge>
            )}
            <Badge className="bg-red-500 text-white hover:bg-red-600 text-xs">
              Breaking
            </Badge>
          </div>
        </div>
        {item.fuentes.length > 0 && (
          <p className="text-xs text-muted-foreground">{item.fuentes.join(" · ")}</p>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Enlaces de contexto */}
        {item.enlaces.length > 0 && (
          <div className="space-y-1">
            {item.enlaces.slice(0, 3).map((en, i) => (
              <a
                key={i}
                href={en.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <ExternalLink className="h-3 w-3 shrink-0" />
                <span className="truncate">{en.titulo || en.url}</span>
              </a>
            ))}
          </div>
        )}

        {/* Estado del borrador + acción */}
        <div className="flex items-center justify-between gap-2 pt-1">
          <BadgeEstadoBorrador
            estado={
              enCurso && !hayBorrador
                ? "generando"
                : item.estado_borrador
            }
          />

          {hayBorrador && item.contenido_id ? (
            <Button variant="outline" size="sm" asChild>
              <a href={`/operacion/feed/lista`} className="gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-evergreen-500" />
                Ver borrador
              </a>
            </Button>
          ) : (
            <Button
              size="sm"
              className="bg-red-500 hover:bg-red-600 text-white gap-1.5"
              disabled={enCurso}
              onClick={() => preparar.mutate()}
            >
              {enCurso ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Preparando…
                </>
              ) : (
                <>
                  <Zap className="h-4 w-4" />
                  Preparar borrador
                </>
              )}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/** Página principal del Carril Rápido. */
export default function CarrilRapido() {
  const { marcaActiva } = useMarcaActiva();

  // Si la marca activa no es Claro Sports ni "Todas", no tiene sentido mostrar esto.
  const marca = marcaActiva === MARCA_CLARO_SPORTS || marcaActiva === null
    ? MARCA_CLARO_SPORTS
    : marcaActiva;

  const query = useQuery({
    queryKey: ["breaking", marca],
    queryFn: ({ signal }) => api.breaking.listar(marca, signal),
    refetchInterval: REFETCH_INTERVAL_MS,
    staleTime: 15_000,
  });

  return (
    <>
      <PageHeader {...CABECERA} />

      <div className="space-y-4">
        {/* Aviso editorial */}
        <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
          <span>
            Temas con señal <strong>acelerando AHORA</strong>. El sistema genera el copy automáticamente;
            tú decides si publicar. Nada sale sin tu aprobación.
          </span>
        </div>

        {query.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-44 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <BloqueError
            titulo="No se pudo cargar el Carril Rápido"
            mensaje={mensajeError(query.error)}
            onReintentar={() => void query.refetch()}
          />
        ) : (query.data?.items ?? []).length === 0 ? (
          <EstadoVacio
            icono={Clock}
            titulo="Sin breaking por ahora"
            texto="Cuando una señal del Radar acelere, aparecerá aquí para que prepares el copy al instante."
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {(query.data?.items ?? []).map((item) => (
              <TarjetaBreaking key={item.titulo} item={item} marca={marca} />
            ))}
          </div>
        )}

        {query.isFetching && !query.isPending && (
          <p className="text-center text-xs text-muted-foreground">Actualizando…</p>
        )}
      </div>
    </>
  );
}
