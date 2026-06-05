import { useQuery } from "@tanstack/react-query";
import { Send } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, ApiError } from "@/lib/api";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import { DialogoDuplicar } from "@/pages/publicaciones/DialogoDuplicar";
import { DialogoEditar } from "@/pages/publicaciones/DialogoEditar";
import { FILTRO_TODOS } from "@/pages/publicaciones/Filtros";
import { VistaCalendario } from "@/pages/publicaciones/VistaCalendario";
import { VistaLista } from "@/pages/publicaciones/VistaLista";
import type { OpcionesPublicaciones, Publicacion } from "@/types";

const TAM_PAGINA = 30;

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/**
 * GESTIÓN de publicaciones en dos modos: `lista` (paginada, con duplicar/editar) y
 * `calendario` (rejilla mensual de programadas, sin paginación ni filtro de estado).
 *
 * Lee `/api/publicaciones` (misma BD que `/api/contenido`: una publicación ES una fila
 * `contenido_plataforma` de un `contenido`) y reutiliza el editor rico
 * (`VistaLista`/`VistaCalendario`/`DialogoEditar`/`DialogoDuplicar`).
 *
 * La MARCA viene del selector global (`useMarcaActiva`); no hay selector de marca local.
 * Los únicos filtros propios son RED y LÍNEA editorial.
 */
export function GestionPublicaciones({
  modo,
  onGestionarFranjas,
}: {
  modo: "lista" | "calendario";
  onGestionarFranjas?: () => void;
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
      onGestionarFranjas={onGestionarFranjas}
    />
  );
}

function Cuerpo({
  modo,
  calendario,
  opciones,
  marcaActiva,
  onGestionarFranjas,
}: {
  modo: "lista" | "calendario";
  calendario: boolean;
  opciones: OpcionesPublicaciones;
  marcaActiva: string | null;
  onGestionarFranjas?: () => void;
}) {
  const [red, setRed] = React.useState(FILTRO_TODOS);
  const [linea, setLinea] = React.useState(FILTRO_TODOS);
  const [paginas, setPaginas] = React.useState(1);
  const [editando, setEditando] = React.useState<Publicacion | null>(null);
  const [duplicando, setDuplicando] = React.useState<Publicacion | null>(null);

  // Líneas elegibles: las de la marca activa + las globales (marca === ""). Con marca
  // activa null (todas) se muestran todas.
  const lineasElegibles = React.useMemo(
    () =>
      opciones.lineas.filter(
        (l) => l.marca === "" || marcaActiva == null || l.marca === marcaActiva,
      ),
    [opciones.lineas, marcaActiva],
  );

  // Si la línea filtrada deja de pertenecer a la marca activa, se resetea.
  React.useEffect(() => {
    if (linea !== FILTRO_TODOS && !lineasElegibles.some((l) => l.id === linea)) {
      setLinea(FILTRO_TODOS);
    }
  }, [lineasElegibles, linea]);

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
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <SelectorRed
          redes={opciones.redes}
          valor={red}
          onCambio={setRed}
          ariaLabel="Filtrar por red"
          className="w-full sm:w-[160px]"
        />
        <Select value={linea} onValueChange={setLinea}>
          <SelectTrigger className="w-full sm:w-[200px]" aria-label="Filtrar por línea editorial">
            <SelectValue placeholder="Línea editorial" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={FILTRO_TODOS}>Todas las líneas</SelectItem>
            {lineasElegibles.map((l) => (
              <SelectItem key={l.id} value={l.id}>
                {l.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

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
            onGestionarFranjas={onGestionarFranjas ?? (() => {})}
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
