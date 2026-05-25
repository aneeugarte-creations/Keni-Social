import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CalendarClock,
  CalendarDays,
  FileText,
  Hash,
  List,
  RefreshCw,
  Send,
} from "lucide-react";
import * as React from "react";

import { EstadoMensaje } from "@/components/layout/EstadoMensaje";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { OpcionesPublicaciones, Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./publicaciones/claves";
import { DialogoDuplicar } from "./publicaciones/DialogoDuplicar";
import { DialogoEditar } from "./publicaciones/DialogoEditar";
import { FILTRO_TODOS, FiltrosPublicaciones } from "./publicaciones/Filtros";
import { GestionFranjas } from "./publicaciones/GestionFranjas";
import { GestionHashtags } from "./publicaciones/GestionHashtags";
import { GestionPlantillas } from "./publicaciones/GestionPlantillas";
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
    <EstadoMensaje
      icono={AlertCircle}
      titulo={titulo}
      mensaje={mensaje ?? "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento."}
      accion={
        <Button variant="outline" size="sm" onClick={onReintentar} disabled={cargando}>
          <RefreshCw className={cn("h-4 w-4", cargando && "animate-spin")} />
          Reintentar
        </Button>
      }
    />
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
  const [soloPerennes, setSoloPerennes] = React.useState(false);
  const [editando, setEditando] = React.useState<Publicacion | null>(null);
  const [duplicando, setDuplicando] = React.useState<Publicacion | null>(null);
  const [gestionFranjas, setGestionFranjas] = React.useState(false);
  const [gestionHashtags, setGestionHashtags] = React.useState(false);
  const [gestionPlantillas, setGestionPlantillas] = React.useState(false);

  const filtros = {
    marca: marca === FILTRO_TODOS ? undefined : marca,
    red: red === FILTRO_TODOS ? undefined : red,
    // En vista calendario ignoramos el filtro de estado (solo programadas).
    estado: vista === "calendario" || estado === FILTRO_TODOS ? undefined : estado,
    evergreen: soloPerennes ? "1" : undefined,
  };

  const query = useQuery({
    queryKey: [
      ...CLAVE_PUBLICACIONES,
      "lista",
      filtros.marca ?? "",
      filtros.red ?? "",
      filtros.estado ?? "",
      filtros.evergreen ?? "",
    ],
    queryFn: ({ signal }) => api.publicaciones(filtros, signal),
  });

  // En la cabecera, junto al titulo: solo las acciones de gestion de la pagina.
  const acciones = (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={() => setGestionPlantillas(true)}
        title="Gestionar plantillas de post"
      >
        <FileText className="h-4 w-4" />
        Plantillas
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setGestionHashtags(true)}
        title="Gestionar grupos de hashtags"
      >
        <Hash className="h-4 w-4" />
        Hashtags
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setGestionFranjas(true)}
        title="Gestionar franjas de la cola"
      >
        <CalendarClock className="h-4 w-4" />
        Franjas
      </Button>
    </div>
  );

  // Barra de herramientas sobre el contenido: filtros a la izquierda y el
  // selector de vista (Lista/Calendario) a la derecha, junto a lo que controla.
  const barraHerramientas = (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <FiltrosPublicaciones
        opciones={opciones}
        marca={marca}
        red={red}
        estado={estado}
        soloPerennes={soloPerennes}
        onMarca={setMarca}
        onRed={setRed}
        onEstado={setEstado}
        onSoloPerennes={setSoloPerennes}
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
  const filtrando =
    marca !== FILTRO_TODOS || red !== FILTRO_TODOS || estado !== FILTRO_TODOS || soloPerennes;

  return (
    <>
      <PageHeader {...CABECERA} acciones={acciones} />

      {barraHerramientas}

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
        <EstadoMensaje
          icono={Send}
          titulo={filtrando ? "Sin resultados con estos filtros" : "Aún no hay publicaciones"}
          mensaje={
            filtrando
              ? "Prueba a cambiar o limpiar los filtros."
              : "Genera un copy y guárdalo como publicación para empezar a gestionarlo aquí."
          }
        />
      ) : (
        <VistaLista
          publicaciones={publicaciones}
          onEditar={setEditando}
          onDuplicar={setDuplicando}
          onGestionarFranjas={() => setGestionFranjas(true)}
        />
      )}

      <DialogoEditar
        publicacion={editando}
        estados={opciones.estados}
        onCerrar={() => setEditando(null)}
      />

      <DialogoDuplicar
        publicacion={duplicando}
        marcas={opciones.marcas}
        redes={opciones.redes}
        onCerrar={() => setDuplicando(null)}
      />

      <GestionFranjas
        abierto={gestionFranjas}
        onCerrar={() => setGestionFranjas(false)}
        marcas={opciones.marcas}
        redes={opciones.redes}
      />

      <GestionHashtags
        abierto={gestionHashtags}
        onCerrar={() => setGestionHashtags(false)}
        marcas={opciones.marcas}
      />

      <GestionPlantillas
        abierto={gestionPlantillas}
        onCerrar={() => setGestionPlantillas(false)}
        marcas={opciones.marcas}
        redes={opciones.redes}
      />
    </>
  );
}
