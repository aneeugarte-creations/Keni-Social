// Vista MENSUAL de la rota (modo «Mes» del Calendario): dos calendarios mensuales de jornada
// (turnos) con un selector de ámbito arriba:
//   • «Equipo» — la jornada de TODO el equipo en el mes (quién trabaja cada franja).
//   • «Yo»     — solo el horario propio del usuario en el mes.
// Sobre esa jornada se SUPERPONE, por día, un indicador compacto de eventos + cobertura (cuántos
// eventos hay y cuántos están sin cubrir), derivado en `useTableroMes`. Pulsar un día con eventos
// abre el «Resumen del día» (detalle de cobertura). La rejilla SEMANAL es el modo «Semana».
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Printer,
  User,
  Users,
} from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup } from "@/components/ui/toggle-group";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { COBERTURA_TEXTO } from "@/lib/estado-color";
import { hoyCDMX } from "@/lib/fecha";
import {
  esFinDeSemana,
  mesDeFecha,
  mesSiguiente,
  mismoMes,
  nombreMes,
  semanasDelMes,
} from "@/lib/rota-calendario";
import { cn } from "@/lib/utils";
import type { TurnoRota } from "@/types";

import { presentacionTurnoPorHora } from "./comun";
import { ResumenDia } from "./ResumenDia";
import { type ResumenDiaCobertura, useTableroMes } from "./useTableroMes";

type Ambito = "equipo" | "yo";

// --- Vista mensual (modo «Mes» del Calendario) ------------------------------

export function VistaMensualTurnos({
  esAdmin = false,
  onVerSemana,
  mostrarCobertura = true,
  controlesPre,
  marcadorSalud,
}: {
  /** El admin no suele estar en la rota: por eso arranca en «Equipo» (sí ve algo). */
  esAdmin?: boolean;
  /** Salta a la rejilla SEMANAL del mismo Calendario (lo ofrece el vacío de «Yo» a quien gestiona). */
  onVerSemana?: () => void;
  /** Superpone el estado de cobertura por día («N ev · M sin cubrir») + el «Resumen del día». En
   *  «Horario» (calendario de turnos puro) va `false`: solo jornada. En Gestión queda `true`. */
  mostrarCobertura?: boolean;
  /** Controles antepuestos a «Equipo|Yo» en la zona izquierda de la barra: el Calendario inyecta aquí
   *  su conmutador Semana|Mes en Gestión. En «Horario» va vacío (no hay vista Semana). */
  controlesPre?: React.ReactNode;
  /** Marcador de estado (✓ «Al día») a la derecha, junto a «Imprimir». Lo inyecta Gestión (SOSIEGO). */
  marcadorSalud?: React.ReactNode;
}) {
  const { marcaActiva } = useMarcaActiva();
  const { usuario } = useSesion();
  const [ambito, setAmbito] = React.useState<Ambito>(esAdmin ? "equipo" : "yo");
  const [mes, setMes] = React.useState(() => mesDeFecha(new Date()));
  const [diaResumen, setDiaResumen] = React.useState<string | null>(null);

  // Cobertura del mes (eventos + estado por día) superpuesta sobre la jornada. Hook propio a
  // escala de mes; NO toca `useTablero` (infra del cockpit). Con `mostrarCobertura=false` (Horario
  // = turnos puros) NO dispara ningún fetch de eventos/cobertura.
  const { porDia } = useTableroMes(mes, marcaActiva ?? undefined, mostrarCobertura);
  const cobertura = mostrarCobertura ? porDia : undefined;
  const onAbrirDia = mostrarCobertura ? setDiaResumen : undefined;

  return (
    <div className="space-y-4">
      {/* UNA barra de tres zonas: izquierda (modo de vista) · centro (el mes, foco) · derecha
          (estado + acción). En md+ es un grid 1fr·auto·1fr para centrar ópticamente el mes; en móvil
          las tres zonas se apilan. */}
      <div className="grid grid-cols-1 items-center gap-3 md:grid-cols-[1fr_auto_1fr]">
        <div className="flex flex-wrap items-center gap-2 md:justify-self-start">
          {controlesPre}
          <SelectorAmbito ambito={ambito} setAmbito={setAmbito} />
        </div>
        <div className="md:justify-self-center">
          <NavegadorMes mes={mes} setMes={setMes} />
        </div>
        <div className="flex items-center gap-2 md:justify-self-end">
          {marcadorSalud}
          {/* «Imprimir»: solo el icono, botón-icono outline (el icon-button de la app). */}
          <Button
            variant="outline"
            size="icon"
            onClick={imprimirMes}
            title="Imprimir o guardar como PDF"
            aria-label="Imprimir / PDF"
          >
            <Printer className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {ambito === "equipo" ? (
        <VistaMesEquipo mes={mes} cobertura={cobertura} onAbrirDia={onAbrirDia} />
      ) : (
        <VistaMesYo
          mes={mes}
          esAdmin={esAdmin}
          onVerSemana={onVerSemana}
          cobertura={cobertura}
          onAbrirDia={onAbrirDia}
        />
      )}

      {diaResumen && (
        <ResumenDia
          fecha={diaResumen}
          marca={marcaActiva ?? undefined}
          usuarioId={usuario?.id ?? null}
          onClose={() => setDiaResumen(null)}
        />
      )}
    </div>
  );
}

/** Conmutador Equipo/Yo, al estilo de la plataforma (segmentado sobrio con palabras). */
function SelectorAmbito({
  ambito,
  setAmbito,
}: {
  ambito: Ambito;
  setAmbito: (a: Ambito) => void;
}) {
  return (
    <ToggleGroup
      ariaLabel="Ámbito de la jornada"
      valor={ambito}
      onCambio={setAmbito}
      opciones={[
        {
          valor: "equipo",
          ariaLabel: "Equipo",
          etiqueta: (
            <>
              <Users className="h-3.5 w-3.5" /> Equipo
            </>
          ),
        },
        {
          valor: "yo",
          ariaLabel: "Yo",
          etiqueta: (
            <>
              <User className="h-3.5 w-3.5" /> Yo
            </>
          ),
        },
      ]}
    />
  );
}

/** Imprime solo la rejilla del mes (o «Guardar como PDF»). La clase en `body` acota el
 *  CSS de impresión a esta vista (un Ctrl+P en otra pantalla no se ve afectado). */
function imprimirMes() {
  document.body.classList.add("imprimiendo-mes");
  const limpiar = () => {
    document.body.classList.remove("imprimiendo-mes");
    window.removeEventListener("afterprint", limpiar);
  };
  window.addEventListener("afterprint", limpiar);
  // Red de seguridad por si `afterprint` no dispara en algún navegador.
  window.setTimeout(limpiar, 2000);
  window.print();
}

/** Navegador de mes (‹ junio de 2026 ›) con atajo «Hoy». */
function NavegadorMes({
  mes,
  setMes,
}: {
  mes: string;
  setMes: (m: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Button
        variant="ghost"
        size="icon"
        aria-label="Mes anterior"
        onClick={() => setMes(mesSiguiente(mes, -1))}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      {/* Sin `capitalize`: title-caseaba cada palabra y dejaba «Junio De 2026»; «junio de 2026» es la
          forma correcta es-MX que devuelve `nombreMes`. */}
      <div className="min-w-[11rem] text-center text-sm font-medium">
        <CalendarDays className="mr-1.5 inline h-4 w-4 text-muted-foreground" />
        {nombreMes(mes)}
      </div>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Mes siguiente"
        onClick={() => setMes(mesSiguiente(mes, 1))}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        onClick={() => setMes(mesDeFecha(new Date()))}
      >
        Hoy
      </Button>
    </div>
  );
}

// --- Rejilla mensual (scaffold compartido por ambas vistas) -----------------

const DIAS_CABECERA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

/**
 * Cuadrícula del mes lun→dom. El contenido de cada día lo decide `renderDia` (las dos
 * vistas comparten el armazón: cabecera, hoy, finde y días del mes vecino atenuados).
 * Bordes REALES (no `gap-px`, que es fondo y no se imprime) para que salga completa en papel.
 *
 * `cobertura` (opcional) superpone el indicador de eventos/cobertura del día; pulsarlo abre el
 * «Resumen del día» vía `onAbrirDia`.
 */
function RejillaMensual({
  mes,
  renderDia,
  cobertura,
  onAbrirDia,
}: {
  mes: string;
  renderDia: (fecha: string, delMes: boolean) => React.ReactNode;
  cobertura?: Map<string, ResumenDiaCobertura>;
  onAbrirDia?: (fecha: string) => void;
}) {
  const hoy = hoyCDMX();
  const dias = React.useMemo(() => semanasDelMes(mes).flat(), [mes]);
  return (
    <div className="overflow-hidden rounded-lg border-l border-t">
      <div className="grid grid-cols-7 bg-muted/40 text-center text-[11px] font-medium uppercase tracking-wide text-muted-foreground print:bg-transparent">
        {DIAS_CABECERA.map((d) => (
          <div key={d} className="border-b border-r py-2">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {dias.map((fecha) => {
          const delMes = mismoMes(fecha, mes);
          const finde = esFinDeSemana(fecha);
          const esHoy = fecha === hoy;
          const resumen = delMes ? cobertura?.get(fecha) : undefined;
          return (
            <div
              key={fecha}
              className={`min-h-[5.25rem] border-b border-r bg-background p-1.5 print:min-h-[3.25rem] ${
                !delMes ? "bg-muted/20" : finde ? "bg-muted/30" : ""
              } ${esHoy ? "ring-1 ring-inset ring-keni-500/50" : ""}`}
            >
              <div
                className={`mb-1 text-right text-xs tabular-nums ${
                  esHoy
                    ? "font-semibold text-keni-700 dark:text-keni-300"
                    : delMes
                      ? "text-muted-foreground"
                      : "text-muted-foreground/50"
                }`}
              >
                {Number(fecha.slice(8, 10))}
              </div>
              {resumen && (
                <IndicadorCobertura
                  fecha={fecha}
                  resumen={resumen}
                  onAbrir={onAbrirDia}
                />
              )}
              <div className="space-y-1">{renderDia(fecha, delMes)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Indicador compacto de la jornada de un día: nº de eventos y, si hay huecos, nº SIN CUBRIR en
 * AMARILLO (la convención central de `estado-color`, NO rojo). Distingue de un vistazo «todo
 * cubierto» (gris, sin amarillo) de «con huecos» (amarillo) de «sin eventos» (no se renderiza).
 * Si hay eventos y `onAbrir`, es un botón que abre el «Resumen del día»; si no, es informativo.
 * Una ausencia que toca el día se marca con un triángulo ámbar al lado.
 */
function IndicadorCobertura({
  fecha,
  resumen,
  onAbrir,
}: {
  fecha: string;
  resumen: ResumenDiaCobertura;
  onAbrir?: (fecha: string) => void;
}) {
  const { nEventos, nSinCubrir, hayAusencia } = resumen;
  const contenido = (
    <>
      {nEventos > 0 ? (
        <span className="tabular-nums">
          {nEventos} ev
          {nSinCubrir > 0 && (
            <>
              {" · "}
              <span className={cn("font-medium", COBERTURA_TEXTO["sin-cubrir"])}>
                {nSinCubrir} sin cubrir
              </span>
            </>
          )}
        </span>
      ) : (
        <span className="text-muted-foreground">Sin eventos</span>
      )}
      {hayAusencia && (
        <AlertTriangle
          className="h-3 w-3 shrink-0 text-amber-600 dark:text-amber-400"
          aria-hidden
        />
      )}
    </>
  );

  const clases =
    "mb-1 flex w-full items-center gap-1 rounded border border-border bg-card px-1.5 py-0.5 text-[10px] leading-tight";

  if (nEventos > 0 && onAbrir) {
    return (
      <button
        type="button"
        onClick={() => onAbrir(fecha)}
        title={`Ver el resumen del día (${nEventos} eventos${nSinCubrir > 0 ? `, ${nSinCubrir} sin cubrir` : ""})`}
        className={cn(
          clases,
          "text-left text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring print:hover:bg-card",
        )}
      >
        {contenido}
      </button>
    );
  }
  return <div className={cn(clases, "text-muted-foreground")}>{contenido}</div>;
}

/** Encabezado que SOLO aparece al imprimir, para identificar la hoja (mes + subtítulo). */
function EncabezadoImpresion({ mes, subtitulo }: { mes: string; subtitulo: string }) {
  return (
    <div className="mb-3 hidden print:block">
      <h2 className="text-lg font-semibold capitalize">{nombreMes(mes)}</h2>
      <p className="text-sm text-neutral-600">{subtitulo}</p>
    </div>
  );
}

// --- Vista YO: solo el horario propio ---------------------------------------

function VistaMesYo({
  mes,
  esAdmin = false,
  onVerSemana,
  cobertura,
  onAbrirDia,
}: {
  mes: string;
  esAdmin?: boolean;
  onVerSemana?: () => void;
  cobertura?: Map<string, ResumenDiaCobertura>;
  onAbrirDia?: (fecha: string) => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const q = useQuery({
    queryKey: ["rota", "mis-turnos-mes", mes, marcaActiva],
    queryFn: ({ signal }) =>
      api.misTurnosMes({ mes, marca: marcaActiva ?? undefined }, signal),
  });
  const datos = q.data;
  const turnos = React.useMemo(() => datos?.mis_turnos ?? [], [datos?.mis_turnos]);
  const porFecha = React.useMemo(() => agruparPorFecha(turnos), [turnos]);

  if (q.isPending) return <Skeleton className="h-[28rem] w-full rounded-lg" />;
  if (q.isError)
    return (
      <BloqueError
        titulo="No se pudo cargar tu mes"
        mensaje={mensajeError(q.error)}
        onReintentar={() => void q.refetch()}
        cargando={q.isFetching}
      />
    );
  if (datos?.aviso)
    return <EstadoVacio icono={User} titulo="Inicia sesión" texto={datos.aviso} />;
  if (turnos.length === 0)
    return (
      <EstadoVacio
        icono={CalendarDays}
        titulo="Sin turnos este mes"
        texto={
          esAdmin
            ? "Tú no estás en la rota; cambia a «Equipo» para ver la jornada de todos."
            : "Aquí verás tu horario del mes en cuanto se publique."
        }
        accion={
          esAdmin && onVerSemana ? (
            <Button variant="outline" size="sm" onClick={onVerSemana}>
              Ver la semana del equipo
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Button>
          ) : undefined
        }
      />
    );

  return (
    <>
      <div className="print-mes">
        <EncabezadoImpresion
          mes={mes}
          subtitulo={`Mis turnos${datos?.miembro_nombre ? ` — ${datos.miembro_nombre}` : ""}`}
        />
        <RejillaMensual
          mes={mes}
          cobertura={cobertura}
          onAbrirDia={onAbrirDia}
          renderDia={(fecha, delMes) =>
            (porFecha.get(fecha) ?? []).map((t) => (
              <ChipTurnoMes key={t.id} turno={t} atenuado={!delMes} />
            ))
          }
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Tus turnos del mes con los eventos y huecos de cada día. Pulsa un día para ver su resumen.
      </p>
    </>
  );
}

/** Chip de un turno propio: franja + horario (o «Descanso» atenuado en los días libres). */
function ChipTurnoMes({ turno, atenuado }: { turno: TurnoRota; atenuado?: boolean }) {
  if (turno.franja === "descanso") {
    return (
      <div
        className={`truncate rounded px-1.5 py-0.5 text-[11px] text-muted-foreground ${
          atenuado ? "opacity-50" : ""
        }`}
      >
        Descanso
      </div>
    );
  }
  // El color del bloque indica el PERIODO del turno (mañana/tarde/noche), igual que la rejilla
  // semanal: misma `presentacionTurnoPorHora` derivada de la hora de inicio.
  const tono = presentacionTurnoPorHora(turno.inicio);
  return (
    <div
      className={cn(
        "rounded px-1.5 py-0.5 text-[11px] leading-tight print:border print:border-border",
        tono.fondo,
        tono.nombre,
        atenuado && "opacity-50",
      )}
    >
      <div className="truncate font-medium">{turno.franja_nombre}</div>
      {turno.inicio && (
        <div className={cn("tabular-nums", tono.horas)}>
          {turno.inicio}–{turno.fin}
        </div>
      )}
    </div>
  );
}

function agruparPorFecha(turnos: TurnoRota[]): Map<string, TurnoRota[]> {
  const m = new Map<string, TurnoRota[]>();
  for (const t of turnos) {
    const arr = m.get(t.fecha);
    if (arr) arr.push(t);
    else m.set(t.fecha, [t]);
  }
  return m;
}

// --- Vista EQUIPO: la jornada de todo el equipo -----------------------------

/** Una franja de un día con la gente que la cubre (agrupada para la celda del equipo). */
type FranjaConPersonas = {
  franjaId: string;
  nombre: string;
  inicio: string;
  fin: string;
  personas: { id: string; nombre: string }[];
};

function VistaMesEquipo({
  mes,
  cobertura,
  onAbrirDia,
}: {
  mes: string;
  cobertura?: Map<string, ResumenDiaCobertura>;
  onAbrirDia?: (fecha: string) => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const { usuario } = useSesion();
  const q = useQuery({
    queryKey: ["rota", "turnos-mes", mes, marcaActiva],
    queryFn: ({ signal }) =>
      api.turnosMes({ mes, marca: marcaActiva ?? undefined }, signal),
  });
  const turnos = React.useMemo(() => q.data?.turnos ?? [], [q.data?.turnos]);
  const porFecha = React.useMemo(() => agruparEquipoPorFecha(turnos), [turnos]);
  const miId = usuario?.id ?? "";

  if (q.isPending) return <Skeleton className="h-[28rem] w-full rounded-lg" />;
  if (q.isError)
    return (
      <BloqueError
        titulo="No se pudo cargar el calendario del equipo"
        mensaje={mensajeError(q.error)}
        onReintentar={() => void q.refetch()}
        cargando={q.isFetching}
      />
    );
  if (turnos.length === 0)
    return (
      <EstadoVacio
        icono={Users}
        titulo="Sin turnos del equipo este mes"
        texto="Cuando se publique la rota del mes, aquí verás la jornada de todo el equipo."
      />
    );

  return (
    <>
      <div className="print-mes">
        <EncabezadoImpresion mes={mes} subtitulo="Turnos del equipo" />
        <RejillaMensual
          mes={mes}
          cobertura={cobertura}
          onAbrirDia={onAbrirDia}
          renderDia={(fecha, delMes) =>
            (porFecha.get(fecha) ?? []).map((fr) => (
              <ChipFranjaEquipo
                key={fr.franjaId}
                franja={fr}
                atenuado={!delMes}
                miId={miId}
              />
            ))
          }
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Jornada de todo el equipo con los eventos y huecos de cada día. Pulsa un día para ver su
        resumen.
      </p>
    </>
  );
}

/** Chip de una franja del equipo: franja + horario y la gente que la cubre (tú, resaltado). */
function ChipFranjaEquipo({
  franja,
  atenuado,
  miId,
}: {
  franja: FranjaConPersonas;
  atenuado?: boolean;
  miId: string;
}) {
  // Color del bloque por PERIODO del turno (mañana/tarde/noche), igual que la rejilla semanal.
  const tono = presentacionTurnoPorHora(franja.inicio);
  return (
    <div
      className={cn(
        "rounded px-1.5 py-0.5 text-[11px] leading-tight print:border print:border-border",
        tono.fondo,
        tono.nombre,
        atenuado && "opacity-50",
      )}
    >
      <div className="font-medium">
        {franja.nombre}
        {franja.inicio && (
          <span className="font-normal tabular-nums">
            {" "}
            · {franja.inicio}–{franja.fin}
          </span>
        )}
      </div>
      <div className={tono.gente}>
        {franja.personas.map((p, i) => (
          <React.Fragment key={p.id}>
            {i > 0 && ", "}
            <span className={p.id === miId ? "font-semibold underline" : ""}>
              {p.nombre}
            </span>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

/**
 * Agrupa los turnos del equipo por día → franja → personas. Excluye descanso (la vista de
 * equipo es «quién trabaja»). Franjas ordenadas por hora de inicio; personas, alfabéticas.
 */
export function agruparEquipoPorFecha(
  turnos: TurnoRota[],
): Map<string, FranjaConPersonas[]> {
  const porDia = new Map<string, Map<string, FranjaConPersonas>>();
  for (const t of turnos) {
    if (t.franja === "descanso") continue;
    let dia = porDia.get(t.fecha);
    if (!dia) {
      dia = new Map();
      porDia.set(t.fecha, dia);
    }
    let fr = dia.get(t.franja_id);
    if (!fr) {
      fr = {
        franjaId: t.franja_id,
        nombre: t.franja_nombre,
        inicio: t.inicio,
        fin: t.fin,
        personas: [],
      };
      dia.set(t.franja_id, fr);
    }
    fr.personas.push({ id: t.miembro_id, nombre: t.miembro_nombre });
  }
  const salida = new Map<string, FranjaConPersonas[]>();
  for (const [fecha, dia] of porDia) {
    const franjas = [...dia.values()].sort(
      (a, b) => a.inicio.localeCompare(b.inicio) || a.nombre.localeCompare(b.nombre),
    );
    for (const fr of franjas)
      fr.personas.sort((a, b) => a.nombre.localeCompare(b.nombre));
    salida.set(fecha, franjas);
  }
  return salida;
}
