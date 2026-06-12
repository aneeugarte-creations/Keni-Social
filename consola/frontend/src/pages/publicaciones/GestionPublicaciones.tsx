import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Send } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { FILTRO_TODOS, useFiltrosContenido } from "@/hooks/filtros-contenido-contexto";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import { DialogoDuplicar } from "@/pages/publicaciones/DialogoDuplicar";
import { DialogoEditar } from "@/pages/publicaciones/DialogoEditar";
import { VistaCalendario } from "@/pages/publicaciones/VistaCalendario";
import { VistaLista } from "@/pages/publicaciones/VistaLista";
import type { OpcionesPublicaciones, Publicacion } from "@/types";

const TAM_PAGINA = 30;

// REPARTO ("la lista"): el flujo de coger/soltar tareas es del piloto de ClaroSports;
// las demás marcas siguen su flujo de siempre (sin chips ni botón de coger).
const MARCA_REPARTO = "claro-sports";

/** Lente del reparto: todas las piezas, solo las LIBRES (por coger) o solo las MÍAS. */
export type FiltroReparto = "todas" | "libres" | "mias";

const ETIQUETA_REPARTO: Record<FiltroReparto, string> = {
  todas: "Todas",
  libres: "Por coger",
  mias: "Mis tareas",
};

/**
 * Filtro `responsable` que corresponde a una lente del reparto: "todas" no filtra,
 * "libres" pide las piezas SIN responsable (centinela `"sin"` del backend) y "mias"
 * filtra por el id del usuario de la sesión (sin sesión no puede filtrar: no filtra).
 * Pura y exportada para testearla sin montar el componente.
 */
export function responsableDeLente(
  reparto: FiltroReparto,
  usuarioId: string | null,
): string | undefined {
  if (reparto === "libres") return "sin";
  if (reparto === "mias") return usuarioId ?? undefined;
  return undefined;
}

/**
 * ¿Avisar de que el usuario no tiene marca asignada? Solo no-admins con la lista de
 * marcas CONOCIDA y vacía. OJO: `marcas` solo viaja en GET /auth/me; el login devuelve
 * la forma mínima SIN esa clave, así que `undefined` = "aún no lo sé" (sesión recién
 * creada), NO "sin marcas" — sin esta distinción todo editor veía el falso aviso
 * durante toda su sesión tras iniciarla. Pura y exportada para testearla sin montar.
 */
export function faltaMarcaAsignada(
  usuario: { rol: string; marcas?: string[] } | null,
): boolean {
  return (
    usuario !== null &&
    usuario.rol !== "admin" &&
    usuario.marcas !== undefined &&
    usuario.marcas.length === 0
  );
}

/**
 * Refresco por-query mientras la lente del reparto está activa: el tablero es COMPARTIDO
 * en vivo (los claims de los compañeros cambian lo que ves), así que no podemos quedarnos
 * con los defaults globales de main.tsx (staleTime 30s, sin refetch al volver a la
 * pestaña). Solo aplica con `repartoActivo`; el resto de marcas no paga el sondeo.
 */
const REFRESCO_REPARTO = {
  refetchInterval: 45_000,
  refetchOnWindowFocus: true,
} as const;

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
      calendario={calendario}
      opciones={opcionesQuery.data}
      marcaActiva={marcaActiva}
      onConfigurarCadencia={onConfigurarCadencia}
    />
  );
}

function Cuerpo({
  calendario,
  opciones,
  marcaActiva,
  onConfigurarCadencia,
}: {
  calendario: boolean;
  opciones: OpcionesPublicaciones;
  marcaActiva: string | null;
  onConfigurarCadencia?: () => void;
}) {
  // RED y LÍNEA las mandan los selectores GLOBALES de la topbar (la elegibilidad de
  // línea por marca y su reseteo viven en el provider). La MARCA, el switch de marca.
  const { red, linea } = useFiltrosContenido();
  const [editando, setEditando] = React.useState<Publicacion | null>(null);
  const [duplicando, setDuplicando] = React.useState<Publicacion | null>(null);

  // REPARTO ("la lista" de ClaroSports): lente Todas / Por coger / Mis tareas sobre el
  // responsable del `contenido` padre. Solo con la marca del piloto activa; "mias" exige
  // sesión (el contexto puede ser null en tests: useContext directo, sin throw).
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const repartoActivo = marcaActiva === MARCA_REPARTO;
  const [reparto, setReparto] = React.useState<FiltroReparto>("todas");
  const responsable = repartoActivo
    ? responsableDeLente(reparto, usuario?.id ?? null)
    : undefined;

  // Usuario (no admin) sin marca asignada: cae a la vista agregada sin saber por qué.
  // Lo avisamos suave: el arreglo es de datos (un admin le asigna su marca en Usuarios).
  const sinMarcaAsignada = faltaMarcaAsignada(usuario);

  const filtrosBase = {
    marca: marcaActiva ?? undefined,
    red: red === FILTRO_TODOS ? undefined : red,
    linea: linea === FILTRO_TODOS ? undefined : linea,
    responsable,
  };

  // CALENDARIO: rejilla mensual; necesita el conjunto completo (sin paginar).
  const calendarioQuery = useQuery({
    queryKey: [
      ...CLAVE_PUBLICACIONES,
      "calendario",
      filtrosBase.marca ?? "",
      filtrosBase.red ?? "",
      filtrosBase.linea ?? "",
      responsable ?? "",
    ],
    queryFn: ({ signal }) => api.publicaciones(filtrosBase, signal),
    enabled: calendario,
    // REPARTO: ver en vivo los claims de los compañeros (sin tocar defaults globales).
    ...(repartoActivo ? REFRESCO_REPARTO : {}),
  });

  // LISTA: paginación KEYSET (modo `feed` del backend). Cada página devuelve
  // `paginacion.cursor_siguiente` y la siguiente se pide con `cursor=` desde la última fila
  // vista. El offset (`limite`+`desplazamiento`) saltaba piezas cuando el conjunto encogía
  // en vivo (lente "Por coger" + claims de compañeros); el cursor es inmune a eso.
  // `paginacion.total` sigue llegando para el "Mostrando X de Y". Cambiar los filtros
  // cambia la queryKey, que resetea las páginas sola.
  const listaQuery = useInfiniteQuery({
    queryKey: [
      ...CLAVE_PUBLICACIONES,
      "lista",
      filtrosBase.marca ?? "",
      filtrosBase.red ?? "",
      filtrosBase.linea ?? "",
      responsable ?? "",
    ],
    // Primera página: sin cursor (pero con `feed: "1"` para activar el modo keyset).
    initialPageParam: "",
    queryFn: ({ pageParam, signal }) =>
      api.publicaciones(
        {
          ...filtrosBase,
          feed: "1",
          limite: String(TAM_PAGINA),
          cursor: pageParam || undefined,
        },
        signal,
      ),
    // El backend OMITE `cursor_siguiente` en la última página: undefined = no hay más.
    getNextPageParam: (ultima, paginas) => {
      // El backend emite cursor cuando la página viene LLENA, incluida la última si el
      // total es múltiplo exacto: con el total fresco ya cubierto no hay más que pedir
      // (evita el "Cargar más" fantasma junto a "Mostrando 30 de 30").
      const cargadas = paginas.reduce((n, p) => n + p.publicaciones.length, 0);
      const total = ultima.paginacion?.total;
      if (total != null && cargadas >= total) return undefined;
      return ultima.paginacion?.cursor_siguiente || undefined;
    },
    enabled: !calendario,
    // REPARTO: ver en vivo los claims de los compañeros (sin tocar defaults globales).
    ...(repartoActivo ? REFRESCO_REPARTO : {}),
  });

  const query = calendario ? calendarioQuery : listaQuery;
  const publicaciones = React.useMemo(
    () =>
      calendario
        ? calendarioQuery.data?.publicaciones ?? []
        : (listaQuery.data?.pages ?? []).flatMap((p) => p.publicaciones),
    [calendario, calendarioQuery.data, listaQuery.data],
  );
  const total = calendario
    ? publicaciones.length
    : listaQuery.data?.pages.at(-1)?.paginacion?.total ?? publicaciones.length;
  const hayMas = !calendario && Boolean(listaQuery.hasNextPage);
  const filtrando =
    red !== FILTRO_TODOS || linea !== FILTRO_TODOS || responsable !== undefined;

  // Aviso de seguridad: si el posteo real esta APAGADO y hay piezas programadas, NO van a
  // salir solas (el programador opera en dry-run). Es justo el fallo que dejaba piezas sin
  // publicar en silencio; lo hacemos visible.
  const hayProgramadasSinSalir =
    !opciones.publicar_real && publicaciones.some((p) => p.estado === "programado");

  return (
    <div className="mt-2">
      {sinMarcaAsignada && (
        <div className="mb-3 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          No tienes marca asignada: pide a un admin que te asigne tu marca en Usuarios para
          ver tu espacio de trabajo.
        </div>
      )}
      {repartoActivo && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="inline-flex overflow-hidden rounded-md border border-border">
            {(Object.keys(ETIQUETA_REPARTO) as FiltroReparto[]).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setReparto(f)}
                disabled={f === "mias" && !usuario}
                className={cn(
                  "px-3 py-1 text-sm transition-colors",
                  reparto === f
                    ? "bg-primary text-primary-foreground"
                    : "bg-card text-muted-foreground hover:bg-muted",
                )}
              >
                {ETIQUETA_REPARTO[f]}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            {reparto === "libres"
              ? "Piezas que nadie ha cogido todavía: coge una y queda asignada a ti."
              : reparto === "mias"
                ? "Las piezas que has cogido tú."
                : "Coge una pieza para que el resto del equipo vea que ya la llevas tú."}
          </p>
        </div>
      )}
      {hayProgramadasSinSalir && (
        <div
          role="alert"
          className="mb-3 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-200"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            <strong>Publicación automática desactivada.</strong> Hay piezas programadas que{" "}
            <strong>no saldrán solas</strong>: con el posteo real apagado el sistema solo las
            previsualiza. Actívalo en el servidor (<code>KENI_PUBLICAR_REAL</code>) o publícalas a
            mano antes de su hora.
          </span>
        </div>
      )}
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
          titulo={filtrando ? "Sin resultados con estos filtros" : "Sin publicaciones"}
          texto={
            filtrando
              ? "Prueba a cambiar o limpiar los filtros."
              : "Vuelca material en Fuentes (cajones y clips) o crea una pieza a mano desde Contenido."
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
                onClick={() => void listaQuery.fetchNextPage()}
                disabled={listaQuery.isFetchingNextPage}
              >
                {listaQuery.isFetchingNextPage ? "Cargando…" : "Cargar más"}
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
