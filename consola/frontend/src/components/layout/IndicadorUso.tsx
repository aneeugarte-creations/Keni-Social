import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useUsoCuenta, type UsoCuenta } from "@/hooks/use-uso-cuenta";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * Indicador SUTIL del uso de las cuentas de Claude del servidor, alojado en el pie del sidebar
 * junto al control «Colapsar». Reutiliza el lenguaje visual de `PanelActualizando` (hilo de 1px,
 * avance discreto, nada de cajas ni alarmas): expandido pinta dos medidores mini (Semana / 5h) por
 * cuenta; colapsado, un único anillo fino con el % semanal (la ventana de 5 h va al tooltip).
 *
 * QUÉ CUENTAS muestra: el backend devuelve solo las que el usuario PUEDE ver (suelo por marcas);
 * de esas, el selector de marca activo (`useMarcaActiva`) decide cuál(es) PINTAR — en "Todas"
 * (`marcaActiva===null`) todas las permitidas (cada una etiquetada por sus marcas); con una marca
 * concreta, solo la cuenta que sirve esa marca. Si no queda ninguna (editor sin marcas o la marca
 * activa no es de una cuenta permitida), no renderiza nada.
 *
 * Estados: neutro cuando aún no hay dato (`undefined`/cargando, nunca rojo) y ROJO por cuenta
 * cuando `alerta_roja` (sin cuenta o alguna ventana al 100 %).
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

/** Tooltip COMPLETO de una cuenta: etiqueta + reset + ambos porcentajes + alerta, en una línea. */
function tooltipCompleto(uso: UsoCuenta): string {
  const partes: string[] = [];
  if (uso.etiqueta) partes.push(uso.etiqueta);
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

/** Círculo del rail colapsado: un único anillo fino con el % semanal; la ventana de 5 h va al tooltip. */
function CirculoUso({ semana, rojo }: { semana: number | null; rojo: boolean }) {
  const r = 15.5;
  const c = 2 * Math.PI * r;
  const sem = pctEntero(semana);
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

/** Bloque expandido de UNA cuenta: medidores Semana/5h, su aviso rojo y —si hay varias— su etiqueta. */
function BloqueCuenta({ uso, etiquetada }: { uso: UsoCuenta; etiquetada: boolean }) {
  const rojo = uso.alerta_roja;
  const alerta = mensajeRojo(uso);
  return (
    <Tooltip label={etiquetaReset(uso) ?? tooltipCompleto(uso)} side="top">
      <div className="w-full space-y-1" aria-label={tooltipCompleto(uso)}>
        {etiquetada ? (
          <p className="truncate px-0.5 text-[10px] font-medium text-muted-foreground/80">
            {uso.etiqueta}
          </p>
        ) : null}
        {alerta ? <p className="px-0.5 text-[10px] font-medium text-destructive">{alerta}</p> : null}
        <MiniMedidor etiqueta="Semana" pct={uso.semana_pct} rojo={rojo} />
        <MiniMedidor etiqueta="5h" pct={uso.sesion_5h_pct} rojo={rojo} />
      </div>
    </Tooltip>
  );
}

/** Círculo colapsado de UNA cuenta, con su tooltip/etiqueta (incluye marcas + alerta). */
function CirculoCuenta({ uso }: { uso: UsoCuenta }) {
  const etiqueta = tooltipCompleto(uso);
  return (
    <Tooltip label={etiqueta} side="right">
      <div aria-label={etiqueta} className="flex items-center justify-center">
        <CirculoUso semana={uso.semana_pct} rojo={uso.alerta_roja} />
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

function IndicadorUsoContenido({ colapsado }: { colapsado: boolean }) {
  const { data } = useUsoCuenta(true);
  const { marcaActiva } = useMarcaActiva();
  const cuentasRecibidas = data?.cuentas;

  // Sin dato todavía (cargando / sin respuesta): estado NEUTRO, nunca rojo (placeholder de una cuenta).
  if (!cuentasRecibidas) {
    if (colapsado) {
      return (
        <Tooltip label="Uso de la cuenta" side="right">
          <div aria-label="Uso de la cuenta" className="flex items-center justify-center">
            <CirculoUso semana={null} rojo={false} />
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

  const cuentas = cuentasAMostrar(cuentasRecibidas, marcaActiva);
  // Sin cuentas que mostrar (editor sin marcas, o la marca activa no es de una cuenta permitida).
  if (cuentas.length === 0) return null;

  const etiquetada = cuentas.length > 1;
  if (colapsado) {
    return (
      <div className="flex flex-col items-center gap-1.5">
        {cuentas.map((c) => (
          <CirculoCuenta key={c.cuenta} uso={c} />
        ))}
      </div>
    );
  }
  return (
    <div className="w-full space-y-2">
      {cuentas.map((c) => (
        <BloqueCuenta key={c.cuenta} uso={c} etiquetada={etiquetada} />
      ))}
    </div>
  );
}

export function IndicadorUso({ colapsado = false }: { colapsado?: boolean }) {
  return <IndicadorUsoContenido colapsado={colapsado} />;
}
