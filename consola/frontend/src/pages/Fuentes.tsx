import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  Rss,
  Sparkles,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { FuenteRss, ItemRss, MarcaDisponible } from "@/types";

import { formatearFechaHora } from "./publicaciones/meta";

const CLAVE_FUENTES = ["rss", "fuentes"] as const;
const CLAVE_ITEMS = ["rss", "items"] as const;

/** Valor de "sin marca / general" en el selector de alta. */
const MARCA_NINGUNA = "__ninguna__";
/** Valor de "todas las fuentes" en el filtro de items. */
const FUENTE_TODAS = "__todas__";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

const CABECERA = {
  titulo: "Fuentes",
  descripcion:
    "Da de alta feeds RSS y usa sus noticias recientes como material para Generar copy.",
};

/**
 * Página de Fuentes RSS.
 *
 * Carga el catálogo de marcas (vía opciones de publicaciones) para el selector
 * de alta, gestiona los feeds (alta/lista/borrado) y muestra los items recientes
 * con un botón "Usar en Generar copy" que navega prellenando el texto.
 */
export default function Fuentes() {
  // Las marcas viven en el catálogo de opciones de publicaciones.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  return (
    <>
      <PageHeader {...CABECERA} />
      <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <GestionFuentes marcas={marcas} />
        <ItemsRecientes />
      </div>
    </>
  );
}

/** Panel izquierdo: alta + lista de feeds. */
function GestionFuentes({ marcas }: { marcas: MarcaDisponible[] }) {
  const query = useQuery({
    queryKey: CLAVE_FUENTES,
    queryFn: ({ signal }) => api.fuentesRss(signal),
  });

  const fuentes = query.data?.fuentes ?? [];

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Rss className="h-4 w-4" />
          Feeds
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <FormularioFuente marcas={marcas} />

        {query.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <p className="py-4 text-center text-sm text-destructive">{mensajeError(query.error)}</p>
        ) : fuentes.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            Aún no hay feeds. Añade el primero arriba.
          </p>
        ) : (
          <div className="space-y-2">
            {fuentes.map((f) => (
              <FilaFuente key={f.id} fuente={f} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Formulario de alta de un feed RSS. */
function FormularioFuente({ marcas }: { marcas: MarcaDisponible[] }) {
  const queryClient = useQueryClient();
  const [nombre, setNombre] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [marca, setMarca] = React.useState(MARCA_NINGUNA);

  const crear = useMutation({
    mutationFn: () =>
      api.crearFuenteRss({
        nombre: nombre.trim(),
        url: url.trim(),
        marca: marca === MARCA_NINGUNA ? undefined : marca,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES });
      void queryClient.invalidateQueries({ queryKey: CLAVE_ITEMS });
      toast.success("Feed añadido");
      setNombre("");
      setUrl("");
      setMarca(MARCA_NINGUNA);
    },
    // El backend puede devolver 400 si la URL no es válida o por SSRF; mostramos su mensaje.
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = nombre.trim().length > 0 && url.trim().length > 0 && !crear.isPending;

  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/20 p-3">
      <div className="space-y-1.5">
        <Label htmlFor="fuente-nombre">Nombre</Label>
        <Input
          id="fuente-nombre"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Ej. UnoTV Deportes"
          maxLength={120}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fuente-url">URL del feed</Label>
        <Input
          id="fuente-url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://ejemplo.com/rss.xml"
          type="url"
          inputMode="url"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fuente-marca">
          Marca <span className="font-normal text-muted-foreground">(opcional)</span>
        </Label>
        <Select value={marca} onValueChange={setMarca}>
          <SelectTrigger id="fuente-marca">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={MARCA_NINGUNA}>Todas las marcas</SelectItem>
            {marcas.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex justify-end">
        <Button size="sm" onClick={() => crear.mutate()} disabled={!puedeCrear}>
          {crear.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Añadir feed
        </Button>
      </div>
    </div>
  );
}

/** Una fila de feed con acción de borrado. */
function FilaFuente({ fuente }: { fuente: FuenteRss }) {
  const queryClient = useQueryClient();
  const borrar = useMutation({
    mutationFn: () => api.eliminarFuenteRss(fuente.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES });
      void queryClient.invalidateQueries({ queryKey: CLAVE_ITEMS });
      toast.success(res?.mensaje ?? "Feed borrado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="flex items-start justify-between gap-3 rounded-md border border-border p-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{fuente.nombre}</span>
          {fuente.marca && (
            <Badge variant="outline" className="font-normal">
              {fuente.marca_nombre || fuente.marca}
            </Badge>
          )}
        </div>
        <a
          href={fuente.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 truncate text-xs text-muted-foreground hover:text-foreground hover:underline"
          title={fuente.url}
        >
          <span className="truncate">{fuente.url}</span>
          <ExternalLink className="h-3 w-3 shrink-0" />
        </a>
      </div>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Borrar feed"
        title="Borrar"
        className="shrink-0 text-muted-foreground hover:text-destructive"
        onClick={() => borrar.mutate()}
        disabled={borrar.isPending}
      >
        {borrar.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Trash2 className="h-4 w-4" />
        )}
      </Button>
    </div>
  );
}

/** Panel derecho: items recientes con filtro por fuente. */
function ItemsRecientes() {
  const [fuenteSel, setFuenteSel] = React.useState(FUENTE_TODAS);

  const fuentesQuery = useQuery({
    queryKey: CLAVE_FUENTES,
    queryFn: ({ signal }) => api.fuentesRss(signal),
  });
  const fuentes = fuentesQuery.data?.fuentes ?? [];

  const fuenteParam = fuenteSel === FUENTE_TODAS ? undefined : fuenteSel;
  const query = useQuery({
    queryKey: [...CLAVE_ITEMS, fuenteParam ?? ""],
    queryFn: ({ signal }) => api.itemsRss(fuenteParam, signal),
  });

  const items = query.data?.items ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle className="text-base">Noticias recientes</CardTitle>
        <div className="flex items-center gap-2">
          <Select value={fuenteSel} onValueChange={setFuenteSel}>
            <SelectTrigger className="w-[200px]" aria-label="Filtrar por fuente">
              <SelectValue placeholder="Fuente" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={FUENTE_TODAS}>Todas las fuentes</SelectItem>
              {fuentes.map((f) => (
                <SelectItem key={f.id} value={f.id}>
                  {f.nombre}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="icon"
            aria-label="Actualizar noticias"
            title="Actualizar"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <RefreshCw className={cn("h-4 w-4", query.isFetching && "animate-spin")} />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {query.isPending ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <AlertCircle className="h-6 w-6" />
            </div>
            <p className="max-w-md text-sm text-muted-foreground">{mensajeError(query.error)}</p>
            <Button onClick={() => void query.refetch()} disabled={query.isFetching}>
              <RefreshCw className={cn("h-4 w-4", query.isFetching && "animate-spin")} />
              Reintentar
            </Button>
          </div>
        ) : items.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No hay noticias para mostrar. Añade un feed o cambia el filtro.
          </p>
        ) : (
          <div className="space-y-3">
            {items.map((item, i) => (
              <ItemNoticia key={`${item.enlace}-${i}`} item={item} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Una noticia con su acción "Usar en Generar copy". */
function ItemNoticia({ item }: { item: ItemRss }) {
  const navigate = useNavigate();

  function usar() {
    const texto = [item.titulo, item.resumen, item.enlace].filter(Boolean).join("\n\n");
    navigate("/generar-copy", { state: { texto } });
  }

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <Badge variant="secondary" className="font-normal">
          {item.fuente_nombre}
        </Badge>
        {item.fecha && <span>{formatearFechaHora(item.fecha)}</span>}
      </div>
      <p className="font-medium leading-snug">{item.titulo}</p>
      {item.resumen && (
        <p className="line-clamp-3 text-sm text-muted-foreground">{item.resumen}</p>
      )}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button size="sm" onClick={usar}>
          <Sparkles className="h-4 w-4" />
          Usar en Generar copy
        </Button>
        {item.enlace && (
          <Button variant="ghost" size="sm" asChild>
            <a href={item.enlace} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-4 w-4" />
              Abrir
            </a>
          </Button>
        )}
      </div>
    </div>
  );
}
