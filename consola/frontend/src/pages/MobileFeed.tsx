/**
 * FEED MÓVIL para revisores (`/feed`).
 *
 * Visión (#qa-movil-feed): el equipo (revisores/productores/editores) revisa en el
 * móvil un FEED tipo red social —una columna, tarjetas a ancho completo— en vez de
 * la consola completa de administración (que opera una sola persona). Aquí solo se
 * APRUEBA, RECHAZA, COMENTA y CREA; nada de sidebar ni navegación lateral.
 *
 * Reutiliza lo existente:
 *  - `VistaPreviaRed` para pintar cada pieza como se vería en su red.
 *  - El editor rico `DialogoEditar` (a pantalla completa en móvil) para comentar/editar.
 *  - Las mutaciones de aprobación (`aprobar`/`rechazar`) y el alta (`crearContenido`).
 *  - `GET /api/publicaciones` filtrado por estado/marca (sin backend nuevo).
 *
 * Esta ruta vive FUERA del `AppShell` (layout propio, sin sidebar); es acceso directo
 * por enlace, así que no se registra en el catálogo de apps.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Loader2,
  MessageSquare,
  Plus,
  RefreshCw,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { MARCA_TODAS, marcaParam } from "@/components/comunes/selectores";
import { VistaPreviaRed } from "@/components/preview/VistaPreviaRed";
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
import { Textarea } from "@/components/ui/textarea";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import { DialogoEditar } from "@/pages/publicaciones/DialogoEditar";
import { EtiquetaRed } from "@/pages/publicaciones/insignias";
import type {
  CuerpoCrearContenido,
  EstadoOpcion,
  MarcaDisponible,
  Publicacion,
} from "@/types";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema. Vuelve a intentarlo.";
}

/** Estados que ve el revisor en el feed: lo pendiente de su revisión y lo ya aprobado. */
type Bandeja = "en_revision" | "aprobado";

const BANDEJAS: { id: Bandeja; etiqueta: string }[] = [
  { id: "en_revision", etiqueta: "Por revisar" },
  { id: "aprobado", etiqueta: "Aprobadas" },
];

/**
 * Diálogo de creación RÁPIDA (a pantalla completa en móvil): título + marca + nota.
 * Reusa `POST /api/contenido`; el equipo afina el copy luego en el editor. Mantenemos
 * el alta mínima a propósito (el flujo completo vive en la consola de escritorio).
 */
function DialogoCrear({
  abierto,
  marcas,
  marcaInicial,
  onCerrar,
}: {
  abierto: boolean;
  marcas: MarcaDisponible[];
  marcaInicial: string;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [marca, setMarca] = React.useState(marcaInicial);
  const [descripcion, setDescripcion] = React.useState("");

  React.useEffect(() => {
    if (abierto) {
      setTitulo("");
      setDescripcion("");
      setMarca(marcaInicial);
    }
  }, [abierto, marcaInicial]);

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearContenido = {
        titulo: titulo.trim(),
        clase: "contenido",
        marca: marca === MARCA_TODAS ? "" : marca,
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
            <Label>Marca</Label>
            <SelectorMarca
              marcas={marcas}
              valor={marca}
              onCambio={setMarca}
              incluirTodas
              etiquetaTodas="Sin marca"
              className="w-full"
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

/** Una tarjeta del feed: vista previa de la pieza + acciones de revisión. */
function TarjetaFeed({
  publicacion,
  bandeja,
  onComentar,
}: {
  publicacion: Publicacion;
  bandeja: Bandeja;
  onComentar: (p: Publicacion) => void;
}) {
  const queryClient = useQueryClient();

  const tras = (mensaje: string) => () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", publicacion.id] });
    toast.success(mensaje);
  };
  const onError = (e: unknown) => toast.error(mensajeError(e));

  const aprobar = useMutation({
    mutationFn: () => api.aprobarPublicacion(publicacion.id),
    onSuccess: tras("Pieza aprobada."),
    onError,
  });
  const rechazar = useMutation({
    mutationFn: () => api.rechazarPublicacion(publicacion.id),
    onSuccess: tras("Devuelta a borrador."),
    onError,
  });
  const ocupado = aprobar.isPending || rechazar.isPending;

  return (
    <article className="border-b border-border bg-background pb-3">
      <header className="flex items-center gap-2 px-4 pb-2 pt-3 text-xs text-muted-foreground">
        <EtiquetaRed red={publicacion.red} nombre={publicacion.red_nombre} />
        <span>· {publicacion.marca_nombre}</span>
        {publicacion.autor_nombre && (
          <span className="ml-auto truncate">{publicacion.autor_nombre}</span>
        )}
      </header>

      <div className="px-4">
        <VistaPreviaRed
          red={publicacion.red}
          marca={publicacion.marca_nombre}
          contenido={publicacion.contenido}
          copy_in={publicacion.copy_in}
          imagen_url={publicacion.imagen_url || publicacion.imagen}
        />
      </div>

      {/* Acciones por tarjeta (alcanzables al hacer scroll). La barra inferior fija
          aloja el alta global. Solo se aprueba/rechaza lo que está en revisión. */}
      <div className="mt-3 flex items-center gap-2 px-4">
        {bandeja === "en_revision" ? (
          <>
            <Button
              variant="positive"
              size="sm"
              className="flex-1"
              onClick={() => aprobar.mutate()}
              disabled={ocupado}
            >
              {aprobar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Aprobar
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              onClick={() => rechazar.mutate()}
              disabled={ocupado}
            >
              {rechazar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              Rechazar
            </Button>
          </>
        ) : (
          <span className="flex flex-1 items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
            <Check className="h-4 w-4" />
            {publicacion.revisor_nombre ? `Aprobada por ${publicacion.revisor_nombre}` : "Aprobada"}
          </span>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onComentar(publicacion)}
          aria-label="Comentar"
        >
          <MessageSquare className="h-4 w-4" />
          Comentar
        </Button>
      </div>
    </article>
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

  // Pieza abierta en el editor rico (pestaña Comentarios) a pantalla completa.
  const [editando, setEditando] = React.useState<Publicacion | null>(null);
  const [crearAbierto, setCrearAbierto] = React.useState(false);

  // Opciones (estados + catálogo de marcas) para el filtro y el editor.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const estados: EstadoOpcion[] = opcionesQuery.data?.estados ?? [];
  const catalogoMarcas = opcionesQuery.data?.marcas ?? [];
  // Acota el selector a las marcas del usuario (si las tiene); admin/sin asignar ve todas.
  const marcas =
    marcasUsuario.length > 0
      ? catalogoMarcas.filter((m) => marcasUsuario.includes(m.id))
      : catalogoMarcas;

  const feedQuery = useQuery({
    queryKey: [...CLAVE_PUBLICACIONES, "feed", bandeja, marca],
    queryFn: ({ signal }) =>
      api.publicaciones({ estado: bandeja, marca: marcaParam(marca) }, signal),
  });

  // Si el usuario tiene marcas asignadas y el filtro está en "todas", restringimos el
  // listado a sus marcas en cliente (defensa extra al pre-filtro del selector).
  const piezas = React.useMemo(() => {
    const todas = feedQuery.data?.publicaciones ?? [];
    if (marca === MARCA_TODAS && marcasUsuario.length > 0) {
      return todas.filter((p) => marcasUsuario.includes(p.marca));
    }
    return todas;
  }, [feedQuery.data, marca, marcasUsuario]);

  const refrescar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });

  return (
    <div className="flex min-h-dvh flex-col bg-muted/20">
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
        <div className="flex gap-1 px-4 pb-2" role="tablist" aria-label="Bandeja">
          {BANDEJAS.map((b) => (
            <button
              key={b.id}
              type="button"
              role="tab"
              aria-selected={bandeja === b.id}
              onClick={() => setBandeja(b.id)}
              className={
                bandeja === b.id
                  ? "rounded-full bg-primary px-3 py-1 text-sm font-medium text-primary-foreground"
                  : "rounded-full border border-border px-3 py-1 text-sm text-muted-foreground"
              }
            >
              {b.etiqueta}
            </button>
          ))}
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
              <Skeleton key={i} className="h-72 w-full rounded-xl" />
            ))}
          </div>
        ) : feedQuery.isError ? (
          <div className="p-6 text-center text-sm text-destructive">
            No se pudo cargar el feed. {mensajeError(feedQuery.error)}
          </div>
        ) : piezas.length === 0 ? (
          <div className="p-6">
            <EstadoVacio
              titulo={bandeja === "en_revision" ? "Nada por revisar" : "Sin piezas aprobadas"}
              texto={
                bandeja === "en_revision"
                  ? "Cuando haya piezas en revisión para tus marcas, aparecerán aquí."
                  : "Las piezas que apruebes se mostrarán en esta bandeja."
              }
            />
          </div>
        ) : (
          piezas.map((p) => (
            <TarjetaFeed
              key={p.id}
              publicacion={p}
              bandeja={bandeja}
              onComentar={setEditando}
            />
          ))
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

      {/* Editor rico (a pantalla completa en móvil) para comentar/editar. */}
      <DialogoEditar
        publicacion={editando}
        estados={estados}
        onCerrar={() => setEditando(null)}
      />

      <DialogoCrear
        abierto={crearAbierto}
        marcas={marcas}
        marcaInicial={marca}
        onCerrar={() => setCrearAbierto(false)}
      />
    </div>
  );
}
