/**
 * FEED DE IDEACIÓN (`/parrilla/feed`) — Flujo D, Fase 4 del plan de máquina automática.
 *
 * La superficie de "red social interna": el equipo ve las piezas como POSTS (copy de IA +
 * arte/formato), con un LABEL de su etapa en la tubería, y APRUEBA en línea —como quien
 * interactúa con un post— sin abrir el kanban.
 *
 * UN SOLO feed por fecha, con 4 PESTAÑAS que son VISTAS del mismo listado (no bandejas que
 * fragmenten el flujo ni hagan fetches distintos): se pide TODO una vez (`creado DESC`) y la
 * pestaña solo FILTRA en cliente qué se enseña —
 *   - "Todo el feed": todas las piezas, mezcladas y por fecha (la vista por defecto).
 *   - "En preparación": las que esperan trabajo del equipo o de la IA (copy en curso, falta
 *     la foto/el clip) — la bandeja diaria de subir material.
 *   - "Por aprobar": las que esperan tu OK (`estado = en_revision`).
 *   - "Publicado y programado": lo que ya salió o tiene hueco (`estado ∈ {publicado, programado}`).
 * Cada pieza enseña en qué va con su label de etapa, y el OK aparece en línea cuando te toca.
 * La vista activa viaja en la URL (`?vista=`): un enlace al feed filtrado es compartible.
 *
 * Vive DENTRO del AppShell (a diferencia del feed móvil `/feed`, que es de una columna y sin
 * sidebar para revisores en el móvil). Aquí es una pestaña del hub Parrilla, pensada para
 * trabajar el día entero desde el feed.
 *
 * Reutiliza lo existente sin tocar backend:
 *  - `GET /api/publicaciones?marca=` (sin `estado`) para listar TODAS las piezas por fecha;
 *    las pestañas filtran ese único listado en memoria (sin más llamadas).
 *  - `PostFeed`: cada pieza como post + aprobación en línea (forwardea a la cadena multinivel)
 *    + comentarios (`Comentarios`).
 *  - El alta de material la implementa el Flujo A (acción de alta): este feed NO la duplica.
 */
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ImagePlus,
  LayoutGrid,
  Minus,
  Plus,
  RefreshCw,
  Send,
  SlidersHorizontal,
  ThumbsUp,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FILTRO_TODOS, useFiltrosContenido } from "@/hooks/filtros-contenido-contexto";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import type { Publicacion } from "@/types";

import { GRID_COLS } from "./formato";
import { GrupoIdea, PlaceholderRed, type GrupoDeIdea } from "./GrupoIdea";
import { PieFeed, SkeletonPost, useSentinelInfinito } from "./infinito";
import { PostFeed } from "./PostFeed";
import { CadenasLoteContexto, useCadenasLote } from "./use-cadenas-lote";

// --- Tamaño (zoom) y nº de columnas del feed (preferencia local, por dispositivo) --- //
// Dos controles independientes que persisten por dispositivo:
//  - Columnas (COLUMNAS_MIN-COLUMNAS_MAX): nº de posts por fila, en cualquier pantalla. En
//    móvil (<640px) se acota a 2 EFECTIVAS (la preferencia guardada no cambia): con más, la
//    fila de acciones desborda la celda y la tarjeta deja de ser operable.
//  - Zoom (60%-140%): escala cada caja ENTERA del feed (imagen + texto a la vez, vía `FeedZoom`),
//    en cualquier pantalla y por encima de las columnas (ampliar sin tocar el nº de posts por fila).
const COLUMNAS_MIN = 1;
// Hasta 5 columnas: una pieza VIDEO va a las 5 redes, así que en "Todas las redes" se puede ver
// la idea entera (sus 5 redes) en UNA fila.
const COLUMNAS_MAX = 5;
const ESCALA_MIN = 0.6;
const ESCALA_MAX = 1.4;
// Tope de columnas EFECTIVAS bajo 640px (la preferencia persiste entera para escritorio).
const COLUMNAS_MAX_MOVIL = 2;
// Tope de la búsqueda encadenada de las vistas filtradas vacías: cada "lote" permite traer
// hasta N páginas más antes de parar y ofrecer "Seguir buscando" (sin esto, una vista vacía
// podía descargar el feed ENTERO con un spinner sin progreso).
const PAGINAS_POR_LOTE = 5;

/**
 * Id del ancla DOM de una idea en el feed (deep-link desde las notificaciones). El cajón
 * de la campana navega a `?pieza=<contenido_id>` y aquí hacemos scroll a `#<este id>`.
 */
function anclaFeed(ideaId: string): string {
  return `feed-pieza-${ideaId}`;
}

/** Lee una preferencia numérica de localStorage, acotada a [min, max]; `defecto` si falta/ inválida. */
function leerPref(clave: string, defecto: number, min: number, max: number): number {
  try {
    const v = Number(window.localStorage.getItem(clave));
    if (!Number.isFinite(v) || v <= 0) return defecto;
    return Math.min(max, Math.max(min, v));
  } catch {
    return defecto; // entornos sin localStorage (SSR/tests): usa el valor por defecto
  }
}

/** Guarda una preferencia en localStorage de forma tolerante (ignora entornos sin storage). */
function guardarPref(clave: string, valor: number): void {
  try {
    window.localStorage.setItem(clave, String(valor));
  } catch {
    /* sin localStorage: la preferencia simplemente no persiste */
  }
}

/**
 * Escala TODO el feed de forma uniforme —cada caja entera: imagen + texto a la vez— como el zoom
 * del navegador. Usa `transform: scale`, NO la propiedad CSS `zoom`: `zoom` sobre un contenedor de
 * ancho fijo deja las imágenes (ancho %) a tamaño constante mientras el texto (px) crece —el
 * clásico "reverse zoom" en el que la cabecera engorda y la foto encoge—. `transform` escala el
 * render completo por igual, así que la caja crece/encoge entera.
 *
 * `transform` no reserva sitio en el flujo: medimos el alto real del contenido (sin escalar) y lo
 * reservamos en el contenedor (× escala) con un `ResizeObserver`. El ancho interno se compensa con
 * `width: 100/escala %` para que, ya escalado, el feed ocupe justo el 100% disponible.
 */
function FeedZoom({ escala, children }: { escala: number; children: React.ReactNode }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [alto, setAlto] = React.useState<number>();
  React.useLayoutEffect(() => {
    if (escala === 1) {
      setAlto(undefined);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const medir = () => setAlto(Math.ceil(el.offsetHeight * escala) + 2);
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, [escala]);

  if (escala === 1) return <>{children}</>;
  return (
    <div style={{ height: alto, overflow: "hidden" }}>
      <div
        ref={ref}
        style={{
          width: `${100 / escala}%`,
          transform: `scale(${escala})`,
          transformOrigin: "top left",
        }}
      >
        {children}
      </div>
    </div>
  );
}

/**
 * Pestañas del feed: NO son bandejas (un fetch por estado), son VISTAS del mismo listado
 * único. Las tres vistas filtradas son una PARTICIÓN del ciclo por ESTADO (toda pieza cae en
 * exactamente una: borrador → en revisión → aprobado/programado/publicado); "Todo el feed" es
 * la unión. `filtra` decide qué piezas se enseñan; `vacio` el mensaje cuando esa vista no
 * tiene; `corta` es el texto siempre visible en <sm (el resto de la etiqueta se oculta).
 */
type Vista = "todo" | "preparacion" | "por_aprobar" | "publicado";

const VISTAS: {
  id: Vista;
  etiqueta: string;
  /** Prefijo de `etiqueta` visible en TODO ancho; el resto se oculta en <sm. Sin él, entera. */
  corta?: string;
  icono: LucideIcon;
  filtra: (p: Publicacion) => boolean;
  vacio: { titulo: string; texto: string };
}[] = [
  {
    id: "todo",
    etiqueta: "Todo el feed",
    corta: "Todo",
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
    id: "preparacion",
    etiqueta: "En preparación",
    icono: ImagePlus,
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
    etiqueta: "Aprobado y publicado",
    corta: "Aprobado",
    icono: Send,
    filtra: (p) => ["aprobado", "programado", "publicado"].includes(p.estado),
    vacio: {
      titulo: "Nada aprobado ni publicado",
      texto: "Las piezas aprobadas, las programadas con hueco y las ya publicadas salen aquí.",
    },
  },
];

/** Vista válida desde la URL (`?vista=`); ausente o desconocida → "todo". */
function vistaDesdeParam(v: string | null): Vista {
  return VISTAS.some((x) => x.id === v) ? (v as Vista) : "todo";
}

/** Stepper de un ajuste de vista: etiqueta + par menos/más con el valor en medio. */
function ControlStepper({
  etiqueta,
  valor,
  onMenos,
  onMas,
  disabledMenos,
  disabledMas,
  ariaLabelMenos,
  ariaLabelMas,
}: {
  etiqueta: string;
  valor: string | number;
  onMenos: () => void;
  onMas: () => void;
  disabledMenos?: boolean;
  disabledMas?: boolean;
  ariaLabelMenos: string;
  ariaLabelMas: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-muted-foreground">{etiqueta}</span>
      <div className="flex items-center">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onMenos}
          disabled={disabledMenos}
          aria-label={ariaLabelMenos}
        >
          <Minus className="h-3.5 w-3.5" />
        </Button>
        <span className="w-9 text-center text-xs font-medium tabular-nums">{valor}</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onMas}
          disabled={disabledMas}
          aria-label={ariaLabelMas}
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

/**
 * Popover "Vista" de la barra de acciones: aloja los steppers de densidad (posts por fila) y
 * zoom. Misma mecánica que `MenuAcciones` (cierre por clic fuera y Escape) pero SIN cerrar al
 * clicar dentro: los steppers se pulsan varias veces seguidas.
 */
function PopoverVista({ children }: { children: React.ReactNode }) {
  const [abierto, setAbierto] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!abierto) return;
    const alClicFuera = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false);
    };
    const alEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierto(false);
    };
    document.addEventListener("mousedown", alClicFuera);
    document.addEventListener("keydown", alEscape);
    return () => {
      document.removeEventListener("mousedown", alClicFuera);
      document.removeEventListener("keydown", alEscape);
    };
  }, [abierto]);

  return (
    <div ref={ref} className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-muted-foreground hover:text-foreground"
        aria-label="Ajustes de vista"
        aria-haspopup="dialog"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
      >
        <SlidersHorizontal className="h-4 w-4" />
      </Button>
      {abierto && (
        <div
          role="dialog"
          aria-label="Ajustes de vista"
          className="absolute right-0 z-50 mt-1 w-56 space-y-2 rounded-md border border-border bg-popover p-3 text-popover-foreground shadow-md"
        >
          {children}
        </div>
      )}
    </div>
  );
}

export default function FeedIdeacion() {
  const queryClient = useQueryClient();
  // La marca la manda el switch global de la barra superior (deriva del perfil).
  // El feed se filtra implícitamente por la marca activa; no hay selector local.
  const { marcaActiva } = useMarcaActiva();
  // Filtros de Red + Línea editorial: los mandan los selectores GLOBALES de la topbar
  // (la marca, el switch de marca). Se aplican en SERVIDOR (van en la query); las pestañas
  // siguen filtrando por estado en memoria.
  const { red, linea } = useFiltrosContenido();

  const rootRef = React.useRef<HTMLDivElement>(null);

  // La vista activa vive en la URL (`?vista=`): sobrevive al refresco y es compartible.
  // "todo" (el default) va sin parámetro para no ensuciar el enlace.
  const [searchParams, setSearchParams] = useSearchParams();
  const [vista, setVista] = React.useState<Vista>(() =>
    vistaDesdeParam(searchParams.get("vista")),
  );
  // Lotes de búsqueda concedidos a la vista filtrada vacía (tope = lotes × PAGINAS_POR_LOTE
  // páginas); "Seguir buscando" concede otro. Se reinicia al cambiar de vista.
  const [lotesBusqueda, setLotesBusqueda] = React.useState(1);
  const cambiarVista = React.useCallback(
    (v: Vista) => {
      setVista(v);
      setLotesBusqueda(1);
      // Cambio de contexto: el listado nuevo se lee desde arriba, no desde donde quedó el scroll.
      const scroller = rootRef.current?.closest("main");
      if (scroller) scroller.scrollTop = 0;
      setSearchParams(
        (prev) => {
          if (v === "todo") prev.delete("vista");
          else prev.set("vista", v);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  // Nº de posts por fila y zoom (escala) de los posts. Preferencias locales, persistidas.
  const [columnas, setColumnas] = React.useState(() =>
    leerPref("keni_feed_columnas", 2, COLUMNAS_MIN, COLUMNAS_MAX),
  );
  const [escala, setEscala] = React.useState(() =>
    leerPref("keni_feed_escala", 1, ESCALA_MIN, ESCALA_MAX),
  );
  React.useEffect(() => {
    guardarPref("keni_feed_columnas", columnas);
  }, [columnas]);
  React.useEffect(() => {
    guardarPref("keni_feed_escala", escala);
  }, [escala]);

  // ¿Viewport móvil (<640px)? Acota las columnas EFECTIVAS (tope responsivo) sin tocar la
  // preferencia guardada. Guard de `matchMedia` para jsdom (tests) y entornos sin la API.
  const [esMovil, setEsMovil] = React.useState(
    () =>
      typeof window.matchMedia === "function" &&
      window.matchMedia("(max-width: 639px)").matches,
  );
  React.useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(max-width: 639px)");
    const aplicar = () => setEsMovil(mq.matches);
    aplicar();
    mq.addEventListener("change", aplicar);
    return () => mq.removeEventListener("change", aplicar);
  }, []);
  const colsEfectivas = esMovil ? Math.min(columnas, COLUMNAS_MAX_MOVIL) : columnas;

  // SCROLL MAGNÉTICO POR POST (solo móvil a UNA columna, estilo YouTube Shorts): el contenedor que
  // hace scroll es el <main> del AppShell. Le ponemos `scroll-snap-type: y proximity` por estilo en
  // línea (más fiable que clases dinámicas que el JIT de Tailwind podría no generar) SOLO por
  // debajo de 640px, vía `matchMedia`, y lo revertimos al salir o al pasar a escritorio.
  // `proximity` (no `mandatory`): las tarjetas superan la altura del viewport y `mandatory`
  // secuestra el scroll del pie. Con 2+ columnas no hay snap (saltaría errático por celda).
  // Cada POST lleva `snap-start` (inerte si el contenedor no tiene snap-type).
  React.useEffect(() => {
    const scroller = rootRef.current?.closest("main") as HTMLElement | null;
    if (!scroller) return;
    const mq = window.matchMedia("(max-width: 639px)");
    const aplicar = () => {
      scroller.style.scrollSnapType = mq.matches && colsEfectivas === 1 ? "y proximity" : "";
    };
    aplicar();
    mq.addEventListener("change", aplicar);
    return () => {
      mq.removeEventListener("change", aplicar);
      scroller.style.scrollSnapType = "";
    };
  }, [colsEfectivas]);

  const ajustarColumnas = (delta: number) =>
    setColumnas((c) => Math.min(COLUMNAS_MAX, Math.max(COLUMNAS_MIN, c + delta)));
  const ajustarEscala = (delta: number) =>
    setEscala((s) => Math.round(Math.min(ESCALA_MAX, Math.max(ESCALA_MIN, s + delta)) * 100) / 100);

  // Catálogo de redes (para la MATRIZ por idea: cada idea se enseña en todas las redes,
  // con huecos en las que falte pieza). Las líneas editoriales viven en el switch global.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });

  // SCROLL INFINITO (feed social): se pide la PRIMERA página pequeña (instantánea) por keyset
  // `creado DESC` y se van pidiendo más al hacer scroll (sentinel + IntersectionObserver). El
  // backend devuelve `paginacion.cursor_siguiente` (clave `<creado>|<id>`) mientras haya más; al
  // omitirlo, `getNextPageParam` devuelve undefined y `hasNextPage` se apaga. Las pestañas siguen
  // filtrando en memoria por estado sobre TODAS las páginas ya cargadas (sin más llamadas).
  const feedQuery = useInfiniteQuery({
    queryKey: [
      ...CLAVE_PUBLICACIONES,
      "feed-ideacion",
      marcaActiva ?? MARCA_ACTIVA_TODAS,
      red,
      linea,
    ],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api.publicaciones(
        {
          marca: marcaActiva ?? undefined,
          red: red === FILTRO_TODOS ? undefined : red,
          linea: linea === FILTRO_TODOS ? undefined : linea,
          // `feed=1` activa el keyset desde la 1ª página (que va sin cursor); `cursor` encadena
          // las siguientes. Así la primera carga es pequeña/instantánea y trae `cursor_siguiente`.
          feed: "1",
          cursor: pageParam,
        },
        signal,
      ),
    // El cursor de la siguiente página lo da el backend; ausente = última página (fin del scroll).
    getNextPageParam: (ultima) => ultima.paginacion?.cursor_siguiente ?? undefined,
  });

  // El backend ya acota por la marca activa (o devuelve todo en la vista "Todas" de admin).
  // Aplanamos TODAS las páginas cargadas en un único listado que el resto de la UI consume igual.
  const piezas = React.useMemo(
    () => (feedQuery.data?.pages ?? []).flatMap((p) => p.publicaciones),
    [feedQuery.data],
  );

  // ANTI-N+1: pide en UN lote las cadenas de aprobación de las piezas cargadas y las
  // siembra en las claves individuales que consumen los `PostFeed` (vía contexto).
  const cadenasLote = useCadenasLote(piezas);

  const { hasNextPage, isFetchingNextPage, fetchNextPage } = feedQuery;

  // Redes del catálogo: el feed enseña CADA idea en TODAS las redes; las que aún no tienen pieza
  // salen como hueco "No generado" (queremos todo el contenido en todas las redes). Si se filtra
  // por una red concreta, el feed es PLANO (solo esa red); si no, es una MATRIZ por idea.
  const catalogoRedes = React.useMemo(
    () => (opcionesQuery.data?.redes ?? []).map((r) => r.id),
    [opcionesQuery.data],
  );
  const redesAMostrar = red === FILTRO_TODOS ? catalogoRedes : [red];
  const agrupar = redesAMostrar.length > 1;

  // Agrupa TODAS las piezas por IDEA (`contenido_id`), preservando el orden de aparición
  // (`creado DESC`). Cada idea es un bloque; así NUNCA se mezclan posts de ideas distintas en una
  // misma fila. Cada idea conoce qué redes tiene generadas y cuáles faltan.
  const grupos = React.useMemo(() => {
    const mapa = new Map<string, GrupoDeIdea>();
    for (const p of piezas) {
      const clave = p.contenido_id || p.id;
      let g = mapa.get(clave);
      if (!g) {
        g = { id: clave, titulo: p.titulo, marca_nombre: p.marca_nombre, piezas: [] };
        mapa.set(clave, g);
      }
      g.piezas.push(p);
    }
    return [...mapa.values()];
  }, [piezas]);

  // DEEP-LINK desde las notificaciones (`?pieza=<contenido_id>`): al entrar, salta a esa idea
  // y la resalta un instante. Forzamos la vista "todo" (que siempre la muestra, esté en el
  // estado que esté) y limpiamos el parámetro para no re-disparar en refetch/re-render. Si la
  // idea no está en el feed de la marca activa (otra marca, ya archivada…), solo limpiamos.
  //
  // SCROLL INFINITO: la idea puede vivir en una página AÚN no cargada. Mientras no esté entre
  // las páginas cargadas y queden más por traer, vamos pidiendo la siguiente (sin limpiar el
  // parámetro) hasta encontrarla o agotar el feed; recién entonces resolvemos (salto + resalte
  // si existe, o solo limpiar si no apareció en todo el feed). No bloquea ni rompe el scroll.
  const piezaParam = searchParams.get("pieza");
  const [piezaDestacada, setPiezaDestacada] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!piezaParam || feedQuery.isLoading) return;
    const existe = grupos.some((g) => g.id === piezaParam);
    // Aún no la vemos pero quedan páginas: trae la siguiente y reevalúa (sin limpiar el param).
    if (!existe && hasNextPage) {
      if (!isFetchingNextPage) void fetchNextPage();
      return;
    }
    setSearchParams(
      (prev) => {
        prev.delete("pieza");
        return prev;
      },
      { replace: true },
    );
    if (!existe) return;
    cambiarVista("todo");
    setPiezaDestacada(piezaParam);
    // Espera a que la idea esté pintada (cambio de vista) y haz scroll centrándola.
    const idAncla = anclaFeed(piezaParam);
    const tScroll = window.setTimeout(() => {
      // WCAG 2.3.3: sin animación de scroll si el SO pide movimiento reducido.
      const sinAnimar =
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      document
        .getElementById(idAncla)
        ?.scrollIntoView({ behavior: sinAnimar ? "auto" : "smooth", block: "center" });
    }, 60);
    const tResalte = window.setTimeout(() => setPiezaDestacada(null), 2500);
    return () => {
      window.clearTimeout(tScroll);
      window.clearTimeout(tResalte);
    };
  }, [
    piezaParam,
    feedQuery.isLoading,
    grupos,
    setSearchParams,
    cambiarVista,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  ]);

  // Las pestañas filtran por estado a nivel de IDEA: una idea aparece si ALGUNA de sus piezas
  // cumple la vista. El badge de cada pestaña cuenta IDEAS (no piezas sueltas).
  const conteos = React.useMemo(
    () =>
      Object.fromEntries(
        VISTAS.map((v) => [v.id, grupos.filter((g) => g.piezas.some(v.filtra)).length]),
      ) as Record<Vista, number>,
    [grupos],
  );
  const vistaActual = VISTAS.find((v) => v.id === vista) ?? VISTAS[0];
  const gruposVista = React.useMemo(
    () => grupos.filter((g) => g.piezas.some(vistaActual.filtra)),
    [grupos, vistaActual],
  );

  // TOPE de la búsqueda encadenada: con la vista filtrada vacía, el sentinel solo encadena hasta
  // `lotesBusqueda × PAGINAS_POR_LOTE` páginas; después se para y ofrece "Seguir buscando".
  // Con resultados delante no hay tope: el usuario scrollea contenido real.
  const vistaVacia = gruposVista.length === 0 && !feedQuery.isLoading && !feedQuery.isError;
  const paginasCargadas = feedQuery.data?.pages.length ?? 0;
  const topeAlcanzado =
    vistaVacia && hasNextPage && paginasCargadas >= lotesBusqueda * PAGINAS_POR_LOTE;

  // Sentinel de scroll infinito compartido (ver `infinito.tsx`); el tope lo apaga sin desmontarlo.
  const sentinelRef = useSentinelInfinito({
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    habilitado: !topeAlcanzado,
  });

  // El spinner del botón Actualizar SOLO cuando de verdad se refresca el listado, no en cada
  // `fetchNextPage` del scroll (si no, el botón parpadea mientras bajas por el feed).
  const refrescando = feedQuery.isRefetching && !feedQuery.isFetchingNextPage;
  const refrescar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });

  return (
    <CadenasLoteContexto.Provider value={cadenasLote}>
    <div ref={rootRef}>
      <AccionesPagina>
        <div className="flex items-center gap-1">
          {/* Ajustes de vista (densidad + zoom) en un popover: no compiten con las pestañas. */}
          <PopoverVista>
            <ControlStepper
              etiqueta="Por fila"
              valor={columnas}
              onMenos={() => ajustarColumnas(-1)}
              onMas={() => ajustarColumnas(1)}
              disabledMenos={columnas <= COLUMNAS_MIN}
              disabledMas={columnas >= COLUMNAS_MAX}
              ariaLabelMenos="Menos columnas"
              ariaLabelMas="Más columnas"
            />
            {/* El tope móvil no es un control roto: se avisa de que la preferencia se acota. */}
            {esMovil && columnas > COLUMNAS_MAX_MOVIL && (
              <p className="text-right text-xs text-muted-foreground">
                (máx. {COLUMNAS_MAX_MOVIL} en móvil)
              </p>
            )}
            <ControlStepper
              etiqueta="Zoom"
              valor={`${Math.round(escala * 100)}%`}
              onMenos={() => ajustarEscala(-0.1)}
              onMas={() => ajustarEscala(0.1)}
              disabledMenos={escala <= ESCALA_MIN}
              disabledMas={escala >= ESCALA_MAX}
              ariaLabelMenos="Reducir tamaño"
              ariaLabelMas="Aumentar tamaño"
            />
          </PopoverVista>
          {/* Actualizar (el verbo de la casa) como botón directo: gira y se deshabilita SOLO
              durante un refresco real, no en cada página del scroll infinito. */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label="Actualizar"
            title="Actualizar"
            onClick={refrescar}
            disabled={refrescando}
          >
            <RefreshCw className={cn("h-4 w-4", refrescando && "animate-spin")} />
          </Button>
        </div>
      </AccionesPagina>

      {/* Pestañas (control segmentado en UNA fila, como en el resto de la app), solas en su
          fila. Son VISTAS del MISMO feed (filtran por estado en cliente); Marca, Red y Línea las
          mandan los switches GLOBALES de la topbar y filtran en servidor. En <sm las etiquetas
          se acortan (el `aria-label` conserva el nombre completo). El conteo solo se pinta con
          el feed AGOTADO: es exacto o no es (nada de "0+" sobre páginas a medio cargar). */}
      <div className="mb-4">
        <Tabs value={vista} onValueChange={(v) => cambiarVista(v as Vista)}>
          <TabsList
            className="w-fit max-w-full justify-start gap-1 overflow-x-auto"
            aria-label="Vista del feed"
          >
            {VISTAS.map((v) => (
              <TabsTrigger key={v.id} value={v.id} className="gap-1.5" aria-label={v.etiqueta}>
                {v.corta ? (
                  <>
                    {v.corta}
                    <span className="hidden sm:inline">{v.etiqueta.slice(v.corta.length)}</span>
                  </>
                ) : (
                  v.etiqueta
                )}
                {!hasNextPage && (
                  <Badge
                    variant="secondary"
                    className="ml-1 px-1.5 py-0 tabular-nums"
                    title={`${conteos[v.id]} ideas`}
                  >
                    {conteos[v.id]}
                  </Badge>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {/* Feed. Con TODAS las redes: una MATRIZ por idea (un bloque por idea; dentro, una rejilla
          con sus redes generadas y la franja "Falta generar" con las pendientes) — así no se
          mezclan ideas en una fila. Filtrado a UNA red: rejilla PLANA (1 col = centrado; más =
          a lo ancho). `colsEfectivas` fija cuántas por fila (la preferencia, acotada en móvil);
          el zoom escala cada caja entera por encima. */}
      <FeedZoom escala={escala}>
        {feedQuery.isLoading ? (
          // El skeleton ESPEJA el contenedor final (misma retícula/anchos) y la ANATOMÍA de la
          // tarjeta (cabecera + imagen 4:5 + copy + acciones): sin salto de layout al aterrizar.
          <div
            className={cn(
              colsEfectivas === 1
                ? "mx-auto w-full max-w-2xl space-y-4"
                : cn("grid items-start gap-4", GRID_COLS[colsEfectivas]),
            )}
          >
            {[0, 1, 2].map((i) => <SkeletonPost key={i} />)}
          </div>
        ) : feedQuery.isError ? (
          <BloqueError
            titulo="No se pudo cargar el feed"
            mensaje={mensajeError(feedQuery.error)}
            onReintentar={() => void feedQuery.refetch()}
            cargando={feedQuery.isFetching}
          />
        ) : gruposVista.length === 0 ? (
          // VACÍO HONESTO: solo se afirma "no hay nada" cuando el feed está agotado. Si quedan
          // páginas, el sentinel encadena la carga HASTA EL TOPE del lote; ahí se para y
          // "Seguir buscando" concede otro lote (sin descargar el feed entero a ciegas).
          topeAlcanzado ? (
            <div className="flex flex-col items-center gap-2 py-6 text-center">
              <p className="text-sm text-muted-foreground">
                No hay piezas de esta vista entre lo ya cargado.
              </p>
              <Button variant="outline" size="sm" onClick={() => setLotesBusqueda((n) => n + 1)}>
                Seguir buscando
              </Button>
            </div>
          ) : hasNextPage ? (
            <PieFeed estado="buscando" />
          ) : (
            <EstadoVacio
              icono={vistaActual.icono}
              titulo={vistaActual.vacio.titulo}
              texto={vistaActual.vacio.texto}
            />
          )
        ) : agrupar ? (
          // Sin role="feed" aquí: sus hijos directos no son <article> (cada grupo agrupa varios).
          <div className="space-y-6" aria-busy={isFetchingNextPage}>
            {gruposVista.map((g) => (
              <div
                key={g.id}
                id={anclaFeed(g.id)}
                className={cn(
                  // NO snap aquí: el snap va por POST (dentro de GrupoIdea), no por idea.
                  "scroll-mt-20 rounded-xl transition-shadow",
                  g.id === piezaDestacada && "ring-2 ring-primary ring-offset-2 ring-offset-background",
                )}
              >
                <GrupoIdea
                  grupo={g}
                  redes={redesAMostrar}
                  columnas={colsEfectivas}
                  // En las vistas filtradas el grupo enseña SOLO lo que cumple el filtro (sin
                  // tarjetas ajenas); la matriz completa es de "Todo el feed".
                  filtra={vista === "todo" ? undefined : vistaActual.filtra}
                />
              </div>
            ))}
          </div>
        ) : (
          <div
            className={cn(
              colsEfectivas === 1
                ? "mx-auto w-full max-w-2xl space-y-4"
                : cn("grid items-start gap-4", GRID_COLS[colsEfectivas]),
            )}
            role="feed"
            aria-busy={isFetchingNextPage}
          >
            {gruposVista.map((g) => {
              const p = g.piezas.find(
                (x) =>
                  x.red === redesAMostrar[0] && (vista === "todo" || vistaActual.filtra(x)),
              );
              return (
                <div
                  key={g.id}
                  id={anclaFeed(g.id)}
                  className={cn(
                    // Cada pieza es un punto de snap (sin margen superior: encaja arriba del todo).
                    "snap-start rounded-xl transition-shadow",
                    g.id === piezaDestacada &&
                      "ring-2 ring-primary ring-offset-2 ring-offset-background",
                  )}
                >
                  {p ? (
                    <PostFeed publicacion={p} />
                  ) : (
                    <PlaceholderRed red={redesAMostrar[0]} titulo={g.titulo} />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* SCROLL INFINITO: el sentinel (invisible) dispara la carga de la siguiente página al
            acercarse al fondo. Se monta SIEMPRE que queden páginas (también con la vista filtrada
            vacía: así la paginación no muere afirmando un vacío falso); el tope del lote lo
            apaga sin desmontarlo. El pie (`PieFeed`) da feedback sin saltos de layout. */}
        {!feedQuery.isLoading && !feedQuery.isError && (
          <>
            {hasNextPage && <div ref={sentinelRef} aria-hidden className="h-px w-full" />}
            {gruposVista.length > 0 &&
              (isFetchingNextPage ? (
                <PieFeed estado="cargando" />
              ) : !hasNextPage ? (
                <PieFeed estado="fin" />
              ) : null)}
          </>
        )}
      </FeedZoom>
    </div>
    </CadenasLoteContexto.Provider>
  );
}
