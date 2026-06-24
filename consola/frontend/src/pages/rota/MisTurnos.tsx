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
import type { AusenciaRota, TurnoRota } from "@/types";

import {
  ausenciaTocaDia,
  type ClavePeriodo,
  formatearFechaCorta,
  ORDEN_PERIODO,
  PRESENTACION_AUSENCIA,
  presentacionTurnoPorHora,
} from "./comun";
import { ResumenDia } from "./ResumenDia";
import { type ResumenDiaCobertura, useTableroMes } from "./useTableroMes";

type Ambito = "equipo" | "yo";

// --- Vista mensual (modo «Mes» del Calendario) ------------------------------

export function VistaMensualTurnos({
  esAdmin = false,
  onVerSemana,
  mostrarCobertura = true,
  mostrarHorasEquipo,
  horasPorPersona = false,
  llenarAltura = false,
  ocultarImprimir = false,
  controlesPre,
  marcadorSalud,
  soloEquipo = false,
  accionesDerecha,
  seleccionable = false,
  diasSel,
  onToggleDia,
  onMes,
}: {
  /** El admin no suele estar en la rota: por eso arranca en «Equipo» (sí ve algo). */
  esAdmin?: boolean;
  /** Salta a la rejilla SEMANAL del mismo Calendario (lo ofrece el vacío de «Yo» a quien gestiona). */
  onVerSemana?: () => void;
  /** Superpone el estado de cobertura por día («N ev · M sin cubrir») + el «Resumen del día». En
   *  «Horario» (calendario de turnos puro) va `false`: solo jornada. En Gestión queda `true`. */
  mostrarCobertura?: boolean;
  /** OVERRIDE del flag «mostrar horas en Equipo». Por defecto (`undefined`) se lee de la config por
   *  marca: la gente de una misma franja puede tener horas distintas, así que el equipo puede
   *  ocultar «· 08:00–16:00» para que «Mañana/Tarde/Noche» no sugiera un horario único. «Yo»
   *  SIEMPRE muestra las horas propias (no le afecta este flag). */
  mostrarHorasEquipo?: boolean;
  /** En «Equipo», muestra «la hora de cada uno»: las horas se agrupan por horario y, si dentro de
   *  una franja difieren, se parten por hora (en vez de un único rango por franja). Lo activan
   *  «Horario» y Gestión; cuando está activo manda sobre `mostrarHorasEquipo` (la hora se ve igual). */
  horasPorPersona?: boolean;
  /** «Horario»: el mes LLENA el alto de su contenedor (filas a partes iguales) para que se vea
   *  entero sin scroll de página. El host debe acotar el alto (p. ej. `h-[calc(100dvh-5.5rem)]`). */
  llenarAltura?: boolean;
  /** Oculta el botón-icono «Imprimir» de la barra para que el host lo ofrezca en su menú ⋯ (junto a
   *  las descargas). Gestión lo usa para no repetir la acción suelta; «Horario» lo deja visible. */
  ocultarImprimir?: boolean;
  /** Controles antepuestos a «Equipo|Yo» en la zona izquierda de la barra: el Calendario inyecta aquí
   *  su conmutador Semana|Mes en Gestión. En «Horario» va vacío (no hay vista Semana). */
  controlesPre?: React.ReactNode;
  /** Marcador de estado (✓ «Al día») a la derecha, junto a «Imprimir». Lo inyecta Gestión (SOSIEGO). */
  marcadorSalud?: React.ReactNode;
  /** Acciones a la derecha de la barra (el menú ⋯ que Gestión inyecta: «Ajustes de turnos» +
   *  «Imprimir / PDF»). En «Horario» va vacío (la acción de imprimir es el icono suelto). */
  accionesDerecha?: React.ReactNode;
  /** Fija el ámbito a «Equipo» y oculta el conmutador Equipo/Yo. Gestión lo activa (coordinar al
   *  equipo, y el admin no está en la rota → «Yo» sería un estado vacío); «Horario» no. */
  soloEquipo?: boolean;
  /** Gestión = Mes único: hace clicables las celdas de día del Equipo para marcar la selección de
   *  reparto (puede cruzar semanas). Solo Gestión lo pasa; «Horario» (solo lectura) no. */
  seleccionable?: boolean;
  /** Días ISO marcados (se tiñen). Controlado por el contenedor (Gestión). */
  diasSel?: Set<string>;
  /** Alterna un día en la selección al clicar su número en la rejilla. */
  onToggleDia?: (fechaIso: string) => void;
  /** Notifica el mes en vista ("YYYY-MM") al montar y al cambiarlo. Lo usa Gestión para «Copiar mes
   *  anterior» (saber qué mes sembrar). */
  onMes?: (mesIso: string) => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const { usuario } = useSesion();
  // Flag por marca de si «Equipo» muestra el rango horario. Override por prop (preview/tests); si
  // no, manda la config por marca (default oculto). Comparte clave con el editor de franjas, así
  // que guardar el ajuste invalida `["rota"]` y el calendario se repinta.
  const configFranjasQ = useQuery({
    queryKey: ["rota", "config", "franjas", marcaActiva] as const,
    queryFn: ({ signal }) =>
      api.obtenerConfigFranjas(marcaActiva ?? undefined, signal),
    enabled: !!marcaActiva,
  });
  const mostrarHoras =
    mostrarHorasEquipo ?? configFranjasQ.data?.mostrar_horas_equipo ?? false;
  // Ausencias (vacaciones/baja/…) superpuestas al calendario: en «Equipo» dicen QUIÉN está fuera y
  // por qué; en «Yo», el tiempo libre propio. Lista global (misma clave que Panorama y el panel de
  // coordinación); cada vista la filtra al mes y a su ámbito.
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"],
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
  });
  const ausencias = React.useMemo(
    () => ausenciasQ.data?.ausencias ?? [],
    [ausenciasQ.data],
  );
  const [ambitoSel, setAmbito] = React.useState<Ambito>(esAdmin ? "equipo" : "yo");
  const ambito: Ambito = soloEquipo ? "equipo" : ambitoSel;
  const [mes, setMes] = React.useState(() => mesDeFecha(new Date()));
  const [diaResumen, setDiaResumen] = React.useState<string | null>(null);
  // Notifica el mes en vista (montaje + cambios) para que Gestión sepa qué mes sembrar al copiar.
  React.useEffect(() => onMes?.(mes), [mes, onMes]);

  // Cobertura del mes (eventos + estado por día) superpuesta sobre la jornada. Hook propio a
  // escala de mes; NO toca `useTablero` (infra del cockpit). Con `mostrarCobertura=false` (Horario
  // = turnos puros) NO dispara ningún fetch de eventos/cobertura.
  const { porDia } = useTableroMes(mes, marcaActiva ?? undefined, mostrarCobertura);
  const cobertura = mostrarCobertura ? porDia : undefined;
  const onAbrirDia = mostrarCobertura ? setDiaResumen : undefined;

  return (
    <div
      className={cn(
        llenarAltura
          ? "space-y-4 lg:flex lg:h-full lg:min-h-0 lg:flex-col lg:gap-4 lg:space-y-0"
          : "space-y-4",
      )}
    >
      {/* UNA barra de tres zonas: izquierda (modo de vista) · centro (el mes, foco) · derecha
          (estado + acción). En md+ es un grid 1fr·auto·1fr para centrar ópticamente el mes; en móvil
          las tres zonas se apilan. */}
      <div className="grid shrink-0 grid-cols-1 items-center gap-3 md:grid-cols-[1fr_auto_1fr]">
        <div className="flex flex-wrap items-center gap-2 md:justify-self-start">
          {controlesPre}
          {!soloEquipo && <SelectorAmbito ambito={ambito} setAmbito={setAmbito} />}
        </div>
        <div className="md:justify-self-center">
          <NavegadorMes mes={mes} setMes={setMes} />
        </div>
        <div className="flex items-center gap-2 md:justify-self-end">
          {marcadorSalud}
          {/* «Imprimir»: solo el icono, botón-icono outline (el icon-button de la app). Gestión lo
              pliega en su menú ⋯ (`ocultarImprimir`); «Horario» lo deja como acción suelta. */}
          {!ocultarImprimir && (
            <Button
              variant="outline"
              size="icon"
              onClick={imprimirMes}
              title="Imprimir o guardar como PDF"
              aria-label="Imprimir / PDF"
            >
              <Printer className="h-4 w-4" />
            </Button>
          )}
          {accionesDerecha}
        </div>
      </div>

      <div className={cn(llenarAltura && "lg:min-h-0 lg:flex-1")}>
        {ambito === "equipo" ? (
          <VistaMesEquipo
            mes={mes}
            cobertura={cobertura}
            onAbrirDia={onAbrirDia}
            mostrarHoras={mostrarHoras}
            horasPorPersona={horasPorPersona}
            ausencias={ausencias}
            llenarAltura={llenarAltura}
            seleccionable={seleccionable}
            diasSel={diasSel}
            onToggleDia={onToggleDia}
          />
        ) : (
          <VistaMesYo
            mes={mes}
            esAdmin={esAdmin}
            onVerSemana={onVerSemana}
            cobertura={cobertura}
            onAbrirDia={onAbrirDia}
            ausencias={ausencias.filter((a) => a.miembro_id === (usuario?.id ?? ""))}
            llenarAltura={llenarAltura}
          />
        )}
      </div>

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
export function imprimirMes() {
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
  seleccionable = false,
  diasSel,
  onToggleDia,
  llenarAltura = false,
}: {
  mes: string;
  renderDia: (fecha: string, delMes: boolean) => React.ReactNode;
  cobertura?: Map<string, ResumenDiaCobertura>;
  onAbrirDia?: (fecha: string) => void;
  /** Gestión: el número del día es un toggle de la selección de reparto; la celda se tiñe. */
  seleccionable?: boolean;
  diasSel?: Set<string>;
  onToggleDia?: (fechaIso: string) => void;
  /** «Horario»: la rejilla LLENA el alto disponible (filas a partes iguales, sin scroll de página);
   *  cada celda recorta su exceso. Por defecto crece con el contenido (la página scrollea). */
  llenarAltura?: boolean;
}) {
  const hoy = hoyCDMX();
  const dias = React.useMemo(() => semanasDelMes(mes).flat(), [mes]);
  return (
    // En lg+ con `llenarAltura` la rejilla es una columna flex que llena su contenedor; en móvil se
    // queda en su flujo natural (un mes no cabe en un teléfono → scroll, como debe).
    <div
      className={cn(
        "overflow-hidden rounded-lg border-l border-t",
        llenarAltura && "lg:flex lg:h-full lg:min-h-0 lg:flex-col",
      )}
    >
      <div className="grid shrink-0 grid-cols-7 bg-muted/40 text-center text-[11px] font-medium uppercase tracking-wide text-muted-foreground print:bg-transparent">
        {DIAS_CABECERA.map((d) => (
          <div key={d} className="border-b border-r py-2">
            {d}
          </div>
        ))}
      </div>
      {/* `minmax(min-content,1fr)`: cada semana mide AL MENOS lo que pide su contenido (no se recorta
          nada) y reparte el alto sobrante a partes iguales para llenar la pantalla. Si un mes muy
          denso no cupiera, la rejilla scrollea (no la página); el caso normal cabe sin scroll. */}
      <div
        className={cn(
          "grid grid-cols-7",
          llenarAltura &&
            "lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:[grid-auto-rows:minmax(min-content,1fr)]",
        )}
      >
        {dias.map((fecha) => {
          const delMes = mismoMes(fecha, mes);
          const finde = esFinDeSemana(fecha);
          const esHoy = fecha === hoy;
          const resumen = delMes ? cobertura?.get(fecha) : undefined;
          const sel = seleccionable && delMes && !!diasSel?.has(fecha);
          const num = Number(fecha.slice(8, 10));
          return (
            <div
              key={fecha}
              className={`min-h-[5.25rem] border-b border-r p-1.5 print:min-h-[3.25rem] ${
                sel
                  ? "bg-keni-50 dark:bg-keni-900/30"
                  : !delMes
                    ? "bg-muted/20"
                    : finde
                      ? "bg-muted/30"
                      : "bg-background"
              } ${esHoy ? "ring-1 ring-inset ring-keni-500/50" : ""}`}
            >
              {seleccionable && delMes ? (
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={sel}
                  aria-label={`Día ${num}`}
                  onClick={() => onToggleDia?.(fecha)}
                  className={`mb-1 block w-full rounded text-right text-xs tabular-nums transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                    sel || esHoy
                      ? "font-semibold text-keni-700 dark:text-keni-300"
                      : "text-muted-foreground"
                  }`}
                >
                  {num}
                </button>
              ) : (
                <div
                  className={`mb-1 text-right text-xs tabular-nums ${
                    esHoy
                      ? "font-semibold text-keni-700 dark:text-keni-300"
                      : delMes
                        ? "text-muted-foreground"
                        : "text-muted-foreground/50"
                  }`}
                >
                  {num}
                </div>
              )}
              {resumen && (
                <IndicadorCobertura fecha={fecha} resumen={resumen} onAbrir={onAbrirDia} />
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
        aria-label={`${formatearFechaCorta(fecha) || fecha}: ${nEventos} ${
          nEventos === 1 ? "evento" : "eventos"
        }${nSinCubrir > 0 ? `, ${nSinCubrir} sin cubrir` : ""}. Ver el resumen del día`}
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
  // Mayúscula SOLO en la inicial (`first-letter`, no `capitalize`, que title-caseaba «Junio De
  // 2026»; la forma es-MX de `nombreMes` es «junio de 2026»).
  return (
    <div className="mb-3 hidden print:block">
      <h2 className="text-lg font-semibold first-letter:uppercase">{nombreMes(mes)}</h2>
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
  ausencias = [],
  llenarAltura = false,
}: {
  mes: string;
  esAdmin?: boolean;
  onVerSemana?: () => void;
  cobertura?: Map<string, ResumenDiaCobertura>;
  onAbrirDia?: (fecha: string) => void;
  /** Tiempo libre PROPIO del usuario, pintado como banda (vacaciones/baja/…) en sus días. */
  ausencias?: AusenciaRota[];
  /** «Horario»: el mes LLENA el alto disponible (sin scroll de página). */
  llenarAltura?: boolean;
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
  // El vacío solo si NO hay ni turnos ni tiempo libre: una semana entera de vacaciones también es
  // información que el calendario debe mostrar.
  if (turnos.length === 0 && ausencias.length === 0)
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
    <div className={cn(llenarAltura && "lg:flex lg:h-full lg:min-h-0 lg:flex-col")}>
      <div className={cn("print-mes", llenarAltura && "lg:min-h-0 lg:flex-1")}>
        <EncabezadoImpresion
          mes={mes}
          subtitulo={`Mis turnos${datos?.miembro_nombre ? ` — ${datos.miembro_nombre}` : ""}`}
        />
        <RejillaMensual
          mes={mes}
          cobertura={cobertura}
          onAbrirDia={onAbrirDia}
          llenarAltura={llenarAltura}
          renderDia={(fecha, delMes) => (
            <>
              {(porFecha.get(fecha) ?? []).map((t) => (
                <ChipTurnoMes key={t.id} turno={t} atenuado={!delMes} />
              ))}
              {ausencias
                .filter((a) => ausenciaTocaDia(a, fecha))
                .map((a) => (
                  <ChipAusenciaMes key={a.id} ausencia={a} atenuado={!delMes} />
                ))}
            </>
          )}
        />
      </div>
      <p className={cn("pt-2 text-xs text-muted-foreground", llenarAltura && "lg:shrink-0")}>
        Tus turnos del mes con los eventos y huecos de cada día. Pulsa un día para ver su resumen.
      </p>
    </div>
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
  // Banda (título + color) derivada de la HORA, no de la franja almacenada: «Mañana»/«Tarde»/«Noche»
  // y su tinte salen ambos de `presentacionTurnoPorHora`, así nunca divergen (p. ej. una franja
  // importada como «Tarde» con horas de noche). Igual criterio que la rejilla semanal.
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
      <div className="truncate font-medium">{tono.etiqueta}</div>
      {turno.inicio && (
        <div className={cn("tabular-nums", tono.horas)}>
          {turno.inicio}–{turno.fin}
        </div>
      )}
    </div>
  );
}

/** Banda de TIEMPO LIBRE en un día: icono + texto (el tipo en «Yo», el nombre de la persona en
 *  «Equipo»), en el tono suave del tipo de ausencia. No es un turno: comunica que NO se trabaja. */
function ChipAusenciaMes({
  ausencia,
  atenuado,
  mostrarNombre = false,
  resaltado = false,
}: {
  ausencia: AusenciaRota;
  atenuado?: boolean;
  /** «Equipo» muestra de QUIÉN es la ausencia; «Yo» muestra el tipo (es del propio usuario). */
  mostrarNombre?: boolean;
  /** Resalta cuando la ausencia es del usuario actual (en «Equipo»). */
  resaltado?: boolean;
}) {
  const pres = PRESENTACION_AUSENCIA[ausencia.tipo] ?? PRESENTACION_AUSENCIA.otro;
  const Icono = pres.icono;
  const texto = mostrarNombre ? ausencia.miembro_nombre || "—" : pres.etiqueta;
  return (
    <div
      className={cn(
        "flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] leading-tight",
        pres.chip,
        atenuado && "opacity-50",
      )}
      title={mostrarNombre ? `${ausencia.miembro_nombre} · ${pres.etiqueta}` : pres.etiqueta}
    >
      <Icono className="h-3 w-3 shrink-0" aria-hidden />
      <span className={cn("truncate", resaltado && "font-semibold underline")}>{texto}</span>
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

/** Una persona de una franja, con su horario EFECTIVO (sus horas a medida o las de la franja). */
type PersonaFranja = { id: string; nombre: string; inicio: string; fin: string };

/** Una banda de un día (mañana/tarde/noche) con la gente que la cubre (para la celda del equipo).
 *  La identidad es el PERIODO (`clave`), derivado de la hora — no la franja almacenada. */
type FranjaConPersonas = {
  clave: ClavePeriodo;
  nombre: string;
  inicio: string;
  fin: string;
  personas: PersonaFranja[];
};

function VistaMesEquipo({
  mes,
  cobertura,
  onAbrirDia,
  mostrarHoras = true,
  horasPorPersona = false,
  ausencias = [],
  llenarAltura = false,
  seleccionable = false,
  diasSel,
  onToggleDia,
}: {
  mes: string;
  cobertura?: Map<string, ResumenDiaCobertura>;
  onAbrirDia?: (fecha: string) => void;
  /** Pinta el rango horario junto a cada franja. El equipo puede ocultarlo (horas heterogéneas). */
  mostrarHoras?: boolean;
  /** Gestión: muestra «la hora de cada uno» (ver `ChipFranjaEquipo`). */
  horasPorPersona?: boolean;
  /** Tiempo libre del equipo: una banda por persona ausente ese día (quién está fuera y por qué). */
  ausencias?: AusenciaRota[];
  /** «Horario»: el mes LLENA el alto disponible (sin scroll de página). */
  llenarAltura?: boolean;
  /** Gestión: celdas de día clicables para marcar la selección de reparto. */
  seleccionable?: boolean;
  diasSel?: Set<string>;
  onToggleDia?: (fechaIso: string) => void;
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
  // En modo selección (Gestión = Mes único) la rejilla se pinta SIEMPRE, aunque el mes esté vacío:
  // hace falta poder marcar días para repartir sobre un mes en blanco. Solo lectura → estado vacío,
  // salvo que haya tiempo libre que mostrar (una semana de vacaciones también es información).
  if (turnos.length === 0 && ausencias.length === 0 && !seleccionable)
    return (
      <EstadoVacio
        icono={Users}
        titulo="Sin turnos del equipo este mes"
        texto="Cuando se publique la rota del mes, aquí verás la jornada de todo el equipo."
      />
    );

  return (
    <div className={cn(llenarAltura && "lg:flex lg:h-full lg:min-h-0 lg:flex-col")}>
      <div className={cn("print-mes", llenarAltura && "lg:min-h-0 lg:flex-1")}>
        <EncabezadoImpresion mes={mes} subtitulo="Turnos del equipo" />
        <RejillaMensual
          mes={mes}
          cobertura={cobertura}
          onAbrirDia={onAbrirDia}
          llenarAltura={llenarAltura}
          seleccionable={seleccionable}
          diasSel={diasSel}
          onToggleDia={onToggleDia}
          renderDia={(fecha, delMes) => (
            <>
              {(porFecha.get(fecha) ?? []).map((fr) => (
                <ChipFranjaEquipo
                  key={fr.clave}
                  franja={fr}
                  atenuado={!delMes}
                  miId={miId}
                  mostrarHoras={mostrarHoras}
                  horasPorPersona={horasPorPersona}
                />
              ))}
              {ausencias
                .filter((a) => ausenciaTocaDia(a, fecha))
                .sort((a, b) => a.miembro_nombre.localeCompare(b.miembro_nombre))
                .map((a) => (
                  <ChipAusenciaMes
                    key={a.id}
                    ausencia={a}
                    atenuado={!delMes}
                    mostrarNombre
                    resaltado={a.miembro_id === miId}
                  />
                ))}
            </>
          )}
        />
      </div>
      <p className={cn("pt-2 text-xs text-muted-foreground", llenarAltura && "lg:shrink-0")}>
        Jornada de todo el equipo con los eventos y huecos de cada día. Pulsa un día para ver su
        resumen.
      </p>
    </div>
  );
}

/** La gente de un grupo, separada por comas, con el usuario resaltado. */
function ListaGente({
  personas,
  miId,
}: {
  personas: { id: string; nombre: string }[];
  miId: string;
}) {
  return (
    <>
      {personas.map((p, i) => (
        <React.Fragment key={p.id}>
          {i > 0 && ", "}
          <span className={p.id === miId ? "font-semibold underline" : ""}>{p.nombre}</span>
        </React.Fragment>
      ))}
    </>
  );
}

/** Chip de una franja del equipo: franja + horario y la gente que la cubre (tú, resaltado). */
function ChipFranjaEquipo({
  franja,
  atenuado,
  miId,
  mostrarHoras = true,
  horasPorPersona = false,
}: {
  franja: FranjaConPersonas;
  atenuado?: boolean;
  miId: string;
  mostrarHoras?: boolean;
  /** Gestión: muestra «la hora de cada uno». Homogénea → hora junto a la franja; heterogénea →
   *  una línea por horario. Resuelve lo que `mostrarHoras` evitaba (un horario único engañoso). */
  horasPorPersona?: boolean;
}) {
  // Color del bloque por PERIODO del turno (mañana/tarde/noche), igual que la rejilla semanal.
  const tono = presentacionTurnoPorHora(franja.inicio);
  const grupos = horasPorPersona ? agruparPersonasPorHorario(franja.personas) : null;
  // Homogénea = todos comparten horario → la hora va una sola vez junto al nombre de la franja.
  const heterogenea = !!grupos && grupos.length > 1;
  // El rango va junto a la franja cuando es un horario único y o bien el equipo lo pide
  // (`mostrarHoras`) o estamos en «la hora de cada uno» (Gestión).
  const horaFranja = !heterogenea && franja.inicio && (mostrarHoras || horasPorPersona);
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
        {horaFranja && (
          <span className="font-normal tabular-nums">
            {" "}
            · {franja.inicio}–{franja.fin}
          </span>
        )}
      </div>
      {heterogenea ? (
        grupos!.map((g) => (
          <div key={`${g.inicio}-${g.fin}`} className={tono.gente}>
            {g.inicio && (
              <span className={cn("tabular-nums", tono.horas)}>
                {g.inicio}–{g.fin} ·{" "}
              </span>
            )}
            <ListaGente personas={g.personas} miId={miId} />
          </div>
        ))
      ) : (
        <div className={tono.gente}>
          <ListaGente personas={franja.personas} miId={miId} />
        </div>
      )}
    </div>
  );
}

/**
 * Agrupa los turnos del equipo por día → PERIODO (mañana/tarde/noche) → personas. El periodo se
 * deriva de la HORA de inicio (`presentacionTurnoPorHora`), NO de la franja almacenada: así un mismo
 * horario (p. ej. 17:00) cae siempre en la misma banda, dos personas de la misma hora comparten
 * cabecera y color, y nunca se mezclan tarde y noche bajo un título que no concuerda con su tinte.
 * Excluye descanso (la vista de equipo es «quién trabaja»). Bandas en orden mañana→tarde→noche;
 * personas, alfabéticas.
 */
export function agruparEquipoPorFecha(
  turnos: TurnoRota[],
): Map<string, FranjaConPersonas[]> {
  const porDia = new Map<string, Map<ClavePeriodo, FranjaConPersonas>>();
  for (const t of turnos) {
    if (t.franja === "descanso") continue;
    const pres = presentacionTurnoPorHora(t.inicio);
    let dia = porDia.get(t.fecha);
    if (!dia) {
      dia = new Map();
      porDia.set(t.fecha, dia);
    }
    let fr = dia.get(pres.clave);
    if (!fr) {
      fr = {
        clave: pres.clave,
        nombre: pres.etiqueta,
        inicio: t.inicio,
        fin: t.fin,
        personas: [],
      };
      dia.set(pres.clave, fr);
    } else if (t.inicio.localeCompare(fr.inicio) < 0) {
      // Hora representativa de la banda = la más temprana del periodo (estable, no «la primera que
      // entró»). El color ya es coherente porque todas las horas del grupo comparten periodo.
      fr.inicio = t.inicio;
      fr.fin = t.fin;
    }
    fr.personas.push({
      id: t.miembro_id,
      nombre: t.miembro_nombre,
      inicio: t.inicio,
      fin: t.fin,
    });
  }
  const salida = new Map<string, FranjaConPersonas[]>();
  for (const [fecha, dia] of porDia) {
    const franjas = [...dia.values()].sort(
      (a, b) => ORDEN_PERIODO[a.clave] - ORDEN_PERIODO[b.clave],
    );
    for (const fr of franjas)
      fr.personas.sort((a, b) => a.nombre.localeCompare(b.nombre));
    salida.set(fecha, franjas);
  }
  return salida;
}

/** Grupo de gente de una franja que comparte el mismo horario efectivo ("HH:MM"). */
export type GrupoHorario = { inicio: string; fin: string; personas: { id: string; nombre: string }[] };

/**
 * Agrupa la gente de una franja por su horario efectivo (Gestión muestra «la hora de cada uno»).
 * Un solo grupo = franja homogénea (todos a la misma hora); varios = horas heterogéneas. Conserva
 * el orden (alfabético) de entrada dentro de cada grupo y ordena los grupos por hora de inicio.
 */
export function agruparPersonasPorHorario(personas: PersonaFranja[]): GrupoHorario[] {
  const grupos: GrupoHorario[] = [];
  for (const p of personas) {
    let g = grupos.find((x) => x.inicio === p.inicio && x.fin === p.fin);
    if (!g) {
      g = { inicio: p.inicio, fin: p.fin, personas: [] };
      grupos.push(g);
    }
    g.personas.push({ id: p.id, nombre: p.nombre });
  }
  grupos.sort((a, b) => a.inicio.localeCompare(b.inicio));
  return grupos;
}
