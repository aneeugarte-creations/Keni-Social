import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
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
import { Card, CardContent } from "@/components/ui/card";
import { api, mensajeError } from "@/lib/api";
import { horaUtcACdmx } from "@/lib/fecha";
import { ETIQUETA_LINEA } from "@/pages/publicaciones/PanelLineasPlan";
import { cn } from "@/lib/utils";
import type { Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import {
  datetimeLocalAIso,
  formatearHora,
  iconoRed,
  isoADatetimeLocal,
  nombreRed,
} from "./meta";

type Vista = "mes" | "semana" | "dia";

/** Nombres de los días (lunes a domingo), abreviados es-MX. */
const DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

/** Clave YYYY-MM-DD en hora CDMX de una pieza programada ("" si no aplica). */
function diaCdmx(p: Publicacion): string {
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

/** Índice día(CDMX) -> publicaciones programadas ese día (ordenadas por hora). */
function indexarPorDia(publicaciones: Publicacion[]): Map<string, Publicacion[]> {
  const mapa = new Map<string, Publicacion[]>();
  for (const p of publicaciones) {
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
function conteoPorRed(items: Publicacion[]): { red: string; n: number }[] {
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

/** Una píldora de publicación: arrastrable, click abre el editor, clic-derecho el menú. */
function PildoraPub({
  publicacion,
  onAbrir,
  onDesprogramar,
  onPublicarYa,
  ocupado,
}: {
  publicacion: Publicacion;
  onAbrir: (p: Publicacion) => void;
  onDesprogramar: (p: Publicacion) => void;
  onPublicarYa: (p: Publicacion) => void;
  ocupado: boolean;
}) {
  const Icono = iconoRed(publicacion.red);
  // Ya publicado → verde; programado (pendiente de salir) → ámbar.
  const publicado = publicacion.estado === "publicado";
  return (
    <MenuContextual
      disparador="contextmenu"
      etiqueta={`Acciones de "${publicacion.titulo}"`}
      items={[
        {
          // BREAKING: publica YA (salta la parrilla). Real o dry-run según KENI_PUBLICAR_REAL.
          etiqueta: "Publicar ya",
          icono: Zap,
          deshabilitado: ocupado,
          onClick: () => onPublicarYa(publicacion),
        },
        { separador: true },
        {
          etiqueta: "Editar",
          icono: Pencil,
          onClick: () => onAbrir(publicacion),
        },
        {
          etiqueta: "Desprogramar",
          icono: CalendarX,
          deshabilitado: ocupado,
          onClick: () => onDesprogramar(publicacion),
        },
      ]}
    >
      <button
        type="button"
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData("text/plain", publicacion.id);
          e.dataTransfer.effectAllowed = "move";
        }}
        onClick={() => onAbrir(publicacion)}
        title={`${publicacion.titulo} (${nombreRed(publicacion.red)}) · arrastra para mover · clic derecho para más`}
        className={cn(
          "flex w-full cursor-grab items-center gap-1 truncate rounded px-1.5 py-0.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring active:cursor-grabbing",
          publicado
            ? "bg-emerald-500/15 text-emerald-800 hover:bg-emerald-500/25 dark:text-emerald-200"
            : "bg-amber-500/15 text-amber-800 hover:bg-amber-500/25 dark:text-amber-200",
        )}
      >
        <Icono className="h-3 w-3 shrink-0" />
        <span className="shrink-0 tabular-nums">{formatearHora(publicacion.fecha_programada)}</span>
        <span className="truncate">{publicacion.titulo}</span>
      </button>
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
 * Reprogramar/desprogramar usan `api.actualizarPublicacion` (horas en CDMX vía `@/lib/fecha`).
 * (El reparto automático por cadencia de cada red es trabajo del motor de producción, aparte.)
 */
export function VistaCalendario({
  publicaciones,
  onEditar,
  marca,
}: {
  publicaciones: Publicacion[];
  onEditar: (p: Publicacion) => void;
  /** Reservado: marca activa (la usará la cadencia por red). */
  marca?: string | null;
}) {
  const [vista, setVista] = React.useState<Vista>("mes");
  const [ancla, setAncla] = React.useState(() => new Date());
  const [diaSel, setDiaSel] = React.useState<string | null>(null);
  const [colActiva, setColActiva] = React.useState<string | null>(null);
  const queryClient = useQueryClient();

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
  };
  const reprogramar = useMutation({
    mutationFn: ({ id, iso }: { id: string; iso: string }) =>
      api.actualizarPublicacion(id, { fecha_programada: iso }),
    onSuccess: () => {
      invalidar();
      toast.success("Pieza reprogramada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const desprogramar = useMutation({
    mutationFn: (id: string) =>
      api.actualizarPublicacion(id, { estado: "borrador", fecha_programada: null }),
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
  const haciaDesprogramar = (p: Publicacion) => desprogramar.mutate(p.id);
  const haciaPublicarYa = async (p: Publicacion) => {
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
    () => publicaciones.filter((p) => !!p.fecha_programada),
    [publicaciones],
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
  const slotsPorDiaCdmx = React.useMemo(() => {
    const mapa = new Map<number, { hora: string; categoria: string }[]>();
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
      lista.push({ hora, categoria: f.categoria });
      mapa.set(diaCdmxN, lista);
    }
    for (const lista of mapa.values()) lista.sort((a, b) => a.hora.localeCompare(b.hora));
    return mapa;
  }, [franjasQuery.data, marca]);

  /** Huecos LIBRES del plan para un día concreto (slots sin pieza a esa misma hora CDMX). */
  const huecosDe = React.useCallback(
    (dia: Date): { hora: string; categoria: string }[] => {
      // weekday(): 0=lunes..6=domingo, igual que el backend.
      const diaSemana = (dia.getDay() + 6) % 7;
      const slots = slotsPorDiaCdmx.get(diaSemana) ?? [];
      if (slots.length === 0) return [];
      const ocupadas = new Set(
        (porDia.get(claveDia(dia)) ?? []).map((p) => hora24Cdmx(p.fecha_programada)),
      );
      return slots.filter((sl) => !ocupadas.has(sl.hora));
    },
    [slotsPorDiaCdmx, porDia],
  );

  const hoy = claveDia(new Date());

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
  // que las piezas (rejilla del mes, navegación, y arriba el plan por línea y la cadencia):
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
    <Card>
      <CardContent className="space-y-3 py-4">
        {programadas.length === 0 && (
          <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
            <CalendarOff className="h-4 w-4 shrink-0" />
            No hay piezas programadas.
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="inline-flex overflow-hidden rounded-md border border-border">
              {(["mes", "semana"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setVista(v)}
                  className={cn(
                    "px-3 py-1 text-sm capitalize transition-colors",
                    vista === v || (v === "semana" && vista === "dia")
                      ? "bg-primary text-primary-foreground"
                      : "bg-card text-muted-foreground hover:bg-muted",
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
            onPublicarYa={haciaPublicarYa}
            onVolver={() => setVista("semana")}
            ocupado={ocupado}
          />
        )}
      </CardContent>
    </Card>
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
  huecosDe: (dia: Date) => { hora: string; categoria: string }[];
  ancla: Date;
  porDia: Map<string, Publicacion[]>;
  hoy: string;
  onAbrirDia: (d: Date) => void;
}) {
  const celdas = celdasDelMes(ancla);
  const mesActual = ancla.getMonth();
  return (
    // MÓVIL: 7 columnas no caben en 360-430px (celdas de ~50px, ilegibles). La cuadrícula
    // conserva un ancho mínimo legible y scrollea en horizontal dentro de su contenedor;
    // el `main` global clampa el eje X, así que el swipe queda acotado al calendario.
    <div className="overflow-x-auto rounded-md border border-border">
    <div className="grid min-w-[560px] grid-cols-7 gap-px bg-border">
      {DIAS_SEMANA.map((d) => (
        <div
          key={d}
          className="bg-muted/60 px-2 py-1.5 text-center text-xs font-medium text-muted-foreground"
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
              "min-h-[5.5rem] space-y-1 bg-card p-1.5 text-left transition-colors hover:bg-accent/30",
              !delMes && "bg-muted/30 text-muted-foreground",
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
                <span className="rounded-full bg-amber-500/15 px-1.5 text-[10px] font-medium tabular-nums text-amber-800 dark:text-amber-200">
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
                {huecosDe(dia).map((h) => (
                  <div
                    key={`${h.hora}-${h.categoria}`}
                    className="truncate border-l-2 border-dashed border-border pl-1 text-[9px] leading-tight text-muted-foreground/80"
                    title={`Hueco del plan: ${ETIQUETA_LINEA[h.categoria] ?? h.categoria} a las ${h.hora}`}
                  >
                    <span className="tabular-nums">{h.hora}</span>{" "}
                    {LINEA_CORTA[h.categoria] ?? h.categoria}
                  </div>
                ))}
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

/** Chip fantasma de UN hueco libre del plan (hora CDMX + línea). */
function ChipHueco({ hueco }: { hueco: { hora: string; categoria: string } }) {
  return (
    <div
      className="flex items-center gap-1 rounded border border-dashed border-border/70 px-1.5 py-0.5 text-[10px] text-muted-foreground"
      title={`Hueco del plan: ${ETIQUETA_LINEA[hueco.categoria] ?? hueco.categoria} a las ${hueco.hora}`}
    >
      <span className="tabular-nums">{hueco.hora}</span>
      <span className="truncate">{ETIQUETA_LINEA[hueco.categoria] ?? hueco.categoria}</span>
    </div>
  );
}

/** Línea de tiempo del día: PIEZAS y HUECOS libres fusionados y ordenados por hora CDMX —
 *  cada pieza aparece EN su posición del plan, no apilada arriba. */
function entradasDelDia(
  items: Publicacion[],
  huecos: { hora: string; categoria: string }[],
): ({ tipo: "pieza"; hora: string; p: Publicacion } | {
  tipo: "hueco"; hora: string; h: { hora: string; categoria: string };
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
  onPublicarYa,
  onAbrirDia,
  onSoltarEnDia,
  ocupado,
  huecosDe,
}: {
  dias: Date[];
  porDia: Map<string, Publicacion[]>;
  hoy: string;
  colActiva: string | null;
  setColActiva: (v: string | null) => void;
  onAbrir: (p: Publicacion) => void;
  onDesprogramar: (p: Publicacion) => void;
  onPublicarYa: (p: Publicacion) => void;
  onAbrirDia: (d: Date) => void;
  onSoltarEnDia: (diaClave: string, id: string) => void;
  ocupado: boolean;
  huecosDe: (dia: Date) => { hora: string; categoria: string }[];
}) {
  return (
    // MÓVIL: mismo tratamiento que la vista MES — la semana scrollea en horizontal.
    <div className="overflow-x-auto rounded-md border border-border">
    <div className="grid min-w-[640px] grid-cols-7 gap-px bg-border">
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
              <span className="text-xs font-medium text-muted-foreground">
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
            <div className="max-h-[28rem] flex-1 space-y-0.5 overflow-y-auto p-1">
              {/* Piezas y huecos del plan FUSIONADOS por hora: cada pieza en su posición. */}
              {entradasDelDia(items, huecosDe(dia)).map((e) =>
                e.tipo === "pieza" ? (
                  <PildoraPub
                    key={e.p.id}
                    publicacion={e.p}
                    onAbrir={onAbrir}
                    onDesprogramar={onDesprogramar}
                    onPublicarYa={onPublicarYa}
                    ocupado={ocupado}
                  />
                ) : (
                  <ChipHueco key={`h-${e.hora}-${e.h.categoria}`} hueco={e.h} />
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
  onPublicarYa,
  onVolver,
  ocupado,
}: {
  huecosDe: (dia: Date) => { hora: string; categoria: string }[];
  diaClave: string;
  porDia: Map<string, Publicacion[]>;
  onAbrir: (p: Publicacion) => void;
  onDesprogramar: (p: Publicacion) => void;
  onPublicarYa: (p: Publicacion) => void;
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
                publicacion={e.p}
                onAbrir={onAbrir}
                onDesprogramar={onDesprogramar}
                onPublicarYa={onPublicarYa}
                ocupado={ocupado}
              />
            ) : (
              <ChipHueco key={`h-${e.hora}-${e.h.categoria}`} hueco={e.h} />
            ),
          )}
        </div>
      )}
    </div>
  );
}
