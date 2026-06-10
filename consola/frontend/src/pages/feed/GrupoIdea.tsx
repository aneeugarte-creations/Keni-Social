/**
 * GRUPO de IDEA del Feed de ideación: una sola IDEA (un `contenido`) con TODAS sus redes juntas,
 * nunca mezclada con otra idea en la misma fila. Resuelve la queja "no quiero que se mezclen posts
 * diferentes en la misma row": cada idea es su propio bloque y dentro va una rejilla con una celda
 * por red ya GENERADA. Las redes del FORMATO de la idea que aún no tienen pieza se condensan en
 * UNA franja "Falta generar: …" bajo la rejilla (una idea foto va a 3 redes; una video a las 5 —
 * `REDES_POR_FORMATO`—: no se listan redes a las que la idea nunca irá). Antes cada hueco era un
 * placeholder de ~400×600px y una idea podía enseñar más vacío que contenido.
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
 * `PlaceholderRed` (hueco con la anatomía de un post) queda SOLO para el fallback de la rejilla
 * plana de `FeedIdeacion` (vista filtrada a una red sin pieza).
 */
import * as React from "react";

import { DistintivoRed } from "@/components/comunes/DistintivoRed";
import { formatearFechaHoraCorta } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import { iconoRed, nombreRed } from "@/pages/publicaciones/meta";
import type { Publicacion } from "@/types";

import { GRID_COLS, normalizarFormato, REDES_POR_FORMATO } from "./formato";
import { PostFeed } from "./PostFeed";

/** Una idea agrupada: el tema + la marca + sus piezas (una por red ya generada). */
export interface GrupoDeIdea {
  id: string;
  titulo: string;
  marca_nombre: string;
  piezas: Publicacion[];
}

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
          {/* El título se diferencia de «No generado» por color/peso (escala del sistema),
              no por 1px de tamaño. */}
          {titulo && <span className="line-clamp-2 text-xs font-medium text-foreground">{titulo}</span>}
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
 * Cabecera de una idea (marca · TÍTULO): el ancla de lectura del feed. La usa la cabecera del
 * grupo (con los metadatos de la nota original a la derecha) y, como MICROCABECERA, cada celda
 * de la rejilla plana (vista filtrada a una red: sin ella no se sabe de qué marca/tema es cada
 * pieza sin abrirla). Con `mostrarMarca: false` se omite el prefijo «marca ·» (cuando hay una
 * marca activa en la topbar, repetirla en cada grupo compite con el título).
 */
export function CabeceraIdea({
  marca,
  titulo,
  mostrarMarca = true,
  derecha,
}: {
  marca: string;
  titulo: string;
  mostrarMarca?: boolean;
  /** Metadatos a la derecha (fecha/fuente de la nota original). */
  derecha?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 pb-2 text-xs text-muted-foreground">
      {mostrarMarca && (
        <>
          <span className="shrink-0">{marca}</span>
          <span aria-hidden="true">·</span>
        </>
      )}
      {/* <h3>: los lectores de pantalla saltan de idea en idea. `line-clamp-2` (no truncate):
          en pantallas estrechas el ancla de lectura no se queda en 2-4 caracteres. */}
      <h3
        className="min-w-0 flex-1 line-clamp-2 text-base font-semibold text-foreground"
        title={titulo}
      >
        {titulo || "Sin título"}
      </h3>
      {derecha}
    </header>
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
  mostrarMarca = true,
}: {
  grupo: GrupoDeIdea;
  redes: string[];
  columnas: number;
  /** Vista filtrada: solo las piezas que cumplen, sin huecos "No generado" ni tarjetas ajenas. */
  filtra?: (p: Publicacion) => boolean;
  /** false con una marca activa en la topbar: el dato ya vive en el switch global. */
  mostrarMarca?: boolean;
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
  // Solo las redes CON pieza pintan tarjeta; las pendientes del formato van a la franja
  // compacta "Falta generar" (sin huecos gigantes).
  const redesVisibles = redes.filter((r) => porRed.has(r));
  const redesFaltantes = filtra
    ? []
    : redes.filter((r) => !porRed.has(r) && REDES_POR_FORMATO[formatoGrupo].includes(r));
  // PROCEDENCIA de la idea (propiedad del tema; todas las piezas la comparten): fecha en que el
  // medio publicó la nota original (`fecha_fuente`, fallback a la captura del Radar) + nombre
  // del medio (`fuente_original`). Vacíos en creación propia -> solo marca + título.
  const fechaNota = grupo.piezas[0]?.fecha_fuente || "";
  const fuenteNota = grupo.piezas[0]?.fuente_original || "";

  return (
    // Sin caja-dentro-de-caja: el agrupamiento lo dan la cabecera de idea y el espaciado entre
    // grupos del feed (las tarjetas ya traen su propio borde).
    <section>
      <CabeceraIdea
        marca={grupo.marca_nombre}
        titulo={grupo.titulo}
        mostrarMarca={mostrarMarca}
        derecha={
          (fechaNota || fuenteNota) && (
            // En xs baja a una segunda línea; en sm+ se queda a la derecha como metadato.
            <span className="flex basis-full items-center gap-2 sm:ml-auto sm:basis-auto">
              {fechaNota && (
                <span className="tabular-nums" title="Fecha de la nota original (hora CDMX)">
                  <span className="sr-only">Fecha de la nota original (hora CDMX): </span>
                  {formatearFechaHoraCorta(fechaNota)}
                </span>
              )}
              {fechaNota && fuenteNota && <span aria-hidden="true">·</span>}
              {fuenteNota && (
                <span className="max-w-[10rem] truncate" title="Medio del que salió la nota original">
                  <span className="sr-only">Medio del que salió la nota original: </span>
                  {fuenteNota}
                </span>
              )}
            </span>
          )
        }
      />
      <div className={cn("grid items-start gap-4", GRID_COLS[columnas])}>
        {redesVisibles.map((r) => {
          const p = porRed.get(r);
          if (!p) return null; // no pasa: redesVisibles ya exige pieza
          // Cada celda es un punto de snap: en móvil a 1 columna el scroll encaja pieza a pieza
          // dentro de la idea (estilo Shorts), no solo de idea a idea.
          return (
            <div key={r} className="snap-start">
              <PostFeed publicacion={p} />
            </div>
          );
        })}
      </div>
      {redesFaltantes.length > 0 && (
        <div className="mt-2 flex min-h-10 flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-dashed border-border px-3 py-1.5 text-xs text-muted-foreground">
          <span>Falta generar:</span>
          {redesFaltantes.map((r) => {
            const Icono = iconoRed(r);
            return (
              <span key={r} className="inline-flex items-center gap-1">
                <Icono className="h-3.5 w-3.5" aria-hidden="true" />
                {nombreRed(r)}
              </span>
            );
          })}
        </div>
      )}
    </section>
  );
}
