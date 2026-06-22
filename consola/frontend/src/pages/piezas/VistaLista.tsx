import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlertTriangle,
  BarChart3,
  CalendarClock,
  CalendarPlus,
  ImageIcon,
  Send,
  Sprout,
  ThumbsUp,
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
import { ImagenMedia } from "@/components/comunes/ImagenMedia";
import { BadgeStock, OverlaySinLicencia } from "@/components/media/OverlaySinLicencia";
import { confirmar } from "@/components/comunes/confirmar";
import { ApiError, api, mensajeError, urlMedia } from "@/lib/api";
import { estaVencida } from "@/lib/fecha";
import {
  MENSAJE_BLOQUEO_STOCK,
  nombreProveedor,
  stockAutorizado,
  stockNoAutorizado,
} from "@/lib/stock";
import { cn } from "@/lib/utils";
import type { Pieza } from "@/types";

import { CLAVE_PIEZAS } from "./claves";
import { BadgeEstado, EtiquetaRed } from "./insignias";
import { formatearFechaHora } from "./meta";

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
function TarjetaPieza({
  pieza,
  onEditar,
  onConfigurarHorarios,
}: {
  pieza: Pieza;
  onEditar: (p: Pieza) => void;
  onConfigurarHorarios: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const imagen = urlMedia(pieza.imagen_url || pieza.imagen);
  // "Aprobar" solo tiene sentido en una pieza pendiente de decisión (borrador o en revisión).
  const puedeAprobar = pieza.estado === "borrador" || pieza.estado === "en_revision";
  // STOCK SIN LICENCIA: foto de stock sin autorizar. Bloquea programar/publicar (defensa en UI; el
  // back devuelve 409) y dispara el tratamiento "SIN LICENCIA" en la miniatura.
  const bloqueoStock = stockNoAutorizado(pieza);

  // Registra tu OK en la cadena (mismo motor que el pulgar del feed): un OK puede cerrar la
  // cadena (queda lista/programada) o ser 1 de 2 (sigue en revisión hasta el segundo OK). El
  // back exige que la pieza esté en revisión y "otro par de ojos"; el toast cuenta el desenlace.
  const aprobar = useMutation({
    mutationFn: () => api.aprobarPieza(pieza.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      const cerrada =
        !!res?.pieza && ["programado", "publicado"].includes(res.pieza.estado);
      toast.success(
        cerrada
          ? "Pieza aprobada: lista para publicar."
          : "Tu OK quedó registrado; falta el de otra persona.",
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const encolar = useMutation({
    mutationFn: () => api.encolarPieza(pieza.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      const fecha = res?.pieza?.fecha_programada;
      toast.success(
        fecha
          ? `Encolada para ${formatearFechaHora(fecha)}`
          : "Publicación añadida a la cola",
      );
    },
    onError: (e) => {
      // 400 = sin franjas de horario: avisamos y ofrecemos configurar los horarios.
      if (e instanceof ApiError && e.status === 400) {
        toast.error(e.message, {
          action: { label: "Configurar horarios", onClick: onConfigurarHorarios },
        });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const programarMetricool = useMutation({
    mutationFn: () => api.programarEnMetricool(pieza.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
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

  const borrar = useMutation({
    mutationFn: () => api.eliminarPieza(pieza.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      toast.success(res?.mensaje ?? "Publicación borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Acción primaria = editar (click izquierdo, no se duplica en el menú). El menú ofrece la
  // decisión propia del estado y "Borrar"; las acciones de cada estado son excluyentes:
  //  - borrador/en revisión → "Aprobar" (registra tu OK en la cadena).
  //  - programado → re-encolar / programar en Metricool. (En pre-aprobación encolar saltaría la
  //    revisión: el camino de esas piezas es el flujo de aprobación, que auto-programa al juntar
  //    los 2 OKs. Una publicada es terminal: su post ya salió, no se re-encola.)
  //  - publicado → ver métricas de la marca.
  const accionesPrimarias: EntradaMenuContextual[] = puedeAprobar
    ? [
        {
          etiqueta: "Aprobar",
          icono: ThumbsUp,
          onClick: () => aprobar.mutate(),
          deshabilitado: aprobar.isPending,
        },
      ]
    : pieza.estado === "programado"
      ? [
          {
            etiqueta: "Añadir a la cola",
            icono: CalendarPlus,
            onClick: () => encolar.mutate(),
            deshabilitado: encolar.isPending,
          },
          {
            etiqueta: bloqueoStock
              ? "Programar en Metricool (imagen sin licencia)"
              : "Programar en Metricool",
            icono: Send,
            onClick: () => {
              if (bloqueoStock) {
                toast.error(MENSAJE_BLOQUEO_STOCK);
                return;
              }
              programarMetricool.mutate();
            },
            deshabilitado: programarMetricool.isPending || bloqueoStock,
          },
        ]
      : pieza.estado === "publicado"
        ? [
            {
              etiqueta: "Ver métricas de la marca",
              icono: BarChart3,
              onClick: () =>
                navigate("/datos/analiticas/metricas", {
                  // Marca activa (workspace) en forma canónica: el switch global la fija.
                  state: { marca: pieza.marca },
                }),
            },
          ]
        : [];

  const acciones: EntradaMenuContextual[] = [
    ...accionesPrimarias,
    ...(accionesPrimarias.length ? [{ separador: true as const }] : []),
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: async () => {
        if (
          await confirmar({
            titulo: `Borrar “${pieza.titulo}”`,
            mensaje: "Esta acción no se puede deshacer.",
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        ) {
          borrar.mutate();
        }
      },
      destructivo: true,
    },
  ];

  return (
    <>
      <FilaConAcciones
        como="div"
        onPrimaria={() => onEditar(pieza)}
        acciones={acciones}
        etiquetaAcciones={`Acciones de "${pieza.titulo}"`}
        kebab="nunca"
        realce
        className="rounded-lg border border-border bg-card text-card-foreground shadow-sm"
      >
        <div className="flex min-w-0 flex-1 gap-3 py-4 pl-4 pr-10">
          {imagen && (
            <div className="relative h-16 w-16 shrink-0">
              <OverlaySinLicencia activo={bloqueoStock} tamano="sm" className="rounded-md">
                <ImagenMedia
                  nombreOUrl={imagen}
                  alt=""
                  ancho={160}
                  className="h-16 w-16 rounded-md border border-border bg-muted object-cover"
                />
              </OverlaySinLicencia>
              {(bloqueoStock || stockAutorizado(pieza)) && (
                <BadgeStock
                  proveedor={nombreProveedor(pieza.imagen_proveedor)}
                  autorizada={!!pieza.imagen_autorizada}
                  className="absolute bottom-0.5 right-0.5 z-10 scale-90"
                />
              )}
            </div>
          )}
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{pieza.titulo}</span>
              <BadgeEstado estado={pieza.estado} />
              {estaVencida(pieza.estado, pieza.fecha_programada) && (
                <Badge
                  variant="error"
                  className="gap-1"
                  title="Pasada de su hora y sin publicar. Publícala ya o revisa por qué no salió."
                >
                  <AlertTriangle className="h-3 w-3" />
                  Sin publicar
                </Badge>
              )}
              {pieza.id_post_metricool && (
                <Badge
                  variant="info"
                  className="gap-1 font-normal"
                  title={`Programada en Metricool · id ${pieza.id_post_metricool}`}
                >
                  <Send className="h-3 w-3" />
                  Metricool
                </Badge>
              )}
              {pieza.evergreen && (
                <Badge variant="ok" className="gap-1 font-normal">
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
              <EtiquetaRed red={pieza.red} nombre={pieza.red_nombre} />
              <span>· {pieza.marca_nombre}</span>
              <Autor nombre={pieza.autor_nombre} />
              {pieza.estado === "programado" && pieza.fecha_programada && (
                <span
                  className={cn(
                    "inline-flex items-center gap-1",
                    estaVencida(pieza.estado, pieza.fecha_programada)
                      ? "text-red-700 dark:text-red-300"
                      : "text-amber-700 dark:text-amber-300",
                  )}
                >
                  <CalendarClock className="h-3.5 w-3.5" />
                  {formatearFechaHora(pieza.fecha_programada)}
                </span>
              )}
            </div>
            {pieza.contenido && (
              <p className="line-clamp-2 whitespace-pre-wrap text-sm text-muted-foreground">
                {pieza.contenido}
              </p>
            )}
          </div>
        </div>
      </FilaConAcciones>

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
 * endpoint batch (`POST /api/piezas/borrar-lote`, un solo round-trip) que reporta
 * fallos parciales; se resume el resultado y se podan las selecciones que ya no estén en
 * la lista (cambió el filtro/página). Las listas largas se virtualizan (react-virtual).
 */
export function VistaLista({
  piezas,
  onEditar,
  onConfigurarHorarios,
}: {
  piezas: Pieza[];
  onEditar: (p: Pieza) => void;
  onConfigurarHorarios: () => void;
}) {
  const queryClient = useQueryClient();
  const [seleccionadas, setSeleccionadas] = React.useState<Set<string>>(() => new Set());

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
  const virtualizar = scroller !== null && piezas.length > UMBRAL_VIRTUALIZAR;
  const virtualizador = useVirtualizer({
    count: virtualizar ? piezas.length : 0,
    getScrollElement: () => scroller,
    estimateSize: () => 122, // alto típico de una tarjeta + separación; se ajusta al medir
    overscan: 8,
    scrollMargin: margenScroll,
  });

  const fila = (p: Pieza) => (
    <div className="flex items-start gap-2">
      <Checkbox
        checked={seleccionadas.has(p.id)}
        onCheckedChange={() => alternar(p.id)}
        aria-label={`Seleccionar "${p.titulo}"`}
        className="mt-4 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <TarjetaPieza
          pieza={p}
          onEditar={onEditar}
          onConfigurarHorarios={onConfigurarHorarios}
        />
      </div>
    </div>
  );

  // Purga las ids seleccionadas que ya no aparecen en la lista (cambió el filtro o la página).
  React.useEffect(() => {
    setSeleccionadas((prev) => {
      if (prev.size === 0) return prev;
      const presentes = new Set(piezas.map((p) => p.id));
      const siguiente = new Set([...prev].filter((id) => presentes.has(id)));
      return siguiente.size === prev.size ? prev : siguiente;
    });
  }, [piezas]);

  const alternar = (id: string) =>
    setSeleccionadas((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return s;
    });

  const todasSeleccionadas =
    piezas.length > 0 && piezas.every((p) => seleccionadas.has(p.id));
  const alternarTodas = () =>
    setSeleccionadas(todasSeleccionadas ? new Set() : new Set(piezas.map((p) => p.id)));

  // Borrado en lote: UN solo round-trip al endpoint batch (`POST /piezas/borrar-lote`),
  // que itera el borrado en servidor y reporta los fallos parciales sin abortar el resto.
  const borrarLote = useMutation({
    mutationFn: async (ids: string[]) => {
      const res = await api.borrarPiezasLote(ids);
      return { total: ids.length, borradas: res.borradas, fallos: res.fallos };
    },
    onSuccess: ({ total, borradas, fallos }) => {
      setSeleccionadas(new Set());
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      if (fallos.length === 0) {
        toast.success(
          `${borradas} ${borradas === 1 ? "publicación borrada" : "piezas borradas"}.`,
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
              onClick={async () => {
                if (
                  await confirmar({
                    titulo: `Borrar ${n} ${n === 1 ? "publicación" : "piezas"}`,
                    mensaje: "Esta acción no se puede deshacer.",
                    destructivo: true,
                    textoConfirmar: `Borrar ${n}`,
                  })
                ) {
                  borrarLote.mutate([...seleccionadas]);
                }
              }}
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
            const p = piezas[vi.index];
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
          {piezas.map((p) => (
            <React.Fragment key={p.id}>{fila(p)}</React.Fragment>
          ))}
        </div>
      )}

    </div>
  );
}
