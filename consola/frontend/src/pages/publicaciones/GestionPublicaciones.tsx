import { useQuery } from "@tanstack/react-query";
import { Send } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { FILTRO_TODOS, useFiltrosContenido } from "@/hooks/filtros-contenido-contexto";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import { DialogoDuplicar } from "@/pages/publicaciones/DialogoDuplicar";
import { DialogoEditar } from "@/pages/publicaciones/DialogoEditar";
import { VistaCalendario } from "@/pages/publicaciones/VistaCalendario";
import { VistaLista } from "@/pages/publicaciones/VistaLista";
import type { OpcionesPublicaciones, Publicacion } from "@/types";

const TAM_PAGINA = 30;

/**
 * GESTIÓN de publicaciones en dos modos: `lista` (paginada, con duplicar/editar) y
 * `calendario` (rejilla mensual de programadas, sin paginación ni filtro de estado).
 *
 * Lee `/api/publicaciones` (misma BD que `/api/contenido`: una publicación ES una fila
 * `contenido_plataforma` de un `contenido`) y reutiliza el editor rico
 * (`VistaLista`/`VistaCalendario`/`DialogoEditar`/`DialogoDuplicar`).
 *
 * MARCA, RED y LÍNEA editorial vienen TODAS de los selectores GLOBALES de la barra
 * superior (`useMarcaActiva` + `useFiltrosContenido`); esta página ya no tiene
 * dropdowns de filtro propios.
 */
export function GestionPublicaciones({
  modo,
  onConfigurarCadencia,
}: {
  modo: "lista" | "calendario";
  onConfigurarCadencia?: () => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const calendario = modo === "calendario";

  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });

  if (opcionesQuery.isPending) {
    return (
      <div className="mt-4 space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (opcionesQuery.isError) {
    return (
      <BloqueError
        titulo="No se pudieron cargar las publicaciones"
        mensaje={mensajeError(opcionesQuery.error)}
        onReintentar={() => void opcionesQuery.refetch()}
        cargando={opcionesQuery.isFetching}
      />
    );
  }

  return (
    <Cuerpo
      modo={modo}
      calendario={calendario}
      opciones={opcionesQuery.data}
      marcaActiva={marcaActiva}
      onConfigurarCadencia={onConfigurarCadencia}
    />
  );
}

function Cuerpo({
  modo,
  calendario,
  opciones,
  marcaActiva,
  onConfigurarCadencia,
}: {
  modo: "lista" | "calendario";
  calendario: boolean;
  opciones: OpcionesPublicaciones;
  marcaActiva: string | null;
  onConfigurarCadencia?: () => void;
}) {
  // RED y LÍNEA las mandan los selectores GLOBALES de la topbar (la elegibilidad de
  // línea por marca y su reseteo viven en el provider). La MARCA, el switch de marca.
  const { red, linea } = useFiltrosContenido();
  const [paginas, setPaginas] = React.useState(1);
  const [editando, setEditando] = React.useState<Publicacion | null>(null);
  const [duplicando, setDuplicando] = React.useState<Publicacion | null>(null);

  const limite = calendario ? undefined : paginas * TAM_PAGINA;

  const filtros = {
    marca: marcaActiva ?? undefined,
    red: red === FILTRO_TODOS ? undefined : red,
    linea: linea === FILTRO_TODOS ? undefined : linea,
    limite: limite != null ? String(limite) : undefined,
    desplazamiento: undefined,
  };

  React.useEffect(() => {
    setPaginas(1);
  }, [marcaActiva, red, linea, modo]);

  const query = useQuery({
    queryKey: [
      ...CLAVE_PUBLICACIONES,
      "lista",
      filtros.marca ?? "",
      filtros.red ?? "",
      filtros.linea ?? "",
      filtros.limite ?? "",
    ],
    queryFn: ({ signal }) => api.publicaciones(filtros, signal),
  });

  const publicaciones = query.data?.publicaciones ?? [];
  const total = query.data?.paginacion?.total ?? publicaciones.length;
  const hayMas = !calendario && publicaciones.length < total;
  const filtrando = red !== FILTRO_TODOS || linea !== FILTRO_TODOS;

  return (
    <div className="mt-2">
      {query.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudieron cargar las publicaciones"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : calendario ? (
        <VistaCalendario publicaciones={publicaciones} onEditar={setEditando} marca={marcaActiva} />
      ) : publicaciones.length === 0 ? (
        <EstadoVacio
          icono={Send}
          titulo={filtrando ? "Sin resultados con estos filtros" : "Aún no hay publicaciones"}
          texto={
            filtrando
              ? "Prueba a cambiar o limpiar los filtros."
              : "Genera un copy y guárdalo como publicación, o créalo desde el contenido."
          }
        />
      ) : (
        <>
          <VistaLista
            publicaciones={publicaciones}
            onEditar={setEditando}
            onDuplicar={setDuplicando}
            onConfigurarCadencia={onConfigurarCadencia ?? (() => {})}
          />
          {hayMas && (
            <div className="mt-4 flex flex-col items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPaginas((p) => p + 1)}
                disabled={query.isFetching}
              >
                {query.isFetching ? "Cargando…" : "Cargar más"}
              </Button>
              <p className="text-xs text-muted-foreground">
                Mostrando {publicaciones.length} de {total}
              </p>
            </div>
          )}
        </>
      )}

      <DialogoEditar
        publicacion={editando}
        onCerrar={() => setEditando(null)}
      />
      <DialogoDuplicar
        publicacion={duplicando}
        marcas={opciones.marcas}
        redes={opciones.redes}
        onCerrar={() => setDuplicando(null)}
      />
    </div>
  );
}
