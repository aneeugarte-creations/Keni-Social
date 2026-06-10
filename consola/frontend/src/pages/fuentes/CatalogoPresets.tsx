import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  CheckCircle2,
  ExternalLink,
  Globe,
  Loader2,
  Plus,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
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
import { cn } from "@/lib/utils";
import type { MarcaDisponible, Preset } from "@/types";

import { CLAVE_FUENTES } from "./lib";

// --- Catálogo de presets (Ola 4) -------------------------------------------

/** Etiquetas humanas de las categorías de presets. */
const ETIQUETA_CATEGORIA: Record<string, string> = {
  mx: "México",
  internacional: "Internacional",
  deportes: "Deportes",
  "ciencia-tech": "Ciencia y Tech",
  gaming: "Gaming",
  tendencias: "Tendencias",
};

/**
 * Sección "Catálogo": lista presets curados de feeds agrupados por categoría,
 * con badges de idioma, región y marca sugerida; checkbox por preset y botón
 * "Activar seleccionadas". Al activar, invalida las queries de RSS/fuentes para
 * que los feeds nuevos aparezcan inmediatamente en la pestaña RSS.
 */
export function CatalogoPresets({ marcas }: { marcas: MarcaDisponible[] }) {
  const { marcaActiva } = useMarcaActiva();
  const queryClient = useQueryClient();
  const [categoriaFiltro, setCategoriaFiltro] = React.useState<string>("todas");
  const [seleccionados, setSeleccionados] = React.useState<Set<string>>(() => new Set());

  const query = useQuery({
    queryKey: ["fuentes", "presets", categoriaFiltro, marcaActiva ?? ""],
    queryFn: ({ signal }) =>
      api.fuentesPresets(
        categoriaFiltro === "todas" ? undefined : categoriaFiltro,
        marcaActiva ?? undefined,
        signal,
      ),
  });

  const activar = useMutation({
    // Al activar: si hay marca activa, úsala como destino por defecto (la preset puede tener
    // su propia marca_sugerida, pero en el contexto de la marca activa tiene precedencia).
    mutationFn: (ids: string[]) =>
      api.activarPresets({ ids, ...(marcaActiva ? { marca: marcaActiva } : {}) }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["fuentes", "presets"] });
      void queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES });
      void queryClient.invalidateQueries({ queryKey: ["fuentes", "hub"] });
      // Los feeds recién activados deben aparecer YA en la pestaña Salud (otra query).
      void queryClient.invalidateQueries({ queryKey: ["noticias", "salud"] });
      setSeleccionados(new Set());
      toast.success(
        data.creadas === 0
          ? "Los feeds ya estaban activos"
          : `${data.creadas} ${data.creadas === 1 ? "feed activado" : "feeds activados"}`,
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const presets = query.data?.presets ?? [];
  const categorias = query.data?.categorias ?? [];

  function alternarPreset(id: string) {
    setSeleccionados((prev) => {
      const siguiente = new Set(prev);
      if (siguiente.has(id)) siguiente.delete(id);
      else siguiente.add(id);
      return siguiente;
    });
  }

  // Agrupa los presets por categoría para mostrarlos en secciones.
  const porCategoria = React.useMemo(() => {
    const mapa = new Map<string, Preset[]>();
    for (const p of presets) {
      const cat = p.categoria;
      if (!mapa.has(cat)) mapa.set(cat, []);
      mapa.get(cat)!.push(p);
    }
    return mapa;
  }, [presets]);

  const seleccionadosArr = [...seleccionados];
  const haySeleccionados = seleccionadosArr.length > 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="max-w-2xl space-y-1">
          <p className="flex items-center gap-2 text-sm font-medium">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            Feeds curados listos para activar
          </p>
          <p className="text-sm text-muted-foreground">
            Selecciona uno o varios feeds del catálogo y actívalos con un clic. Aparecerán
            inmediatamente en la pestaña RSS y alimentarán el Radar.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Select value={categoriaFiltro} onValueChange={setCategoriaFiltro}>
            <SelectTrigger className="w-44" aria-label="Filtrar por categoría">
              <SelectValue placeholder="Categoría" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todas">Todas</SelectItem>
              {categorias.map((c) => (
                <SelectItem key={c} value={c}>
                  {ETIQUETA_CATEGORIA[c] ?? c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            onClick={() => activar.mutate(seleccionadosArr)}
            disabled={!haySeleccionados || activar.isPending}
          >
            {activar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Activar seleccionadas
            {haySeleccionados && (
              <Badge variant="secondary" className="ml-1">
                {seleccionadosArr.length}
              </Badge>
            )}
          </Button>
        </div>
      </div>

      {query.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-md" />
          ))}
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar el catálogo"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : presets.length === 0 ? (
        <EstadoVacioTexto
          texto="No hay presets disponibles para esta categoría."
          className="py-8"
        />
      ) : (
        <div className="space-y-8">
          {[...porCategoria.entries()].map(([cat, items]) => (
            <div key={cat} className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Globe className="h-4 w-4 text-muted-foreground" />
                {ETIQUETA_CATEGORIA[cat] ?? cat}
                <Badge variant="secondary">{items.length}</Badge>
              </h3>
              <ul className="space-y-2">
                {items.map((preset) => (
                  <FilaPreset
                    key={preset.id}
                    preset={preset}
                    seleccionado={seleccionados.has(preset.id)}
                    onAlternar={() => alternarPreset(preset.id)}
                    marcas={marcas}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Una fila del catálogo de presets. */
function FilaPreset({
  preset,
  seleccionado,
  onAlternar,
  marcas,
}: {
  preset: Preset;
  seleccionado: boolean;
  onAlternar: () => void;
  marcas: MarcaDisponible[];
}) {
  const marcaNombre = marcas.find((m) => m.id === preset.marca_sugerida)?.nombre ?? preset.marca_sugerida;

  return (
    <li
      className={cn(
        "flex items-start gap-3 rounded-md border border-border p-3 transition-colors",
        preset.activa && "opacity-60",
        seleccionado && !preset.activa && "border-primary/50 bg-primary/5",
      )}
    >
      <Checkbox
        id={`preset-${preset.id}`}
        checked={seleccionado}
        onCheckedChange={() => onAlternar()}
        disabled={preset.activa}
        aria-label={`Seleccionar ${preset.nombre}`}
        className="mt-0.5"
      />
      <div className="min-w-0 flex-1 space-y-1">
        <Label
          htmlFor={`preset-${preset.id}`}
          className={cn(
            "block cursor-pointer font-medium leading-snug",
            preset.activa && "cursor-default",
          )}
        >
          {preset.nombre}
          {preset.activa && (
            <Badge variant="ok" className="ml-2 font-normal">
              <CheckCircle2 className="mr-1 h-3 w-3" />
              Activo
            </Badge>
          )}
        </Label>
        {preset.descripcion && (
          <p className="text-xs text-muted-foreground">{preset.descripcion}</p>
        )}
        <div className="flex flex-wrap items-center gap-1.5">
          {preset.idioma && preset.idioma !== "es" && (
            <Badge variant="outline" className="font-normal">
              {preset.idioma.toUpperCase()}
            </Badge>
          )}
          {preset.region && (
            <Badge variant="secondary" className="font-normal">
              {preset.region}
            </Badge>
          )}
          {marcaNombre && (
            <Badge variant="secondary" className="font-normal">
              {marcaNombre}
            </Badge>
          )}
          {preset.linea_sugerida && (
            <Badge variant="outline" className="font-normal">
              {preset.linea_sugerida}
            </Badge>
          )}
        </div>
      </div>
      <a
        href={preset.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-0.5 shrink-0 text-muted-foreground hover:text-foreground"
        title={preset.url}
        aria-label={`Abrir ${preset.nombre}`}
        onClick={(e) => e.stopPropagation()}
      >
        <ExternalLink className="h-4 w-4" />
      </a>
    </li>
  );
}
