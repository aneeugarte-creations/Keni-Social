import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarOff, CalendarX, ChevronLeft, ChevronRight } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MenuContextual } from "@/components/comunes/MenuContextual";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Franja, Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { CLAVE_FRANJAS } from "./franjas";
import { datetimeLocalAIso, formatearHora, iconoRed, nombreRed } from "./meta";

/** Nombres de los días (lunes a domingo), abreviados es-MX. */
const DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

/** Día de la semana de un `Date` en convención de franjas: 0=lunes .. 6=domingo. */
function diaSemanaFranja(d: Date): number {
  return (d.getDay() + 6) % 7;
}

/** Clave YYYY-MM-DD en hora local para agrupar por día. */
function claveDia(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema. Vuelve a intentarlo.";
}

/** Índice día -> publicaciones programadas ese día (ordenadas por hora). */
function indexarPorDia(publicaciones: Publicacion[]): Map<string, Publicacion[]> {
  const mapa = new Map<string, Publicacion[]>();
  for (const p of publicaciones) {
    if (!p.fecha_programada) continue;
    const d = new Date(p.fecha_programada);
    if (Number.isNaN(d.getTime())) continue;
    const clave = claveDia(d);
    const lista = mapa.get(clave) ?? [];
    lista.push(p);
    mapa.set(clave, lista);
  }
  for (const lista of mapa.values()) {
    lista.sort((a, b) => {
      const ta = a.fecha_programada ? new Date(a.fecha_programada).getTime() : 0;
      const tb = b.fecha_programada ? new Date(b.fecha_programada).getTime() : 0;
      return ta - tb;
    });
  }
  return mapa;
}

/** Devuelve las celdas (42, 6 semanas) que componen la rejilla del mes. */
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
 * Mapa día-de-semana (0=lun..6=dom) -> horas de franja ordenadas, a partir de las franjas
 * relevantes a la marca activa. Una franja `marca===""` aplica a todas; si hay marca activa,
 * además las suyas. Colapsa horas repetidas (varias redes pueden compartir hueco).
 */
function horasPorDiaSemana(franjas: Franja[], marca: string | null): Map<number, string[]> {
  const porDia = new Map<number, Set<string>>();
  for (const f of franjas) {
    if (marca != null && f.marca !== "" && f.marca !== marca) continue;
    const set = porDia.get(f.dia_semana) ?? new Set<string>();
    set.add(f.hora);
    porDia.set(f.dia_semana, set);
  }
  const ordenado = new Map<number, string[]>();
  for (const [dia, horas] of porDia) {
    ordenado.set(dia, [...horas].sort());
  }
  return ordenado;
}

/** Una píldora de publicación: arrastrable, click abre el editor, clic-derecho el menú. */
function PildoraPub({
  publicacion,
  onAbrir,
  onDesprogramar,
  ocupado,
}: {
  publicacion: Publicacion;
  onAbrir: (p: Publicacion) => void;
  onDesprogramar: (p: Publicacion) => void;
  ocupado: boolean;
}) {
  const Icono = iconoRed(publicacion.red);
  return (
    <MenuContextual
      disparador="contextmenu"
      etiqueta={`Acciones de "${publicacion.titulo}"`}
      items={[
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
        title={`${formatearHora(publicacion.fecha_programada)} · ${nombreRed(publicacion.red)} · ${publicacion.titulo} · arrastra para reprogramar · clic derecho para desprogramar`}
        className="flex w-full cursor-grab items-center gap-1 truncate rounded bg-amber-500/15 px-1.5 py-0.5 text-left text-xs text-amber-800 transition-colors hover:bg-amber-500/25 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring active:cursor-grabbing dark:text-amber-200"
      >
        <Icono className="h-3 w-3 shrink-0" />
        <span className="shrink-0 tabular-nums">{formatearHora(publicacion.fecha_programada)}</span>
        <span className="truncate">{publicacion.titulo}</span>
      </button>
    </MenuContextual>
  );
}

/** Un hueco de franja (hora) dentro de un día: etiqueta + piezas, y zona de drop. */
function FranjaSlot({
  hora,
  items,
  resaltado,
  onAbrir,
  onDesprogramar,
  ocupado,
  onDragOver,
  onDragLeave,
  onDrop,
}: {
  hora: string;
  items: Publicacion[];
  resaltado: boolean;
  onAbrir: (p: Publicacion) => void;
  onDesprogramar: (p: Publicacion) => void;
  ocupado: boolean;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (e: React.DragEvent) => void;
}) {
  return (
    <div
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={cn(
        "rounded border border-dashed border-border/70 p-1 transition-colors",
        resaltado && "border-primary bg-primary/10",
      )}
    >
      <div className="px-0.5 text-[10px] font-medium tabular-nums text-muted-foreground">
        {hora}
      </div>
      {items.length === 0 ? (
        <p className="px-0.5 text-[10px] text-muted-foreground/50">Vacío</p>
      ) : (
        <div className="mt-0.5 space-y-0.5">
          {items.map((p) => (
            <PildoraPub
              key={p.id}
              publicacion={p}
              onAbrir={onAbrir}
              onDesprogramar={onDesprogramar}
              ocupado={ocupado}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Vista calendario: rejilla mensual navegable que muestra las publicaciones programadas en
 * su día, ORGANIZADAS POR FRANJA DE POSTEO (las horas-cola de la marca). Permite:
 *  - ver las franjas de cada día (huecos, incluso vacíos);
 *  - reprogramar arrastrando una pieza de un hueco a otro (cualquier día/hora de franja);
 *  - desprogramar una pieza (clic derecho → vuelve a Borrador, sale de la parrilla).
 *
 * Las franjas se filtran por la marca activa (las globales aplican siempre). Las horas se
 * tratan en zona CDMX (vía `@/lib/fecha`), coherente con el resto de la consola.
 */
export function VistaCalendario({
  publicaciones,
  onEditar,
  marca = null,
}: {
  publicaciones: Publicacion[];
  onEditar: (p: Publicacion) => void;
  /** Marca activa para acotar las franjas (null = todas). */
  marca?: string | null;
}) {
  const [ancla, setAncla] = React.useState(() => new Date());
  // Hueco resaltado durante un drag (clave `dia|hora`), para feedback de drop.
  const [slotActivo, setSlotActivo] = React.useState<string | null>(null);
  const queryClient = useQueryClient();

  const franjasQuery = useQuery({
    queryKey: CLAVE_FRANJAS,
    queryFn: ({ signal }) => api.franjas(signal),
  });
  const horasPorDia = React.useMemo(
    () => horasPorDiaSemana(franjasQuery.data?.franjas ?? [], marca),
    [franjasQuery.data, marca],
  );

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
  const ocupado = reprogramar.isPending || desprogramar.isPending;

  const programadas = React.useMemo(
    () => publicaciones.filter((p) => !!p.fecha_programada),
    [publicaciones],
  );
  const porDia = React.useMemo(() => indexarPorDia(programadas), [programadas]);
  const celdas = React.useMemo(() => celdasDelMes(ancla), [ancla]);

  const hoy = claveDia(new Date());
  const mesActual = ancla.getMonth();
  const etiquetaMes = new Intl.DateTimeFormat("es-MX", {
    month: "long",
    year: "numeric",
  }).format(ancla);

  function cambiarMes(delta: number) {
    setAncla((prev) => new Date(prev.getFullYear(), prev.getMonth() + delta, 1));
  }

  /** Reprograma la pieza arrastrada a `diaClave` + `hora` (CDMX); no-op si ya está ahí. */
  function soltarEn(diaClave: string, hora: string, idArrastrada: string) {
    setSlotActivo(null);
    const pub = programadas.find((p) => p.id === idArrastrada);
    if (!pub) return;
    const yaAqui =
      pub.fecha_programada != null &&
      claveDia(new Date(pub.fecha_programada)) === diaClave &&
      formatearHora(pub.fecha_programada) === hora;
    if (yaAqui) return;
    const iso = datetimeLocalAIso(`${diaClave}T${hora}`);
    if (!iso) return;
    reprogramar.mutate({ id: idArrastrada, iso });
  }

  const sinFranjas = (franjasQuery.data?.franjas ?? []).length === 0;
  if (programadas.length === 0 && sinFranjas) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <CalendarOff className="h-6 w-6" />
          </div>
          <div className="space-y-1">
            <p className="font-medium">No hay publicaciones programadas ni franjas</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Define franjas de posteo (en “Gestionar”) y programa piezas para verlas y
              moverlas aquí.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-3 py-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium capitalize">{etiquetaMes}</p>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAncla(new Date())}
              title="Ir al mes actual"
            >
              Hoy
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Mes anterior"
              onClick={() => cambiarMes(-1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Mes siguiente"
              onClick={() => cambiarMes(1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-7 gap-px overflow-hidden rounded-md border border-border bg-border">
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
            const franjaHoras = horasPorDia.get(diaSemanaFranja(dia)) ?? [];
            // Reparte las piezas del día por hora de franja; las que no casan ninguna van a "otras".
            const porHora = new Map<string, Publicacion[]>();
            const otras: Publicacion[] = [];
            for (const p of items) {
              const h = formatearHora(p.fecha_programada);
              if (franjaHoras.includes(h)) {
                porHora.set(h, [...(porHora.get(h) ?? []), p]);
              } else {
                otras.push(p);
              }
            }
            return (
              <div
                key={clave}
                className={cn(
                  "min-h-[7rem] space-y-1 bg-card p-1.5",
                  !delMes && "bg-muted/30 text-muted-foreground",
                )}
              >
                <div
                  className={cn(
                    "flex h-5 w-5 items-center justify-center text-xs",
                    esHoy && "rounded-full bg-primary font-medium text-primary-foreground",
                  )}
                >
                  {dia.getDate()}
                </div>

                <div className="space-y-1">
                  {franjaHoras.map((hora) => {
                    const slotKey = `${clave}|${hora}`;
                    return (
                      <FranjaSlot
                        key={slotKey}
                        hora={hora}
                        items={porHora.get(hora) ?? []}
                        resaltado={slotActivo === slotKey}
                        onAbrir={onEditar}
                        onDesprogramar={(p) => desprogramar.mutate(p.id)}
                        ocupado={ocupado}
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.dataTransfer.dropEffect = "move";
                          if (slotActivo !== slotKey) setSlotActivo(slotKey);
                        }}
                        onDragLeave={() => setSlotActivo((s) => (s === slotKey ? null : s))}
                        onDrop={(e) => {
                          e.preventDefault();
                          const id = e.dataTransfer.getData("text/plain");
                          if (id) soltarEn(clave, hora, id);
                        }}
                      />
                    );
                  })}

                  {/* Piezas fuera de cualquier franja (hora no-cola): visibles y arrastrables. */}
                  {otras.length > 0 && (
                    <div className="space-y-0.5 pt-0.5">
                      {franjaHoras.length > 0 && (
                        <p className="px-0.5 text-[10px] text-muted-foreground/60">Fuera de franja</p>
                      )}
                      {otras.map((p) => (
                        <PildoraPub
                          key={p.id}
                          publicacion={p}
                          onAbrir={onEditar}
                          onDesprogramar={(x) => desprogramar.mutate(x.id)}
                          ocupado={ocupado}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
