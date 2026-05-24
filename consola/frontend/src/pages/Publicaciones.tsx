import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CalendarDays, List, RefreshCw, Send } from "lucide-react";
import * as React from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { OpcionesPublicaciones, Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./publicaciones/claves";
import { DialogoEditar } from "./publicaciones/DialogoEditar";
import { FILTRO_TODOS, FiltrosPublicaciones } from "./publicaciones/Filtros";
import { VistaCalendario } from "./publicaciones/VistaCalendario";
import { VistaLista } from "./publicaciones/VistaLista";

type Vista = "lista" | "calendario";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Bloque de error reutilizable con botón de reintento. */
function BloqueError({
  titulo,
  mensaje,
  onReintentar,
  cargando,
}: {
  titulo: string;
  mensaje?: string;
  onReintentar: () => void;
  cargando: boolean;
}) {
  return (
    <Card className="border-destructive/40">
      <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertCircle className="h-6 w-6" />
        </div>
        <div className="space-y-1">
          <p className="font-medium">{titulo}</p>
          <p className="max-w-md text-sm text-muted-foreground">
            {mensaje ?? "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento."}
          </p>
        </div>
        <Button onClick={onReintentar} disabled={cargando}>
          <RefreshCw className={cn("h-4 w-4", cargando && "animate-spin")} />
          Reintentar
        </Button>
      </CardContent>
    </Card>
  );
}

/** Esqueleto de carga (lista de tarjetas). */
function EsqueletoLista() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-24 w-full rounded-xl" />
      ))}
    </div>
  );
}

const CABECERA = {
  titulo: "Publicaciones",
  descripcion: "Gestiona tus borradores: aprueba, programa y publica por red.",
};

/**
 * Página de Publicaciones: gestión del contenido por estado.
 *
 * Carga primero las opciones (marcas, redes, estados) y luego la lista filtrada.
 * Permite alternar entre vista Lista y Calendario, editar, cambiar de estado y
 * borrar. React Query + invalidación; modo claro/oscuro; texto es-MX.
 */
export default function Publicaciones() {
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });

  if (opcionesQuery.isPending) {
    return (
      <>
        <PageHeader {...CABECERA} />
        <EsqueletoLista />
      </>
    );
  }

  if (opcionesQuery.isError) {
    return (
      <>
        <PageHeader {...CABECERA} />
        <BloqueError
          titulo="No se pudieron cargar las publicaciones"
          mensaje={mensajeError(opcionesQuery.error)}
          onReintentar={() => void opcionesQuery.refetch()}
          cargando={opcionesQuery.isFetching}
        />
      </>
    );
  }

  return <Gestion opciones={opcionesQuery.data} />;
}

/** Cuerpo de la página una vez tenemos el catálogo de opciones. */
function Gestion({ opciones }: { opciones: OpcionesPublicaciones }) {
  const [vista, setVista] = React.useState<Vista>("lista");
  const [marca, setMarca] = React.useState(FILTRO_TODOS);
  const [red, setRed] = React.useState(FILTRO_TODOS);
  const [estado, setEstado] = React.useState(FILTRO_TODOS);
  const [editando, setEditando] = React.useState<Publicacion | null>(null);

  const filtros = {
    marca: marca === FILTRO_TODOS ? undefined : marca,
    red: red === FILTRO_TODOS ? undefined : red,
    // En vista calendario ignoramos el filtro de estado (solo programadas).
    estado: vista === "calendario" || estado === FILTRO_TODOS ? undefined : estado,
  };

  const query = useQuery({
    queryKey: [...CLAVE_PUBLICACIONES, "lista", filtros.marca ?? "", filtros.red ?? "", filtros.estado ?? ""],
    queryFn: ({ signal }) => api.publicaciones(filtros, signal),
  });

  const acciones = (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <FiltrosPublicaciones
        opciones={opciones}
        marca={marca}
        red={red}
        estado={estado}
        onMarca={setMarca}
        onRed={setRed}
        onEstado={setEstado}
      />
      <Tabs value={vista} onValueChange={(v) => setVista(v as Vista)}>
        <TabsList>
          <TabsTrigger value="lista" className="gap-1.5">
            <List className="h-4 w-4" />
            Lista
          </TabsTrigger>
          <TabsTrigger value="calendario" className="gap-1.5">
            <CalendarDays className="h-4 w-4" />
            Calendario
          </TabsTrigger>
        </TabsList>
      </Tabs>
    </div>
  );

  const publicaciones = query.data?.publicaciones ?? [];
  const filtrando = marca !== FILTRO_TODOS || red !== FILTRO_TODOS || estado !== FILTRO_TODOS;

  return (
    <>
      <PageHeader {...CABECERA} acciones={acciones} />

      {query.isPending ? (
        <EsqueletoLista />
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudieron cargar las publicaciones"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : vista === "calendario" ? (
        <VistaCalendario publicaciones={publicaciones} onEditar={setEditando} />
      ) : publicaciones.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Send className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">
                {filtrando ? "Sin resultados con estos filtros" : "Aún no hay publicaciones"}
              </p>
              <p className="max-w-md text-sm text-muted-foreground">
                {filtrando
                  ? "Prueba a cambiar o limpiar los filtros."
                  : "Genera un copy y guárdalo como publicación para empezar a gestionarlo aquí."}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <VistaLista publicaciones={publicaciones} onEditar={setEditando} />
      )}

      <DialogoEditar
        publicacion={editando}
        estados={opciones.estados}
        onCerrar={() => setEditando(null)}
      />
    </>
  );
}
