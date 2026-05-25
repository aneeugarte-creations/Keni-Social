import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  CalendarDays,
  FileText,
  Hash,
  List,
  Send,
  Sparkles,
} from "lucide-react";
import * as React from "react";
import { Link, useLocation } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError } from "@/lib/api";
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
  const location = useLocation();

  // Marca preseleccionada al llegar desde otra página (p. ej. «Ver
  // publicaciones» desde el detalle de un agente). El id canónico viaja por
  // `?marca=`; solo lo aceptamos si existe en el catálogo, si no, "Todas".
  const marcaInicial = React.useMemo(() => {
    const desdeQuery = new URLSearchParams(location.search).get("marca") ?? undefined;
    return desdeQuery && opciones.marcas.some((m) => m.id === desdeQuery)
      ? desdeQuery
      : FILTRO_TODOS;
    // Solo al montar (la query no cambia dentro de esta página).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [vista, setVista] = React.useState<Vista>("lista");
  const [marca, setMarca] = React.useState(marcaInicial);
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

  const acciones = (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
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
      <div className="flex items-center gap-2">
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
    </div>
  );

  const publicaciones = query.data?.publicaciones ?? [];
  const filtrando =
    marca !== FILTRO_TODOS || red !== FILTRO_TODOS || estado !== FILTRO_TODOS || soloPerennes;

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
        <EstadoVacio
          icono={Send}
          titulo={filtrando ? "Sin resultados con estos filtros" : "Aún no hay publicaciones"}
          texto={
            filtrando
              ? "Prueba a cambiar o limpiar los filtros."
              : "Genera un copy y guárdalo como publicación para empezar a gestionarlo aquí."
          }
          accion={
            !filtrando && (
              <Button asChild size="sm">
                <Link to="/generar-copy">
                  <Sparkles className="h-4 w-4" />
                  Generar copy
                </Link>
              </Button>
            )
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
