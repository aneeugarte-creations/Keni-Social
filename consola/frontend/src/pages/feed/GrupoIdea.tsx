/**
 * GRUPO de IDEA del Feed de ideación: una sola IDEA (un `contenido`) con TODAS sus redes juntas,
 * nunca mezclada con otra idea en la misma fila. Resuelve la queja "no quiero que se mezclen posts
 * diferentes en la misma row": cada idea es su propio bloque y dentro va una rejilla con una celda
 * por red. Las redes del FORMATO de la idea que aún NO tienen pieza salen como un hueco "No
 * generado" (una idea foto va a 3 redes; una video a las 5 — `REDES_POR_FORMATO`—: no se pintan
 * huecos en redes a las que la idea nunca irá).
 *
 * Cabecera del grupo: el TÍTULO de la idea manda (es el ancla de lectura); la marca va DELANTE
 * como metadato (`UnoTV · Solari fue…`); a la DERECHA la FECHA de la nota original (hora CDMX) +
 * la FUENTE original (el medio del que salió la nota), truncable. Si la idea no nació de una nota
 * (creación propia), solo marca + título. Los logos de redes NO van aquí: cada tarjeta lleva su
 * `DistintivoRed` y los huecos cantan lo que falta.
 *
 * En las VISTAS FILTRADAS (`filtra`) el grupo enseña SOLO las piezas que cumplen el filtro, sin
 * huecos ni tarjetas ajenas: la matriz completa se reserva a "Todo el feed".
 *
 * `PlaceholderRed` es el hueco: comparte la anatomía del post real (cabecera con el distintivo de
 * red + área 4:5 + alto del copy plegado) para que la rejilla quede pareja, atenuado.
 */
import * as React from "react";

import { DistintivoRed } from "@/components/comunes/DistintivoRed";
import { formatearFechaHoraCorta } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import { iconoRed } from "@/pages/publicaciones/meta";
import type { Publicacion } from "@/types";

import { normalizarFormato, REDES_POR_FORMATO } from "./formato";
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
  5: "grid-cols-5",
};

/** Hueco de una red SIN pieza generada para esta idea: la MISMA anatomía que un post real
 *  (cabecera con distintivo + área 4:5 + alto del copy plegado), atenuado. `titulo` (opcional)
 *  identifica la idea cuando el hueco va suelto (vista de una sola red); en la matriz por idea
 *  no hace falta (la cabecera del grupo ya lleva el tema). */
export function PlaceholderRed({ red, titulo }: { red: string; titulo?: string }) {
  const Icono = iconoRed(red);
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-dashed border-border bg-muted/30">
      <header className="flex items-center px-4 pb-2 pt-3">
        <DistintivoRed red={red} />
      </header>
      <div className="flex aspect-[4/5] w-full items-center justify-center">
        <div className="flex flex-col items-center gap-1.5 px-4 text-center text-muted-foreground">
          <Icono className="h-7 w-7 opacity-40" aria-hidden="true" />
          <span className="text-xs">No generado</span>
          {titulo && <span className="line-clamp-2 text-[11px] opacity-80">{titulo}</span>}
        </div>
      </div>
      {/* Reserva el alto del copy plegado del post real (2 líneas + fila del "más"): la rejilla
          no queda dentada entre huecos y posts. */}
      <div className="px-4 pb-1 pt-3">
        <div className="min-h-[2.625rem]" />
        <div className="h-5" />
      </div>
    </div>
  );
}

/**
 * Un bloque por idea: cabecera ligera (marca · TÍTULO + fecha/fuente de la nota original) + una
 * rejilla con UNA celda por red: el post si existe, o un hueco "No generado" en las redes del
 * formato de la idea. `columnas` controla cuántas redes por fila (1-5). Las ideas NO comparten
 * fila: cada `GrupoIdea` es su propio bloque. Con `filtra`, solo se pintan las piezas que cumplen
 * (sin huecos): es el modo de las vistas filtradas del feed.
 */
export function GrupoIdea({
  grupo,
  redes,
  columnas,
  filtra,
}: {
  grupo: GrupoDeIdea;
  redes: string[];
  columnas: number;
  /** Vista filtrada: solo las piezas que cumplen, sin huecos "No generado" ni tarjetas ajenas. */
  filtra?: (p: Publicacion) => boolean;
}) {
  const porRed = React.useMemo(() => {
    const m = new Map<string, Publicacion>();
    for (const p of grupo.piezas) {
      if (filtra && !filtra(p)) continue;
      if (!m.has(p.red)) m.set(p.red, p);
    }
    return m;
  }, [grupo.piezas, filtra]);
  // FORMATO de la idea: si alguna pieza es video, la idea va a las 5 redes; si no, a las 3 de
  // foto. Acota los huecos "No generado" a las redes que el backend SÍ generará.
  const formatoGrupo = grupo.piezas.some((p) => normalizarFormato(p.formato) === "video")
    ? "video"
    : "foto";
  const redesVisibles = filtra
    ? redes.filter((r) => porRed.has(r))
    : redes.filter((r) => porRed.has(r) || REDES_POR_FORMATO[formatoGrupo].includes(r));
  // PROCEDENCIA de la idea (propiedad del tema; todas las piezas la comparten): fecha en que el
  // medio publicó la nota original (`fecha_fuente`, fallback a la captura del Radar) + nombre
  // del medio (`fuente_original`). Vacíos en creación propia -> solo marca + título.
  const fechaNota = grupo.piezas[0]?.fecha_fuente || "";
  const fuenteNota = grupo.piezas[0]?.fuente_original || "";

  return (
    <section className="rounded-xl border border-border/60 bg-muted/20 p-2 sm:p-3">
      <header className="flex items-baseline gap-2 px-1 pb-2 text-xs text-muted-foreground">
        <span className="shrink-0">{grupo.marca_nombre}</span>
        <span aria-hidden="true">·</span>
        <span
          className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground"
          title={grupo.titulo}
        >
          {grupo.titulo || "Sin título"}
        </span>
        {(fechaNota || fuenteNota) && (
          <span className="ml-auto flex shrink-0 items-center gap-2">
            {fechaNota && (
              <span className="tabular-nums" title="Fecha de la nota original (hora CDMX)">
                {formatearFechaHoraCorta(fechaNota)}
              </span>
            )}
            {fechaNota && fuenteNota && <span aria-hidden="true">·</span>}
            {fuenteNota && (
              <span className="max-w-[10rem] truncate" title="Medio del que salió la nota original">
                {fuenteNota}
              </span>
            )}
          </span>
        )}
      </header>
      <div className={cn("grid items-start gap-4", GRID_COLS[columnas])}>
        {redesVisibles.map((r) => {
          const p = porRed.get(r);
          // Cada celda (post o hueco) es un punto de snap: en móvil a 1 columna el scroll encaja
          // pieza a pieza dentro de la idea (estilo Shorts), no solo de idea a idea.
          return (
            <div key={r} className="snap-start">
              {p ? <PostFeed publicacion={p} /> : <PlaceholderRed red={r} />}
            </div>
          );
        })}
      </div>
    </section>
  );
}
