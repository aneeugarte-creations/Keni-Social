/**
 * PARTICIÓN DE VISTAS del feed, COMPARTIDA por las dos superficies (escritorio
 * `FeedIdeacion` y móvil `MobileFeed`): las 4 pestañas que particionan el ciclo por ESTADO,
 * el mapeo vista→estado del servidor, los topes de la búsqueda encadenada, los CONTEOS
 * exactos de los badges y el contenido del propio trigger de pestaña. Un solo sitio para
 * que ambas superficies enseñen el MISMO trabajo con el MISMO vocabulario.
 */
import { useQuery } from "@tanstack/react-query";
import { LayoutGrid, PencilRuler, Send, ThumbsUp, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { FILTRO_TODOS } from "@/hooks/filtros-contenido-contexto";
import { MARCA_ACTIVA_TODAS } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { plural } from "@/lib/formato";
import { cn } from "@/lib/utils";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import type { Publicacion } from "@/types";

// Tope de la búsqueda encadenada de la vista filtrada EN CLIENTE vacía ("Aprobadas y
// publicadas"): cada "lote" permite traer hasta N páginas más antes de parar y ofrecer
// "Seguir buscando".
export const PAGINAS_POR_LOTE = 5;
// Tope del deep-link `?pieza=`: páginas máximas que se encadenan buscando la idea enlazada
// antes de renunciar (y avisar), para no descargar el feed entero persiguiendo un enlace viejo.
export const TOPE_PAGINAS_PIEZA = 3 * PAGINAS_POR_LOTE;

/**
 * Pestañas del feed: una PARTICIÓN del ciclo por ESTADO (borrador → en revisión →
 * aprobado/programado/publicado); "Todo el feed" es la unión. "En preparación" y "Por aprobar"
 * mapean 1:1 a un estado y van con consulta DEDICADA (el servidor filtra); `filtra` mantiene la
 * misma regla en cliente (idempotente en las dedicadas; el filtro real de "Aprobadas y
 * publicadas"). `etiquetaCorta` es el texto visible en <sm (un sr-only conserva el completo).
 */
export type Vista = "todo" | "preparacion" | "por_aprobar" | "publicado";

export interface VistaFeed {
  id: Vista;
  // Vocabulario en FEMENINO donde se nombra a la pieza ("Aprobadas y publicadas"): la unidad
  // del feed es LA pieza (regla documentada en `etapa.ts`).
  etiqueta: string;
  /** Etiqueta corta EXPLÍCITA para <sm: las 4 pestañas caben en una fila a 320px. */
  etiquetaCorta: string;
  icono: LucideIcon;
  filtra: (p: Publicacion) => boolean;
  vacio: { titulo: string; texto: string };
}

export const VISTAS: VistaFeed[] = [
  {
    id: "todo",
    etiqueta: "Todo el feed",
    etiquetaCorta: "Todo",
    icono: LayoutGrid,
    filtra: () => true,
    vacio: {
      titulo: "El feed está vacío",
      texto:
        "El equipo postea material y la IA lo convierte en piezas; aparecerán aquí, las más recientes primero, y aprobarás en línea cuando alguna esté lista.",
    },
  },
  {
    // TODO lo anterior a revisión: copy en curso, falta la foto/el clip, borradores completos
    // que entran solos y piezas devueltas a redacción. Es la bandeja del trabajo del equipo.
    // "Preparar" (verbo, simétrico con "Aprobar") y PencilRuler: la vista cubre copy en curso
    // y devueltas a redacción, no solo "falta la imagen" (lo que sugería ImagePlus).
    id: "preparacion",
    etiqueta: "En preparación",
    etiquetaCorta: "Preparar",
    icono: PencilRuler,
    filtra: (p) => p.estado === "borrador",
    vacio: {
      titulo: "Nada en preparación",
      texto:
        "Cuando una pieza esté en manos del equipo o de la IA (copy en curso, falta la foto o el video, o devuelta a redacción), aparecerá aquí.",
    },
  },
  {
    id: "por_aprobar",
    etiqueta: "Por aprobar",
    etiquetaCorta: "Aprobar",
    icono: ThumbsUp,
    filtra: (p) => p.estado === "en_revision",
    vacio: {
      titulo: "Nada por aprobar",
      // El detalle de cuántos OK lleva cada pieza lo enseña `CadenaAprobacion` pieza a pieza.
      texto: "Cuando la IA deje una pieza lista, aparecerá aquí para los OK del equipo.",
    },
  },
  {
    id: "publicado",
    etiqueta: "Aprobadas y publicadas",
    etiquetaCorta: "Publicadas",
    icono: Send,
    filtra: (p) => ["aprobado", "programado", "publicado"].includes(p.estado),
    vacio: {
      titulo: "Sin piezas aprobadas ni publicadas",
      texto: "Las piezas aprobadas, las programadas con hueco y las ya publicadas salen aquí.",
    },
  },
];

/**
 * Vista válida desde la URL (`?vista=`); ausente o desconocida → `porDefecto` ("todo" en
 * escritorio; el móvil arranca en "por_aprobar", su trabajo).
 */
export function vistaDesdeParam(v: string | null, porDefecto: Vista = "todo"): Vista {
  return VISTAS.some((x) => x.id === v) ? (v as Vista) : porDefecto;
}

/**
 * CONSULTA DEDICADA por estado: "En preparación" y "Por aprobar" mapean 1:1 a un estado del
 * backend y el SERVIDOR filtra. "Todo" y "Aprobadas y publicadas" comparten el listado base
 * (`estado` ausente → misma query cacheada); la vista de 3 estados filtra en cliente (el
 * parámetro `estado` del backend admite UNO).
 */
export const ESTADO_SERVIDOR_DE_VISTA: Record<Vista, "borrador" | "en_revision" | undefined> = {
  todo: undefined,
  preparacion: "borrador",
  por_aprobar: "en_revision",
  publicado: undefined,
};

/**
 * CONTEOS para los badges de las pestañas: el total EXACTO del servidor con cualquier filtro
 * (`limite=1` activa el modo offset: 1 fila + `paginacion.total`). Tres consultas ligeras:
 * todos / borrador / en_revision; "Aprobadas y publicadas" es la RESTA exacta (las 4 vistas
 * son una partición). Se cuentan PIEZAS (la unidad canónica del hub), no ideas: deliberado.
 *
 * `filtros` lleva los parámetros YA resueltos para la query (ausente = sin filtro); la clave
 * usa los mismos centinelas que las claves históricas de `FeedIdeacion` (caché compartida).
 */
export function useConteosFeed(filtros: { marca?: string; red?: string; linea?: string }): {
  totalTodos: number | undefined;
  totalBorrador: number | undefined;
  totalRevision: number | undefined;
  conteoVista: Record<Vista, number | undefined>;
} {
  const { marca, red, linea } = filtros;
  const claveConteo = (estado?: string) =>
    [
      ...CLAVE_PUBLICACIONES,
      "conteo-feed",
      marca ?? MARCA_ACTIVA_TODAS,
      red ?? FILTRO_TODOS,
      linea ?? FILTRO_TODOS,
      estado ?? "todos",
    ] as const;
  const conteoTodos = useQuery({
    queryKey: claveConteo(),
    queryFn: ({ signal }) => api.publicaciones({ marca, red, linea, limite: "1" }, signal),
    staleTime: 30_000,
  });
  const conteoBorrador = useQuery({
    queryKey: claveConteo("borrador"),
    queryFn: ({ signal }) =>
      api.publicaciones({ marca, red, linea, estado: "borrador", limite: "1" }, signal),
    staleTime: 30_000,
  });
  const conteoRevision = useQuery({
    queryKey: claveConteo("en_revision"),
    queryFn: ({ signal }) =>
      api.publicaciones({ marca, red, linea, estado: "en_revision", limite: "1" }, signal),
    staleTime: 30_000,
  });
  const totalTodos = conteoTodos.data?.paginacion?.total;
  const totalBorrador = conteoBorrador.data?.paginacion?.total;
  const totalRevision = conteoRevision.data?.paginacion?.total;
  // El badge solo se pinta con su número RESUELTO (nada de parpadeos de 0 mientras carga).
  const conteoVista: Record<Vista, number | undefined> = {
    todo: totalTodos,
    preparacion: totalBorrador,
    por_aprobar: totalRevision,
    publicado:
      totalTodos != null && totalBorrador != null && totalRevision != null
        ? Math.max(0, totalTodos - totalBorrador - totalRevision)
        : undefined,
  };
  return { totalTodos, totalBorrador, totalRevision, conteoVista };
}

/**
 * Contenido de un `TabsTrigger` de vista (etiqueta responsive + badge de conteo), compartido
 * por las pestañas de escritorio y las móviles.
 *
 * NOMBRE ACCESIBLE compuesto desde el DOM (sin `aria-label` que pise el conteo): en <sm la
 * etiqueta corta visible va `aria-hidden` y un sr-only lleva la completa; el número del badge
 * se anuncia con su unidad ("… 3 piezas").
 *
 * Badge `outline` sobre `bg-muted`: discreto sobre el rail muted del TabsList y destacado
 * sobre el trigger activo (fondo background) — la jerarquía correcta en claro y oscuro.
 * `enfasis` (la pestaña "Por aprobar" con pendientes) usa el mismo acento keni del
 * "te toca decidir" de `PostFeed`.
 */
export function ContenidoPestanaVista({
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
