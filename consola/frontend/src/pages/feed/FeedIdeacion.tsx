/**
 * FEED DE IDEACIÓN (`/parrilla/feed`) — Flujo D, Fase 4 del plan de máquina automática.
 *
 * La superficie de "red social interna": el equipo ve las piezas como POSTS (copy de IA +
 * arte/formato), con un LABEL de su etapa en la tubería, y APRUEBA en línea —como quien
 * interactúa con un post— sin abrir el kanban.
 *
 * UN SOLO feed por fecha, con 3 PESTAÑAS que son VISTAS del mismo listado (no bandejas que
 * fragmenten el flujo ni hagan fetches distintos): se pide TODO una vez (`creado DESC`) y la
 * pestaña solo FILTRA en cliente qué se enseña —
 *   - "Todo el feed": todas las piezas, mezcladas y por fecha (la vista por defecto).
 *   - "Por aprobar": las que esperan tu OK (`estado = en_revision`).
 *   - "Publicado y programado": lo que ya salió o tiene hueco (`estado ∈ {publicado, programado}`).
 * Cada pieza enseña en qué va con su label de etapa, y el OK aparece en línea cuando te toca.
 *
 * Vive DENTRO del AppShell (a diferencia del feed móvil `/feed`, que es de una columna y sin
 * sidebar para revisores en el móvil). Aquí es una pestaña del hub Parrilla, pensada para
 * trabajar el día entero desde el feed.
 *
 * Reutiliza lo existente sin tocar backend:
 *  - `GET /api/publicaciones?marca=` (sin `estado`) para listar TODAS las piezas por fecha;
 *    las pestañas filtran ese único listado en memoria (sin más llamadas).
 *  - `PostFeed`: cada pieza como post + aprobación en línea (forwardea a la cadena multinivel)
 *    + comentarios (`Comentarios`).
 *  - El alta de material la implementa el Flujo A (acción de alta): este feed NO la duplica.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import * as React from "react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, ApiError } from "@/lib/api";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import type { Publicacion } from "@/types";

import { PostFeed } from "./PostFeed";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema. Vuelve a intentarlo.";
}

/**
 * Pestañas del feed: NO son bandejas (un fetch por estado), son VISTAS del mismo listado
 * único. `filtra` decide qué piezas se enseñan; `vacio` el mensaje cuando esa vista no tiene.
 */
type Vista = "todo" | "por_aprobar" | "publicado";

const VISTAS: {
  id: Vista;
  etiqueta: string;
  filtra: (p: Publicacion) => boolean;
  vacio: { titulo: string; texto: string };
}[] = [
  {
    id: "todo",
    etiqueta: "Todo el feed",
    filtra: () => true,
    vacio: {
      titulo: "El feed está vacío",
      texto:
        "El equipo postea material y la IA lo convierte en piezas; aparecerán aquí, las más recientes primero, y aprobarás en línea cuando alguna esté lista.",
    },
  },
  {
    id: "por_aprobar",
    etiqueta: "Por aprobar",
    filtra: (p) => p.estado === "en_revision",
    vacio: {
      titulo: "Nada por aprobar",
      texto: "Cuando la IA deje una pieza lista, aparecerá aquí para tu visto bueno (los 2 OK).",
    },
  },
  {
    id: "publicado",
    etiqueta: "Publicado y programado",
    filtra: (p) => p.estado === "publicado" || p.estado === "programado",
    vacio: {
      titulo: "Nada publicado ni programado",
      texto: "Las piezas que apruebes y tengan hueco en la parrilla saldrán aquí.",
    },
  },
];

export default function FeedIdeacion() {
  const queryClient = useQueryClient();
  // La marca la manda el switch global de la barra superior (deriva del perfil).
  // El feed se filtra implícitamente por la marca activa; no hay selector local.
  const { marcaActiva } = useMarcaActiva();

  const [vista, setVista] = React.useState<Vista>("todo");

  // UN solo fetch: TODAS las etapas mezcladas y ordenadas por fecha (el backend devuelve
  // `creado DESC` cuando no se filtra estado). Las pestañas filtran este listado en memoria.
  const feedQuery = useQuery({
    queryKey: [...CLAVE_PUBLICACIONES, "feed-ideacion", marcaActiva ?? MARCA_ACTIVA_TODAS],
    queryFn: ({ signal }) => api.publicaciones({ marca: marcaActiva ?? undefined }, signal),
  });

  // El backend ya acota por la marca activa (o devuelve todo en la vista "Todas" de admin).
  const piezas = React.useMemo(
    () => feedQuery.data?.publicaciones ?? [],
    [feedQuery.data],
  );

  // Conteo por pestaña (sobre el listado ya acotado por marca) para el badge de cada tab.
  const conteos = React.useMemo(
    () =>
      Object.fromEntries(VISTAS.map((v) => [v.id, piezas.filter(v.filtra).length])) as Record<
        Vista,
        number
      >,
    [piezas],
  );
  const vistaActual = VISTAS.find((v) => v.id === vista) ?? VISTAS[0];
  const piezasVista = React.useMemo(
    () => piezas.filter(vistaActual.filtra),
    [piezas, vistaActual],
  );

  const refrescar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });

  return (
    <div>
      <PageHeader
        titulo="Feed de ideación"
        descripcion="Una sola línea por fecha: la IA genera y verifica, tú das tu OK en línea, y la pieza sigue a programada y publicada."
        acciones={
          <Button
            variant="outline"
            size="sm"
            onClick={refrescar}
            disabled={feedQuery.isFetching}
          >
            <RefreshCw className={feedQuery.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            Refrescar
          </Button>
        }
      />

      {/* Pestañas: vistas del MISMO feed (la marca la fija el switch global de la
          topbar). Las pestañas no hacen otra llamada: filtran en cliente lo ya cargado. */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex gap-1" role="tablist" aria-label="Vista del feed">
          {VISTAS.map((v) => (
            <button
              key={v.id}
              type="button"
              role="tab"
              aria-selected={vista === v.id}
              onClick={() => setVista(v.id)}
              className={
                vista === v.id
                  ? "inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1 text-sm font-medium text-primary-foreground"
                  : "inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-sm text-muted-foreground transition-colors hover:bg-muted"
              }
            >
              {v.etiqueta}
              <span
                className={
                  vista === v.id
                    ? "rounded-full bg-primary-foreground/20 px-1.5 text-xs tabular-nums"
                    : "rounded-full bg-muted px-1.5 text-xs tabular-nums"
                }
              >
                {conteos[v.id]}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Columna del feed (centrada, lectura cómoda). */}
      <div className="mx-auto w-full max-w-2xl space-y-4">
        {feedQuery.isLoading ? (
          [0, 1, 2].map((i) => <Skeleton key={i} className="h-80 w-full rounded-xl" />)
        ) : feedQuery.isError ? (
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6 text-center text-sm text-destructive">
            No se pudo cargar el feed. {mensajeError(feedQuery.error)}
          </div>
        ) : piezasVista.length === 0 ? (
          <EstadoVacio titulo={vistaActual.vacio.titulo} texto={vistaActual.vacio.texto} />
        ) : (
          piezasVista.map((p) => <PostFeed key={p.id} publicacion={p} />)
        )}
      </div>
    </div>
  );
}
