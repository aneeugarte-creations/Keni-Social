// Controles de formulario reutilizables por el inspector: campo etiquetado, entrada numérica y los
// bloques compuestos de sombra, esquinas y degradado.

import { Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { ColorControl } from "../ColorControl";

import type { RellenoDegradado, Sombra } from "../documento";

export function Campo({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="text-muted-foreground">{etiqueta}</span>
      {children}
    </label>
  );
}

export function Num({
  valor,
  onChange,
  paso = 1,
}: {
  valor: number;
  onChange: (v: number) => void;
  paso?: number;
}) {
  // BORRADOR local mientras se edita, para que el valor del store no machaque el texto a medio
  // teclear. Antes el input era 100% controlado y `Number("") === 0` (campo vacío, "-" o "."
  // iniciales reportan value "") escribía 0 al documento al instante: la capa saltaba al origen al
  // vaciar el campo o al empezar a teclear un negativo, y el value redondeado lo reescribía a "0".
  // Solo se emite cuando el texto parsea a un número FINITO ("1e999" -> Infinity viajaría como
  // null en JSON y el guardado lo rechazaría con 400), SIN redondear (el redondeo a 2 decimales es
  // solo presentación). Escape restaura el valor de entrada; blur/Enter vuelven a la presentación.
  const [borrador, setBorrador] = useState<string | null>(null);
  const inicial = useRef(valor);
  return (
    <input
      type="number"
      step={paso}
      value={borrador ?? Math.round(valor * 100) / 100}
      onFocus={() => {
        inicial.current = valor;
      }}
      onChange={(e) => {
        const texto = e.target.value;
        setBorrador(texto);
        // Estados PARCIALES no se emiten (badInput cubre "-"/"." sueltos, que reportan "");
        // el resto se aplica en vivo para conservar la previsualización en el lienzo.
        if (texto === "" || e.target.validity.badInput) return;
        const v = Number(texto);
        if (Number.isFinite(v)) onChange(v);
      }}
      onBlur={() => setBorrador(null)}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") {
          onChange(inicial.current);
          setBorrador(null);
          (e.target as HTMLInputElement).blur();
        }
      }}
      className="w-20 rounded border border-input bg-background px-1.5 py-0.5 text-right text-xs"
    />
  );
}

// Campos comunes de una Sombra (dx, dy, desenfoque, opacidad, color). Reutilizado por texto,
// imagen y marco. `onChange` recibe la sombra completa actualizada.
export function CamposSombra({ sombra, onChange }: { sombra: Sombra; onChange: (s: Sombra) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2 pl-2">
      <Campo etiqueta="Desp. X"><Num valor={sombra.dx} onChange={(v) => onChange({ ...sombra, dx: v })} /></Campo>
      <Campo etiqueta="Desp. Y"><Num valor={sombra.dy} onChange={(v) => onChange({ ...sombra, dy: v })} /></Campo>
      <Campo etiqueta="Desenfoque">
        <input
          type="range"
          min={0}
          max={60}
          step={1}
          value={sombra.desenfoque ?? 0}
          onChange={(e) => onChange({ ...sombra, desenfoque: Number(e.target.value) })}
          className="w-20"
        />
      </Campo>
      <Campo etiqueta="Opacidad">
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={sombra.opacidad ?? 1}
          onChange={(e) => onChange({ ...sombra, opacidad: Number(e.target.value) })}
          className="w-20"
        />
      </Campo>
      <Campo etiqueta="Color">
        <ColorControl valor={sombra.color} onChange={(c) => onChange({ ...sombra, color: c })} />
      </Campo>
    </div>
  );
}

// Control de esquinas de un rect: radio uniforme o independiente por esquina ([tl,tr,br,bl]).
// Al activar "Esquinas independientes" siembra los 4 con el radio uniforme actual; al desactivar,
// vuelve al radio uniforme (toma la esquina superior izquierda). `onChange` emite {radio} y/o {radios}.
export function RadioEsquinas({
  radio,
  radios,
  onChange,
}: {
  radio: number;
  radios?: [number, number, number, number];
  onChange: (cambios: { radio?: number; radios?: [number, number, number, number] }) => void;
}) {
  const indep = radios != null;
  return (
    <>
      <Campo etiqueta="Esquinas independientes">
        <input
          type="checkbox"
          checked={indep}
          onChange={(e) =>
            onChange(
              e.target.checked
                ? { radios: [radio || 0, radio || 0, radio || 0, radio || 0] }
                : { radio: radios ? radios[0] : radio, radios: undefined },
            )
          }
        />
      </Campo>
      {indep ? (
        <div className="grid grid-cols-2 gap-2">
          {(["Sup. izq.", "Sup. der.", "Inf. der.", "Inf. izq."] as const).map((etq, i) => (
            <Campo key={etq} etiqueta={etq}>
              <Num
                valor={radios![i]}
                onChange={(v) => {
                  const next = [...radios!] as [number, number, number, number];
                  next[i] = Math.max(0, v);
                  onChange({ radios: next });
                }}
              />
            </Campo>
          ))}
        </div>
      ) : (
        <Campo etiqueta="Radio">
          <Num valor={radio} onChange={(v) => onChange({ radio: Math.max(0, v) })} />
        </Campo>
      )}
    </>
  );
}

// Controles de un degradado (texto/marco/fondo): tipo (Lineal/Radial), colores Desde/Hasta y, en
// lineal, el Ángulo. El multi-stop avanzado se ofrece como editor de paradas (añadir/editar/quitar).
// `onChange` recibe el degradado completo actualizado.
export function CamposDegradado({ deg, onChange }: { deg: RellenoDegradado; onChange: (d: RellenoDegradado) => void }) {
  const stops = deg.stops ?? null;
  return (
    <>
      <Campo etiqueta="Tipo">
        <select
          value={deg.tipo ?? "lineal"}
          onChange={(e) => onChange({ ...deg, tipo: e.target.value === "radial" ? "radial" : "lineal" })}
          className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
        >
          <option value="lineal">Lineal</option>
          <option value="radial">Radial</option>
        </select>
      </Campo>
      {!stops && (
        <>
          <Campo etiqueta="Desde">
            <ColorControl valor={deg.desde} onChange={(c) => onChange({ ...deg, desde: c })} />
          </Campo>
          <Campo etiqueta="Hasta">
            <ColorControl valor={deg.hasta} onChange={(c) => onChange({ ...deg, hasta: c })} />
          </Campo>
          {(deg.tipo ?? "lineal") === "lineal" && (
            <Campo etiqueta="Ángulo">
              <Num valor={deg.angulo ?? 180} onChange={(v) => onChange({ ...deg, angulo: v })} />
            </Campo>
          )}
        </>
      )}
      {(deg.tipo ?? "lineal") === "lineal" && stops && (
        <Campo etiqueta="Ángulo">
          <Num valor={deg.angulo ?? 180} onChange={(v) => onChange({ ...deg, angulo: v })} />
        </Campo>
      )}
      {/* Multi-stop AVANZADO: editor de paradas. Al activarlo se siembran desde/hasta como 2 paradas. */}
      {stops ? (
        <div className="flex flex-col gap-1.5 rounded border border-border/60 p-1.5">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>Paradas</span>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => onChange({ ...deg, stops: [...stops, { pos: 1, color: deg.hasta }] })}
                className="rounded border border-input bg-background px-1.5 py-0.5 hover:bg-accent"
              >
                + Parada
              </button>
              <button
                type="button"
                onClick={() => { const { stops: _omit, ...resto } = deg; void _omit; onChange(resto); }}
                className="rounded border border-input bg-background px-1.5 py-0.5 hover:bg-accent"
              >
                Simple
              </button>
            </div>
          </div>
          {stops.map((s, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <Num
                valor={s.pos}
                paso={0.05}
                onChange={(v) => {
                  const next = stops.map((x, j) => (j === i ? { ...x, pos: Math.max(0, Math.min(1, v)) } : x));
                  onChange({ ...deg, stops: next });
                }}
              />
              <ColorControl
                valor={s.color}
                onChange={(c) => onChange({ ...deg, stops: stops.map((x, j) => (j === i ? { ...x, color: c } : x)) })}
              />
              {stops.length > 2 && (
                <button
                  type="button"
                  onClick={() => onChange({ ...deg, stops: stops.filter((_, j) => j !== i) })}
                  className="text-muted-foreground hover:text-destructive"
                  title="Quitar parada"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => onChange({ ...deg, stops: [{ pos: 0, color: deg.desde }, { pos: 1, color: deg.hasta }] })}
          className="self-start rounded border border-input bg-background px-1.5 py-0.5 text-[11px] hover:bg-accent"
        >
          Multi-parada (avanzado)
        </button>
      )}
    </>
  );
}
