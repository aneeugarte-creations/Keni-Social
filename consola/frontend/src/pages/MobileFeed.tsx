/**
 * FEED MÓVIL para revisores (`/feed`).
 *
 * Visión (#qa-movil-feed): el equipo (revisores/productores/editores) revisa en el
 * móvil un FEED tipo red social —una columna, tarjetas a ancho completo— en vez de
 * la consola completa de administración (que opera una sola persona). Aquí se
 * APRUEBA, RECHAZA, COMENTA y CREA; nada de sidebar ni navegación lateral.
 *
 * Reutiliza lo existente (MISMA tarjeta y MISMA partición que el feed de escritorio):
 *  - `VISTAS` (vistas.tsx): las 4 pestañas-partición del ciclo, con conteos exactos
 *    (`useConteosFeed`) y el mismo vocabulario. Aquí el DEFAULT sin parámetro es
 *    "Por aprobar" (el trabajo del revisor móvil), no "Todo".
 *  - `PostFeed` por pieza: cadena de aprobación visible, like/dislike como toggle con sus
 *    gates (`elegibilidadOK`, comentarios sin resolver), badge de etapa, editor y
 *    comentarios en línea. Sin duplicar lógica de aprobación aquí.
 *  - `useCadenasLote` (anti-N+1): las cadenas de la página en UNA llamada.
 *  - El alta rápida (`crearContenido`) en la barra inferior.
 *  - `GET /api/publicaciones` filtrado por estado/marca (sin backend nuevo).
 *
 * Esta ruta vive FUERA del `AppShell` (layout propio, sin sidebar); es acceso directo
 * por enlace, así que no se registra en el catálogo de apps.
 */
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Loader2, Plus, RefreshCw } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { MARCA_TODAS, marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { PieFeed, SkeletonPost, useSentinelInfinito } from "@/pages/feed/infinito";
import { PostFeed } from "@/pages/feed/PostFeed";
import { CadenasLoteContexto, useCadenasLote } from "@/pages/feed/use-cadenas-lote";
import {
  ContenidoPestanaVista,
  ESTADO_SERVIDOR_DE_VISTA,
  PAGINAS_POR_LOTE,
  useConteosFeed,
  VISTAS,
  vistaDesdeParam,
  type Vista,
} from "@/pages/feed/vistas";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import type { CuerpoCrearContenido } from "@/types";

// Mismo padding para el skeleton y el listado real: el propósito de `SkeletonPost` es que el
// contenido aterrice SIN desplazarse (antes 4px de salto entre p-4 y p-3).
const CLASES_LISTA = "space-y-4 p-4";

/**
 * Diálogo de creación RÁPIDA (a pantalla completa en móvil): título + nota.
 * Reusa `POST /api/contenido`; el equipo afina el copy luego en el editor. Mantenemos
 * el alta mínima a propósito (el flujo completo vive en la consola de escritorio).
 *
 * La MARCA NO se elige aquí (ya no hay selector duplicado): la pieza nace en la marca
 * ACTIVA de la superficie (la del filtro de marca de la cabecera, `marcaInicial`); en
 * "todas" nace sin marca y se asigna luego en el editor.
 */
function DialogoCrear({
  abierto,
  marcaInicial,
  onCerrar,
}: {
  abierto: boolean;
  marcaInicial: string;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [descripcion, setDescripcion] = React.useState("");

  React.useEffect(() => {
    if (abierto) {
      setTitulo("");
      setDescripcion("");
    }
  }, [abierto]);

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearContenido = {
        titulo: titulo.trim(),
        clase: "contenido",
        marca: marcaInicial === MARCA_TODAS ? "" : marcaInicial,
        descripcion: descripcion.trim(),
      };
      return api.crearContenido(cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      toast.success("Pieza creada.");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = titulo.trim().length > 0 && !crear.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-dvh h-dvh max-w-full overflow-y-auto rounded-none sm:h-auto sm:max-h-[90vh] sm:max-w-md sm:rounded-lg">
        <DialogHeader>
          <DialogTitle>Nueva pieza</DialogTitle>
        </DialogHeader>
        {/* <form>: el Enter/«ir» del teclado móvil envía el alta (el flujo que más se repite). */}
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (puedeCrear) crear.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="feed-crear-titulo">Título</Label>
            <Input
              id="feed-crear-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              maxLength={200}
              autoFocus
              placeholder="¿De qué trata la pieza?"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="feed-crear-desc">Nota (opcional)</Label>
            <Textarea
              id="feed-crear-desc"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              rows={4}
              placeholder="Contexto, ángulo, enlaces…"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCerrar} disabled={crear.isPending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!puedeCrear}>
              {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Crear
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Página raíz del feed móvil. */
export default function MobileFeed() {
  const { usuario } = useSesion();
  const queryClient = useQueryClient();

  // La vista vive en la URL (`?vista=`), igual que en el feed de escritorio: sobrevive al
  // refresco y es compartible. DEFAULT MÓVIL deliberado: sin parámetro se arranca en
  // "Por aprobar" (el trabajo del revisor), no en "Todo". El parámetro LEGADO
  // `?bandeja=aprobado` (deep-links compartidos antes de unificar) mapea a "publicado".
  const [searchParams, setSearchParams] = useSearchParams();
  const vista: Vista = vistaDesdeParam(
    searchParams.get("vista") ??
      (searchParams.get("bandeja") === "aprobado" ? "publicado" : null),
    "por_aprobar",
  );
  const cambiarVista = React.useCallback(
    (v: Vista) => {
      setSearchParams(
        (prev) => {
          prev.delete("bandeja"); // migra el parámetro legado al canónico
          if (v === "por_aprobar") prev.delete("vista");
          else prev.set("vista", v);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );
  // Marcas del usuario: si tiene exactamente una, esa es la marca por defecto; con varias o
  // ninguna asignada, "todas" (sus marcas). Memoizado para no recalcular el array por render.
  const marcasUsuario = React.useMemo(() => usuario?.marcas ?? [], [usuario?.marcas]);
  // La MARCA también vive en la URL (`?marca=`), DERIVADA en cada render: sin parámetro vale
  // el default calculado, así la sesión que aterriza tarde (carga fría) preselecciona sola la
  // única marca del usuario sin workarounds de estado.
  const marcaDefecto = marcasUsuario.length === 1 ? marcasUsuario[0] : MARCA_TODAS;
  const marca = searchParams.get("marca") ?? marcaDefecto;
  const cambiarMarca = React.useCallback(
    (v: string) => {
      setSearchParams(
        (prev) => {
          if (v === marcaDefecto) prev.delete("marca");
          else prev.set("marca", v);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams, marcaDefecto],
  );

  const [crearAbierto, setCrearAbierto] = React.useState(false);

  // Opciones (estados + catálogo de marcas) para el filtro y el editor.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const catalogoMarcas = opcionesQuery.data?.marcas ?? [];
  // Acota el selector a las marcas del usuario (si las tiene); admin/sin asignar ve todas.
  const marcas =
    marcasUsuario.length > 0
      ? catalogoMarcas.filter((m) => marcasUsuario.includes(m.id))
      : catalogoMarcas;

  // CONSULTA DEDICADA por estado (misma mecánica que el escritorio, ver vistas.tsx): "En
  // preparación" y "Por aprobar" llegan filtradas del servidor; "Todo" y "Aprobadas y
  // publicadas" comparten la query base sin `estado` y la última filtra en cliente.
  const estadoServidor = ESTADO_SERVIDOR_DE_VISTA[vista];

  // SCROLL INFINITO (feed tipo red social): primera página pequeña e instantánea por keyset
  // `creado DESC`; se piden más al hacer scroll (sentinel + IntersectionObserver). El backend
  // devuelve `paginacion.cursor_siguiente` mientras haya más; al omitirlo se apaga `hasNextPage`.
  const feedQuery = useInfiniteQuery({
    queryKey: [...CLAVE_PUBLICACIONES, "feed", estadoServidor ?? "todos", marca],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api.publicaciones(
        { estado: estadoServidor, marca: marcaParam(marca), feed: "1", cursor: pageParam },
        signal,
      ),
    getNextPageParam: (ultima) => ultima.paginacion?.cursor_siguiente ?? undefined,
    // La frescura llega por el botón Actualizar y las actualizaciones in-place tras cada
    // reacción: sin refetch en cadena de N páginas en cada vuelta a la pestaña.
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // Conteos exactos de los badges (compartidos con el escritorio; ver vistas.tsx).
  const { totalRevision, conteoVista } = useConteosFeed({ marca: marcaParam(marca) });

  // Aplana todas las páginas cargadas y aplica el filtro de la vista (idempotente en las
  // dedicadas; el filtro REAL de "Aprobadas y publicadas"). Si el usuario tiene marcas
  // asignadas y el filtro está en "todas", restringimos a sus marcas (defensa extra).
  const vistaActual = VISTAS.find((v) => v.id === vista) ?? VISTAS[0];
  const piezas = React.useMemo(() => {
    let todas = (feedQuery.data?.pages ?? []).flatMap((p) => p.publicaciones);
    todas = todas.filter(vistaActual.filtra);
    if (marca === MARCA_TODAS && marcasUsuario.length > 0) {
      return todas.filter((p) => marcasUsuario.includes(p.marca));
    }
    return todas;
  }, [feedQuery.data, vistaActual, marca, marcasUsuario]);

  // ANTI-N+1: las cadenas de aprobación de la página en UN lote; los `PostFeed` las
  // consumen vía contexto (igual que en el feed de escritorio).
  const cadenasLote = useCadenasLote(piezas);

  const { hasNextPage, isFetchingNextPage, fetchNextPage } = feedQuery;

  // SCROLL MAGNÉTICO POR PIEZA estilo Reels/Shorts. OJO: el snap ya NO va en el documento.
  // El CSS global (index.css) bloquea el scroll de html/body (`overflow: hidden`, para
  // matar el rubber-band/pull-to-refresh de iOS), así que el documento nunca se mueve y
  // un scroll-snap puesto ahí es INERTE (así se perdió el imán del feed). Esta pantalla
  // scrollea en su PROPIO contenedor (`scrollerRef`, el div raíz: overflow-y-auto +
  // snap-y snap-mandatory). Cada pieza ocupa un SLOT de un viewport (ver el wrapper de la
  // lista): se ve UNA pieza encuadrada y el scroll aterriza exacto en la siguiente; una
  // tarjeta más larga scrollea POR DENTRO de su slot.
  const scrollerRef = React.useRef<HTMLDivElement | null>(null);

  // TOPE de la búsqueda encadenada (mismo mecanismo que el escritorio): SOLO en la vista que
  // filtra en cliente ("Aprobadas y publicadas"). Con la vista vacía, el sentinel encadena
  // hasta `lotesBusqueda × PAGINAS_POR_LOTE` páginas; ahí se para y ofrece "Seguir buscando".
  // Cambio de contexto (vista o marca): el lote se reinicia y se vuelve arriba.
  const [lotesBusqueda, setLotesBusqueda] = React.useState(1);
  React.useEffect(() => {
    setLotesBusqueda(1);
    // Llamada opcional: jsdom no implementa scrollTo en elementos.
    scrollerRef.current?.scrollTo?.(0, 0);
  }, [vista, marca]);
  const vistaVacia = piezas.length === 0 && !feedQuery.isLoading && !feedQuery.isError;
  const paginasCargadas = feedQuery.data?.pages.length ?? 0;
  const topeAlcanzado =
    estadoServidor === undefined &&
    vistaVacia &&
    hasNextPage &&
    paginasCargadas >= lotesBusqueda * PAGINAS_POR_LOTE;
  // ¿El listado visible puede perder filas EN CLIENTE? Pasa en la vista de 3 estados (filtra
  // `vistaActual.filtra`) y también en "todas mis marcas" (defensa por `marcasUsuario`): la
  // página cargada pudo venir entera de otras marcas/estados, así que el pie dice "buscando"
  // (no "cargando", que afirmaría que ya hay resultados en camino).
  const filtraEnCliente =
    estadoServidor === undefined || (marca === MARCA_TODAS && marcasUsuario.length > 0);

  // Sentinel del fondo del feed (compartido con escritorio, ver `pages/feed/infinito.tsx`).
  const sentinelRef = useSentinelInfinito({
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    habilitado: !topeAlcanzado,
  });

  // GEOMETRÍA MEDIDA, no hardcodeada: la cabecera sticky puede tener 1 o 2 filas (selector de
  // marca) y la barra inferior fija crece con el safe-area de iOS. Un ResizeObserver escribe
  // las alturas REALES en variables CSS del scroller (`--feed-top` / `--feed-bottom`); el
  // scroll-padding y el alto del slot las consumen. Así ningún slot queda ocluido por la barra
  // fija ni deja hueco bajo la cabecera. Los fallbacks (6rem/4.5rem, en el style del
  // contenedor) cubren jsdom/SSR, donde el RO no dispara.
  const headerRef = React.useRef<HTMLElement | null>(null);
  const barraRef = React.useRef<HTMLDivElement | null>(null);
  React.useLayoutEffect(() => {
    const raiz = scrollerRef.current;
    if (!raiz) return;
    const medir = () => {
      const top = headerRef.current?.offsetHeight ?? 0;
      const bottom = barraRef.current?.offsetHeight ?? 0;
      // Solo con medidas reales (>0): en jsdom el layout no existe y los fallbacks valen.
      if (top > 0) raiz.style.setProperty("--feed-top", `${top}px`);
      if (bottom > 0) raiz.style.setProperty("--feed-bottom", `${bottom}px`);
    };
    medir();
    if (typeof ResizeObserver !== "function") return;
    const ro = new ResizeObserver(medir);
    if (headerRef.current) ro.observe(headerRef.current);
    if (barraRef.current) ro.observe(barraRef.current);
    return () => ro.disconnect();
  }, []);

  // El spinner del botón Actualizar SOLO en un refresco real, no en cada página del scroll
  // (mismo comportamiento que el feed de escritorio). "Actualizar" = volver arriba + refrescar
  // la PRIMERA página (reset, no refetch en serie de todas las cargadas); el resto de
  // superficies solo se marca stale y los conteos de las pestañas sí refrescan.
  const refrescando = feedQuery.isRefetching && !feedQuery.isFetchingNextPage;
  const refrescar = () => {
    scrollerRef.current?.scrollTo?.(0, 0);
    void queryClient.resetQueries({ queryKey: [...CLAVE_PUBLICACIONES, "feed"] });
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES, refetchType: "none" });
    void queryClient.invalidateQueries({ queryKey: [...CLAVE_PUBLICACIONES, "conteo-feed"] });
  };
  const botonActualizar = (
    <Button
      variant="ghost"
      size="icon"
      onClick={refrescar}
      disabled={refrescando}
      aria-label="Actualizar"
      title="Actualizar"
    >
      <RefreshCw className={refrescando ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
    </Button>
  );
  // Con UNA sola marca asignada el selector no es una decisión (dos opciones idénticas): se
  // oculta y las pestañas comparten fila con Actualizar. Con varias (o admin), dos filas.
  const conSelectorMarca = marcasUsuario.length !== 1;
  // Las MISMAS 4 vistas que el escritorio (vistas.tsx), con sus conteos exactos.
  const tabs = (
    <Tabs
      value={vista}
      onValueChange={(v) => cambiarVista(v as Vista)}
      className={conSelectorMarca ? undefined : "min-w-0 flex-1"}
    >
      <TabsList className="w-full" aria-label="Vista del feed">
        {VISTAS.map((v) => (
          <TabsTrigger key={v.id} value={v.id} className="flex-1 gap-1.5">
            <ContenidoPestanaVista
              vista={v}
              conteo={conteoVista[v.id]}
              enfasis={v.id === "por_aprobar" && (totalRevision ?? 0) > 0}
            />
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );

  return (
    /* SCROLLER PROPIO de la pantalla (el documento está bloqueado por el CSS global):
       alto fijo de un viewport, scroll vertical interno y el imán Reels aquí mismo
       (snap-y mandatory + scroll-padding con la altura REAL de la cabecera sticky). */
    <div
      ref={scrollerRef}
      className="flex h-dvh w-full max-w-full snap-y snap-mandatory flex-col overflow-y-auto overflow-x-hidden bg-background"
      style={
        {
          scrollPaddingTop: "var(--feed-top)",
          "--feed-top": "6rem",
          "--feed-bottom": "4.5rem",
        } as React.CSSProperties
      }
    >
      {/* Cabecera sticky COMPACTA (sin fila de título: se va un tercio del viewport en chrome). */}
      <header
        ref={headerRef}
        className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur"
      >
        <h1 className="sr-only">Feed de revisión</h1>
        {conSelectorMarca ? (
          <>
            <div className="flex items-center gap-2 px-4 pb-2 pt-2.5">
              <SelectorMarca
                marcas={marcas}
                valor={marca}
                onCambio={cambiarMarca}
                incluirTodas
                etiquetaTodas={marcasUsuario.length > 0 ? "Todas mis marcas" : "Todas las marcas"}
                className="min-w-0 flex-1"
              />
              {botonActualizar}
            </div>
            <div className="px-4 pb-2">{tabs}</div>
          </>
        ) : (
          <div className="flex items-center gap-2 px-4 py-2">
            {tabs}
            {botonActualizar}
          </div>
        )}
      </header>

      {/* Columna del feed. Padding inferior para no quedar tapado por la barra fija. */}
      <main className="mx-auto w-full max-w-xl flex-1 pb-28">
        <CadenasLoteContexto.Provider value={cadenasLote}>
          {feedQuery.isLoading ? (
            <div className={CLASES_LISTA}>
              {[0, 1, 2].map((i) => (
                <SkeletonPost key={i} />
              ))}
            </div>
          ) : feedQuery.isError && piezas.length === 0 ? (
            // El BloqueError a pantalla completa queda para el PRIMER load: con páginas ya
            // cargadas un fallo de "cargar más" NO descarta el feed (el pie ofrece reintentar).
            <div className="p-4">
              <BloqueError
                titulo="No se pudo cargar el feed"
                mensaje={mensajeError(feedQuery.error)}
                onReintentar={() => void feedQuery.refetch()}
                cargando={feedQuery.isFetching}
              />
            </div>
          ) : (
            <>
              {piezas.length > 0 ? (
                /* MISMA tarjeta que el feed de escritorio: PostFeed es autocontenido (cadena de
                   aprobación, like/dislike con sus gates, editor y comentarios en línea).
                   Mismo padding que el skeleton: sin salto de 4px al aterrizar. */
                <div className={CLASES_LISTA} role="feed" aria-busy={isFetchingNextPage}>
                  {piezas.map((p) => (
                    /* SLOT estilo Reels: un viewport por pieza (alto = pantalla menos la
                       cabecera y la barra fija MEDIDAS, no estimadas: la fila de like/dislike
                       nunca scrollea hacia la franja ocluida por la barra), snap obligatorio
                       sin saltarse piezas (`snap-always`). Una tarjeta más larga que el slot
                       scrollea POR DENTRO; `tabIndex` hace ese scroll interno operable por
                       teclado (WCAG 2.1.1: Firefox/Safari no enfocan scrollers solos). */
                    <div
                      key={p.id}
                      tabIndex={0}
                      role="group"
                      aria-label={p.titulo}
                      className="h-[calc(100dvh-var(--feed-top)-var(--feed-bottom))] snap-start snap-always overflow-y-auto"
                    >
                      <PostFeed publicacion={p} />
                    </div>
                  ))}
                </div>
              ) : feedQuery.isError ? (
                // Hay datos base pero la vista filtrada quedó vacía y "cargar más" falló.
                <PieFeed estado="error" onReintentar={() => void fetchNextPage()} />
              ) : topeAlcanzado ? (
                // Tope del lote en la vista filtrada EN CLIENTE: mismo trato que el escritorio.
                <div className="p-6">
                  <EstadoVacio
                    icono={vistaActual.icono}
                    titulo={vistaActual.vacio.titulo}
                    texto="Puede haber piezas más antiguas aún sin cargar."
                    accion={
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setLotesBusqueda((n) => n + 1)}
                      >
                        Seguir buscando
                      </Button>
                    }
                  />
                </div>
              ) : hasNextPage ? (
                // VACÍO HONESTO: la página cargada puede ser toda de otras marcas (filtro en
                // cliente); mientras queden páginas se busca, no se afirma "nada por aprobar".
                <PieFeed estado={filtraEnCliente ? "buscando" : "cargando"} />
              ) : (
                <div className="p-6">
                  <EstadoVacio
                    icono={vistaActual.icono}
                    titulo={vistaActual.vacio.titulo}
                    texto={vistaActual.vacio.texto}
                  />
                </div>
              )}
              {/* SCROLL INFINITO: el sentinel se monta SIEMPRE que queden páginas (también con
                  el listado filtrado vacío) + pie de estado compartido; un error de "cargar
                  más" lo apaga y el pie ofrece reintentar SOLO la página fallida. */}
              {hasNextPage && !feedQuery.isError && (
                <div ref={sentinelRef} aria-hidden className="h-px w-full" />
              )}
              {piezas.length > 0 &&
                (feedQuery.isError ? (
                  <PieFeed estado="error" onReintentar={() => void fetchNextPage()} />
                ) : isFetchingNextPage ? (
                  <PieFeed estado="cargando" />
                ) : !hasNextPage ? (
                  <PieFeed estado="fin" />
                ) : null)}
            </>
          )}
        </CadenasLoteContexto.Provider>
      </main>

      {/* Barra de acciones inferior fija (thumb-reachable): alta de pieza. El padding inferior
          respeta el safe-area de iOS (home indicator); su altura REAL la mide el RO de arriba. */}
      <div
        ref={barraRef}
        className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-background/95 px-4 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur"
      >
        <div className="mx-auto flex w-full max-w-xl">
          <Button className="w-full" onClick={() => setCrearAbierto(true)}>
            <Plus className="h-4 w-4" />
            Crear pieza
          </Button>
        </div>
      </div>

      <DialogoCrear
        abierto={crearAbierto}
        marcaInicial={marca}
        onCerrar={() => setCrearAbierto(false)}
      />
    </div>
  );
}
