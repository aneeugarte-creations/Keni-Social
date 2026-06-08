/**
 * Cobertura — el pool de Noticias (flujo continuo de historias).
 *
 * Muestra el archivo persistente del motor de ingesta DEDUPLICADO en HISTORIAS
 * (clusters): una historia = la misma noticia contada por N fuentes, con su señal
 * de corroboración, badges de verificación/traducción y acciones Usar/Descartar.
 * Filtros por categoría/estado. El crudo por artículo ya no se muestra (Historias
 * es la única vista) y la salud de feeds se gestiona en Fuentes.
 *
 * Contrato: docs/maquina-contenido/A-motor-ingesta.md
 *           docs/maquina-contenido/B-clustering-historias.md
 *           docs/maquina-contenido/D-cobertura-verificacion.md
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Flame,
  Globe,
  Loader2,
  Newspaper,
  Radio,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  Trash2,
  Zap,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { Historia } from "@/types";

// ── Constantes ────────────────────────────────────────────────────────────────

/** Cada cuánto (ms) se refresca la lista automáticamente (sensación "live"). */
const REFETCH_INTERVAL_MS = 45_000;

/** Artículos / historias por página. */
const PAGE_SIZE = 30;

// ── Utilidades ────────────────────────────────────────────────────────────────

/** Tiempo relativo legible en español («hace 3 min», «hace 2 h», etc.). */
function tiempoRelativo(iso: string): string {
  if (!iso) return "";
  try {
    const delta = Date.now() - new Date(iso).getTime();
    const seg = Math.floor(delta / 1000);
    if (seg < 60) return "hace unos segundos";
    const min = Math.floor(seg / 60);
    if (min < 60) return `hace ${min} min`;
    const h = Math.floor(min / 60);
    if (h < 24) return `hace ${h} h`;
    const d = Math.floor(h / 24);
    return `hace ${d} día${d !== 1 ? "s" : ""}`;
  } catch {
    return iso.slice(0, 16).replace("T", " ");
  }
}

// ── Claves de React Query ─────────────────────────────────────────────────────

const CLAVE_HISTORIAS = (
  marcaActiva: string | null,
  estado: string,
  offset: number,
) => ["noticias", "historias", marcaActiva ?? "", estado, offset] as const;

const CLAVE_COBERTURA = ["noticias", "cobertura"] as const;

// ── Componente: barra de cobertura (resumen de salud) ─────────────────────────

function BarraCobertura() {
  const query = useQuery({
    queryKey: CLAVE_COBERTURA,
    queryFn: ({ signal }) => api.noticias.cobertura(signal),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  if (query.isError) return null;
  if (query.isPending) {
    return (
      <div className="mb-6 flex flex-wrap gap-2" aria-label="Cargando estado de cobertura">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-8 w-28 rounded-full" />
        ))}
      </div>
    );
  }

  const d = query.data;

  return (
    <div
      className="mb-6 flex flex-wrap items-center gap-2"
      data-testid="barra-cobertura"
      aria-label="Estado del motor de ingesta"
    >
      {/* Feeds activos */}
      {d?.feeds_activos != null && (
        <Badge variant="outline" className="gap-1 text-xs">
          <Radio className="h-3 w-3 text-evergreen-500" />
          {d.feeds_activos} feed{d.feeds_activos !== 1 ? "s" : ""} activo{d.feeds_activos !== 1 ? "s" : ""}
        </Badge>
      )}

      {/* Feeds con error */}
      {d?.feeds_con_error != null && d.feeds_con_error > 0 && (
        <Badge variant="outline" className="gap-1 border-amber-400 text-amber-600 text-xs">
          <AlertTriangle className="h-3 w-3" />
          {d.feeds_con_error} con error
        </Badge>
      )}

      {/* Items últimas 24h */}
      {d?.items_24h != null && (
        <Badge variant="secondary" className="gap-1 text-xs">
          <Newspaper className="h-3 w-3" />
          {d.items_24h.toLocaleString("es-MX")} en 24 h
        </Badge>
      )}

      {/* Frescura: último sondeo */}
      {d?.ultimo_sondeo && (
        <span className="text-xs text-muted-foreground ml-1">
          Sondeo {tiempoRelativo(d.ultimo_sondeo)}
        </span>
      )}

      {/* Indicador de live-refresh */}
      {query.isFetching && (
        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" aria-label="Actualizando" />
      )}
    </div>
  );
}

interface PropsTarjetaHistoria {
  historia: Historia;
  queryKey: readonly unknown[];
}

function TarjetaHistoria({ historia, queryKey }: PropsTarjetaHistoria) {
  const queryClient = useQueryClient();
  const [expandida, setExpandida] = React.useState(false);

  const usarMut = useMutation({
    mutationFn: () => api.noticias.usarHistoria(historia.id, { generar: true }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      toast.success("Copy en marcha — aparecerá en el Feed para imagen y aprobación.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const descartarMut = useMutation({
    mutationFn: () => api.noticias.descartarHistoria(historia.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      toast.success("Historia descartada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const enCurso = usarMut.isPending || descartarMut.isPending;
  const esUsada = historia.estado === "usado";
  const esDescartada = historia.estado === "descartado";
  const tieneEnlaces = historia.enlaces && historia.enlaces.length > 0;

  return (
    <Card
      className={`text-sm transition-opacity ${esDescartada ? "opacity-50" : ""}`}
      data-testid="historia-item"
    >
      <CardContent className="pt-3 pb-3 space-y-2">
        {/* Cabecera: título + acciones */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <p className="font-medium leading-snug">{historia.titulo || "(sin título)"}</p>
          </div>

          {/* Acciones */}
          <div className="flex shrink-0 items-center gap-1">
            {esUsada ? (
              <Badge variant="ok" className="gap-1 text-xs">
                <CheckCircle2 className="h-3 w-3" />
                En el feed
              </Badge>
            ) : esDescartada ? (
              <Badge variant="secondary" className="text-xs">Descartada</Badge>
            ) : (
              <>
                <Badge variant="secondary" className="text-xs">En el pool</Badge>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 gap-1 px-2 text-xs text-muted-foreground"
                  onClick={() => usarMut.mutate()}
                  disabled={enCurso}
                  aria-label="Empujar ya (fuerza al feed)"
                  title="Forzar esta nota al feed ahora. Normalmente el auto-feed lleva solas las historias relevantes."
                >
                  {usarMut.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Newspaper className="h-3 w-3" />
                  )}
                  Empujar ya
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                  onClick={() => descartarMut.mutate()}
                  disabled={enCurso}
                  aria-label="Descartar historia"
                >
                  {descartarMut.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Resumen */}
        {historia.resumen && (
          <p className="text-muted-foreground text-xs leading-relaxed line-clamp-2">
            {historia.resumen}
          </p>
        )}

        {/* Badges de metadatos */}
        <div className="flex flex-wrap items-center gap-1.5">
          {/* Corroboración: badge prominente de fuentes */}
          <Badge
            variant="secondary"
            className="gap-1 text-xs font-semibold"
            data-testid="badge-fuentes"
          >
            <Radio className="h-3 w-3" />
            {historia.n_fuentes} fuente{historia.n_fuentes !== 1 ? "s" : ""}
          </Badge>

          {/* Verificación (Ola D) */}
          {historia.verificacion === "corroborada" && (
            <Badge
              variant="outline"
              className="gap-1 text-xs border-evergreen-500 text-evergreen-700"
              data-testid="badge-verificacion"
            >
              <ShieldCheck className="h-3 w-3" />
              Corroborada
            </Badge>
          )}
          {historia.verificacion === "unica_fuente" && (
            <Badge
              variant="outline"
              className="gap-1 text-xs text-muted-foreground"
              data-testid="badge-verificacion"
            >
              <ShieldQuestion className="h-3 w-3" />
              Única fuente
            </Badge>
          )}
          {historia.verificacion === "dudosa" && (
            <Badge
              variant="outline"
              className="gap-1 text-xs border-amber-400 text-amber-600"
              data-testid="badge-verificacion"
            >
              <ShieldAlert className="h-3 w-3" />
              Dudosa
            </Badge>
          )}

          {/* Traducción (Ola D) */}
          {historia.traducido && historia.idioma && (
            <Tooltip
              label={historia.titulo_original ? `Original: ${historia.titulo_original}` : `Traducido de ${historia.idioma.toUpperCase()}`}
              side="top"
            >
              <Badge
                variant="outline"
                className="gap-1 text-xs text-blue-600 border-blue-400"
                data-testid="badge-traducido"
              >
                <Globe className="h-3 w-3" />
                traducido de {historia.idioma.toUpperCase()}
              </Badge>
            </Tooltip>
          )}

          {/* Breaking */}
          {historia.breaking === 1 && (
            <Badge className="gap-1 text-xs bg-red-600 hover:bg-red-600 text-white border-0">
              <Zap className="h-3 w-3" />
              Breaking
            </Badge>
          )}

          {/* Score de jerarquización (algoritmo de ponderación): mayor = más prioritaria */}
          {historia.score > 0 && (
            <Badge variant="secondary" className="gap-1 text-xs" data-testid="badge-score">
              <Flame className="h-3 w-3 text-amber-500" />
              {Math.round(historia.score * 100)}
            </Badge>
          )}

          {/* Idiomas (excepto solo "es") */}
          {historia.idiomas
            .filter((l) => l && l !== "es")
            .map((l) => (
              <Badge key={l} variant="outline" className="text-xs uppercase">{l}</Badge>
            ))}

          {/* Rango temporal */}
          {historia.primer_visto && (
            <span className="text-xs text-muted-foreground self-center">
              {tiempoRelativo(historia.primer_visto)}
              {historia.ultimo_visto &&
                historia.ultimo_visto !== historia.primer_visto && (
                  <> – {tiempoRelativo(historia.ultimo_visto)}</>
                )}
            </span>
          )}
        </div>

        {/* Lista expandible de enlaces corroborantes */}
        {tieneEnlaces && (
          <div>
            <button
              type="button"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setExpandida((v) => !v)}
              aria-expanded={expandida}
              aria-label={expandida ? "Ocultar fuentes" : "Ver fuentes corroborantes"}
            >
              {expandida ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              {expandida ? "Ocultar fuentes" : `Ver ${historia.enlaces.length} fuente${historia.enlaces.length !== 1 ? "s" : ""}`}
            </button>

            {expandida && (
              <ul className="mt-1.5 space-y-1 pl-4" data-testid="lista-enlaces">
                {historia.enlaces.map((enlace, i) => (
                  <li key={i} className="text-xs flex items-start gap-1">
                    <a
                      href={enlace.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline flex items-center gap-0.5 break-words flex-1 min-w-0"
                    >
                      {enlace.titulo || enlace.url}
                      <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
                    </a>
                    {enlace.fuente && (
                      <span className="text-muted-foreground shrink-0">— {enlace.fuente}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Vista: Historias (Ola B) ──────────────────────────────────────────────────

interface PropsVistaHistorias {
  marcaActiva: string | null;
}

function VistaHistorias({ marcaActiva }: PropsVistaHistorias) {
  const [estado, setEstado] = React.useState("");
  const [offset, setOffset] = React.useState(0);

  React.useEffect(() => {
    setOffset(0);
  }, [marcaActiva, estado]);

  const clave = CLAVE_HISTORIAS(marcaActiva, estado, offset);

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) =>
      api.noticias.historias(
        {
          marca: marcaActiva ?? undefined,
          estado: estado || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    staleTime: 20_000,
    refetchInterval: REFETCH_INTERVAL_MS,
  });

  const historias = query.data?.historias ?? [];
  const total = query.data?.total ?? 0;
  const hayMas = offset + PAGE_SIZE < total;
  const hayAnterior = offset > 0;

  return (
    <>
      {/* Filtros — la jerarquización es por marca/línea editorial, no por categoría */}
      <div className="mb-5 flex flex-wrap items-end gap-3">
        {/* Estado */}
        <Select value={estado || "__todos__"} onValueChange={(v) => setEstado(v === "__todos__" ? "" : v)}>
          <SelectTrigger className="w-36" aria-label="Filtrar por estado" data-testid="filtro-estado-historias">
            <SelectValue placeholder="Estado" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__todos__">Todos los estados</SelectItem>
            <SelectItem value="nuevo">Nuevo</SelectItem>
            <SelectItem value="usado">Usado</SelectItem>
            <SelectItem value="descartado">Descartado</SelectItem>
          </SelectContent>
        </Select>

        {/* Totales */}
        {query.data && (
          <span className="ml-auto text-xs text-muted-foreground self-center">
            {total.toLocaleString("es-MX")} historia{total !== 1 ? "s" : ""}
            {query.isFetching && !query.isPending && (
              <Loader2 className="inline ml-1 h-3 w-3 animate-spin" />
            )}
          </span>
        )}
      </div>

      {/* Error */}
      {query.isError && (
        <BloqueError
          titulo="No se pudieron cargar las historias"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
        />
      )}

      {/* Esqueletos de carga */}
      {query.isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      )}

      {/* Lista */}
      {!query.isLoading && !query.isError && (
        <>
          {historias.length === 0 ? (
            <EstadoVacio
              icono={Newspaper}
              titulo="Sin historias por ahora"
              texto="El motor de clustering agrupará las noticias conforme lleguen artículos corroborados de múltiples fuentes."
            />
          ) : (
            <div className="space-y-2">
              {historias.map((h) => (
                <TarjetaHistoria key={h.id} historia={h} queryKey={clave} />
              ))}
            </div>
          )}

          {/* Paginación */}
          {(hayAnterior || hayMas) && (
            <div className="mt-6 flex items-center justify-between gap-3">
              <Button
                variant="outline"
                size="sm"
                disabled={!hayAnterior}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                aria-label="Página anterior historias"
              >
                Anterior
              </Button>
              <span className="text-xs text-muted-foreground">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total.toLocaleString("es-MX")}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={!hayMas}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                aria-label="Página siguiente historias"
                data-testid="btn-siguiente-historias"
              >
                Siguiente
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}



// ── Página principal ──────────────────────────────────────────────────────────

export default function Cobertura() {
  const { marcaActiva } = useMarcaActiva();

  return (
    <>
      {/* Contenido del índice del hub (pestaña Noticias): encabezado ligero, no una página. */}
      <h2 className="mb-1 text-base font-semibold tracking-tight">Cobertura</h2>

      {/* Barra de salud del motor */}
      <BarraCobertura />

      {/* Explainer del pool */}
      <p className="mb-4 text-xs text-muted-foreground">
        El auto-feed lleva al feed las historias relevantes (tope por marca, configurable). Aquí curas el pool: descarta lo que no sirva o empuja algo concreto con "Empujar ya".
      </p>

      {/* Noticias = el pool DEDUPLICADO en historias (una historia = la misma noticia
          contada por N fuentes). El crudo por artículo ya no se muestra; la salud de
          feeds se gestiona en Fuentes. */}
      <VistaHistorias marcaActiva={marcaActiva} />
    </>
  );
}
