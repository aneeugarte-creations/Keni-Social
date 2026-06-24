import { FilterX } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CategoriaPlanOpcion, Pieza } from "@/types";

/** Filtros de LIMPIEZA del feed (sobre el contenido padre). Vacío = sin filtrar. */
export interface FiltrosLimpieza {
  /** Antigüedad mínima en horas (>24h=24, >48h=48, >1 semana=168…). */
  antiguedad_h?: string;
  /** Fase de producción: incompleto | producido | programado | publicado. */
  fase?: string;
  /** Tipo de contenido: ia | galeria | fuente. */
  tipo?: string;
  /** Categoría del plan (breaking, mx, internacional…). */
  categoria?: string;
  /** Medio de origen (fuente_original/fuente_nombre). */
  fuente?: string;
}

const _TODOS = "__todos__";

const ANTIGUEDAD = [
  { v: "24", n: "Más de 24 h" },
  { v: "48", n: "Más de 48 h" },
  { v: "72", n: "Más de 3 días" },
  { v: "168", n: "Más de 1 semana" },
  { v: "720", n: "Más de 1 mes" },
];
const FASE = [
  { v: "incompleto", n: "En producción (incompletos)" },
  { v: "producido", n: "Producidos (sin aprobar)" },
  { v: "programado", n: "Programados" },
  { v: "publicado", n: "Publicados" },
];
const TIPO = [
  { v: "ia", n: "IA" },
  { v: "galeria", n: "Galería" },
  { v: "fuente", n: "Fuente" },
];

/** Medios de origen distintos no vacíos de las piezas cargadas, ordenados. */
function fuentesDistintas(piezas: Pieza[]): string[] {
  const vistos = new Set<string>();
  for (const p of piezas) {
    const v = (p.fuente_original ?? "").trim();
    if (v) vistos.add(v);
  }
  return [...vistos].sort((a, b) => a.localeCompare(b, "es"));
}

/**
 * Barra de filtros para LIMPIAR el feed por lotes: acota la lista (y por tanto lo que la
 * selección múltiple puede borrar) por antigüedad, fase de producción, tipo, categoría y
 * medio. La CATEGORÍA viene del catálogo del plan (`{id, nombre}`, misma fuente que «Crear
 * post» y Programa › Plan): el dropdown muestra el NOMBRE legible y filtra por el `id`. La
 * fuente se deriva de las piezas cargadas (no hay catálogo aparte). Controlado: el estado
 * vive en el padre (que lo pasa a `api.piezas`).
 */
export function PanelFiltrosLimpieza({
  valor,
  onCambio,
  categorias,
  piezas,
}: {
  valor: FiltrosLimpieza;
  onCambio: (v: FiltrosLimpieza) => void;
  categorias: CategoriaPlanOpcion[];
  piezas: Pieza[];
}) {
  const fuentes = React.useMemo(() => fuentesDistintas(piezas), [piezas]);
  const set = (clave: keyof FiltrosLimpieza, v: string) =>
    onCambio({ ...valor, [clave]: v === _TODOS ? undefined : v });
  const hayFiltro = Object.values(valor).some(Boolean);

  const ancho = "h-9 w-full sm:w-[180px]";
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <Select value={valor.antiguedad_h ?? _TODOS} onValueChange={(v) => set("antiguedad_h", v)}>
        <SelectTrigger className={ancho} aria-label="Filtrar por antigüedad">
          <SelectValue placeholder="Antigüedad" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={_TODOS}>Cualquier antigüedad</SelectItem>
          {ANTIGUEDAD.map((o) => (
            <SelectItem key={o.v} value={o.v}>{o.n}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={valor.fase ?? _TODOS} onValueChange={(v) => set("fase", v)}>
        <SelectTrigger className={ancho} aria-label="Filtrar por fase">
          <SelectValue placeholder="Fase" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={_TODOS}>Cualquier fase</SelectItem>
          {FASE.map((o) => (
            <SelectItem key={o.v} value={o.v}>{o.n}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={valor.tipo ?? _TODOS} onValueChange={(v) => set("tipo", v)}>
        <SelectTrigger className={ancho} aria-label="Filtrar por tipo">
          <SelectValue placeholder="Tipo" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={_TODOS}>Cualquier tipo</SelectItem>
          {TIPO.map((o) => (
            <SelectItem key={o.v} value={o.v}>{o.n}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      {categorias.length > 0 && (
        <Select value={valor.categoria ?? _TODOS} onValueChange={(v) => set("categoria", v)}>
          <SelectTrigger className={ancho} aria-label="Filtrar por categoría">
            <SelectValue placeholder="Categoría" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={_TODOS}>Cualquier categoría</SelectItem>
            {categorias.map((c) => (
              <SelectItem key={c.id} value={c.id}>{c.nombre}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {fuentes.length > 0 && (
        <Select value={valor.fuente ?? _TODOS} onValueChange={(v) => set("fuente", v)}>
          <SelectTrigger className={ancho} aria-label="Filtrar por fuente">
            <SelectValue placeholder="Fuente" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={_TODOS}>Cualquier fuente</SelectItem>
            {fuentes.map((f) => (
              <SelectItem key={f} value={f}>{f}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {hayFiltro && (
        <Button
          variant="ghost"
          size="sm"
          className="h-9 gap-1.5 text-muted-foreground"
          onClick={() => onCambio({})}
        >
          <FilterX className="h-4 w-4" aria-hidden="true" />
          Limpiar filtros
        </Button>
      )}
    </div>
  );
}
