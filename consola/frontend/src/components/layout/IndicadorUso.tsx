import { useSesion } from "@/hooks/sesion-contexto";
import { useUsoCuenta, type UsoCuenta } from "@/hooks/use-uso-cuenta";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * Indicador SUTIL del uso de la cuenta de Claude del servidor, alojado en el pie del sidebar
 * junto al control «Colapsar». Reutiliza el lenguaje visual de `PanelActualizando` (hilo de 1px,
 * avance discreto, nada de cajas ni alarmas): expandido pinta dos medidores mini (Semana / 5h);
 * colapsado, un círculo con el % semanal y un anillo secundario para la ventana de 5 h.
 *
 * Solo ADMIN (igual que el panel Sistema → Cuenta); para el resto no renderiza nada. La señal
 * vive aislada en `use-uso-cuenta` (cliente + hook + ruta como constante).
 *
 * Estados: neutro cuando aún no hay dato (`null`/cargando, nunca rojo) y ROJO cuando `alerta_roja`
 * (sin cuenta o alguna ventana al 100 %).
 */

/** Redondea un porcentaje (0–100) a entero; `null` => `null`. */
function pctEntero(pct: number | null): number | null {
  return pct == null ? null : Math.max(0, Math.min(100, Math.round(pct)));
}

/** Mensaje breve del estado rojo (sin cuenta / al 100 %), o `null` si no hay alerta. */
function mensajeRojo(uso: UsoCuenta): string | null {
  if (!uso.alerta_roja) return null;
  if (!uso.conectada) return "Sin cuenta";
  if (uso.semana_pct != null && uso.semana_pct >= 100) return "Límite semanal al 100%";
  if (uso.sesion_5h_pct != null && uso.sesion_5h_pct >= 100) return "Límite de sesión al 100%";
  return "Límite al 100%";
}

/** Texto del reset semanal para el tooltip ("Se renueva: …"), o `null` si no se conoce. */
function etiquetaReset(uso: UsoCuenta): string | null {
  const txt = uso.reset_semana_txt ?? uso.reset_semana_iso;
  return txt ? `Se renueva: ${txt}` : null;
}

/** Tooltip COMPLETO: reset + ambos porcentajes + alerta, en una línea. */
function tooltipCompleto(uso: UsoCuenta): string {
  const partes: string[] = [];
  const rojo = mensajeRojo(uso);
  if (rojo) partes.push(rojo);
  const s = pctEntero(uso.semana_pct);
  const v = pctEntero(uso.sesion_5h_pct);
  partes.push(`Semana ${s == null ? "—" : `${s}%`} · 5h ${v == null ? "—" : `${v}%`}`);
  const reset = etiquetaReset(uso);
  if (reset) partes.push(reset);
  return partes.join(" · ");
}

/** Medidor mini (etiqueta + hilo de 1px + %), del mismo lenguaje calmado que `PanelActualizando`. */
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
    <div className="flex items-center gap-2">
      <span className="w-12 shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground/70">
        {etiqueta}
      </span>
      <div
        className="h-px flex-1 overflow-hidden bg-border"
        role="progressbar"
        aria-label={`Uso ${etiqueta}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={valor ?? 0}
      >
        <div
          className={cn("h-full transition-[width] duration-500", rojo ? "bg-destructive" : "bg-foreground")}
          style={{ width: `${tiene ? valor : 0}%` }}
        />
      </div>
      <span
        className={cn(
          "w-8 shrink-0 text-right text-[10px] tabular-nums",
          rojo ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {tiene ? `${valor}%` : "—"}
      </span>
    </div>
  );
}

/** Círculo del rail colapsado: anillo externo = semana, anillo interno = 5 h, número = % semanal. */
function CirculoUso({
  semana,
  sesion5h,
  rojo,
}: {
  semana: number | null;
  sesion5h: number | null;
  rojo: boolean;
}) {
  const rExt = 15.5;
  const rInt = 11;
  const cExt = 2 * Math.PI * rExt;
  const cInt = 2 * Math.PI * rInt;
  const sem = pctEntero(semana);
  const ses = pctEntero(sesion5h);
  const colorTrazo = rojo ? "hsl(var(--destructive))" : "hsl(var(--foreground))";
  return (
    <svg viewBox="0 0 36 36" className="h-8 w-8" aria-hidden="true">
      {/* Pistas (lo no usado): mismo gris fino del hilo de PanelActualizando. */}
      <circle cx="18" cy="18" r={rExt} fill="none" stroke="hsl(var(--border))" strokeWidth="2.5" />
      <circle cx="18" cy="18" r={rInt} fill="none" stroke="hsl(var(--border))" strokeWidth="1.5" />
      {/* Progreso: semana (externo) + sesión 5 h (interno, secundario). Arranca arriba (-90°). */}
      {sem != null && (
        <circle
          cx="18"
          cy="18"
          r={rExt}
          fill="none"
          stroke={colorTrazo}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={cExt}
          strokeDashoffset={cExt * (1 - sem / 100)}
          transform="rotate(-90 18 18)"
        />
      )}
      {ses != null && (
        <circle
          cx="18"
          cy="18"
          r={rInt}
          fill="none"
          stroke={colorTrazo}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeDasharray={cInt}
          strokeDashoffset={cInt * (1 - ses / 100)}
          transform="rotate(-90 18 18)"
          opacity="0.55"
        />
      )}
      <text
        x="18"
        y="18"
        textAnchor="middle"
        dominantBaseline="central"
        className={cn("text-[10px] tabular-nums", rojo ? "fill-destructive" : "fill-muted-foreground")}
        style={{ fontSize: "11px" }}
      >
        {sem == null ? "—" : sem}
      </text>
    </svg>
  );
}

function IndicadorUsoContenido({ colapsado }: { colapsado: boolean }) {
  const { data } = useUsoCuenta(true);

  // Sin dato todavía (cargando / sin respuesta): estado NEUTRO, nunca rojo.
  if (!data) {
    if (colapsado) {
      return (
        <Tooltip label="Uso de la cuenta" side="right">
          <div aria-label="Uso de la cuenta" className="flex items-center justify-center">
            <CirculoUso semana={null} sesion5h={null} rojo={false} />
          </div>
        </Tooltip>
      );
    }
    return (
      <div className="space-y-1">
        <MiniMedidor etiqueta="Semana" pct={null} rojo={false} />
        <MiniMedidor etiqueta="5h" pct={null} rojo={false} />
      </div>
    );
  }

  const rojo = data.alerta_roja;
  const alerta = mensajeRojo(data);

  if (colapsado) {
    return (
      <Tooltip label={tooltipCompleto(data)} side="right">
        <div aria-label={tooltipCompleto(data)} className="flex items-center justify-center">
          <CirculoUso semana={data.semana_pct} sesion5h={data.sesion_5h_pct} rojo={rojo} />
        </div>
      </Tooltip>
    );
  }

  return (
    <Tooltip label={etiquetaReset(data) ?? tooltipCompleto(data)} side="top">
      <div className="w-full space-y-1" aria-label={tooltipCompleto(data)}>
        {alerta ? (
          <p className="px-0.5 text-[10px] font-medium text-destructive">{alerta}</p>
        ) : null}
        <MiniMedidor etiqueta="Semana" pct={data.semana_pct} rojo={rojo} />
        <MiniMedidor etiqueta="5h" pct={data.sesion_5h_pct} rojo={rojo} />
      </div>
    </Tooltip>
  );
}

export function IndicadorUso({ colapsado = false }: { colapsado?: boolean }) {
  const { usuario } = useSesion();
  // Solo admin (igual que Sistema → Cuenta). Para el resto, nada.
  if (usuario?.rol !== "admin") return null;
  return <IndicadorUsoContenido colapsado={colapsado} />;
}
