/**
 * GRUPO de IDEA del Feed de ideación: una sola IDEA (un `contenido`) con TODAS sus redes juntas,
 * nunca mezclada con otra idea en la misma fila. Resuelve la queja "no quiero que se mezclen posts
 * diferentes en la misma row": cada idea es su propio bloque y dentro va una rejilla con una celda
 * por red. Las redes que aún NO tienen pieza salen como un hueco "No generado" (todo el contenido
 * debería existir en todas las redes; si no se quiere postear, se rechaza, no se omite).
 *
 * `PlaceholderRed` es ese hueco: una tarjeta atenuada con la etiqueta de la red y "No generado",
 * con la MISMA forma (4:5) que un post real para que la rejilla quede pareja.
 */
import * as React from "react";

import { cn } from "@/lib/utils";
import { iconoRed, nombreRed } from "@/pages/publicaciones/meta";
import type { Publicacion } from "@/types";

import { PostFeed } from "./PostFeed";

/** Una idea agrupada: el tema + la marca + sus piezas (una por red ya generada). */
export interface GrupoDeIdea {
  id: string;
  titulo: string;
  marca_nombre: string;
  piezas: Publicacion[];
}

/** Clases estáticas (Tailwind las detecta) por nº de columnas de la rejilla interna. Sin prefijo:
 *  aplican en TODOS los anchos (móvil incluido), igual que en el feed plano. */
const GRID_COLS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
};

/** Hueco de una red SIN pieza generada para esta idea: misma forma que un post, atenuado.
 *  `titulo` (opcional) identifica la idea cuando el hueco va suelto (vista de una sola red); en la
 *  matriz por idea no hace falta (la cabecera del grupo ya lleva el tema). */
export function PlaceholderRed({ red, titulo }: { red: string; titulo?: string }) {
  const Icono = iconoRed(red);
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-dashed border-border bg-muted/30">
      <div className="relative flex aspect-[4/5] w-full items-center justify-center">
        {/* Distintivo de la red, en el mismo sitio que el label sobre la imagen de un post real. */}
        <span className="absolute left-2.5 top-2.5 inline-flex items-center gap-1 rounded-md bg-background/80 px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
          <Icono className="h-3 w-3" aria-hidden="true" />
          {nombreRed(red)}
        </span>
        <div className="flex flex-col items-center gap-1.5 px-4 text-center text-muted-foreground">
          <Icono className="h-7 w-7 opacity-40" aria-hidden="true" />
          <span className="text-xs">No generado</span>
          {titulo && <span className="line-clamp-2 text-[11px] opacity-80">{titulo}</span>}
        </div>
      </div>
    </div>
  );
}

/**
 * Un bloque por idea: cabecera ligera (tema · marca · cuántas redes generadas) + una rejilla con
 * UNA celda por red (`redes`): el post si existe, o un hueco "No generado". `columnas` controla
 * cuántas redes por fila (1-4). Las ideas NO comparten fila: cada `GrupoIdea` es su propio bloque.
 */
export function GrupoIdea({
  grupo,
  redes,
  columnas,
}: {
  grupo: GrupoDeIdea;
  redes: string[];
  columnas: number;
}) {
  const porRed = React.useMemo(() => {
    const m = new Map<string, Publicacion>();
    for (const p of grupo.piezas) if (!m.has(p.red)) m.set(p.red, p);
    return m;
  }, [grupo.piezas]);
  const generadas = redes.filter((r) => porRed.has(r)).length;

  return (
    <section className="rounded-xl border border-border/60 bg-muted/20 p-2 sm:p-3">
      <header className="flex items-center gap-2 px-1 pb-2 text-xs text-muted-foreground">
        <span className="truncate font-medium text-foreground">{grupo.titulo || "Sin título"}</span>
        <span aria-hidden="true">·</span>
        <span className="shrink-0">{grupo.marca_nombre}</span>
        <span className="ml-auto shrink-0 tabular-nums">
          {generadas}/{redes.length} redes
        </span>
      </header>
      <div className={cn("grid items-start gap-3", GRID_COLS[columnas])}>
        {redes.map((r) => {
          const p = porRed.get(r);
          return p ? <PostFeed key={r} publicacion={p} /> : <PlaceholderRed key={r} red={r} />;
        })}
      </div>
    </section>
  );
}
