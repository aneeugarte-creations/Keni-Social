/**
 * FEED DE IDEACIÓN (`/parrilla/feed`) — Flujo D, Fase 4 del plan de máquina automática.
 *
 * La superficie de "red social interna": el equipo ve las piezas como POSTS (material
 * original → copy de IA → arte/formato), el ESTADO de la IA en vivo por pieza ("generando
 * copy / generando arte / lista para revisar / aprobada"), y APRUEBA en línea —como quien
 * interactúa con un post— sin abrir el kanban.
 *
 * Vive DENTRO del AppShell (a diferencia del feed móvil `/feed`, que es de una columna y sin
 * sidebar para revisores en el móvil). Aquí es una pestaña del hub Parrilla, pensada para
 * trabajar el día entero desde el feed.
 *
 * Reutiliza lo existente sin tocar backend:
 *  - `GET /api/publicaciones?estado=&marca=` para listar piezas por bandeja/marca.
 *  - `PostFeed`: cada pieza como post + aprobación en línea (forwardea a la cadena multinivel)
 *    + comentarios (`Comentarios`).
 *  - El alta de material la implementa el Flujo A (acción de alta): este feed NO la duplica.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import * as React from "react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { MARCA_TODAS, marcaParam } from "@/components/comunes/selectores";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";

import { PostFeed } from "./PostFeed";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema. Vuelve a intentarlo.";
}

/** Bandejas del feed: lo que la IA aún cocina, lo que espera tu firma, y lo ya aprobado. */
type Bandeja = "en_revision" | "borrador" | "aprobado";

const BANDEJAS: { id: Bandeja; etiqueta: string }[] = [
  { id: "en_revision", etiqueta: "Por revisar" },
  { id: "borrador", etiqueta: "En proceso" },
  { id: "aprobado", etiqueta: "Aprobadas" },
];

export default function FeedIdeacion() {
  const { usuario } = useSesion();
  const queryClient = useQueryClient();

  const [bandeja, setBandeja] = React.useState<Bandeja>("en_revision");
  const marcasUsuario = React.useMemo(() => usuario?.marcas ?? [], [usuario?.marcas]);
  const [marca, setMarca] = React.useState<string>(
    marcasUsuario.length === 1 ? marcasUsuario[0] : MARCA_TODAS,
  );

  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const catalogoMarcas = opcionesQuery.data?.marcas ?? [];
  const marcas =
    marcasUsuario.length > 0
      ? catalogoMarcas.filter((m) => marcasUsuario.includes(m.id))
      : catalogoMarcas;

  const feedQuery = useQuery({
    queryKey: [...CLAVE_PUBLICACIONES, "feed-ideacion", bandeja, marca],
    queryFn: ({ signal }) =>
      api.publicaciones({ estado: bandeja, marca: marcaParam(marca) }, signal),
  });

  // Si el usuario tiene marcas y el filtro está en "todas", acota a sus marcas en cliente.
  const piezas = React.useMemo(() => {
    const todas = feedQuery.data?.publicaciones ?? [];
    if (marca === MARCA_TODAS && marcasUsuario.length > 0) {
      return todas.filter((p) => marcasUsuario.includes(p.marca));
    }
    return todas;
  }, [feedQuery.data, marca, marcasUsuario]);

  const refrescar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });

  return (
    <div>
      <PageHeader
        titulo="Feed de ideación"
        descripcion="El equipo postea material; la IA lo convierte en piezas y tú apruebas en línea."
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

      {/* Filtros: bandeja + marca. */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex gap-1" role="tablist" aria-label="Bandeja">
          {BANDEJAS.map((b) => (
            <button
              key={b.id}
              type="button"
              role="tab"
              aria-selected={bandeja === b.id}
              onClick={() => setBandeja(b.id)}
              className={
                bandeja === b.id
                  ? "rounded-full bg-primary px-3 py-1 text-sm font-medium text-primary-foreground"
                  : "rounded-full border border-border px-3 py-1 text-sm text-muted-foreground transition-colors hover:bg-muted"
              }
            >
              {b.etiqueta}
            </button>
          ))}
        </div>
        <SelectorMarca
          marcas={marcas}
          valor={marca}
          onCambio={setMarca}
          incluirTodas
          etiquetaTodas={marcasUsuario.length > 0 ? "Todas mis marcas" : "Todas las marcas"}
          className="w-auto min-w-48"
        />
      </div>

      {/* Columna del feed (centrada, lectura cómoda). */}
      <div className="mx-auto w-full max-w-2xl space-y-4">
        {feedQuery.isLoading ? (
          [0, 1, 2].map((i) => <Skeleton key={i} className="h-80 w-full rounded-xl" />)
        ) : feedQuery.isError ? (
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6 text-center text-sm text-destructive">
            No se pudo cargar el feed. {mensajeError(feedQuery.error)}
          </div>
        ) : piezas.length === 0 ? (
          <EstadoVacio
            titulo={
              bandeja === "en_revision"
                ? "Nada por revisar"
                : bandeja === "borrador"
                  ? "Nada en proceso"
                  : "Sin piezas aprobadas"
            }
            texto={
              bandeja === "en_revision"
                ? "Cuando la IA deje piezas listas, aparecerán aquí para tu visto bueno."
                : bandeja === "borrador"
                  ? "El equipo postea material y la IA lo procesa; las piezas en curso saldrán aquí."
                  : "Las piezas que apruebes se mostrarán en esta bandeja."
            }
          />
        ) : (
          piezas.map((p) => <PostFeed key={p.id} publicacion={p} />)
        )}
      </div>
    </div>
  );
}
