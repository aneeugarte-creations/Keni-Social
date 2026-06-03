/**
 * FEED DE IDEACIÓN (`/parrilla/feed`) — Flujo D, Fase 4 del plan de máquina automática.
 *
 * La superficie de "red social interna": el equipo ve las piezas como POSTS (copy de IA +
 * arte/formato), con un LABEL de su etapa en la tubería, y APRUEBA en línea —como quien
 * interactúa con un post— sin abrir el kanban.
 *
 * UNA SOLA LÍNEA, sin bandejas: el flujo no se separa por estado (autogeneración → auto QA →
 * tu OK → programada → publicada), va todo mezclado y ordenado por fecha (lo más reciente
 * primero). No hay tabs "por revisar / en proceso / aprobadas": la etapa la dice el label de
 * cada pieza, y el OK aparece en línea solo cuando te toca.
 *
 * Vive DENTRO del AppShell (a diferencia del feed móvil `/feed`, que es de una columna y sin
 * sidebar para revisores en el móvil). Aquí es una pestaña del hub Parrilla, pensada para
 * trabajar el día entero desde el feed.
 *
 * Reutiliza lo existente sin tocar backend:
 *  - `GET /api/publicaciones?marca=` (sin `estado`) para listar TODAS las piezas por fecha.
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

export default function FeedIdeacion() {
  const { usuario } = useSesion();
  const queryClient = useQueryClient();

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

  // UN solo feed, TODAS las etapas mezcladas y ordenadas por fecha (el backend devuelve
  // `creado DESC` cuando no se filtra estado). El flujo es una sola línea —autogeneración →
  // auto QA → tu OK (2 likes) → programada/publicada—, no bandejas que separen las etapas:
  // cada pieza enseña en qué va con su label de etapa y, si te toca, su OK en línea.
  const feedQuery = useQuery({
    queryKey: [...CLAVE_PUBLICACIONES, "feed-ideacion", marca],
    queryFn: ({ signal }) => api.publicaciones({ marca: marcaParam(marca) }, signal),
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

      {/* Filtro: solo marca. El feed NO separa por etapa (no es bandejas): todas las piezas
          van en una línea por fecha, cada una con su label de etapa. */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
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
            titulo="El feed está vacío"
            texto="El equipo postea material y la IA lo convierte en piezas; aparecerán aquí, las más recientes primero, y aprobarás en línea cuando alguna esté lista."
          />
        ) : (
          piezas.map((p) => <PostFeed key={p.id} publicacion={p} />)
        )}
      </div>
    </div>
  );
}
