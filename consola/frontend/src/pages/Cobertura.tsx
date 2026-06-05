/**
 * Cobertura — flujo continuo de noticias.
 *
 * Visualiza el archivo persistente del motor de ingesta (Ola A): una lista
 * siempre actualizada de artículos capturados de todas las fuentes RSS, con
 * filtros por categoría/idioma/estado/búsqueda libre y acciones Usar/Descartar
 * por ítem. La barra superior muestra el resumen de salud del motor.
 *
 * Contrato: docs/maquina-contenido/A-motor-ingesta.md
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Newspaper,
  Radio,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { NoticiaItem } from "@/types";

// ── Constantes ────────────────────────────────────────────────────────────────

/** Cada cuánto (ms) se refresca la lista automáticamente (sensación "live"). */
const REFETCH_INTERVAL_MS = 45_000;

/** Artículos por página. */
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

const CLAVE_NOTICIAS = (
  marcaActiva: string | null,
  categoria: string,
  idioma: string,
  q: string,
  estado: string,
  offset: number,
) => ["noticias", "listar", marcaActiva ?? "", categoria, idioma, q, estado, offset] as const;

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
  const categorias = d?.por_categoria ?? {};
  const cats = Object.entries(categorias).sort((a, b) => b[1] - a[1]);

  return (
    <div
      className="mb-6 flex flex-wrap items-center gap-2"
      data-testid="barra-cobertura"
      aria-label="Estado del motor de ingesta"
    >
      {/* Feeds activos */}
      {d?.feeds_activos != null && (
        <Badge variant="outline" className="gap-1 text-xs">
          <Radio className="h-3 w-3 text-green-500" />
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

      {/* Breakdown por categoría (top 4) */}
      {cats.slice(0, 4).map(([cat, n]) => (
        <Badge key={cat} variant="outline" className="text-xs">
          {cat || "sin categoría"}: {n}
        </Badge>
      ))}

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

// ── Componente: tarjeta de noticia ────────────────────────────────────────────

interface PropsTarjetaNoticia {
  item: NoticiaItem;
  queryKey: readonly unknown[];
}

function TarjetaNoticia({ item, queryKey }: PropsTarjetaNoticia) {
  const queryClient = useQueryClient();

  const usarMut = useMutation({
    mutationFn: () => api.noticias.usar(item.id, { generar: true }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      toast.success("Noticia llevada al tablero.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const descartarMut = useMutation({
    mutationFn: () => api.noticias.descartar(item.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      toast.success("Noticia descartada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const enCurso = usarMut.isPending || descartarMut.isPending;
  const esUsado = item.estado === "usado";
  const esDescartado = item.estado === "descartado";

  return (
    <Card
      className={`text-sm transition-opacity ${esDescartado ? "opacity-50" : ""}`}
      data-testid="noticia-item"
    >
      <CardContent className="pt-3 pb-3 space-y-1.5">
        {/* Cabecera: título + acciones */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium leading-snug hover:underline flex items-center gap-1 break-words"
              >
                {item.titulo || "(sin título)"}
                <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
              </a>
            ) : (
              <p className="font-medium leading-snug">{item.titulo || "(sin título)"}</p>
            )}
          </div>

          {/* Acciones */}
          <div className="flex shrink-0 items-center gap-1">
            {esUsado ? (
              <Badge variant="ok" className="gap-1 text-xs">
                <CheckCircle2 className="h-3 w-3" />
                En tablero
              </Badge>
            ) : esDescartado ? (
              <Badge variant="secondary" className="text-xs">Descartada</Badge>
            ) : (
              <>
                <Button
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs"
                  onClick={() => usarMut.mutate()}
                  disabled={enCurso}
                  aria-label="Usar noticia"
                >
                  {usarMut.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Newspaper className="h-3 w-3" />
                  )}
                  Usar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                  onClick={() => descartarMut.mutate()}
                  disabled={enCurso}
                  aria-label="Descartar noticia"
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
        {item.resumen && (
          <p className="text-muted-foreground text-xs leading-relaxed line-clamp-2">
            {item.resumen}
          </p>
        )}

        {/* Badges de metadatos */}
        <div className="flex flex-wrap gap-1.5">
          {item.fuente_nombre && (
            <Badge variant="secondary" className="text-xs">{item.fuente_nombre}</Badge>
          )}
          {item.categoria && (
            <Badge variant="outline" className="text-xs">{item.categoria}</Badge>
          )}
          {item.idioma && item.idioma !== "es" && (
            <Badge variant="outline" className="text-xs uppercase">{item.idioma}</Badge>
          )}
          {item.capturado_en && (
            <span className="text-xs text-muted-foreground self-center">
              {tiempoRelativo(item.capturado_en)}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function Cobertura() {
  const { marcaActiva } = useMarcaActiva();

  // Filtros
  const [categoria, setCategoria] = React.useState("");
  const [idioma, setIdioma] = React.useState("");
  const [q, setQ] = React.useState("");
  const [estado, setEstado] = React.useState("");
  const [offset, setOffset] = React.useState(0);

  // Resetear paginación al cambiar filtros
  React.useEffect(() => {
    setOffset(0);
  }, [marcaActiva, categoria, idioma, q, estado]);

  const clave = CLAVE_NOTICIAS(marcaActiva, categoria, idioma, q, estado, offset);

  const noticiasQuery = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) =>
      api.noticias.listar(
        {
          marca: marcaActiva ?? undefined,
          categoria: categoria || undefined,
          q: q.trim() || undefined,
          estado: estado || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    staleTime: 20_000,
    refetchInterval: REFETCH_INTERVAL_MS,
  });

  const items = noticiasQuery.data?.items ?? [];
  const total = noticiasQuery.data?.total ?? 0;
  const hayMas = offset + PAGE_SIZE < total;
  const hayAnterior = offset > 0;

  return (
    <>
      <PageHeader
        titulo="Cobertura — flujo continuo de noticias"
        descripcion="Archivo persistente del motor de ingesta. Todo lo que los feeds capturan, en tiempo real."
      />

      {/* Barra de salud del motor */}
      <BarraCobertura />

      {/* Filtros */}
      <div className="mb-5 flex flex-wrap items-end gap-3">
        {/* Búsqueda libre */}
        <Input
          placeholder="Buscar por título…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-56"
          aria-label="Buscar noticias"
          data-testid="filtro-q"
        />

        {/* Categoría */}
        <Select value={categoria || "__todas__"} onValueChange={(v) => setCategoria(v === "__todas__" ? "" : v)}>
          <SelectTrigger className="w-44" aria-label="Filtrar por categoría" data-testid="filtro-categoria">
            <SelectValue placeholder="Categoría" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__todas__">Todas las categorías</SelectItem>
            <SelectItem value="mx">MX</SelectItem>
            <SelectItem value="internacional">Internacional</SelectItem>
            <SelectItem value="deportes">Deportes</SelectItem>
            <SelectItem value="ciencia-tech">Ciencia / Tech</SelectItem>
            <SelectItem value="gaming">Gaming</SelectItem>
            <SelectItem value="tendencias">Tendencias</SelectItem>
          </SelectContent>
        </Select>

        {/* Idioma */}
        <Select value={idioma || "__todos__"} onValueChange={(v) => setIdioma(v === "__todos__" ? "" : v)}>
          <SelectTrigger className="w-36" aria-label="Filtrar por idioma" data-testid="filtro-idioma">
            <SelectValue placeholder="Idioma" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__todos__">Todos los idiomas</SelectItem>
            <SelectItem value="es">Español</SelectItem>
            <SelectItem value="en">Inglés</SelectItem>
            <SelectItem value="pt">Portugués</SelectItem>
            <SelectItem value="fr">Francés</SelectItem>
          </SelectContent>
        </Select>

        {/* Estado */}
        <Select value={estado || "__todos__"} onValueChange={(v) => setEstado(v === "__todos__" ? "" : v)}>
          <SelectTrigger className="w-36" aria-label="Filtrar por estado" data-testid="filtro-estado">
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
        {noticiasQuery.data && (
          <span className="ml-auto text-xs text-muted-foreground self-center">
            {total.toLocaleString("es-MX")} noticia{total !== 1 ? "s" : ""}
            {noticiasQuery.isFetching && !noticiasQuery.isPending && (
              <Loader2 className="inline ml-1 h-3 w-3 animate-spin" />
            )}
          </span>
        )}
      </div>

      {/* Error */}
      {noticiasQuery.isError && (
        <BloqueError
          titulo="No se pudieron cargar las noticias"
          mensaje={mensajeError(noticiasQuery.error)}
          onReintentar={() => void noticiasQuery.refetch()}
        />
      )}

      {/* Esqueletos de carga */}
      {noticiasQuery.isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      )}

      {/* Lista */}
      {!noticiasQuery.isLoading && !noticiasQuery.isError && (
        <>
          {items.length === 0 ? (
            <EstadoVacio
              icono={Newspaper}
              titulo="Sin noticias por ahora"
              texto="El motor de ingesta irá llenando el archivo conforme sondee los feeds."
            />
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <TarjetaNoticia key={item.id} item={item} queryKey={clave} />
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
                aria-label="Página anterior"
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
                aria-label="Página siguiente"
                data-testid="btn-siguiente"
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
