import * as React from "react";
import { createPortal } from "react-dom";

import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useUsoCuenta, type UsoCuenta } from "@/hooks/use-uso-cuenta";
import { Tooltip } from "@/components/ui/tooltip";
import { limiteMasUrgente } from "@/lib/uso-burn";
import { cn } from "@/lib/utils";

/**
 * Indicador SUTIL del uso de las cuentas de Claude del servidor, alojado en el pie del sidebar.
 * Expandido pinta, por cuenta, UNA sola línea («Uso» + %) con una barra de progreso fina debajo; la
 * cabecera «Cuenta A/B» solo aparece en la vista "Todas" (varias cuentas), porque con una sola es su
 * cuenta siempre. Colapsado, un anillo fino con el % del límite que ANTES bloqueará (burn rate). Esa
 * línea es un BOTÓN: un click despliega un panel flotante con el desglose completo (Semana/24h/5h,
 * cada uno con su barra), igual que antes se veían siempre — así el pie ocupa una línea en reposo
 * pero el detalle sigue a un solo click, no solo al tooltip.
 *
 * EL NÚMERO QUE SE VE: la ventana SEMANAL que primero se agota (el mayor de all-models vs cuota
 * Sonnet) — es el límite de mayor alcance y el que de verdad frena el trabajo de la semana. «24h» y
 * «5h» siguen calculándose (van en el desglose del panel) pero no compiten por espacio visual con el
 * número principal. El anillo colapsado usa en cambio el burn rate (`limiteMasUrgente`, el que antes
 * tocará el 100 % por ventanas duras 5h/semana/Sonnet), porque ahí sí importa la predicción, no solo
 * el nivel actual.
 *
 * QUÉ CUENTAS muestra: el backend devuelve solo las que el usuario PUEDE ver (suelo por marcas);
 * de esas, el selector de marca activo (`useMarcaActiva`) decide cuál(es) PINTAR — en "Todas"
 * (`marcaActiva===null`) todas las permitidas; con una marca concreta, solo la cuenta que sirve esa
 * marca. Si no queda ninguna (editor sin marcas o la marca activa no es de una cuenta permitida),
 * no renderiza nada.
 *
 * Estados: neutro cuando aún no hay dato (`undefined`/cargando, nunca rojo) y ROJO por cuenta
 * cuando `alerta_roja` (sin cuenta o alguna ventana al 100 %). El 100 % se ve en la barra al tope en
 * rojo; el único texto de alerta es "Sin cuenta" (no hay barra que lo muestre).
 */

/** Redondea un porcentaje (0–100) a entero; `null` => `null`. */
function pctEntero(pct: number | null): number | null {
  return pct == null ? null : Math.max(0, Math.min(100, Math.round(pct)));
}

/** Ventana SEMANAL que primero se agota: el mayor de all-models vs cuota Sonnet (y si ata Sonnet).
 *  Es la barra «Semana» que pinta el indicador: el límite que de verdad frena la semana. */
function semanaBinding(uso: UsoCuenta): { pct: number | null; sonnet: boolean } {
  const { semana_pct: s, sonnet_pct: son } = uso;
  if (son != null && (s == null || son > s)) return { pct: son, sonnet: true };
  return { pct: s, sonnet: false };
}

/** Barra «24h»: % del cupo del DÍA ya consumido (consumo/umbral del límite que primero se agota).
 *  `null` mientras no haya dato del día (gate inerte). */
function dia24hPct(uso: UsoCuenta): number | null {
  const { consumo_pct, umbral_pct } = uso.dia;
  if (consumo_pct == null || umbral_pct <= 0) return null;
  return (consumo_pct / umbral_pct) * 100;
}

/** Rótulo de la cabecera del bloque: "Cuenta A" / "Cuenta B". */
function etiquetaCuenta(uso: UsoCuenta): string {
  return `Cuenta ${uso.cuenta.toUpperCase()}`;
}

/** % que pinta el anillo colapsado: el límite que ANTES bloqueará (burn rate); si aún no hay resets
 *  para predecir, cae al binding semanal de hoy (el mayor de all-models vs Sonnet). */
function pctColapsado(uso: UsoCuenta): number | null {
  return limiteMasUrgente(uso)?.pct ?? semanaBinding(uso).pct;
}

/** Mensaje breve del estado rojo, o `null` si no hay alerta. Solo "Sin cuenta": el 100 % ya se ve
 *  en la barra roja al tope, sin repetirlo en texto. */
function mensajeRojo(uso: UsoCuenta): string | null {
  if (!uso.alerta_roja) return null;
  if (!uso.conectada) return "Sin cuenta";
  return null;
}

/** Texto del reset semanal para el tooltip ("Se renueva: …"), o `null` si no se conoce. */
function etiquetaReset(uso: UsoCuenta): string | null {
  const txt = uso.reset_semana_txt ?? uso.reset_semana_iso;
  return txt ? `Se renueva: ${txt}` : null;
}

/** Tooltip COMPLETO de una cuenta: etiqueta + reset + los tres porcentajes + alerta, en una línea.
 *  «Semana» y «24h» rotulan "(Sonnet)" cuando es Sonnet el límite que primero se agota. */
function tooltipCompleto(uso: UsoCuenta): string {
  const partes: string[] = [];
  if (uso.etiqueta) partes.push(uso.etiqueta);
  const rojo = mensajeRojo(uso);
  if (rojo) partes.push(rojo);
  const sb = semanaBinding(uso);
  const s = pctEntero(sb.pct);
  const dia = pctEntero(dia24hPct(uso));
  const v = pctEntero(uso.sesion_5h_pct);
  const notaSem = sb.sonnet ? " (Sonnet)" : "";
  const notaDia = uso.dia.limite === "sonnet" ? " (Sonnet)" : "";
  partes.push(
    `Semana ${s == null ? "—" : `${s}%`}${notaSem}` +
      ` · 24h ${dia == null ? "—" : `${dia}%`}${notaDia}` +
      ` · 5h ${v == null ? "—" : `${v}%`}`,
  );
  const urgente = limiteMasUrgente(uso);
  if (urgente) {
    const cuando =
      urgente.horas === 0 ? "ya" : urgente.horas < 1 ? "<1 h" : `~${Math.round(urgente.horas)} h`;
    partes.push(`Antes al 100%: ${urgente.etiqueta} (${cuando})`);
  }
  const reset = etiquetaReset(uso);
  if (reset) partes.push(reset);
  return partes.join(" · ");
}

/** Medidor compacto (una CELDA del desglose): etiqueta encima del %, y debajo una barra de
 *  progreso fina. Apilado (no en fila): con 3 celdas a 1/3 del ancho cada una, «Semana» + «100%»
 *  en la MISMA línea no cabían (el "100%" invadía la celda vecina) — apilados, cada línea solo
 *  compite por ancho consigo misma. Pensado para ir en fila con sus hermanos (`flex-1`). */
function MiniMedidor({
  etiqueta,
  pct,
  rojo,
}: {
  etiqueta: string;
  pct: number | null;
  rojo: boolean;
}) {
  const valor = pctEntero(pct);
  const tiene = valor != null;
  return (
    <div className="min-w-0 flex-1 space-y-1">
      <span className="block truncate text-[10px] uppercase leading-none tracking-wide text-muted-foreground/70">
        {etiqueta}
      </span>
      <span
        className={cn(
          "block text-xs font-medium leading-none tabular-nums",
          rojo ? "text-destructive" : "text-foreground",
        )}
      >
        {tiene ? `${valor}%` : "—"}
      </span>
      <div
        className="h-0.5 w-full overflow-hidden rounded-full bg-border"
        role="progressbar"
        aria-label={`Uso ${etiqueta}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={valor ?? 0}
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500",
            rojo ? "bg-destructive" : "bg-foreground",
          )}
          style={{ width: `${tiene ? valor : 0}%` }}
        />
      </div>
    </div>
  );
}

/** Panel flotante con el desglose completo (Semana/24h/5h) de una cuenta: se porta a `<body>` y se
 *  ancla ENCIMA de la línea «Uso» (vive en el pie, no hay sitio debajo), igual que
 *  `PopoverCubridores` en tareas/tarjetas.tsx. Incluye el reset semanal, que antes solo vivía en el
 *  tooltip. */
function PopoverDesgloseUso({
  uso,
  anclaRef,
  contenedorRef,
}: {
  uso: UsoCuenta;
  anclaRef: React.RefObject<HTMLButtonElement>;
  contenedorRef: React.RefObject<HTMLDivElement>;
}) {
  const [pos, setPos] = React.useState<{ x: number; y: number } | null>(null);
  const rojo = uso.alerta_roja;
  const reset = etiquetaReset(uso);

  React.useLayoutEffect(() => {
    const ancla = anclaRef.current;
    const panel = contenedorRef.current;
    if (!ancla || !panel) return;
    const a = ancla.getBoundingClientRect();
    const p = panel.getBoundingClientRect();
    const m = 8;
    let x = a.left;
    if (x + p.width > window.innerWidth - m) x = Math.max(m, window.innerWidth - p.width - m);
    let y = a.top - p.height - 6;
    if (y < m) y = a.bottom + 6;
    setPos({ x, y });
  }, [anclaRef, contenedorRef]);

  return createPortal(
    <div
      ref={contenedorRef}
      role="dialog"
      aria-label="Desglose de uso"
      style={pos ? { left: pos.x, top: pos.y } : { left: 0, top: 0, visibility: "hidden" }}
      className="pointer-events-auto fixed z-50 w-52 rounded-lg border border-border bg-popover p-2.5 text-popover-foreground shadow-md"
    >
      <div className="flex items-end gap-2.5">
        <MiniMedidor etiqueta="Semana" pct={semanaBinding(uso).pct} rojo={rojo} />
        <MiniMedidor etiqueta="24h" pct={dia24hPct(uso)} rojo={rojo} />
        <MiniMedidor etiqueta="5h" pct={uso.sesion_5h_pct} rojo={rojo} />
      </div>
      {reset ? <p className="mt-2 text-[10px] text-muted-foreground">{reset}</p> : null}
    </div>,
    document.body,
  );
}

/** Círculo del rail colapsado: un anillo fino con el % del límite que ANTES bloqueará (burn rate);
 *  el desglose va al tooltip. */
function CirculoUso({ pct, rojo }: { pct: number | null; rojo: boolean }) {
  const r = 15.5;
  const c = 2 * Math.PI * r;
  const sem = pctEntero(pct);
  const colorTrazo = rojo ? "hsl(var(--destructive))" : "hsl(var(--foreground))";
  return (
    <svg viewBox="0 0 36 36" className="h-[22px] w-[22px]" aria-hidden="true">
      {/* Pista (lo no usado): mismo gris fino del hilo de PanelActualizando. */}
      <circle cx="18" cy="18" r={r} fill="none" stroke="hsl(var(--border))" strokeWidth="2" />
      {/* Progreso: % semanal. Arranca arriba (-90°). */}
      {sem != null && (
        <circle
          cx="18"
          cy="18"
          r={r}
          fill="none"
          stroke={colorTrazo}
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - sem / 100)}
          transform="rotate(-90 18 18)"
        />
      )}
      <text
        x="18"
        y="18"
        textAnchor="middle"
        dominantBaseline="central"
        className={cn("tabular-nums", rojo ? "fill-destructive" : "fill-muted-foreground")}
        style={{ fontSize: "13px" }}
      >
        {sem == null ? "—" : sem}
      </text>
    </svg>
  );
}

/** Bloque expandido de UNA cuenta: UNA línea («Uso» + %) + su barra, más el aviso rojo. El número es
 *  el binding semanal (el límite de mayor alcance); un click en la línea despliega el desglose
 *  completo (Semana/24h/5h) en un panel flotante. La cabecera "Cuenta A/B" solo cuando hay VARIAS
 *  cuentas (vista "Todas"): con una sola es su cuenta siempre. */
function BloqueCuenta({
  uso,
  etiquetada,
  abierto,
  onToggle,
}: {
  uso: UsoCuenta;
  etiquetada: boolean;
  abierto: boolean;
  onToggle: () => void;
}) {
  const rojo = uso.alerta_roja;
  const alerta = mensajeRojo(uso);
  const pct = pctEntero(semanaBinding(uso).pct);
  const tiene = pct != null;
  const tooltip = tooltipCompleto(uso);
  const anclaRef = React.useRef<HTMLButtonElement>(null);
  const panelRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!abierto) return;
    function fuera(e: MouseEvent) {
      const t = e.target as Node;
      if (anclaRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      onToggle();
    }
    function tecla(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onToggle();
        anclaRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", tecla);
    };
  }, [abierto, onToggle]);

  return (
    <div className="w-full space-y-1">
      {etiquetada ? (
        <p className="truncate px-0.5 text-[10px] font-medium text-muted-foreground/80">
          {etiquetaCuenta(uso)}
        </p>
      ) : null}
      {alerta ? <p className="px-0.5 text-[10px] font-medium text-destructive">{alerta}</p> : null}
      <button
        ref={anclaRef}
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onToggle();
        }}
        aria-expanded={abierto}
        aria-haspopup="dialog"
        title={tooltip}
        aria-label={tooltip}
        className="-mx-0.5 w-[calc(100%+4px)] space-y-1 rounded-sm px-0.5 transition-colors hover:bg-accent focus:outline-none focus-visible:bg-accent"
      >
        <div className="flex items-baseline justify-between gap-1">
          <span className="text-[11px] text-muted-foreground">Uso</span>
          <span
            className={cn(
              "text-xs font-medium tabular-nums",
              rojo ? "text-destructive" : "text-foreground",
            )}
          >
            {tiene ? `${pct}%` : "—"}
          </span>
        </div>
        <div
          className="h-0.5 w-full overflow-hidden rounded-full bg-border"
          role="progressbar"
          aria-label="Uso"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct ?? 0}
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500",
              rojo ? "bg-destructive" : "bg-foreground",
            )}
            style={{ width: `${tiene ? pct : 0}%` }}
          />
        </div>
      </button>
      {abierto ? <PopoverDesgloseUso uso={uso} anclaRef={anclaRef} contenedorRef={panelRef} /> : null}
    </div>
  );
}

/** Círculo colapsado de UNA cuenta, con su tooltip/etiqueta (incluye marcas + alerta). */
function CirculoCuenta({ uso }: { uso: UsoCuenta }) {
  const etiqueta = tooltipCompleto(uso);
  return (
    <Tooltip label={etiqueta} side="right">
      <div aria-label={etiqueta} className="flex items-center justify-center">
        <CirculoUso pct={pctColapsado(uso)} rojo={uso.alerta_roja} />
      </div>
    </Tooltip>
  );
}

/** Cuentas a MOSTRAR según el selector de marca activo (el back ya acotó las permitidas):
 *  "Todas" (`null`) -> todas; una marca concreta -> solo la cuenta que sirve esa marca. */
function cuentasAMostrar(cuentas: UsoCuenta[], marcaActiva: string | null): UsoCuenta[] {
  if (marcaActiva === null) return cuentas;
  return cuentas.filter((c) => c.marcas.includes(marcaActiva));
}

function IndicadorUsoContenido({
  colapsado,
  onAbiertoChange,
}: {
  colapsado: boolean;
  onAbiertoChange?: (abierto: boolean) => void;
}) {
  const { data } = useUsoCuenta(true);
  const { marcaActiva } = useMarcaActiva();
  const cuentasRecibidas = data?.cuentas;

  // Un solo panel abierto a la vez (entre las hasta 2 cuentas). Colapsar la barra cierra cualquiera
  // que quedara abierto: si no, el panel quedaría flotando sin su ancla visible.
  const [cuentaAbiertaId, setCuentaAbiertaId] = React.useState<string | null>(null);
  React.useEffect(() => {
    onAbiertoChange?.(cuentaAbiertaId !== null);
  }, [cuentaAbiertaId, onAbiertoChange]);
  React.useEffect(() => {
    if (colapsado) setCuentaAbiertaId(null);
  }, [colapsado]);

  // Sin dato todavía (cargando / sin respuesta): estado NEUTRO, nunca rojo (placeholder de una cuenta).
  if (!cuentasRecibidas) {
    if (colapsado) {
      return (
        <Tooltip label="Uso de la cuenta" side="right">
          <div aria-label="Uso de la cuenta" className="flex items-center justify-center">
            <CirculoUso pct={null} rojo={false} />
          </div>
        </Tooltip>
      );
    }
    return (
      <div className="w-full space-y-1 px-0.5">
        <div className="flex items-baseline justify-between gap-1">
          <span className="text-[11px] text-muted-foreground">Uso</span>
          <span className="text-xs font-medium tabular-nums text-muted-foreground">—</span>
        </div>
        <div
          className="h-0.5 w-full overflow-hidden rounded-full bg-border"
          role="progressbar"
          aria-label="Uso"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={0}
        >
          <div className="h-full rounded-full bg-foreground" style={{ width: "0%" }} />
        </div>
      </div>
    );
  }

  const cuentas = cuentasAMostrar(cuentasRecibidas, marcaActiva);
  // Sin cuentas que mostrar (editor sin marcas, o la marca activa no es de una cuenta permitida).
  if (cuentas.length === 0) return null;

  if (colapsado) {
    return (
      <div className="flex flex-col items-center gap-1.5">
        {cuentas.map((c) => (
          <CirculoCuenta key={c.cuenta} uso={c} />
        ))}
      </div>
    );
  }
  const etiquetada = cuentas.length > 1;
  return (
    <div className="w-full space-y-2">
      {cuentas.map((c) => (
        <BloqueCuenta
          key={c.cuenta}
          uso={c}
          etiquetada={etiquetada}
          abierto={cuentaAbiertaId === c.cuenta}
          onToggle={() => setCuentaAbiertaId((v) => (v === c.cuenta ? null : c.cuenta))}
        />
      ))}
    </div>
  );
}

export function IndicadorUso({
  colapsado = false,
  onAbiertoChange,
}: {
  colapsado?: boolean;
  /** Avisa cuando el panel de desglose abre/cierra: el dock no debe colapsar con el panel abierto
   *  (mismo mecanismo que `onCuentaAbierta` del avatar). */
  onAbiertoChange?: (abierto: boolean) => void;
}) {
  return <IndicadorUsoContenido colapsado={colapsado} onAbiertoChange={onAbiertoChange} />;
}
