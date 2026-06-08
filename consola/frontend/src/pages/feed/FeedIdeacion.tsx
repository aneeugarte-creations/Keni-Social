/**
 * FEED DE IDEACIÓN (`/parrilla/feed`) — Flujo D, Fase 4 del plan de máquina automática.
 *
 * La superficie de "red social interna": el equipo ve las piezas como POSTS (copy de IA +
 * arte/formato), con un LABEL de su etapa en la tubería, y APRUEBA en línea —como quien
 * interactúa con un post— sin abrir el kanban.
 *
 * UN SOLO feed por fecha, con 3 PESTAÑAS que son VISTAS del mismo listado (no bandejas que
 * fragmenten el flujo ni hagan fetches distintos): se pide TODO una vez (`creado DESC`) y la
 * pestaña solo FILTRA en cliente qué se enseña —
 *   - "Todo el feed": todas las piezas, mezcladas y por fecha (la vista por defecto).
 *   - "Por aprobar": las que esperan tu OK (`estado = en_revision`).
 *   - "Publicado y programado": lo que ya salió o tiene hueco (`estado ∈ {publicado, programado}`).
 * Cada pieza enseña en qué va con su label de etapa, y el OK aparece en línea cuando te toca.
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
import { Loader2, Minus, Plus, RefreshCw } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FILTRO_TODOS, useFiltrosContenido } from "@/hooks/filtros-contenido-contexto";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import type { Publicacion } from "@/types";

import { GrupoIdea, PlaceholderRed, type GrupoDeIdea } from "./GrupoIdea";
import { PostFeed } from "./PostFeed";

// --- Tamaño (zoom) y nº de columnas del feed (preferencia local, por dispositivo) --- //
// Dos controles independientes que persisten por dispositivo:
//  - Columnas (1-4): nº de posts por fila. Aplica en TODOS los anchos, móvil incluido; más
//    columnas = posts más pequeños y densos (en móvil quedan apretados, es lo que se quiere).
//  - Zoom (60%-140%): escala cada caja ENTERA del feed (imagen + texto a la vez, vía `FeedZoom`),
//    en cualquier pantalla y por encima de las columnas (ampliar sin tocar el nº de posts por fila).
const COLUMNAS_MIN = 1;
// Hasta 5 columnas: una pieza VIDEO va a las 5 redes, así que en "Todas las redes" se puede ver
// la idea entera (sus 5 redes) en UNA fila.
const COLUMNAS_MAX = 5;
const ESCALA_MIN = 0.6;
const ESCALA_MAX = 1.4;
// Clases estáticas (Tailwind las detecta) por nº de columnas. Sin prefijo: aplican en TODOS los
// anchos (móvil incluido), no solo en PC. El usuario manda cuántos posts por fila en cada pantalla.
const GRID_COLS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
  5: "grid-cols-5",
};

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
 * único. `filtra` decide qué piezas se enseñan; `vacio` el mensaje cuando esa vista no tiene.
 */
type Vista = "todo" | "por_aprobar" | "publicado";

const VISTAS: {
  id: Vista;
  etiqueta: string;
  filtra: (p: Publicacion) => boolean;
  vacio: { titulo: string; texto: string };
}[] = [
  {
    id: "todo",
    etiqueta: "Todo el feed",
    filtra: () => true,
    vacio: {
      titulo: "El feed está vacío",
      texto:
        "El equipo postea material y la IA lo convierte en piezas; aparecerán aquí, las más recientes primero, y aprobarás en línea cuando alguna esté lista.",
    },
  },
  {
    id: "por_aprobar",
    etiqueta: "Por aprobar",
    filtra: (p) => p.estado === "en_revision",
    vacio: {
      titulo: "Nada por aprobar",
      texto: "Cuando la IA deje una pieza lista, aparecerá aquí para tu visto bueno (los 2 OK).",
    },
  },
  {
    id: "publicado",
    etiqueta: "Publicado y programado",
    filtra: (p) => p.estado === "publicado" || p.estado === "programado",
    vacio: {
      titulo: "Nada publicado ni programado",
      texto: "Las piezas que apruebes y tengan hueco en la parrilla saldrán aquí.",
    },
  },
];

export default function FeedIdeacion() {
  const queryClient = useQueryClient();
  // La marca la manda el switch global de la barra superior (deriva del perfil).
  // El feed se filtra implícitamente por la marca activa; no hay selector local.
  const { marcaActiva } = useMarcaActiva();
  // Filtros de Red + Línea editorial: los mandan los selectores GLOBALES de la topbar
  // (la marca, el switch de marca). Se aplican en SERVIDOR (van en la query); las pestañas
  // siguen filtrando por estado en memoria.
  const { red, linea } = useFiltrosContenido();

  const [vista, setVista] = React.useState<Vista>("todo");

  // Nº de posts por fila en PC (1-4) y zoom (escala) de los posts. Preferencias locales, persistidas.
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

  // SCROLL MAGNÉTICO POR FILA (solo móvil): el contenedor que hace scroll es el <main> del
  // AppShell. Le activamos scroll-snap mientras el feed está montado (variantes `max-sm:`, así solo
  // por debajo de 640px) y lo revertimos al salir, sin que el AppShell tenga que conocer esta ruta.
  // Cada fila lleva `snap-start` (inerte si el contenedor no tiene snap-type, p. ej. en escritorio).
  const rootRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const scroller = rootRef.current?.closest("main");
    if (!scroller) return;
    const clases = ["max-sm:snap-y", "max-sm:snap-mandatory"];
    scroller.classList.add(...clases);
    return () => scroller.classList.remove(...clases);
  }, []);

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

  // Sentinel de scroll infinito: cuando el ancla del fondo entra en viewport, pide la siguiente
  // página (con guardas de `hasNextPage`/`isFetchingNextPage` para no encadenar peticiones).
  const sentinelRef = React.useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = feedQuery;
  React.useEffect(() => {
    const nodo = sentinelRef.current;
    if (!nodo || !hasNextPage) return;
    const obs = new IntersectionObserver(
      (entradas) => {
        if (entradas[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      // `rootMargin` adelanta la carga ~600px antes del fondo: el feed se siente continuo, sin
      // que el usuario llegue a ver el final antes de que aparezca lo siguiente.
      { rootMargin: "600px 0px" },
    );
    obs.observe(nodo);
    return () => obs.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

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
  const [searchParams, setSearchParams] = useSearchParams();
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
    setVista("todo");
    setPiezaDestacada(piezaParam);
    // Espera a que la idea esté pintada (cambio de vista) y haz scroll centrándola.
    const idAncla = anclaFeed(piezaParam);
    const tScroll = window.setTimeout(() => {
      document.getElementById(idAncla)?.scrollIntoView({ behavior: "smooth", block: "center" });
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

  const refrescar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });

  return (
    <div ref={rootRef}>
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu icono={RefreshCw} onClick={refrescar} disabled={feedQuery.isFetching}>
            Refrescar
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* Pestañas (formato tab, no bubble) + controles de densidad. Las pestañas son VISTAS del
          MISMO feed (filtran por estado en cliente); Marca, Red y Línea las mandan los switches
          GLOBALES de la topbar y filtran en servidor. En móvil las pestañas hacen wrap. */}
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <Tabs value={vista} onValueChange={(v) => setVista(v as Vista)}>
          <TabsList
            className="flex h-auto w-full flex-wrap justify-start gap-1 lg:w-auto"
            aria-label="Vista del feed"
          >
            {VISTAS.map((v) => (
              <TabsTrigger key={v.id} value={v.id} className="gap-1.5">
                {v.etiqueta}
                <span className="rounded-full bg-muted px-1.5 text-xs tabular-nums">
                  {conteos[v.id]}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          {/* Red y Línea ya no tienen dropdown aquí: los mandan los selectores globales de
              la topbar (SwitchFiltrosContenido). Quedan solo los controles de densidad/zoom. */}

          {/* Posts por fila: +/- de 1 a 4 (parte la rejilla en CUALQUIER pantalla, móvil incluido). Persiste. */}
          <div
            className="flex items-center gap-1 rounded-md border border-input bg-background px-1.5 py-1"
            role="group"
            aria-label="Posts por fila"
          >
            <span className="px-1 text-xs text-muted-foreground">Por fila</span>
            <button
              type="button"
              onClick={() => ajustarColumnas(-1)}
              disabled={columnas <= COLUMNAS_MIN}
              title="Menos columnas (posts más grandes)"
              aria-label="Menos columnas"
              className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent/50 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <span className="w-5 text-center text-xs font-medium tabular-nums">{columnas}</span>
            <button
              type="button"
              onClick={() => ajustarColumnas(1)}
              disabled={columnas >= COLUMNAS_MAX}
              title="Más columnas (posts más pequeños)"
              aria-label="Más columnas"
              className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent/50 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Zoom: agranda/encoge los posts en CUALQUIER pantalla (la palanca de tamaño en móvil). Persiste. */}
          <div
            className="flex items-center gap-1 rounded-md border border-input bg-background px-1.5 py-1"
            role="group"
            aria-label="Tamaño de los posts"
          >
            <span className="px-1 text-xs text-muted-foreground">Zoom</span>
            <button
              type="button"
              onClick={() => ajustarEscala(-0.1)}
              disabled={escala <= ESCALA_MIN}
              title="Posts más pequeños"
              aria-label="Reducir tamaño"
              className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent/50 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <span className="w-9 text-center text-xs tabular-nums text-muted-foreground">
              {Math.round(escala * 100)}%
            </span>
            <button
              type="button"
              onClick={() => ajustarEscala(0.1)}
              disabled={escala >= ESCALA_MAX}
              title="Posts más grandes"
              aria-label="Aumentar tamaño"
              className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent/50 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Feed. Con TODAS las redes: una MATRIZ por idea (un bloque por idea; dentro, una rejilla con
          todas las redes y huecos "No generado" en las que falten) — así no se mezclan ideas en una
          fila. Filtrado a UNA red: rejilla PLANA (1 col = centrado; 2-4 = a lo ancho). `columnas`
          fija cuántas por fila en cualquier pantalla; el zoom escala cada caja entera por encima. */}
      <FeedZoom escala={escala}>
        {feedQuery.isLoading ? (
          <div className={cn("grid items-start gap-4", GRID_COLS[columnas])}>
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-80 w-full rounded-xl" />)}
          </div>
        ) : feedQuery.isError ? (
          <BloqueError
            titulo="No se pudo cargar el feed"
            mensaje={mensajeError(feedQuery.error)}
            onReintentar={() => void feedQuery.refetch()}
            cargando={feedQuery.isFetching}
          />
        ) : gruposVista.length === 0 ? (
          <EstadoVacio titulo={vistaActual.vacio.titulo} texto={vistaActual.vacio.texto} />
        ) : agrupar ? (
          <div className="space-y-5">
            {gruposVista.map((g) => (
              <div
                key={g.id}
                id={anclaFeed(g.id)}
                className={cn(
                  "scroll-mt-20 snap-start rounded-xl transition-shadow",
                  g.id === piezaDestacada && "ring-2 ring-primary ring-offset-2 ring-offset-background",
                )}
              >
                <GrupoIdea grupo={g} redes={redesAMostrar} columnas={columnas} />
              </div>
            ))}
          </div>
        ) : (
          <div
            className={cn(
              columnas === 1
                ? "mx-auto w-full max-w-2xl space-y-4"
                : cn("grid items-start gap-4", GRID_COLS[columnas]),
            )}
          >
            {gruposVista.map((g) => {
              const p = g.piezas.find((x) => x.red === redesAMostrar[0]);
              return (
                <div
                  key={g.id}
                  id={anclaFeed(g.id)}
                  className={cn(
                    "scroll-mt-20 snap-start rounded-xl transition-shadow",
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
            acercarse al fondo. Solo cuando hay feed cargado y NO estamos en carga/error/vacío,
            para no encadenar peticiones mientras se pinta la primera página. El spinner
            "Cargando más…" da feedback sin saltos de layout (alto fijo). */}
        {!feedQuery.isLoading && !feedQuery.isError && gruposVista.length > 0 && (
          <>
            <div ref={sentinelRef} aria-hidden className="h-px w-full" />
            {isFetchingNextPage ? (
              <div
                className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground"
                role="status"
                aria-live="polite"
              >
                <Loader2 className="h-4 w-4 animate-spin" />
                Cargando más…
              </div>
            ) : !hasNextPage ? (
              <p className="py-6 text-center text-xs text-muted-foreground">
                Has llegado al final del feed.
              </p>
            ) : null}
          </>
        )}
      </FeedZoom>
    </div>
  );
}
