import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarClock,
  CalendarOff,
  CalendarX,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Zap,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { MenuContextual } from "@/components/comunes/MenuContextual";
import { Button } from "@/components/ui/button";
import { api, mensajeError } from "@/lib/api";
import { estaVencida, horaUtcACdmx, hoyCDMX } from "@/lib/fecha";
import { colorCategoria, ETIQUETA_CATEGORIA } from "@/lib/categorias";
import { cn } from "@/lib/utils";
import type { Pieza } from "@/types";

import { BotonHoraPieza } from "./BotonHoraPieza";
import { CLAVE_PIEZAS } from "./claves";
import { DialogoReprogramar } from "./DialogoReprogramar";
import {
  datetimeLocalAIso,
  formatearHoraOperativa,
  iconoRed,
  isoADatetimeLocal,
  nombreRed,
} from "./meta";

type Vista = "mes" | "semana" | "dia";

/**
 * Un HUECO LIBRE del plan, ya expandido POR RED: un slot del plan (día/hora/categoría) que el
 * plan espera cubrir con la red `red` y para el que no existe pieza de ESA red a esa hora.
 */
export type Hueco = { hora: string; categoria: string; etiqueta: string; red: string };

/** Nombres de los días (lunes a domingo), abreviados es-MX. */
const DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

// Caja compartida por las entradas de las columnas semana/día (piezas y huecos del plan):
// fija tamaño de fuente, padding y borde idénticos para que TODAS las filas midan lo mismo.
// Cada entrada añade encima su color e identidad (sólida vs. punteada).
const CLASES_ENTRADA_CALENDARIO =
  "flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs";

/** Clave YYYY-MM-DD en hora CDMX de una pieza programada ("" si no aplica). */
function diaCdmx(p: Pieza): string {
  return p.fecha_programada ? isoADatetimeLocal(p.fecha_programada).slice(0, 10) : "";
}

/** Hora "HH:mm" (24h CDMX) de una pieza, para reprogramar conservando la hora. */
function hora24Cdmx(iso: string): string {
  return isoADatetimeLocal(iso).slice(11, 16);
}

/** Clave YYYY-MM-DD (local) de un `Date` de celda del calendario. */
function claveDia(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Índice día(CDMX) -> piezas programadas ese día (ordenadas por hora). */
function indexarPorDia(piezas: Pieza[]): Map<string, Pieza[]> {
  const mapa = new Map<string, Pieza[]>();
  for (const p of piezas) {
    const clave = diaCdmx(p);
    if (!clave) continue;
    const lista = mapa.get(clave) ?? [];
    lista.push(p);
    mapa.set(clave, lista);
  }
  for (const lista of mapa.values()) {
    lista.sort((a, b) => (a.fecha_programada ?? "").localeCompare(b.fecha_programada ?? ""));
  }
  return mapa;
}

/** Conteo por red de una lista de piezas (orden por más frecuentes). */
function conteoPorRed(items: Pieza[]): { red: string; n: number }[] {
  const m = new Map<string, number>();
  for (const p of items) m.set(p.red, (m.get(p.red) ?? 0) + 1);
  return [...m.entries()].map(([red, n]) => ({ red, n })).sort((a, b) => b.n - a.n);
}

/** Las 42 celdas (6 semanas) del mes que ancla `ancla`. */
function celdasDelMes(ancla: Date): Date[] {
  const primero = new Date(ancla.getFullYear(), ancla.getMonth(), 1);
  const offset = (primero.getDay() + 6) % 7;
  const inicio = new Date(primero);
  inicio.setDate(primero.getDate() - offset);
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(inicio);
    d.setDate(inicio.getDate() + i);
    return d;
  });
}

/**
 * Rango `{desde, hasta}` (ISO `YYYY-MM-DD`) que cubre la rejilla de 42 celdas del mes de
 * `ancla` con ±1 semana de margen. El calendario pide SOLO este rango a `/api/piezas`
 * (`?desde=&hasta=`) en vez del conjunto completo, que el cap de 1000 filas truncaba en
 * silencio. El margen absorbe el desfase UTC↔CDMX y las vistas semana/día (cuyo ancla cae
 * siempre dentro de su propia rejilla mensual). Pura y exportada para el query de la página.
 */
export function rangoVisibleCalendario(ancla: Date): { desde: string; hasta: string } {
  const celdas = celdasDelMes(ancla);
  const primero = new Date(celdas[0]);
  primero.setDate(primero.getDate() - 7);
  const ultimo = new Date(celdas[celdas.length - 1]);
  ultimo.setDate(ultimo.getDate() + 7);
  return { desde: claveDia(primero), hasta: claveDia(ultimo) };
}

/** Los 7 días (lunes→domingo) de la semana que contiene a `ancla`. */
function diasDeSemana(ancla: Date): Date[] {
  const offset = (ancla.getDay() + 6) % 7;
  const lunes = new Date(ancla);
  lunes.setDate(ancla.getDate() - offset);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(lunes);
    d.setDate(lunes.getDate() + i);
    return d;
  });
}

/**
 * Una píldora de publicación: arrastrable, clic en el título abre el editor, clic-derecho el
 * menú. La HORA es editable EN SITIO: un botón aparte (`BotonHoraPieza`) abre un popover para
 * personalizar el instante de ese post sin salir del calendario (solo para piezas no publicadas).
 *
 * La fila es un `<div>` arrastrable que envuelve dos botones (hora + título): así el editor de
 * hora y el del post no se anidan y cada uno recibe su propio clic.
 */
function PildoraPub({
  pieza,
  onAbrir,
  onDesprogramar,
  onReprogramar,
  onCambiarHora,
  onPublicarYa,
  ocupado,
}: {
  pieza: Pieza;
  onAbrir: (p: Pieza) => void;
  onDesprogramar: (p: Pieza) => void;
  onReprogramar: (p: Pieza) => void;
  onCambiarHora: (p: Pieza, hhmm: string) => void;
  onPublicarYa: (p: Pieza) => void;
  ocupado: boolean;
}) {
  const Icono = iconoRed(pieza.red);
  // Ya publicado → verde; vencida (programada y pasada de hora sin salir) → rojo;
  // programado a futuro → ámbar.
  const publicado = pieza.estado === "publicado";
  const vencida = estaVencida(pieza.estado, pieza.fecha_programada);

  return (
    <MenuContextual
      disparador="contextmenu"
      etiqueta={`Acciones de "${pieza.titulo}"`}
      items={[
        // Una pieza ya PUBLICADA es terminal: solo Editar/ver. No "Publicar ya" (doble post)
        // ni "Desprogramar" (el post ya salió; cambiar su fecha aquí solo mentiría).
        ...(!publicado
          ? [
              {
                // BREAKING: publica YA (salta la parrilla). Real o dry-run según KENI_PUBLICAR_REAL.
                etiqueta: "Publicar ya",
                icono: Zap,
                deshabilitado: ocupado,
                onClick: () => onPublicarYa(pieza),
              },
            ]
          : []),
        { separador: true },
        {
          etiqueta: "Editar",
          icono: Pencil,
          onClick: () => onAbrir(pieza),
        },
        ...(!publicado
          ? [
              {
                // Reprograma a un instante CUALQUIERA (fuera de los cajones fijos del plan).
                etiqueta: "Reprogramar a otra hora",
                icono: CalendarClock,
                deshabilitado: ocupado,
                onClick: () => onReprogramar(pieza),
              },
              {
                etiqueta: "Desprogramar",
                icono: CalendarX,
                deshabilitado: ocupado,
                onClick: () => onDesprogramar(pieza),
              },
            ]
          : []),
      ]}
    >
      <div
        draggable={!publicado}
        onDragStart={(e) => {
          if (publicado) {
            e.preventDefault();
            return;
          }
          e.dataTransfer.setData("text/plain", pieza.id);
          e.dataTransfer.effectAllowed = "move";
        }}
        className={cn(
          CLASES_ENTRADA_CALENDARIO,
          "w-full max-w-full border-transparent transition-colors",
          publicado ? "cursor-pointer" : "cursor-grab active:cursor-grabbing",
          publicado
            ? "bg-emerald-500/15 text-emerald-800 hover:bg-emerald-500/25 dark:text-emerald-200"
            : vencida
              ? "bg-red-500/15 text-red-800 hover:bg-red-500/25 dark:text-red-200"
              : "bg-amber-500/15 text-amber-800 hover:bg-amber-500/25 dark:text-amber-200",
        )}
      >
        {vencida ? (
          <AlertTriangle className="h-3 w-3 shrink-0" aria-label="Pasada de hora, sin publicar" />
        ) : (
          <Icono className="h-3 w-3 shrink-0" />
        )}
        {/* Una pieza publicada ya salió: su hora es histórica (texto plano, no editable). */}
        {publicado ? (
          <span className="shrink-0 tabular-nums">
            {formatearHoraOperativa(pieza.fecha_programada)}
          </span>
        ) : (
          <BotonHoraPieza
            iso={pieza.fecha_programada}
            ocupado={ocupado}
            onGuardar={(hhmm) => onCambiarHora(pieza, hhmm)}
            onOtroDia={() => onReprogramar(pieza)}
          />
        )}
        <button
          type="button"
          onClick={() => onAbrir(pieza)}
          title={
            publicado
              ? `${pieza.titulo} (${nombreRed(pieza.red)}) · ya publicada · abre para ver`
              : vencida
                ? `${pieza.titulo} (${nombreRed(pieza.red)}) · PASADA DE HORA, sin publicar · "Publicar ya" vive en el menú contextual (clic derecho)`
                : `${pieza.titulo} (${nombreRed(pieza.red)}) · clic para editar · arrastra para mover · clic en la hora para reprogramarla`
          }
          className="min-w-0 flex-1 truncate text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          {pieza.titulo}
        </button>
      </div>
    </MenuContextual>
  );
}

/**
 * Vista calendario de la PROGRAMACIÓN, pensada para alto volumen (cientos/semana). Tres
 * lentes sobre las piezas ya programadas:
 *  - `mes`: rejilla mensual de RESUMEN (conteo por red por día); clic en un día → detalle.
 *  - `semana`: 7 columnas con las piezas del día listadas; se ARRASTRA una pieza a otro día
 *    para reprogramarla (conserva su hora). Scroll vertical por día.
 *  - `dia`: detalle de un día (todas sus piezas, editar/desprogramar).
 *
 * Reprogramar/desprogramar usan `api.actualizarPieza` (horas en CDMX vía `@/lib/fecha`).
 * (El reparto automático por las franjas de horario es trabajo del motor de producción, aparte.)
 */
export function VistaCalendario({
  piezas,
  onEditar,
  marca,
  ancla: anclaProp,
  onAncla,
  mostrarHuecosPlan = true,
  filtroRed = null,
}: {
  piezas: Pieza[];
  onEditar: (p: Pieza) => void;
  /** Reservado: marca activa (la usarán las franjas de horario por red). */
  marca?: string | null;
  /**
   * Ancla del calendario CONTROLADA por el padre (mes/semana/día visible). La página la
   * eleva para pedir a `/api/piezas` solo el rango visible (`rangoVisibleCalendario`).
   * Si se omite, el calendario gestiona su propia ancla (uso suelto / tests).
   */
  ancla?: Date;
  onAncla?: React.Dispatch<React.SetStateAction<Date>>;
  /**
   * Pintar el overlay de HUECOS LIBRES del plan. El padre lo apaga si la foto no es fiable
   * (p. ej. el rango venía truncado). Los huecos se expanden POR RED, así que un filtro por
   * red NO obliga a apagarlos: basta acotar los huecos a ese filtro (`filtroRed`), sin riesgo
   * de doble-reserva.
   */
  mostrarHuecosPlan?: boolean;
  /** Red activa en el filtro del padre (id canónico), o `null` si no se filtra por red. */
  filtroRed?: string | null;
}) {
  const [vista, setVista] = React.useState<Vista>("semana");
  // Ancla CONTROLADA-O-NO: si el padre la eleva (para acotar la query por rango), manda la
  // suya; si no, el calendario usa su estado local (no cambia el uso standalone ni los tests).
  const [anclaLocal, setAnclaLocal] = React.useState(() => new Date());
  const ancla = anclaProp ?? anclaLocal;
  const setAncla = onAncla ?? setAnclaLocal;
  const [diaSel, setDiaSel] = React.useState<string | null>(null);
  const [colActiva, setColActiva] = React.useState<string | null>(null);
  // Pieza con el diálogo de "Reprogramar a otra hora" abierto (null = cerrado).
  const [reprogramarPub, setReprogramarPub] = React.useState<Pieza | null>(null);
  const queryClient = useQueryClient();

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
  };
  const reprogramar = useMutation({
    mutationFn: ({ id, iso }: { id: string; iso: string }) =>
      api.actualizarPieza(id, { fecha_programada: iso }),
    onSuccess: () => {
      invalidar();
      toast.success("Pieza reprogramada.");
      setReprogramarPub(null);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const desprogramar = useMutation({
    mutationFn: (id: string) =>
      api.actualizarPieza(id, { estado: "borrador", fecha_programada: null }),
    onSuccess: () => {
      invalidar();
      toast.success("Pieza desprogramada (vuelve a Borrador).");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  // BREAKING: publica YA (salta la parrilla). Respeta `KENI_PUBLICAR_REAL`: ON publica de
  // verdad por Metricool; OFF deja una vista previa (dry-run) sin publicar.
  const publicarYa = useMutation({
    mutationFn: (id: string) => api.programarEnMetricool(id),
    onSuccess: (res) => {
      invalidar();
      const r = res.resultado;
      const redes = (r.redes ?? []).join(", ") || "—";
      toast.success(
        r.dry_run
          ? `Vista previa lista: se enviaría a Metricool (${redes}). No se publicó (dry-run).`
          : `Publicado ya en Metricool (${redes})${r.id_post ? ` · id ${r.id_post}` : ""}`,
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const ocupado = reprogramar.isPending || desprogramar.isPending || publicarYa.isPending;
  const haciaDesprogramar = (p: Pieza) => desprogramar.mutate(p.id);
  const haciaReprogramar = (p: Pieza) => setReprogramarPub(p);
  // Cambia SOLO la hora (HH:MM CDMX) conservando el DÍA de la pieza; reusa la mutación de
  // reprogramar (mismo toast/invalidación). El día sale del instante actual proyectado a CDMX.
  const haciaCambiarHora = (p: Pieza, hhmm: string) => {
    if (!p.fecha_programada) return;
    const dia = isoADatetimeLocal(p.fecha_programada).slice(0, 10);
    const iso = datetimeLocalAIso(`${dia}T${hhmm}`);
    if (iso) reprogramar.mutate({ id: p.id, iso });
  };
  const haciaPublicarYa = async (p: Pieza) => {
    if (
      await confirmar({
        titulo: "¿Publicar ya?",
        mensaje: `Se publicará "${p.titulo}" en ${nombreRed(p.red)} de inmediato, saltando la parrilla.`,
        textoConfirmar: "Publicar ya",
      })
    ) {
      publicarYa.mutate(p.id);
    }
  };

  const programadas = React.useMemo(
    () => piezas.filter((p) => !!p.fecha_programada),
    [piezas],
  );
  const porDia = React.useMemo(() => indexarPorDia(programadas), [programadas]);

  // SLOTS del plan de la marca activa (franjas con línea), como PLACEHOLDERS en las vistas
  // semana/día: el equipo ve la programación exacta del día (Nacional 18:45, …) aunque el
  // hueco siga vacío. El backend guarda (día_semana, hora) en UTC; aquí se proyecta a CDMX
  // (una hora UTC < 06:00 pertenece al día CDMX anterior).
  const franjasQuery = useQuery({
    queryKey: ["franjas"],
    queryFn: ({ signal }) => api.franjas(signal),
    enabled: Boolean(marca),
  });
  // El slot del plan es por categoría/hora (sin red): la red la multiplica `huecosDe`.
  const slotsPorDiaCdmx = React.useMemo(() => {
    const mapa = new Map<number, { hora: string; categoria: string; etiqueta: string }[]>();
    if (!marca) return mapa;
    const vistos = new Set<string>();
    for (const f of franjasQuery.data?.franjas ?? []) {
      if (f.marca !== marca || !(f.categoria ?? "")) continue;
      const [hUtc] = f.hora.split(":").map(Number);
      const diaCdmxN = hUtc >= 6 ? f.dia_semana : (f.dia_semana + 6) % 7;
      const hora = horaUtcACdmx(f.hora);
      const clave = `${diaCdmxN}|${hora}|${f.categoria}`;
      if (vistos.has(clave)) continue;
      vistos.add(clave);
      const lista = mapa.get(diaCdmxN) ?? [];
      lista.push({ hora, categoria: f.categoria, etiqueta: f.etiqueta ?? "" });
      mapa.set(diaCdmxN, lista);
    }
    for (const lista of mapa.values()) lista.sort((a, b) => a.hora.localeCompare(b.hora));
    return mapa;
  }, [franjasQuery.data, marca]);

  // REDES ESPERADAS DEL PLAN (contrato compartido con GestionPlan): el ajuste
  // `KENI_PLAN_REDES::<marca>` lleído de `/api/ajustes` (CSV de ids de red canónicos). Si el
  // ajuste falta o está vacío, fallback a las redes OBSERVADAS entre las piezas visibles de la
  // marca; si tampoco hay, queda vacío (no se pintan huecos por red, sin romper).
  const ajustesQuery = useQuery({
    queryKey: ["ajustes"],
    queryFn: ({ signal }) => api.ajustes(signal),
    enabled: Boolean(marca),
    // `/api/ajustes` es solo-admin: para el resto el 403 cae al fallback de redes observadas;
    // sin reintentos para no repetir la llamada rechazada en cada carga del calendario.
    retry: false,
  });
  const redesDelPlan = React.useMemo(() => {
    if (!marca) return [] as string[];
    const clave = `KENI_PLAN_REDES::${marca}`;
    let csv = "";
    for (const g of ajustesQuery.data?.grupos ?? []) {
      const a = g.ajustes.find((x) => x.clave === clave);
      if (a) {
        csv = String(a.valor ?? "");
        break;
      }
    }
    const delAjuste = csv
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (delAjuste.length > 0) return delAjuste;
    // Fallback: redes observadas entre las piezas programadas de la marca en el rango.
    const observadas = new Set<string>();
    for (const p of programadas) if (p.red) observadas.add(p.red);
    return [...observadas];
  }, [ajustesQuery.data, marca, programadas]);

  /**
   * Huecos LIBRES del plan para un día, EXPANDIDOS por red: por cada slot del plan y cada red
   * esperada se emite un `Hueco` salvo que exista una pieza de ESA red a esa hora ese día.
   * `ocupadas` es un set `${hora}|${red}`. Con filtro de red/línea activo se acota a él (los
   * huecos van por red, así que filtrar no produce falsos "libre").
   */
  const huecosDe = React.useCallback(
    (dia: Date): Hueco[] => {
      if (!mostrarHuecosPlan || redesDelPlan.length === 0) return [];
      // weekday(): 0=lunes..6=domingo, igual que el backend.
      const diaSemana = (dia.getDay() + 6) % 7;
      const slots = slotsPorDiaCdmx.get(diaSemana) ?? [];
      if (slots.length === 0) return [];
      const ocupadas = new Set(
        (porDia.get(claveDia(dia)) ?? []).map((p) => `${hora24Cdmx(p.fecha_programada)}|${p.red}`),
      );
      const huecos: Hueco[] = [];
      for (const sl of slots) {
        for (const red of redesDelPlan) {
          if (filtroRed && red !== filtroRed) continue;
          if (ocupadas.has(`${sl.hora}|${red}`)) continue;
          huecos.push({ hora: sl.hora, categoria: sl.categoria, etiqueta: sl.etiqueta, red });
        }
      }
      return huecos;
    },
    [slotsPorDiaCdmx, porDia, mostrarHuecosPlan, redesDelPlan, filtroRed],
  );

  const hoy = hoyCDMX();

  /** Mueve la pieza al día `diaClave` conservando su hora; no-op si ya está ese día. */
  function moverADia(diaClave: string, idArrastrada: string) {
    setColActiva(null);
    const pub = programadas.find((p) => p.id === idArrastrada);
    if (!pub?.fecha_programada) return;
    if (diaCdmx(pub) === diaClave) return;
    // datetime-local (CDMX) destino = ese día a la MISMA hora; lo pasamos a instante UTC.
    const destino = datetimeLocalAIso(`${diaClave}T${hora24Cdmx(pub.fecha_programada)}`);
    if (!destino) return;
    reprogramar.mutate({ id: idArrastrada, iso: destino });
  }

  // OJO: SIN early-return cuando no hay programadas — el panel de programación lleva más
  // que las piezas (rejilla del mes, navegación, y arriba el plan por línea y los horarios):
  // debe verse siempre. El vacío se señala con un aviso inline sobre la rejilla.

  // --- Cabecera: toggle de vista + navegación contextual ------------------------------------
  const fmtMes = new Intl.DateTimeFormat("es-MX", { month: "long", year: "numeric" });
  const fmtDiaLargo = new Intl.DateTimeFormat("es-MX", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  const fmtRango = new Intl.DateTimeFormat("es-MX", { day: "numeric", month: "short" });

  const diasSemana = diasDeSemana(ancla);
  let etiqueta: string;
  if (vista === "mes") etiqueta = fmtMes.format(ancla);
  else if (vista === "semana")
    etiqueta = `${fmtRango.format(diasSemana[0])} – ${fmtRango.format(diasSemana[6])}`;
  else etiqueta = fmtDiaLargo.format(ancla);

  function navegar(delta: number) {
    setAncla((prev) => {
      const d = new Date(prev);
      if (vista === "mes") d.setMonth(d.getMonth() + delta);
      else if (vista === "semana") d.setDate(d.getDate() + delta * 7);
      else d.setDate(d.getDate() + delta);
      return d;
    });
  }

  function abrirDia(dia: Date) {
    setAncla(dia);
    setDiaSel(claveDia(dia));
    setVista("dia");
  }

  return (
    <>
      <div className="space-y-3">
        {programadas.length === 0 && (
          <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
            <CalendarOff className="h-4 w-4 shrink-0" />
            No hay piezas programadas en esta ventana. Las piezas sin fecha se trabajan desde
            la Lista del Feed.
          </div>
        )}
        {!mostrarHuecosPlan && (
          <div className="rounded-md border border-border/60 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            Huecos del plan ocultos: la programación de esta ventana no está completa, así que un
            slot vacío podría no serlo de verdad.
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {/* Control segmentado al estilo de la plataforma (mismo look que `TabsList`/
                `TabsTrigger`): pista gris `bg-muted` con pastilla activa blanca + sombra,
                en lugar de la pastilla negra (`bg-primary`) que rompía con el resto. */}
            <div className="inline-flex h-9 items-center rounded-lg bg-muted p-1">
              {(["semana", "mes"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setVista(v)}
                  className={cn(
                    "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium capitalize transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    vista === v || (v === "semana" && vista === "dia")
                      ? "bg-background text-foreground shadow"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {v}
                </button>
              ))}
            </div>
            <p className="text-sm font-medium capitalize">{etiqueta}</p>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onClick={() => setAncla(new Date())} title="Hoy">
              Hoy
            </Button>
            <Button variant="ghost" size="icon" aria-label="Anterior" onClick={() => navegar(-1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" aria-label="Siguiente" onClick={() => navegar(1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {vista === "mes" && (
          <VistaMes
            huecosDe={huecosDe}
            ancla={ancla}
            porDia={porDia}
            hoy={hoy}
            onAbrirDia={abrirDia}
          />
        )}
        {vista === "semana" && (
          <VistaSemana
            dias={diasSemana}
            porDia={porDia}
            huecosDe={huecosDe}
            hoy={hoy}
            colActiva={colActiva}
            setColActiva={setColActiva}
            onAbrir={onEditar}
            onDesprogramar={haciaDesprogramar}
            onReprogramar={haciaReprogramar}
            onCambiarHora={haciaCambiarHora}
            onPublicarYa={haciaPublicarYa}
            onAbrirDia={abrirDia}
            onSoltarEnDia={moverADia}
            ocupado={ocupado}
          />
        )}
        {vista === "dia" && (
          <VistaDia
            huecosDe={huecosDe}
            diaClave={diaSel ?? claveDia(ancla)}
            porDia={porDia}
            onAbrir={onEditar}
            onDesprogramar={haciaDesprogramar}
            onReprogramar={haciaReprogramar}
            onCambiarHora={haciaCambiarHora}
            onPublicarYa={haciaPublicarYa}
            onVolver={() => setVista("semana")}
            ocupado={ocupado}
          />
        )}
      </div>
      <DialogoReprogramar
        pieza={reprogramarPub}
        ocupado={reprogramar.isPending}
        onConfirmar={(iso) => {
          if (reprogramarPub) reprogramar.mutate({ id: reprogramarPub.id, iso });
        }}
        onCerrar={() => setReprogramarPub(null)}
      />
    </>
  );
}

/** Rejilla mensual de RESUMEN: por día, total + conteo por red. Clic en un día → detalle. */
function VistaMes({
  huecosDe,
  ancla,
  porDia,
  hoy,
  onAbrirDia,
}: {
  huecosDe: (dia: Date) => Hueco[];
  ancla: Date;
  porDia: Map<string, Pieza[]>;
  hoy: string;
  onAbrirDia: (d: Date) => void;
}) {
  const celdas = celdasDelMes(ancla);
  const mesActual = ancla.getMonth();
  return (
    // El mes entero CABE en pantalla sin scroll vertical: la rejilla se acota al alto del
    // viewport (`calc(100dvh - …)`, idiom de la casa — cf. Turnos/parrilla) y las 6 semanas
    // reparten ese alto con filas `minmax(0,1fr)`, en vez de celdas fijas de 5.5rem que se
    // salían por abajo. `minHeight` es el suelo para pantallas cortas (ahí sí cede a scroll).
    // MÓVIL: 7 columnas no caben en 360-430px; la cuadrícula conserva un ancho mínimo legible
    // y scrollea en HORIZONTAL dentro de su contenedor (el `main` global clampa el eje X).
    <div
      className="overflow-x-auto rounded-xl border border-border"
      style={{ height: "calc(100dvh - 20rem)", minHeight: "22rem" }}
    >
    <div
      className="grid h-full min-w-[560px] grid-cols-7 gap-px bg-border/60"
      style={{ gridTemplateRows: "auto repeat(6, minmax(0, 1fr))" }}
    >
      {DIAS_SEMANA.map((d) => (
        <div
          key={d}
          className="bg-background px-2 py-2 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          {d}
        </div>
      ))}
      {celdas.map((dia) => {
        const clave = claveDia(dia);
        const delMes = dia.getMonth() === mesActual;
        const esHoy = clave === hoy;
        const items = porDia.get(clave) ?? [];
        const porRed = conteoPorRed(items);
        return (
          <button
            type="button"
            key={clave}
            onClick={() => onAbrirDia(dia)}
            className={cn(
              "min-h-0 space-y-1 overflow-hidden bg-card p-1.5 text-left transition-colors hover:bg-accent/30",
              !delMes && "bg-muted/20 text-muted-foreground",
            )}
          >
            <div className="flex items-center justify-between">
              <span
                className={cn(
                  "flex h-5 w-5 items-center justify-center text-xs",
                  esHoy && "rounded-full bg-primary font-medium text-primary-foreground",
                )}
              >
                {dia.getDate()}
              </span>
              {items.length > 0 && (
                <span className="rounded-full bg-muted px-1.5 text-[10px] font-medium tabular-nums text-muted-foreground">
                  {items.length}
                </span>
              )}
            </div>
            {porRed.length > 0 && (
              <div className="flex flex-wrap gap-x-1.5 gap-y-0.5">
                {porRed.map(({ red, n }) => {
                  const Icono = iconoRed(red);
                  return (
                    <span
                      key={red}
                      className="inline-flex items-center gap-0.5 text-[10px] tabular-nums text-muted-foreground"
                      title={`${nombreRed(red)}: ${n}`}
                    >
                      <Icono className="h-3 w-3" />
                      {n}
                    </span>
                  );
                })}
              </div>
            )}
            {/* Huecos LIBRES del plan, compactos (hora + línea abreviada, CDMX). */}
            {delMes && (
              <div className="space-y-px">
                {huecosDe(dia).map((h) => {
                  const col = colorCategoria(h.categoria);
                  const IconoRed = iconoRed(h.red);
                  return (
                    <div
                      key={`${h.hora}-${h.categoria}-${h.red}`}
                      className="flex items-center gap-1 truncate text-[9px] leading-tight text-muted-foreground/80"
                      title={`Hueco del plan: falta ${nombreRed(h.red)} · ${h.etiqueta || ETIQUETA_CATEGORIA[h.categoria] || h.categoria} a las ${h.hora}`}
                    >
                      <span
                        className={cn("h-1.5 w-1.5 shrink-0 rounded-full", col.punto)}
                        aria-hidden="true"
                      />
                      <IconoRed className="h-2.5 w-2.5 shrink-0" />
                      <span className="tabular-nums">{h.hora}</span>
                      <span className="truncate">
                        {h.etiqueta || LINEA_CORTA[h.categoria] || h.categoria}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </button>
        );
      })}
    </div>
    </div>
  );
}

/** Etiqueta CORTA de línea para las celdas del mes (espacio mínimo). */
const LINEA_CORTA: Record<string, string> = {
  mx: "Nac.",
  internacional: "Intl.",
  breaking: "Brk.",
  entretenimiento: "Entret.",
  evergreen: "Ever.",
};

/** Chip fantasma de UN hueco libre del plan (hora CDMX + RED que falta + línea). */
function ChipHueco({ hueco }: { hueco: Hueco }) {
  const nombre = hueco.etiqueta || ETIQUETA_CATEGORIA[hueco.categoria] || hueco.categoria;
  const col = colorCategoria(hueco.categoria);
  const IconoRed = iconoRed(hueco.red);
  return (
    <div
      className={cn(
        CLASES_ENTRADA_CALENDARIO,
        "border-dashed border-border/70 text-muted-foreground",
      )}
      title={`Hueco del plan: falta ${nombreRed(hueco.red)} · ${nombre} a las ${hueco.hora}`}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", col.punto)} aria-hidden="true" />
      <IconoRed className="h-3 w-3 shrink-0" aria-label={nombreRed(hueco.red)} />
      <span className="tabular-nums">{hueco.hora}</span>
      <span className="truncate">{nombre}</span>
    </div>
  );
}

/** Línea de tiempo del día: PIEZAS y HUECOS libres fusionados y ordenados por hora CDMX —
 *  cada pieza aparece EN su posición del plan, no apilada arriba. */
function entradasDelDia(
  items: Pieza[],
  huecos: Hueco[],
): ({ tipo: "pieza"; hora: string; p: Pieza } | {
  tipo: "hueco"; hora: string; h: Hueco;
})[] {
  return [
    ...items.map((p) => ({
      tipo: "pieza" as const, hora: hora24Cdmx(p.fecha_programada), p,
    })),
    ...huecos.map((h) => ({ tipo: "hueco" as const, hora: h.hora, h })),
  ].sort((a, b) => a.hora.localeCompare(b.hora));
}

/** Vista SEMANA: 7 columnas; piezas del día listadas; se arrastran entre días (reprograma). */
function VistaSemana({
  dias,
  porDia,
  hoy,
  colActiva,
  setColActiva,
  onAbrir,
  onDesprogramar,
  onReprogramar,
  onCambiarHora,
  onPublicarYa,
  onAbrirDia,
  onSoltarEnDia,
  ocupado,
  huecosDe,
}: {
  dias: Date[];
  porDia: Map<string, Pieza[]>;
  hoy: string;
  colActiva: string | null;
  setColActiva: (v: string | null) => void;
  onAbrir: (p: Pieza) => void;
  onDesprogramar: (p: Pieza) => void;
  onReprogramar: (p: Pieza) => void;
  onCambiarHora: (p: Pieza, hhmm: string) => void;
  onPublicarYa: (p: Pieza) => void;
  onAbrirDia: (d: Date) => void;
  onSoltarEnDia: (diaClave: string, id: string) => void;
  ocupado: boolean;
  huecosDe: (dia: Date) => Hueco[];
}) {
  return (
    // La semana llena el alto disponible (espeja el idiom de MES) y NO scrollea por columna:
    // en días ligeros un `min-h` calc(viewport − chrome) estira la rejilla; en días cargados la
    // rejilla CRECE y scrollea la PÁGINA (`<main>`), no la columna. `min-w` conserva el scroll
    // HORIZONTAL en móvil (7 columnas no caben en 360-430px).
    <div className="overflow-x-auto rounded-xl border border-border">
    <div className="grid min-h-[calc(100dvh-15rem)] min-w-[640px] grid-cols-7 gap-px bg-border/60">
      {dias.map((dia, i) => {
        const clave = claveDia(dia);
        const esHoy = clave === hoy;
        const items = porDia.get(clave) ?? [];
        return (
          <div
            key={clave}
            onDragOver={(e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
              if (colActiva !== clave) setColActiva(clave);
            }}
            onDragLeave={() => setColActiva(colActiva === clave ? null : colActiva)}
            onDrop={(e) => {
              e.preventDefault();
              const id = e.dataTransfer.getData("text/plain");
              if (id) onSoltarEnDia(clave, id);
            }}
            className={cn(
              "flex min-h-[18rem] flex-col bg-card transition-colors",
              colActiva === clave && "bg-primary/10",
            )}
          >
            <button
              type="button"
              onClick={() => onAbrirDia(dia)}
              className="flex items-center justify-between border-b border-border px-2 py-1.5 text-left hover:bg-accent/30"
            >
              <span className="text-xs font-semibold capitalize text-muted-foreground">
                {DIAS_SEMANA[i]}{" "}
                <span
                  className={cn(
                    "ml-0.5 tabular-nums",
                    esHoy && "rounded-full bg-primary px-1.5 text-primary-foreground",
                  )}
                >
                  {dia.getDate()}
                </span>
              </span>
              {items.length > 0 && (
                <span className="text-[10px] tabular-nums text-muted-foreground">{items.length}</span>
              )}
            </button>
            <div className="flex-1 space-y-0.5 p-1">
              {/* Piezas y huecos del plan FUSIONADOS por hora: cada pieza en su posición. */}
              {entradasDelDia(items, huecosDe(dia)).map((e) =>
                e.tipo === "pieza" ? (
                  <PildoraPub
                    key={e.p.id}
                    pieza={e.p}
                    onAbrir={onAbrir}
                    onDesprogramar={onDesprogramar}
                    onReprogramar={onReprogramar}
                    onCambiarHora={onCambiarHora}
                    onPublicarYa={onPublicarYa}
                    ocupado={ocupado}
                  />
                ) : (
                  <ChipHueco key={`h-${e.hora}-${e.h.categoria}-${e.h.red}`} hueco={e.h} />
                ),
              )}
            </div>
          </div>
        );
      })}
    </div>
    </div>
  );
}

/** Detalle de UN día: todas sus piezas (editar/desprogramar). */
function VistaDia({
  huecosDe,
  diaClave,
  porDia,
  onAbrir,
  onDesprogramar,
  onReprogramar,
  onCambiarHora,
  onPublicarYa,
  onVolver,
  ocupado,
}: {
  huecosDe: (dia: Date) => Hueco[];
  diaClave: string;
  porDia: Map<string, Pieza[]>;
  onAbrir: (p: Pieza) => void;
  onDesprogramar: (p: Pieza) => void;
  onReprogramar: (p: Pieza) => void;
  onCambiarHora: (p: Pieza, hhmm: string) => void;
  onPublicarYa: (p: Pieza) => void;
  onVolver: () => void;
  ocupado: boolean;
}) {
  const items = porDia.get(diaClave) ?? [];
  const porRed = conteoPorRed(items);
  // diaClave es "YYYY-MM-DD" (día CDMX): ancla a mediodía para que el weekday no baile.
  const huecos = huecosDe(new Date(`${diaClave}T12:00:00`));
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={onVolver}>
          <ChevronLeft className="h-4 w-4" />
          Volver a la semana
        </Button>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="tabular-nums">{items.length} piezas</span>
          {porRed.map(({ red, n }) => {
            const Icono = iconoRed(red);
            return (
              <span key={red} className="inline-flex items-center gap-0.5 tabular-nums" title={nombreRed(red)}>
                <Icono className="h-3.5 w-3.5" />
                {n}
              </span>
            );
          })}
        </div>
      </div>
      {items.length === 0 && huecos.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Nada programado este día.</p>
      ) : (
        <div className="space-y-1">
          {/* Piezas y huecos del plan FUSIONADOS por hora: cada pieza en su posición. */}
          {entradasDelDia(items, huecos).map((e) =>
            e.tipo === "pieza" ? (
              <PildoraPub
                key={e.p.id}
                pieza={e.p}
                onAbrir={onAbrir}
                onDesprogramar={onDesprogramar}
                onReprogramar={onReprogramar}
                onCambiarHora={onCambiarHora}
                onPublicarYa={onPublicarYa}
                ocupado={ocupado}
              />
            ) : (
              <ChipHueco key={`h-${e.hora}-${e.h.categoria}-${e.h.red}`} hueco={e.h} />
            ),
          )}
        </div>
      )}
    </div>
  );
}
