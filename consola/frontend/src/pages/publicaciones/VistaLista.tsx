import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CalendarClock,
  CalendarPlus,
  Copy,
  ImageIcon,
  Pencil,
  Send,
  Sprout,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useMediaQuery } from "@/hooks/use-media-query";
import { ApiError, api, mensajeError, urlMedia } from "@/lib/api";
import { estaVencida } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { BadgeEstado, EtiquetaRed } from "./insignias";
import { formatearFechaHora, metaEstado, siguienteEstado } from "./meta";

/**
 * Visibilidad del kebab "⋮" según el puntero. En TÁCTIL (puntero grueso) no hay hover, así
 * que las acciones secundarias quedaban inalcanzables: lo dejamos SIEMPRE visible. En puntero
 * fino (ratón) sigue apareciendo al hover, como hoy. Pura para testearla sin montar la fila.
 */
export function kebabSegunPuntero(punteroGrueso: boolean): "siempre" | "hover" {
  return punteroGrueso ? "siempre" : "hover";
}

/**
 * Una tarjeta de publicación. Click izquierdo sobre la tarjeta = editar (acción
 * primaria); el resto de operaciones viven en el menú contextual (click derecho) y en
 * el kebab "⋮", sin hilera de botones-icono.
 */
function TarjetaPublicacion({
  publicacion,
  onEditar,
  onDuplicar,
  onConfigurarCadencia,
}: {
  publicacion: Publicacion;
  onEditar: (p: Publicacion) => void;
  onDuplicar: (p: Publicacion) => void;
  onConfigurarCadencia: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);
  const proximo = siguienteEstado(publicacion.estado);
  const imagen = urlMedia(publicacion.imagen_url || publicacion.imagen);
  // TÁCTIL: sin hover el kebab "⋮" era inalcanzable; con puntero grueso lo dejamos fijo.
  const punteroGrueso = useMediaQuery("(pointer: coarse)");

  const avanzar = useMutation({
    mutationFn: () => {
      if (!proximo) throw new Error("Estado final");
      return api.actualizarPublicacion(publicacion.id, { estado: proximo });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      if (proximo) toast.success(`Estado cambiado a "${metaEstado(proximo).nombre}"`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const encolar = useMutation({
    mutationFn: () => api.encolarPublicacion(publicacion.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      const fecha = res?.publicacion?.fecha_programada;
      toast.success(
        fecha
          ? `Encolada para ${formatearFechaHora(fecha)}`
          : "Publicación añadida a la cola",
      );
    },
    onError: (e) => {
      // 400 = sin cadencia/franjas: avisamos y ofrecemos configurar la cadencia.
      if (e instanceof ApiError && e.status === 400) {
        toast.error(e.message, {
          action: { label: "Configurar cadencia", onClick: onConfigurarCadencia },
        });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const programarMetricool = useMutation({
    mutationFn: () => api.programarEnMetricool(publicacion.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      const r = res.resultado;
      const redes = (r.redes ?? []).join(", ") || "—";
      if (r.dry_run) {
        toast.success(
          `Vista previa lista: se enviaría a Metricool (${redes}). No se publicó (modo dry-run).`,
        );
      } else {
        toast.success(`Publicado en Metricool (${redes})${r.id_post ? ` · id ${r.id_post}` : ""}`);
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const alternarEverevergreen = useMutation({
    mutationFn: () =>
      api.actualizarPublicacion(publicacion.id, { evergreen: !publicacion.evergreen }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      toast.success(
        publicacion.evergreen ? "Ya no es evergreen" : "Marcada como evergreen",
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarPublicacion(publicacion.id),
    onSuccess: (res) => {
      setConfirmarBorrado(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      toast.success(res?.mensaje ?? "Publicación borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Acción primaria = editar. Las demás operaciones, condicionadas por estado, en el menú.
  const acciones: EntradaMenuContextual[] = [
    { etiqueta: "Editar", icono: Pencil, onClick: () => onEditar(publicacion) },
    ...(proximo
      ? [
          {
            etiqueta: `Avanzar a "${metaEstado(proximo).nombre}"`,
            icono: ArrowRight,
            onClick: () => avanzar.mutate(),
            deshabilitado: avanzar.isPending,
          },
        ]
      : []),
    { separador: true },
    // "Añadir a la cola" SOLO para piezas APROBADAS o ya programadas (re-encolar). Programar
    // una pre-aprobación (borrador/en_revisión) saltaría la revisión: el camino de esas piezas
    // es el flujo de aprobación, que auto-programa al aprobarse (auto_programar) con sus gates
    // (mínimo de OKs + QA). Así el botón no es un footgun de un clic en la pantalla diaria. Una
    // publicada es terminal (su post ya salió): tampoco se re-encola.
    ...(publicacion.estado === "aprobado" || publicacion.estado === "programado"
      ? [
          {
            etiqueta: "Añadir a la cola",
            icono: CalendarPlus,
            onClick: () => encolar.mutate(),
            deshabilitado: encolar.isPending,
          },
        ]
      : []),
    ...(publicacion.estado === "aprobado" || publicacion.estado === "programado"
      ? [
          {
            etiqueta: "Programar en Metricool",
            icono: Send,
            onClick: () => programarMetricool.mutate(),
            deshabilitado: programarMetricool.isPending,
          },
        ]
      : []),
    ...(publicacion.estado === "publicado"
      ? [
          {
            etiqueta: "Ver métricas de la marca",
            icono: BarChart3,
            onClick: () =>
              navigate("/datos/analiticas/metricas", {
                // Marca activa (workspace) en forma canónica: el switch global la fija.
                state: { marca: publicacion.marca },
              }),
          },
        ]
      : []),
    {
      etiqueta: publicacion.evergreen ? "Quitar de evergreens" : "Marcar como evergreen",
      icono: Sprout,
      onClick: () => alternarEverevergreen.mutate(),
      activo: publicacion.evergreen,
      deshabilitado: alternarEverevergreen.isPending,
    },
    { etiqueta: "Duplicar", icono: Copy, onClick: () => onDuplicar(publicacion) },
    { separador: true },
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: () => setConfirmarBorrado(true),
      destructivo: true,
    },
  ];

  return (
    <>
      <FilaConAcciones
        como="div"
        onPrimaria={() => onEditar(publicacion)}
        acciones={acciones}
        etiquetaAcciones={`Acciones de "${publicacion.titulo}"`}
        kebab={kebabSegunPuntero(punteroGrueso)}
        className="rounded-lg border border-border bg-card text-card-foreground shadow-sm transition-colors hover:border-foreground/20"
      >
        <div className="flex min-w-0 flex-1 gap-3 py-4 pl-4 pr-10">
          {imagen && (
            <img
              src={imagen}
              alt=""
              className="h-16 w-16 shrink-0 rounded-md border border-border object-cover"
            />
          )}
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{publicacion.titulo}</span>
              <BadgeEstado estado={publicacion.estado} />
              {estaVencida(publicacion.estado, publicacion.fecha_programada) && (
                <Badge
                  variant="error"
                  className="gap-1"
                  title="Pasada de su hora y sin publicar. Publícala ya o revisa por qué no salió."
                >
                  <AlertTriangle className="h-3 w-3" />
                  Sin publicar
                </Badge>
              )}
              {publicacion.id_post_metricool && (
                <Badge
                  variant="outline"
                  className="gap-1 border-sky-500/40 font-normal text-sky-700 dark:text-sky-300"
                  title={`Programada en Metricool · id ${publicacion.id_post_metricool}`}
                >
                  <Send className="h-3 w-3" />
                  Metricool
                </Badge>
              )}
              {publicacion.evergreen && (
                <Badge
                  variant="outline"
                  className="gap-1 border-emerald-500/40 font-normal text-emerald-700 dark:text-emerald-300"
                >
                  <Sprout className="h-3 w-3" />
                  Evergreen
                </Badge>
              )}
              {imagen && (
                <ImageIcon
                  className="h-3.5 w-3.5 text-muted-foreground"
                  aria-label="Con imagen"
                />
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
              <EtiquetaRed red={publicacion.red} nombre={publicacion.red_nombre} />
              <span>· {publicacion.marca_nombre}</span>
              <Autor nombre={publicacion.autor_nombre} />
              {publicacion.estado === "programado" && publicacion.fecha_programada && (
                <span
                  className={cn(
                    "inline-flex items-center gap-1",
                    estaVencida(publicacion.estado, publicacion.fecha_programada)
                      ? "text-red-700 dark:text-red-300"
                      : "text-amber-700 dark:text-amber-300",
                  )}
                >
                  <CalendarClock className="h-3.5 w-3.5" />
                  {formatearFechaHora(publicacion.fecha_programada)}
                </span>
              )}
            </div>
            {publicacion.contenido && (
              <p className="line-clamp-2 whitespace-pre-wrap text-sm text-muted-foreground">
                {publicacion.contenido}
              </p>
            )}
          </div>
        </div>
      </FilaConAcciones>

      <Dialog open={confirmarBorrado} onOpenChange={setConfirmarBorrado}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Borrar “{publicacion.titulo}”</DialogTitle>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmarBorrado(false)}
              disabled={borrar.isPending}
            >
              Cancelar
            </Button>
            <Button variant="destructive" onClick={() => borrar.mutate()} disabled={borrar.isPending}>
              {borrar.isPending ? "Borrando…" : "Borrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// Nº de filas a partir del cual la lista se VIRTUALIZA (solo se montan las visibles).
const UMBRAL_VIRTUALIZAR = 40;

/**
 * Vista de lista: tarjetas de publicación con SELECCIÓN MÚLTIPLE para borrar en masa.
 *
 * Cada tarjeta lleva un checkbox a la izquierda; al marcar una o más aparece una barra de
 * acciones (pegajosa arriba) con "seleccionar todo" y "borrar". El borrado en lote va al
 * endpoint batch (`POST /api/publicaciones/borrar-lote`, un solo round-trip) que reporta
 * fallos parciales; se resume el resultado y se podan las selecciones que ya no estén en
 * la lista (cambió el filtro/página). Las listas largas se virtualizan (react-virtual).
 */
export function VistaLista({
  publicaciones,
  onEditar,
  onDuplicar,
  onConfigurarCadencia,
}: {
  publicaciones: Publicacion[];
  onEditar: (p: Publicacion) => void;
  onDuplicar: (p: Publicacion) => void;
  onConfigurarCadencia: () => void;
}) {
  const queryClient = useQueryClient();
  const [seleccionadas, setSeleccionadas] = React.useState<Set<string>>(() => new Set());
  const [confirmar, setConfirmar] = React.useState(false);

  // --- Virtualización de filas (listas largas) ---------------------------------------
  // El scroll de la app vive en el <main> del AppShell (no en window): lo localizamos
  // subiendo desde la raíz del componente. `margenScroll` es el offset del arranque de la
  // lista dentro de ese scroller (cambia cuando aparece la barra pegajosa de selección).
  const raizRef = React.useRef<HTMLDivElement>(null);
  const listaRef = React.useRef<HTMLDivElement>(null);
  const [scroller, setScroller] = React.useState<HTMLElement | null>(null);
  const [margenScroll, setMargenScroll] = React.useState(0);
  React.useLayoutEffect(() => {
    setScroller((raizRef.current?.closest("main") as HTMLElement | null) ?? null);
  }, []);
  const haySeleccion = seleccionadas.size > 0;
  React.useLayoutEffect(() => {
    if (!scroller || !listaRef.current) return;
    setMargenScroll(
      listaRef.current.getBoundingClientRect().top -
        scroller.getBoundingClientRect().top +
        scroller.scrollTop,
    );
  }, [scroller, haySeleccion]);
  // Solo merece la pena virtualizar con muchas filas; por debajo, lista plana (y los
  // tests/jsdom, sin <main> ni medidas reales, siempre van por la rama plana).
  const virtualizar = scroller !== null && publicaciones.length > UMBRAL_VIRTUALIZAR;
  const virtualizador = useVirtualizer({
    count: virtualizar ? publicaciones.length : 0,
    getScrollElement: () => scroller,
    estimateSize: () => 122, // alto típico de una tarjeta + separación; se ajusta al medir
    overscan: 8,
    scrollMargin: margenScroll,
  });

  const fila = (p: Publicacion) => (
    <div className="flex items-start gap-2">
      <Checkbox
        checked={seleccionadas.has(p.id)}
        onCheckedChange={() => alternar(p.id)}
        aria-label={`Seleccionar "${p.titulo}"`}
        className="mt-4 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <TarjetaPublicacion
          publicacion={p}
          onEditar={onEditar}
          onDuplicar={onDuplicar}
          onConfigurarCadencia={onConfigurarCadencia}
        />
      </div>
    </div>
  );

  // Poda las ids seleccionadas que ya no aparecen en la lista (cambió el filtro o la página).
  React.useEffect(() => {
    setSeleccionadas((prev) => {
      if (prev.size === 0) return prev;
      const presentes = new Set(publicaciones.map((p) => p.id));
      const siguiente = new Set([...prev].filter((id) => presentes.has(id)));
      return siguiente.size === prev.size ? prev : siguiente;
    });
  }, [publicaciones]);

  const alternar = (id: string) =>
    setSeleccionadas((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return s;
    });

  const todasSeleccionadas =
    publicaciones.length > 0 && publicaciones.every((p) => seleccionadas.has(p.id));
  const alternarTodas = () =>
    setSeleccionadas(todasSeleccionadas ? new Set() : new Set(publicaciones.map((p) => p.id)));

  // Borrado en lote: UN solo round-trip al endpoint batch (`POST /publicaciones/borrar-lote`),
  // que itera el borrado en servidor y reporta los fallos parciales sin abortar el resto
  // (antes: N DELETEs en paralelo desde el cliente).
  const borrarLote = useMutation({
    mutationFn: async (ids: string[]) => {
      const res = await api.borrarPublicacionesLote(ids);
      return { total: ids.length, borradas: res.borradas, fallos: res.fallos };
    },
    onSuccess: ({ total, borradas, fallos }) => {
      setConfirmar(false);
      setSeleccionadas(new Set());
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      if (fallos.length === 0) {
        toast.success(
          `${borradas} ${borradas === 1 ? "publicación borrada" : "publicaciones borradas"}.`,
        );
      } else {
        toast.error(
          `Borradas ${borradas} de ${total}; ${fallos.length} no se ${
            fallos.length === 1 ? "pudo" : "pudieron"
          } borrar (ya no existían).`,
        );
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const n = seleccionadas.size;

  return (
    <div ref={raizRef} className="space-y-3">
      {n > 0 && (
        <div className="sticky top-0 z-10 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card/95 px-3 py-2 shadow-sm backdrop-blur">
          <span className="text-sm font-medium">
            {n} seleccionada{n === 1 ? "" : "s"}
          </span>
          <button
            type="button"
            onClick={alternarTodas}
            className="text-sm text-muted-foreground underline-offset-2 hover:underline"
          >
            {todasSeleccionadas ? "Quitar selección" : "Seleccionar todo"}
          </button>
          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSeleccionadas(new Set())}
              disabled={borrarLote.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setConfirmar(true)}
              disabled={borrarLote.isPending}
            >
              <Trash2 className="mr-1 h-4 w-4" />
              Borrar {n}
            </Button>
          </div>
        </div>
      )}

      {/* FILAS. Con listas largas se VIRTUALIZA (solo se montan las filas visibles +
          overscan): el scroll vive en el <main> del AppShell, así que el virtualizador
          usa ese contenedor y mide cada fila real (alturas variables: imagen, badges…).
          Con pocas filas (o sin <main>, p. ej. en tests) se pinta la lista plana. */}
      {virtualizar ? (
        <div
          ref={listaRef}
          className="relative"
          style={{ height: virtualizador.getTotalSize() }}
        >
          {virtualizador.getVirtualItems().map((vi) => {
            const p = publicaciones[vi.index];
            if (!p) return null;
            return (
              <div
                key={p.id}
                data-index={vi.index}
                ref={virtualizador.measureElement}
                className="absolute left-0 top-0 w-full pb-3"
                style={{ transform: `translateY(${vi.start - margenScroll}px)` }}
              >
                {fila(p)}
              </div>
            );
          })}
        </div>
      ) : (
        <div ref={listaRef} className="space-y-3">
          {publicaciones.map((p) => (
            <React.Fragment key={p.id}>{fila(p)}</React.Fragment>
          ))}
        </div>
      )}

      <Dialog open={confirmar} onOpenChange={(o) => !o && setConfirmar(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Borrar {n} {n === 1 ? "publicación" : "publicaciones"}
            </DialogTitle>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmar(false)}
              disabled={borrarLote.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => borrarLote.mutate([...seleccionadas])}
              disabled={borrarLote.isPending}
            >
              {borrarLote.isPending ? "Borrando…" : `Borrar ${n}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
