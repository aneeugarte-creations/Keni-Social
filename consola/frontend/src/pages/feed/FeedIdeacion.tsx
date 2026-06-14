/**
 * FEED DE IDEACIÓN (`/parrilla/feed`) — Flujo D, Fase 4 del plan de máquina automática.
 *
 * La superficie de "red social interna": el equipo ve las piezas como POSTS (copy de IA +
 * arte/formato), con un LABEL de su etapa en la tubería, y APRUEBA en línea —como quien
 * interactúa con un post— sin abrir el kanban.
 *
 * UN feed por fecha (keyset `feed=1` + `cursor`, `creado DESC`, scroll infinito) con 4 PESTAÑAS
 * que PARTICIONAN el ciclo por ESTADO (toda pieza cae en exactamente una; "Todo el feed" es la
 * unión). La partición, el mapeo vista→estado del servidor y los conteos de los badges viven en
 * `vistas.tsx`, COMPARTIDOS con el feed móvil (`MobileFeed`).
 * La vista activa vive SOLO en la URL (`?vista=`): compartible, sobrevive al refresco y a
 * atrás/adelante del navegador (no hay estado duplicado en memoria).
 * Los badges de las pestañas cuentan PIEZAS con el total EXACTO del servidor
 * (`paginacion.total` vía `limite=1`), no lo que casualmente haya cargado el scroll.
 *
 * Vive DENTRO del AppShell (a diferencia del feed móvil `/feed`, de una columna y sin sidebar).
 * Marca, Red y Línea los mandan los switches GLOBALES de la topbar y filtran en servidor.
 *
 * Reutiliza lo existente sin tocar backend:
 *  - `GET /api/publicaciones` (keyset con `feed=1`; `estado=` en las vistas dedicadas).
 *  - `PostFeed`: cada pieza como post + aprobación en línea + comentarios.
 *  - El alta de material la implementa el Flujo A (acción de alta): este feed NO la duplica.
 */
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Minus, Plus, RefreshCw } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import { FILTRO_TODOS, useFiltrosContenido } from "@/hooks/filtros-contenido-contexto";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";

import { DialogoCrearPost } from "./DialogoCrearPost";
import { GRID_COLS, MAX_W_FEED, REDES_POR_FORMATO } from "./formato";
import { CabeceraIdea, GrupoIdea, PlaceholderRed, type GrupoDeIdea } from "./GrupoIdea";
import { PieFeed, SkeletonPost, useSentinelInfinito } from "./infinito";
import { PostFeed } from "./PostFeed";
import { CadenasLoteContexto, useCadenasLote } from "./use-cadenas-lote";
import {
  ContenidoPestanaVista,
  ESTADO_SERVIDOR_DE_VISTA,
  PAGINAS_POR_LOTE,
  TOPE_PAGINAS_PIEZA,
  useConteosFeed,
  VISTAS,
  vistaDesdeParam,
  type Vista,
} from "./vistas";

// Nº de posts por fila (preferencia local, por dispositivo). Hasta 5 columnas: una pieza VIDEO
// va a las 5 redes, así que en "Todas las redes" se puede ver la idea entera en UNA fila.
const COLUMNAS_MIN = 1;
const COLUMNAS_MAX = 5;
// Ancho mínimo OPERABLE de una celda (~px): por debajo, la fila de acciones de la tarjeta
// desborda. Las columnas EFECTIVAS se acotan a las que caben en el ancho real del contenedor.
const ANCHO_MIN_CELDA = 240;

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

export default function FeedIdeacion() {
  const queryClient = useQueryClient();
  // La marca la manda el switch global de la barra superior (deriva del perfil).
  // El feed se filtra implícitamente por la marca activa; no hay selector local.
  const { marcaActiva } = useMarcaActiva();
  // Filtros de Red + Línea editorial: los mandan los selectores GLOBALES de la topbar.
  // Se aplican en SERVIDOR (van en la query), igual que el `estado` de las vistas dedicadas.
  const { red, linea } = useFiltrosContenido();

  const rootRef = React.useRef<HTMLDivElement>(null);

  // Diálogo "Crear post" (alta directa): el equipo teclea el copy FINAL y nace un
  // borrador por red por el mismo motor que el copy generado.
  const [creandoPost, setCreandoPost] = React.useState(false);

  // La vista activa vive SOLO en la URL (`?vista=`): derivada, sin useState que se
  // desincronice. "pendiente" (el default: el trabajo por hacer) va sin parámetro para no
  // ensuciar el enlace.
  const [searchParams, setSearchParams] = useSearchParams();
  const vista = vistaDesdeParam(searchParams.get("vista"), "pendiente");
  // Lotes de búsqueda concedidos a la vista filtrada EN CLIENTE vacía (tope = lotes ×
  // PAGINAS_POR_LOTE páginas); "Seguir buscando" concede otro. Se reinicia al cambiar de vista.
  const [lotesBusqueda, setLotesBusqueda] = React.useState(1);
  const cambiarVista = React.useCallback(
    (v: Vista) => {
      setSearchParams(
        (prev) => {
          if (v === "pendiente") prev.delete("vista");
          else prev.set("vista", v);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );
  // Cambio de contexto —incluye atrás/adelante del navegador, no solo el clic en la pestaña—:
  // el lote de búsqueda se reinicia y el listado nuevo se lee desde arriba.
  React.useEffect(() => {
    setLotesBusqueda(1);
    const scroller = rootRef.current?.closest("main");
    if (scroller) scroller.scrollTop = 0;
  }, [vista]);

  // Nº de posts por fila. Preferencia local, persistida por dispositivo.
  const [columnas, setColumnas] = React.useState(() =>
    leerPref("keni_feed_columnas", 2, COLUMNAS_MIN, COLUMNAS_MAX),
  );
  React.useEffect(() => {
    guardarPref("keni_feed_columnas", columnas);
  }, [columnas]);
  // El zoom (FeedZoom) se retiró: limpia la preferencia muerta de instalaciones previas.
  React.useEffect(() => {
    try {
      window.localStorage.removeItem("keni_feed_escala");
    } catch {
      /* sin localStorage */
    }
  }, []);

  // ANCHO REAL del contenedor (ResizeObserver): acota las columnas EFECTIVAS a las que caben
  // con celdas operables (≥ANCHO_MIN_CELDA px). Sustituye al tope binario "móvil = 2": un
  // tablet de 800px tampoco soporta 5 columnas. `null` (jsdom/SSR o aún sin medir) cae a la
  // preferencia; la medición inicial es la que vale en tests (el stub de RO no dispara).
  const [ancho, setAncho] = React.useState<number | null>(null);
  React.useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const medir = () => setAncho(el.clientWidth || null);
    medir();
    if (typeof ResizeObserver !== "function") return;
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const colsEfectivas =
    ancho == null
      ? columnas
      : Math.min(columnas, Math.max(1, Math.floor(ancho / ANCHO_MIN_CELDA)));

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

  // Catálogo de redes (para la MATRIZ por idea: cada idea se enseña en todas las redes,
  // con huecos en las que falte pieza). Las líneas editoriales viven en el switch global.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });

  // CONSULTA DEDICADA por estado (ver `ESTADO_SERVIDOR_DE_VISTA` en vistas.tsx): "Pendientes" y
  // "Publicadas" llegan filtradas del servidor (pseudo-estados); "Todas" comparte el listado base.
  const estadoServidor = ESTADO_SERVIDOR_DE_VISTA[vista];

  // SCROLL INFINITO (feed social): primera página pequeña (instantánea) por keyset `creado DESC`
  // y más al hacer scroll (sentinel + IntersectionObserver). El backend devuelve
  // `paginacion.cursor_siguiente` mientras haya más; al omitirlo, `hasNextPage` se apaga.
  const feedQuery = useInfiniteQuery({
    queryKey: [
      ...CLAVE_PUBLICACIONES,
      "feed-ideacion",
      marcaActiva ?? MARCA_ACTIVA_TODAS,
      red,
      linea,
      // "todos" identifica la vista "Todas" (sin `estado`); las otras dos van por pseudo-estado.
      estadoServidor ?? "todos",
    ],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api.publicaciones(
        {
          marca: marcaActiva ?? undefined,
          red: red === FILTRO_TODOS ? undefined : red,
          linea: linea === FILTRO_TODOS ? undefined : linea,
          estado: estadoServidor,
          // `feed=1` activa el keyset desde la 1ª página (que va sin cursor); `cursor` encadena
          // las siguientes. Así la primera carga es pequeña/instantánea y trae `cursor_siguiente`.
          feed: "1",
          cursor: pageParam,
        },
        signal,
      ),
    // El cursor de la siguiente página lo da el backend; ausente = última página (fin del scroll).
    getNextPageParam: (ultima) => ultima.paginacion?.cursor_siguiente ?? undefined,
    // La frescura llega por el botón Actualizar, las actualizaciones in-place tras cada reacción
    // y los conteos (que SÍ refrescan al volver el foco): sin refetch en cadena de N páginas
    // cada vez que la pestaña recupera el foco.
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // Conteos exactos de los badges de las pestañas (compartidos con el móvil; ver vistas.tsx).
  const { totalRevision, conteoVista } = useConteosFeed({
    marca: marcaActiva ?? undefined,
    red: red === FILTRO_TODOS ? undefined : red,
    linea: linea === FILTRO_TODOS ? undefined : linea,
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
  // salen como hueco "No generado". Si se filtra por una red concreta, el feed es PLANO.
  // RESPALDO ante error de /opciones: el catálogo estático de formato.ts (las 5 redes conocidas)
  // en vez de `[]` —con catálogo vacío TODAS las ideas se pintaban como "No generado" aunque
  // tuvieran contenido—. Mientras /opciones está en vuelo, el gate de abajo enseña skeleton.
  const catalogoRedes = React.useMemo(
    () =>
      opcionesQuery.isError
        ? [...REDES_POR_FORMATO.video]
        : (opcionesQuery.data?.redes ?? []).map((r) => r.id),
    [opcionesQuery.data, opcionesQuery.isError],
  );
  const redesAMostrar = red === FILTRO_TODOS ? catalogoRedes : [red];
  const agrupar = redesAMostrar.length > 1;
  // GATE: sin catálogo todavía (carrera habitual en frío: el feed aterriza antes que /opciones)
  // el feed agrupado mentiría ("No generado" en todo); se enseña skeleton hasta tenerlo.
  const cargandoCatalogo =
    red === FILTRO_TODOS && opcionesQuery.isLoading && !opcionesQuery.data;

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
  // y la resalta un instante. La búsqueda encadenada corre sobre el LISTADO BASE: si la URL
  // traía otra vista, se fuerza "todo" primero (que siempre la muestra, esté como esté).
  //
  // SCROLL INFINITO: la idea puede vivir en una página AÚN no cargada. Mientras no aparezca y
  // queden páginas, se encadena la siguiente HASTA `TOPE_PAGINAS_PIEZA`; al hallarla se salta y
  // resalta; al renunciar (tope) o agotar el feed sin verla, se limpia el parámetro y un toast
  // lo dice (antes el enlace moría en silencio).
  const piezaParam = searchParams.get("pieza");
  const [piezaDestacada, setPiezaDestacada] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!piezaParam || feedQuery.isLoading) return;
    if (vista !== "todo") {
      cambiarVista("todo");
      return;
    }
    const existe = grupos.some((g) => g.id === piezaParam);
    const paginas = feedQuery.data?.pages.length ?? 0;
    if (!existe && hasNextPage && paginas < TOPE_PAGINAS_PIEZA) {
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
    if (!existe) {
      toast("No encontramos esa pieza");
      return;
    }
    setPiezaDestacada(piezaParam);
    // Espera a que la idea esté pintada y haz scroll centrándola.
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
    vista,
    feedQuery.isLoading,
    feedQuery.data,
    grupos,
    setSearchParams,
    cambiarVista,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  ]);

  // La vista filtra a nivel de IDEA: una idea aparece si ALGUNA de sus piezas cumple. En las
  // vistas dedicadas el servidor ya filtró (el filtro local es idempotente).
  const vistaActual = VISTAS.find((v) => v.id === vista) ?? VISTAS[0];
  const gruposVista = React.useMemo(
    () => grupos.filter((g) => g.piezas.some(vistaActual.filtra)),
    [grupos, vistaActual],
  );

  // TOPE de la búsqueda encadenada: SOLO en la vista sin `estado` ("Todas",
  // `estadoServidor === undefined`); en las dedicadas el servidor filtra y cada página trae
  // resultados. Con la vista vacía, el sentinel encadena hasta `lotesBusqueda ×
  // PAGINAS_POR_LOTE` páginas; después se para y ofrece "Seguir buscando".
  const vistaVacia = gruposVista.length === 0 && !feedQuery.isLoading && !feedQuery.isError;
  const paginasCargadas = feedQuery.data?.pages.length ?? 0;
  const topeAlcanzado =
    estadoServidor === undefined &&
    vistaVacia &&
    hasNextPage &&
    paginasCargadas >= lotesBusqueda * PAGINAS_POR_LOTE;

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
  // "Actualizar" = VOLVER ARRIBA + refrescar la PRIMERA página (resetQueries), la semántica
  // estándar de refrescar un feed. NO se refetchean las N páginas cargadas (TanStack las
  // encadenaría en serie tras una tarde de scroll); las demás superficies (lista, kanban) solo
  // se marcan stale (refetchType: "none") y los conteos de las pestañas sí refrescan.
  const refrescar = () => {
    const scroller = rootRef.current?.closest("main");
    if (scroller) scroller.scrollTop = 0;
    void queryClient.resetQueries({ queryKey: [...CLAVE_PUBLICACIONES, "feed-ideacion"] });
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES, refetchType: "none" });
    void queryClient.invalidateQueries({ queryKey: [...CLAVE_PUBLICACIONES, "conteo-feed"] });
  };

  // El número del stepper "por fila" es la PREFERENCIA, a secas (nada de "2/5"): si el
  // ancho real acota las columnas efectivas, la explicación va en title + sr-only.
  const topado = colsEfectivas < columnas;
  const valorColumnas = (
    <span
      aria-live="polite"
      title={topado ? `Limitado por el ancho` : undefined}
      className="min-w-5 px-0.5 text-center text-xs font-medium tabular-nums"
    >
      {columnas}
      <span className="sr-only">
        {topado
          ? ` por fila (limitado por el ancho)`
          : " por fila"}
      </span>
    </span>
  );

  // SALIDA de los vacíos de las vistas dedicadas/filtradas: un vacío sin acción es un punto
  // muerto. "Pendientes" y "Publicadas" mandan al feed completo.
  const accionVacio =
    vista === "pendiente" || vista === "publicado" ? (
      <Button variant="outline" size="sm" onClick={() => cambiarVista("todo")}>
        Ver todo el feed
      </Button>
    ) : undefined;

  return (
    <CadenasLoteContexto.Provider value={cadenasLote}>
    <div ref={rootRef}>
      <AccionesPagina>
        <div className="flex items-center gap-1">
          {/* "Por fila" directo en la barra: no es un ajuste sino un control de vista tipo
              zoom, de uso constante mientras se lee el feed. Sin icono: el grupo rotulado
              (aria-label) + los steppers se explican solos. */}
          <div role="group" aria-label="Piezas por fila" className="flex items-center gap-1">
            <Tooltip label="Menos por fila">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-foreground"
                onClick={() => ajustarColumnas(-1)}
                disabled={columnas <= COLUMNAS_MIN}
                aria-label="Menos por fila"
              >
                <Minus className="h-4 w-4" />
              </Button>
            </Tooltip>
            {valorColumnas}
            <Tooltip label="Más por fila">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-foreground"
                onClick={() => ajustarColumnas(1)}
                disabled={columnas >= COLUMNAS_MAX}
                aria-label="Más por fila"
              >
                <Plus className="h-4 w-4" />
              </Button>
            </Tooltip>
          </div>
          {/* Frontera con el menú: acción de otra naturaleza (refresco, no densidad). */}
          <span aria-hidden="true" className="mx-1 h-4 w-px bg-border" />
          {/* Actualizar (el verbo de la casa): se deshabilita SOLO durante un refresco
              real, no en cada página del scroll infinito. */}
          <MenuAcciones>
            <ItemMenu icono={RefreshCw} onClick={refrescar} disabled={refrescando}>
              Actualizar
            </ItemMenu>
          </MenuAcciones>
          {/* Frontera con el alta: crear un post es de OTRA naturaleza que ver/refrescar. */}
          <span aria-hidden="true" className="mx-1 h-4 w-px bg-border" />
          {/* Alta directa: tu copy FINAL, tal cual, como borrador por red — el mismo motor
              que las piezas que nacen al usar una noticia/investigación, sin generación.
              Sin tooltip: el botón ya se nombra a sí mismo (texto visible). */}
          <Button variant="outline" size="sm" className="h-8 gap-1.5" onClick={() => setCreandoPost(true)}>
            <Plus className="h-4 w-4" />
            Crear post
          </Button>
        </div>
      </AccionesPagina>
      <DialogoCrearPost abierto={creandoPost} onCerrar={() => setCreandoPost(false)} />

      {/* UN SOLO EJE de composición: pestañas, estados (skeleton/error/vacío), feed y pie viven
          en la MISMA columna centrada (`MAX_W_FEED` por columnas efectivas). Antes las pestañas
          iban pegadas al borde y los vacíos a TODO el ancho: la página saltaba de eje al
          cambiar de pestaña en monitores anchos. */}
      <div className={cn("mx-auto w-full", MAX_W_FEED[colsEfectivas])}>
        <h2 className="sr-only">Feed de ideación</h2>
        {/* Pestañas (control segmentado en UNA fila), solas en su fila. El scroll horizontal de
            emergencia vive FUERA del rail (dentro recortaba el anillo de foco y pintaba scrollbar
            sobre las píldoras). El badge cuenta PIEZAS con el total real del servidor y se pinta
            en cuanto su número está resuelto, no solo con el feed agotado. */}
        <div className="mb-4 overflow-x-auto">
          <Tabs value={vista} onValueChange={(v) => cambiarVista(v as Vista)}>
            <TabsList className="w-fit gap-1" aria-label="Vista del feed">
              {VISTAS.map((v) => (
                <TabsTrigger key={v.id} value={v.id} className="gap-1.5">
                  <ContenidoPestanaVista
                    vista={v}
                    conteo={conteoVista[v.id]}
                    // Énfasis pasivo "te toca decidir" (mismo acento keni que el pulgar de
                    // PostFeed) cuando hay piezas esperando OK; en cero, neutro.
                    enfasis={v.id === "pendiente" && (totalRevision ?? 0) > 0}
                  />
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        {/* Feed. Con TODAS las redes: una MATRIZ por idea (un bloque por idea; dentro, una rejilla
            con sus redes generadas y la franja "Falta generar") — así no se mezclan ideas en una
            fila. Filtrado a UNA red: rejilla PLANA con microcabecera por celda. `colsEfectivas`
            fija cuántas por fila (la preferencia, acotada al ancho real). */}
        {feedQuery.isLoading || cargandoCatalogo ? (
          // El skeleton ESPEJA el contenedor final (misma retícula/anchos) y la ANATOMÍA de la
          // tarjeta (cabecera + imagen 4:5 + copy + acciones): sin salto de layout al aterrizar.
          // También cubre la espera del catálogo de /opciones (sin él, la matriz mentiría).
          <div
            className={
              colsEfectivas === 1
                ? "space-y-4"
                : cn("grid items-start gap-4", GRID_COLS[colsEfectivas])
            }
          >
            {Array.from({ length: Math.max(3, colsEfectivas) }, (_, i) => (
              <SkeletonPost key={i} />
            ))}
          </div>
        ) : feedQuery.isError && piezas.length === 0 ? (
          // El BloqueError a página completa queda para el PRIMER load: con páginas ya cargadas
          // un fallo de `fetchNextPage` NO descarta el feed visible (el pie ofrece reintentar).
          <BloqueError
            titulo="Error al cargar"
            mensaje={mensajeError(feedQuery.error)}
            onReintentar={() => void feedQuery.refetch()}
            cargando={feedQuery.isFetching}
          />
        ) : gruposVista.length === 0 ? (
          feedQuery.isError ? (
            // Hay datos base pero la vista filtrada quedó vacía y el último "cargar más" falló.
            <PieFeed estado="error" onReintentar={() => void fetchNextPage()} />
          ) : topeAlcanzado ? (
            // VACÍO HONESTO: solo se afirma "no hay nada" cuando el feed está agotado. En la
            // vista filtrada en cliente, si quedan páginas el sentinel encadena HASTA EL TOPE
            // del lote; ahí se para y el vacío ofrece "Seguir buscando".
            <EstadoVacio
              icono={vistaActual.icono}
              titulo={vistaActual.vacio.titulo}
              accion={
                <Button variant="outline" size="sm" onClick={() => setLotesBusqueda((n) => n + 1)}>
                  Seguir buscando
                </Button>
              }
            />
          ) : hasNextPage ? (
            <PieFeed estado={estadoServidor === undefined ? "buscando" : "cargando"} />
          ) : (
            <EstadoVacio
              icono={vistaActual.icono}
              titulo={vistaActual.vacio.titulo}
              texto={vistaActual.vacio.texto}
              accion={accionVacio}
            />
          )
        ) : agrupar ? (
          // Sin role="feed" aquí: sus hijos directos no son <article> (cada grupo agrupa varios).
          <div className="space-y-8" aria-busy={isFetchingNextPage}>
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
                  // Con una marca activa en la topbar, repetirla en cada grupo compite con el título.
                  mostrarMarca={marcaActiva == null}
                  // En las vistas filtradas el grupo enseña SOLO lo que cumple el filtro (sin
                  // tarjetas ajenas); la matriz completa es de "Todo el feed".
                  filtra={vista === "todo" ? undefined : vistaActual.filtra}
                />
              </div>
            ))}
          </div>
        ) : (
          <div
            className={
              colsEfectivas === 1
                ? "space-y-4"
                : cn("grid items-start gap-4", GRID_COLS[colsEfectivas])
            }
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
                  {/* Microcabecera de la idea: filtrado a una red no hay cabecera de grupo y sin
                      esto no se sabe de qué marca/tema es cada pieza sin abrirla. Variante
                      "micro": se repite en CADA celda y no debe gritar como inicio de sección. */}
                  <CabeceraIdea
                    marca={g.marca_nombre}
                    titulo={g.titulo}
                    mostrarMarca={marcaActiva == null}
                    tamano="micro"
                  />
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
            vacía: así la paginación no muere afirmando un vacío falso); el tope del lote y un
            error de "cargar más" lo apagan sin tirar el feed. El pie (`PieFeed`) da feedback sin
            saltos de layout, y en error ofrece reintentar SOLO la página fallida. */}
        {!feedQuery.isLoading &&
          !cargandoCatalogo &&
          !(feedQuery.isError && piezas.length === 0) && (
            <>
              {hasNextPage && !feedQuery.isError && (
                <div ref={sentinelRef} aria-hidden className="h-px w-full" />
              )}
              {gruposVista.length > 0 &&
                (feedQuery.isError ? (
                  <PieFeed estado="error" onReintentar={() => void fetchNextPage()} />
                ) : isFetchingNextPage ? (
                  <PieFeed estado="cargando" />
                ) : !hasNextPage ? (
                  <PieFeed estado="fin" />
                ) : null)}
            </>
          )}
      </div>
    </div>
    </CadenasLoteContexto.Provider>
  );
}
