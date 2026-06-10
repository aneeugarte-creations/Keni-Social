/**
 * FEED MÓVIL para revisores (`/feed`).
 *
 * Visión (#qa-movil-feed): el equipo (revisores/productores/editores) revisa en el
 * móvil un FEED tipo red social —una columna, tarjetas a ancho completo— en vez de
 * la consola completa de administración (que opera una sola persona). Aquí solo se
 * APRUEBA, RECHAZA, COMENTA y CREA; nada de sidebar ni navegación lateral.
 *
 * Reutiliza lo existente (MISMA tarjeta que el feed de escritorio):
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
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { MARCA_TODAS, marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { PostFeed } from "@/pages/feed/PostFeed";
import { CadenasLoteContexto, useCadenasLote } from "@/pages/feed/use-cadenas-lote";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import type { CuerpoCrearContenido } from "@/types";

/** Estados que ve el revisor en el feed: lo pendiente de su aprobación y lo ya aprobado. */
type Bandeja = "en_revision" | "aprobado";

const BANDEJAS: { id: Bandeja; etiqueta: string }[] = [
  // Mismo vocabulario que el feed de escritorio: "Por aprobar" (el OK), no "Por revisar".
  { id: "en_revision", etiqueta: "Por aprobar" },
  { id: "aprobado", etiqueta: "Aprobadas" },
];

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
          <DialogDescription>
            Crea una idea rápida; el copy se afina luego en el editor.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
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
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button variant="positive" onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Crear
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Página raíz del feed móvil. */
export default function MobileFeed() {
  const { usuario } = useSesion();
  const queryClient = useQueryClient();

  const [bandeja, setBandeja] = React.useState<Bandeja>("en_revision");
  // Pre-filtra por las marcas del usuario: si tiene exactamente una, arranca en ella;
  // si tiene varias o ninguna asignada, arranca en "todas" (sus marcas). Memoizado
  // para no recalcular el array (y no invalidar dependencias) en cada render.
  const marcasUsuario = React.useMemo(() => usuario?.marcas ?? [], [usuario?.marcas]);
  const [marca, setMarca] = React.useState<string>(
    marcasUsuario.length === 1 ? marcasUsuario[0] : MARCA_TODAS,
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

  // SCROLL INFINITO (feed tipo red social): primera página pequeña e instantánea por keyset
  // `creado DESC`; se piden más al hacer scroll (sentinel + IntersectionObserver). El backend
  // devuelve `paginacion.cursor_siguiente` mientras haya más; al omitirlo se apaga `hasNextPage`.
  const feedQuery = useInfiniteQuery({
    queryKey: [...CLAVE_PUBLICACIONES, "feed", bandeja, marca],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api.publicaciones(
        { estado: bandeja, marca: marcaParam(marca), feed: "1", cursor: pageParam },
        signal,
      ),
    getNextPageParam: (ultima) => ultima.paginacion?.cursor_siguiente ?? undefined,
  });

  // Aplana todas las páginas cargadas. Si el usuario tiene marcas asignadas y el filtro está en
  // "todas", restringimos el listado a sus marcas en cliente (defensa extra al pre-filtro).
  const piezas = React.useMemo(() => {
    const todas = (feedQuery.data?.pages ?? []).flatMap((p) => p.publicaciones);
    if (marca === MARCA_TODAS && marcasUsuario.length > 0) {
      return todas.filter((p) => marcasUsuario.includes(p.marca));
    }
    return todas;
  }, [feedQuery.data, marca, marcasUsuario]);

  // ANTI-N+1: las cadenas de aprobación de la página en UN lote; los `PostFeed` las
  // consumen vía contexto (igual que en el feed de escritorio).
  const cadenasLote = useCadenasLote(piezas);

  // Sentinel del fondo del feed: al acercarse, pide la siguiente página (con guardas).
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
      { rootMargin: "600px 0px" },
    );
    obs.observe(nodo);
    return () => obs.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  // SCROLL MAGNÉTICO POR PIEZA (feed estilo red social): activa scroll-snap en el documento (el
  // que hace scroll en esta pantalla) mientras está montada y lo revierte al salir. `proximity`
  // (no `mandatory`): las tarjetas superan la altura del viewport y `mandatory` secuestra el
  // scroll del pie. `scrollPadding` superior deja sitio a la cabecera sticky para que la pieza
  // no quede tapada al encajar.
  React.useEffect(() => {
    const el = document.documentElement;
    const prevTipo = el.style.scrollSnapType;
    const prevPad = el.style.scrollPaddingTop;
    el.style.scrollSnapType = "y proximity";
    el.style.scrollPaddingTop = "8rem";
    return () => {
      el.style.scrollSnapType = prevTipo;
      el.style.scrollPaddingTop = prevPad;
    };
  }, []);

  const refrescar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });

  return (
    <div className="flex min-h-dvh w-full max-w-full flex-col overflow-x-hidden bg-muted/20">
      {/* Cabecera sticky: bandejas + filtro por marca. */}
      <header className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur">
        <div className="flex items-center gap-2 px-4 py-2.5">
          <h1 className="text-base font-semibold">Feed de revisión</h1>
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto"
            onClick={refrescar}
            aria-label="Refrescar"
          >
            <RefreshCw className={feedQuery.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          </Button>
        </div>
        <div className="px-4 pb-2">
          <Tabs value={bandeja} onValueChange={(v) => setBandeja(v as Bandeja)}>
            <TabsList className="w-full" aria-label="Bandeja">
              {BANDEJAS.map((b) => (
                <TabsTrigger key={b.id} value={b.id} className="flex-1">
                  {b.etiqueta}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
        <div className="px-4 pb-2.5">
          <SelectorMarca
            marcas={marcas}
            valor={marca}
            onCambio={setMarca}
            incluirTodas
            etiquetaTodas={marcasUsuario.length > 0 ? "Todas mis marcas" : "Todas las marcas"}
            className="w-full"
          />
        </div>
      </header>

      {/* Columna del feed. Padding inferior para no quedar tapado por la barra fija. */}
      <main className="mx-auto w-full max-w-xl flex-1 pb-24">
        {feedQuery.isLoading ? (
          <div className="space-y-4 p-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-80 w-full rounded-xl" />
            ))}
          </div>
        ) : feedQuery.isError ? (
          <div className="p-4">
            <BloqueError
              titulo="No se pudo cargar el feed"
              mensaje={mensajeError(feedQuery.error)}
              onReintentar={() => void feedQuery.refetch()}
              cargando={feedQuery.isFetching}
            />
          </div>
        ) : piezas.length === 0 ? (
          <div className="p-6">
            <EstadoVacio
              titulo={bandeja === "en_revision" ? "Nada por aprobar" : "Sin piezas aprobadas"}
              texto={
                bandeja === "en_revision"
                  ? "Cuando haya piezas en revisión para tus marcas, aparecerán aquí."
                  : "Las piezas que apruebes se mostrarán en esta bandeja."
              }
            />
          </div>
        ) : (
          <CadenasLoteContexto.Provider value={cadenasLote}>
            {/* MISMA tarjeta que el feed de escritorio: PostFeed es autocontenido (cadena de
                aprobación, like/dislike con sus gates, editor y comentarios en línea). */}
            <div className="space-y-4 p-3">
              {piezas.map((p) => (
                <div key={p.id} className="snap-start">
                  <PostFeed publicacion={p} />
                </div>
              ))}
            </div>
            {/* SCROLL INFINITO: sentinel invisible + spinner "Cargando más…" al fondo. */}
            <div ref={sentinelRef} aria-hidden className="h-px w-full" />
            {isFetchingNextPage && (
              <div
                className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground"
                role="status"
                aria-live="polite"
              >
                <Loader2 className="h-4 w-4 animate-spin" />
                Cargando más…
              </div>
            )}
          </CadenasLoteContexto.Provider>
        )}
      </main>

      {/* Barra de acciones inferior fija (thumb-reachable): alta de pieza. */}
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-background/95 px-4 py-3 backdrop-blur">
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
