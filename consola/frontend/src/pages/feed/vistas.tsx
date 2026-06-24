/**
 * PARTICIÓN DE VISTAS del feed, COMPARTIDA por las dos superficies (escritorio
 * `FeedIdeacion` y móvil `MobileFeed`): las 3 pestañas que particionan el ciclo por ESTADO,
 * el mapeo vista→estado del servidor, los topes de la búsqueda encadenada, los CONTEOS
 * exactos de los badges y el contenido del propio trigger de pestaña. Un solo sitio para
 * que ambas superficies enseñen el MISMO trabajo con el MISMO vocabulario.
 */
import { useQuery } from "@tanstack/react-query";
import { Clock, LayoutGrid, Send, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { FILTRO_TODOS } from "@/hooks/filtros-contenido-contexto";
import { MARCA_ACTIVA_TODAS } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { plural } from "@/lib/formato";
import { cn } from "@/lib/utils";
import { CLAVE_PIEZAS } from "@/pages/piezas/claves";
import type { Pieza } from "@/types";

// Tope de la búsqueda encadenada de la vista filtrada EN CLIENTE vacía ("Aprobadas y
// publicadas"): cada "lote" permite traer hasta N páginas más antes de parar y ofrecer
// "Seguir buscando".
export const PAGINAS_POR_LOTE = 5;
// Tope del deep-link `?pieza=`: páginas máximas que se encadenan buscando la idea enlazada
// antes de renunciar (y avisar), para no descargar el feed entero persiguiendo un enlace viejo.
export const TOPE_PAGINAS_PIEZA = 3 * PAGINAS_POR_LOTE;

// CANAL «Portal»: el origen de los auto-producidos de fuente propia (cross-marca). El clon
// Portal del feed pide `origen=ORIGEN_PORTAL`; el feed normal pide `excluir_origen=ORIGEN_PORTAL`
// para mantenerse INDEPENDIENTE de ese canal. La Lista no usa ninguno (ve todos los orígenes).
export const ORIGEN_PORTAL = "portal";

/**
 * Pestañas del feed: una PARTICIÓN BINARIA del ciclo por ESTADO, con "Todas" como unión.
 * "Pendientes" es TODO lo que aún no salió (cualquier estado salvo `publicado`: borrador,
 * en_revision, programado); "Publicadas" es exactamente lo `publicado`. Ambas van
 * con consulta DEDICADA al servidor (pseudo-estados `pendiente`/`publicado`, ver
 * `ESTADO_SERVIDOR_DE_VISTA`), así la paginación y los totales son exactos en las dos
 * superficies (feed por keyset y lista por offset). `filtra` repite la misma regla en cliente
 * (idempotente sobre la consulta ya filtrada). `etiquetaCorta` es el texto visible en <sm (un
 * sr-only conserva el completo). El ORDEN de este array ES el orden de las pestañas:
 * Pendientes · Publicadas · Todas.
 *
 * NO hay pestaña «En preparación»: «borrador» dejó de ser un estado donde descanse una pieza
 * —el pipeline mueve sola toda pieza completa a la cola de revisión—, así que los borradores
 * son transitorios y caen en "Pendientes" (no son `publicado`) mientras existen.
 */
export type Vista = "pendiente" | "publicado" | "todo";

export interface VistaFeed {
  id: Vista;
  // Vocabulario en FEMENINO donde se nombra a la pieza ("Pendientes", "Publicadas", "Todas"):
  // la unidad del feed es LA pieza (regla documentada en `etapa.ts`).
  etiqueta: string;
  /** Etiqueta corta EXPLÍCITA para <sm: las 3 pestañas caben en una fila a 320px. */
  etiquetaCorta: string;
  icono: LucideIcon;
  filtra: (p: Pieza) => boolean;
  vacio: { titulo: string; texto: string };
}

export const VISTAS: VistaFeed[] = [
  {
    id: "pendiente",
    etiqueta: "Pendientes",
    etiquetaCorta: "Pendientes",
    icono: Clock,
    // Pendiente = TODO lo que aún no salió: cualquier estado que no sea `publicado`
    // (borrador, en_revision, programado). El servidor ya filtra igual.
    filtra: (p) => p.estado !== "publicado",
    vacio: {
      titulo: "Nada pendiente",
      texto: "No hay piezas en cola; todo lo del equipo ya salió.",
    },
  },
  {
    id: "publicado",
    etiqueta: "Publicadas",
    etiquetaCorta: "Publicadas",
    icono: Send,
    filtra: (p) => p.estado === "publicado",
    vacio: {
      titulo: "Sin piezas publicadas",
      texto: "",
    },
  },
  {
    id: "todo",
    etiqueta: "Todas",
    etiquetaCorta: "Todas",
    icono: LayoutGrid,
    filtra: () => true,
    vacio: {
      titulo: "El feed está vacío",
      texto: "Esperando piezas del equipo.",
    },
  },
];

/**
 * Vista válida desde la URL (`?vista=`); ausente o desconocida → `porDefecto` ("todo" en
 * escritorio; el móvil arranca en "pendiente", su trabajo).
 */
export function vistaDesdeParam(v: string | null, porDefecto: Vista = "todo"): Vista {
  return VISTAS.some((x) => x.id === v) ? (v as Vista) : porDefecto;
}

/**
 * CONSULTA DEDICADA por estado: el SERVIDOR filtra las dos vistas de partición vía
 * pseudo-estados (`?estado=pendiente` = todo lo no publicado; `?estado=publicado` = lo
 * publicado). "Todas" va sin `estado` (listado base). Así cada vista paginada (keyset del
 * feed y offset de la lista) trae solo SUS filas y el `total` es exacto, sin filtrar en
 * cliente listas enteras.
 */
export const ESTADO_SERVIDOR_DE_VISTA: Record<Vista, "pendiente" | "publicado" | undefined> = {
  pendiente: "pendiente",
  publicado: "publicado",
  todo: undefined,
};

/**
 * CONTEOS para los badges de las pestañas: el total EXACTO del servidor con cualquier filtro
 * (`limite=1` activa el modo offset: 1 fila + `paginacion.total`). Tres consultas ligeras:
 * pendiente / publicado / en_revision. "Todas" es la SUMA exacta (pendiente + publicado), así
 * que no se gasta una cuarta consulta. `totalRevision` no tiene pestaña propia (cae dentro de
 * "Pendientes") pero alimenta el ÉNFASIS de "Pendientes" (el "te toca decidir": hay algo
 * realmente esperando aprobación). Se cuentan PIEZAS (la unidad canónica del hub), no ideas.
 *
 * `filtros` lleva los parámetros YA resueltos para la query (ausente = sin filtro); la clave
 * usa los mismos centinelas que las claves históricas de `FeedIdeacion` (caché compartida).
 * `origen` acota TODOS los conteos al canal de la superficie (el Portal pasa `"portal"`), así
 * sus badges cuentan SOLO sus piezas; `excluirOrigen` hace lo INVERSO (el feed normal pasa
 * `"portal"` para no contar ese canal). La Lista omite ambos (cuenta todos los orígenes).
 */
export function useConteosFeed(filtros: {
  marca?: string;
  red?: string;
  linea?: string;
  busqueda?: string;
  categoria?: string;
  responsable?: string;
  origen?: string;
  excluirOrigen?: string;
  enVivo?: boolean;
}): {
  totalRevision: number | undefined;
  conteoVista: Record<Vista, number | undefined>;
} {
  // `responsable` (lente del reparto "la lista"): cuando está activa, la Lista filtra por
  // ella, así que los badges deben contar lo MISMO que se lista (si no, el número no cuadra
  // con las filas). Ausente en los demás feeds (MobileFeed/FeedIdeacion): sin efecto.
  const { marca, red, linea, busqueda, categoria, responsable, origen, excluirOrigen, enVivo } = filtros;
  // `enVivo` (tablero COMPARTIDO del reparto): los conteos laten al MISMO pulso que la lista
  // y el calendario (que ya tienen refetchInterval+refetchOnWindowFocus), para que tras el
  // claim de un compañero el badge no quede rancio mientras la lista ya cambió.
  const refrescoEnVivo = enVivo
    ? { refetchInterval: 45_000, refetchOnWindowFocus: true }
    : {};
  const claveConteo = (estado?: string) =>
    [
      ...CLAVE_PIEZAS,
      "conteo-feed",
      marca ?? MARCA_ACTIVA_TODAS,
      red ?? FILTRO_TODOS,
      linea ?? FILTRO_TODOS,
      busqueda ?? "",
      categoria ?? "",
      responsable ?? "",
      origen ?? "",
      excluirOrigen ?? "",
      estado ?? "todos",
    ] as const;
  const conteoPendiente = useQuery({
    queryKey: claveConteo("pendiente"),
    queryFn: ({ signal }) =>
      api.piezas({ marca, red, linea, busqueda, categoria, responsable, origen, excluir_origen: excluirOrigen, estado: "pendiente", limite: "1" }, signal),
    staleTime: 30_000,
    ...refrescoEnVivo,
  });
  const conteoPublicado = useQuery({
    queryKey: claveConteo("publicado"),
    queryFn: ({ signal }) =>
      api.piezas({ marca, red, linea, busqueda, categoria, responsable, origen, excluir_origen: excluirOrigen, estado: "publicado", limite: "1" }, signal),
    staleTime: 30_000,
    ...refrescoEnVivo,
  });
  const conteoRevision = useQuery({
    queryKey: claveConteo("en_revision"),
    queryFn: ({ signal }) =>
      api.piezas({ marca, red, linea, busqueda, categoria, responsable, origen, excluir_origen: excluirOrigen, estado: "en_revision", limite: "1" }, signal),
    staleTime: 30_000,
    ...refrescoEnVivo,
  });
  const totalPendiente = conteoPendiente.data?.paginacion?.total;
  const totalPublicado = conteoPublicado.data?.paginacion?.total;
  const totalRevision = conteoRevision.data?.paginacion?.total;
  // El badge solo se pinta con su número RESUELTO (nada de parpadeos de 0 mientras carga).
  const conteoVista: Record<Vista, number | undefined> = {
    pendiente: totalPendiente,
    publicado: totalPublicado,
    todo:
      totalPendiente != null && totalPublicado != null
        ? totalPendiente + totalPublicado
        : undefined,
  };
  return { totalRevision, conteoVista };
}

/**
 * Publicacion de un `TabsTrigger` de vista (etiqueta responsive + badge de conteo), compartido
 * por las pestañas de escritorio y las móviles.
 *
 * NOMBRE ACCESIBLE compuesto desde el DOM (sin `aria-label` que pise el conteo): en <sm la
 * etiqueta corta visible va `aria-hidden` y un sr-only lleva la completa; el número del badge
 * se anuncia con su unidad ("… 3 piezas").
 *
 * Badge `outline` sobre `bg-muted`: discreto sobre el rail muted del TabsList y destacado
 * sobre el trigger activo (fondo background) — la jerarquía correcta en claro y oscuro.
 * `enfasis` (la pestaña "Pendientes" cuando hay algo realmente esperando aprobación) usa el
 * mismo acento keni del "te toca decidir" de `PostFeed`.
 */
export function PublicacionPestanaVista({
  vista,
  conteo,
  enfasis = false,
}: {
  vista: VistaFeed;
  conteo?: number;
  enfasis?: boolean;
}) {
  return (
    <>
      <span aria-hidden="true" className="sm:hidden">
        {vista.etiquetaCorta}
      </span>
      <span className="hidden sm:inline">{vista.etiqueta}</span>
      <span className="sr-only sm:hidden">{vista.etiqueta}</span>
      {conteo != null && (
        <Badge
          variant="outline"
          className={cn(
            "bg-muted px-1.5 py-0 tabular-nums",
            enfasis && "border-keni-600/30 bg-keni-600/10 text-keni-700 dark:text-keni-300",
          )}
          title={plural(conteo, "pieza")}
        >
          {conteo}
          <span className="sr-only">{conteo === 1 ? " pieza" : " piezas"}</span>
        </Badge>
      )}
    </>
  );
}
