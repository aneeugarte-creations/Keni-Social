/**
 * Editor de la LISTA de horas de publicación de una línea (en hora CDMX). En reposo muestra solo
 * las horas elegidas como chips con × y un botón «+ hora»; al pulsarlo aparece un campo «hh:mm»
 * donde se puede TECLEAR la hora o, al enfocarlo, ELEGIRLA de una lista desplegable (cada 15 min).
 * Teclear filtra la lista; un clic en una hora la añade; Enter o el ✓ confirman lo tecleado. El
 * valor es la misma cadena CSV que consume `GestionPlan` (`parsearHoras` + franjas): no cambia el
 * contrato. Las altas tecleadas se redondean al paso de 5 minutos; rango 00:00–23:55.
 */
import { Check, ChevronDown, Plus, X } from "lucide-react";
import * as React from "react";

const RE_HORA = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** Lee el CSV de horas a "HH:MM" únicas y ordenadas (CDMX); descarta trozos vacíos o inválidos. */
function leerHoras(texto: string): string[] {
  const horas = new Set<string>();
  for (const trozo of (texto || "").split(",")) {
    const t = trozo.trim();
    if (!t) continue;
    const norm = t.length === 4 ? `0${t}` : t; // "8:45" -> "08:45"
    if (RE_HORA.test(norm)) horas.add(norm);
  }
  return [...horas].sort();
}

/** Parseo tolerante de lo tecleado: "8"→08:00, "845"→08:45, "1045"→10:45, "20.30"/"20 30"→20:30,
 *  "9:5"→09:50. Redondea minutos a paso de 5; rango 00:00–23:55. Inválido → null. */
function parsearTecleo(raw: string): string | null {
  const s = raw.trim();
  if (!s) return null;
  let h: number;
  let m: number;
  const sep = s.match(/^(\d{1,2})\s*[:.\s]\s*(\d{1,2})$/);
  if (sep) {
    h = Number(sep[1]);
    m = sep[2].length === 1 ? Number(sep[2]) * 10 : Number(sep[2]);
  } else if (/^\d+$/.test(s)) {
    if (s.length <= 2) {
      h = Number(s);
      m = 0;
    } else if (s.length === 3) {
      h = Number(s.slice(0, 1));
      m = Number(s.slice(1));
    } else if (s.length === 4) {
      h = Number(s.slice(0, 2));
      m = Number(s.slice(2));
    } else {
      return null;
    }
  } else {
    return null;
  }
  if (!Number.isInteger(h) || !Number.isInteger(m)) return null;
  m = Math.round(m / 5) * 5;
  if (m === 60) {
    m = 0;
    h += 1;
  }
  if (h < 0 || h > 23 || m < 0 || m > 59) return null;
  if (h * 60 + m > 23 * 60 + 55) return null;
  const out = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  return RE_HORA.test(out) ? out : null;
}

/** Todas las horas del día en pasos de 15 minutos (la lista para elegir a clic). */
const TIEMPOS: string[] = (() => {
  const out: string[] = [];
  for (let h = 0; h < 24; h += 1) {
    for (const m of [0, 15, 30, 45]) {
      out.push(`${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`);
    }
  }
  return out;
})();

/** Clases del campo de hora; resalta el borde si lo tecleado no es una hora válida. */
function clasesCampo(error: boolean): string {
  return (
    "h-7 w-[4.7rem] rounded-md border bg-transparent pl-2 pr-5 font-mono text-xs tabular-nums " +
    "placeholder:text-muted-foreground/60 focus:outline-none focus-visible:ring-1 focus-visible:ring-ring " +
    (error ? "border-destructive ring-1 ring-destructive" : "border-input")
  );
}

export function SelectorHoras({
  value,
  onChange,
  ariaLabel,
}: {
  value: string;
  onChange: (csv: string) => void;
  ariaLabel: string;
}) {
  const horas = React.useMemo(() => leerHoras(value), [value]);
  const [texto, setTexto] = React.useState("");
  const [abierto, setAbierto] = React.useState(false);
  const [desplegado, setDesplegado] = React.useState(false);
  const [error, setError] = React.useState(false);

  const contenedorRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const listaRef = React.useRef<HTMLDivElement>(null);

  const anadir = (hhmm: string) => {
    if (horas.includes(hhmm)) return;
    onChange([...horas, hhmm].sort().join(", "));
  };
  const quitar = (hora: string) => onChange(horas.filter((h) => h !== hora).join(", "));

  const confirmar = () => {
    const hhmm = parsearTecleo(texto);
    if (hhmm && !horas.includes(hhmm)) {
      anadir(hhmm);
      setTexto("");
      setError(false);
      inputRef.current?.focus();
    } else {
      setError(true);
    }
  };

  const colapsar = React.useCallback(() => {
    setDesplegado(false);
    setAbierto(false);
    setTexto("");
    setError(false);
  }, []);

  // Lista filtrada por lo tecleado (por prefijo de texto o de dígitos).
  const lista = React.useMemo(() => {
    const f = texto.trim();
    if (!f) return TIEMPOS;
    const d = f.replace(/[^0-9]/g, "");
    const r = TIEMPOS.filter((t) => t.startsWith(f) || t.replace(":", "").startsWith(d));
    return r.length ? r : TIEMPOS;
  }, [texto]);

  // Cierra el desplegable (y colapsa si está vacío) al hacer clic fuera.
  React.useEffect(() => {
    if (!desplegado) return;
    const fuera = (e: MouseEvent) => {
      if (!contenedorRef.current?.contains(e.target as Node)) {
        setDesplegado(false);
        if (!texto.trim()) colapsar();
      }
    };
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, [desplegado, texto, colapsar]);

  // Al desplegar, acerca la lista a la hora tecleada (o a las 08:00 por defecto).
  React.useEffect(() => {
    if (!desplegado || !listaRef.current) return;
    const objetivo = parsearTecleo(texto) ?? "08:00";
    const fila = listaRef.current.querySelector<HTMLElement>(`[data-hora="${objetivo}"]`);
    fila?.scrollIntoView?.({ block: "center" });
  }, [desplegado, texto]);

  return (
    <div
      ref={contenedorRef}
      className="flex flex-wrap items-center gap-1.5"
      role="group"
      aria-label={ariaLabel}
    >
      {horas.map((hora) => (
        <span
          key={hora}
          className="inline-flex items-center gap-1 rounded-md border border-input bg-muted/40 py-0.5 pl-2 pr-1 font-mono text-xs tabular-nums"
        >
          {hora}
          <button
            type="button"
            onClick={() => quitar(hora)}
            aria-label={`Quitar ${hora}`}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}

      {abierto ? (
        <div className="flex items-center gap-1">
          <div className="relative inline-flex items-center">
            <input
              ref={inputRef}
              type="text"
              inputMode="numeric"
              value={texto}
              placeholder="hh:mm"
              aria-label="Hora (CDMX): teclea o elige"
              onChange={(e) => {
                setTexto(e.target.value);
                setError(false);
                setDesplegado(true);
              }}
              onFocus={() => setDesplegado(true)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  confirmar();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  if (desplegado) setDesplegado(false);
                  else colapsar();
                }
              }}
              className={clasesCampo(error)}
            />
            <ChevronDown className="pointer-events-none absolute right-1.5 h-3 w-3 text-muted-foreground/60" />
            {desplegado ? (
              <div
                ref={listaRef}
                className="absolute left-0 top-full z-50 mt-1 max-h-52 w-28 overflow-auto rounded-md border border-border bg-popover p-1 shadow-md"
              >
                {lista.map((t) => {
                  const yace = horas.includes(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      data-hora={t}
                      disabled={yace}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        if (yace) return;
                        anadir(t);
                        setTexto("");
                        setError(false);
                        inputRef.current?.focus();
                      }}
                      className={
                        "flex w-full items-center justify-between rounded px-2 py-1 text-left font-mono text-xs tabular-nums " +
                        (yace ? "text-muted-foreground/40" : "hover:bg-accent")
                      }
                    >
                      <span>{t}</span>
                      {yace ? <Check className="h-3 w-3" /> : null}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
          <button
            type="button"
            onClick={confirmar}
            aria-label="Guardar hora"
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <Check className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => {
            setAbierto(true);
            setDesplegado(true);
            requestAnimationFrame(() => inputRef.current?.focus());
          }}
          aria-label="Añadir hora"
          className="inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <Plus className="h-3.5 w-3.5" /> hora
        </button>
      )}
    </div>
  );
}
