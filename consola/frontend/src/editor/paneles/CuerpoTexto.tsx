// Inspector · capa de TEXTO: contenido, rol/binding, tipografía, efectos (presets + manual),
// relleno degradado y chip.

import { ColorControl } from "../ColorControl";

import type { Capa, CapaTexto } from "../documento";
import { ETIQUETA_BINDING } from "../documento";
import { Seccion } from "../Seccion";

import { Campo, CamposDegradado, CamposSombra, Num } from "./Campos";
import type { PropsCuerpoCapa } from "./tipos";

export function CuerpoTexto({ capa, set, familias }: PropsCuerpoCapa<CapaTexto>) {
  return (
    <>
      {/* TEXTO · PRINCIPAL: contenido, rol/binding, mayúsculas, valign y el chip (toggle + color).
          Los detalles del chip (margen/redondeo) viven en Avanzado. */}
      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <Campo etiqueta="Rol en la plantilla">
          <select
            value={capa.binding ?? "fijo"}
            onChange={(e) => set({ binding: e.target.value === "fijo" ? null : (e.target.value as CapaTexto["binding"]) } as Partial<Capa>)}
            className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          >
            <option value="fijo">{ETIQUETA_BINDING.fijo}</option>
            <option value="copy_in">{ETIQUETA_BINDING.copy_in}</option>
            <option value="etiqueta_default">{ETIQUETA_BINDING.etiqueta_default}</option>
          </select>
        </Campo>
        <textarea
          value={capa.texto}
          onChange={(e) => set({ texto: e.target.value } as Partial<Capa>)}
          placeholder={capa.binding ? "Texto de ejemplo (se sustituye por el de la pieza)…" : "Texto…"}
          className="min-h-[60px] rounded border border-input bg-background p-1.5 text-sm"
        />
        <Campo etiqueta="Mayúsculas">
          <input type="checkbox" checked={capa.mayusculas} onChange={(e) => set({ mayusculas: e.target.checked } as Partial<Capa>)} />
        </Campo>
        <Campo etiqueta="Alineación vertical">
          <div className="flex gap-1">
            {(["arriba", "centro", "abajo"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => set({ valign: v } as Partial<Capa>)}
                className={`rounded border px-1.5 py-0.5 text-xs capitalize ${
                  (capa.valign ?? "centro") === v
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                {v}
              </button>
            ))}
          </div>
        </Campo>
        <Campo etiqueta="Fondo (chip)">
          <input
            type="checkbox"
            checked={!!capa.chip}
            onChange={(e) =>
              set({ chip: e.target.checked ? { color: "#E30613", pad_x: 24, pad_y: 14, radio: 0 } : null } as Partial<Capa>)
            }
          />
        </Campo>
        {capa.chip && (
          <Campo etiqueta="Color del chip">
            <ColorControl
              valor={capa.chip.color}
              onChange={(c) => set({ chip: { ...capa.chip!, color: c } } as Partial<Capa>)}
            />
          </Campo>
        )}
      </div>

      {/* TEXTO · MÁS: tipografía de uso frecuente (también accesible en la barra rápida). */}
      <Seccion titulo="Más">
        <div className="grid grid-cols-2 gap-2">
          <Campo etiqueta="Tamaño"><Num valor={capa.tamano} onChange={(v) => set({ tamano: v } as Partial<Capa>)} /></Campo>
          <Campo etiqueta="Peso"><Num valor={capa.peso} paso={100} onChange={(v) => set({ peso: v } as Partial<Capa>)} /></Campo>
          <Campo etiqueta="Color">
            <ColorControl valor={capa.color} onChange={(c) => set({ color: c } as Partial<Capa>)} />
          </Campo>
        </div>
        <Campo etiqueta="Fuente">
          <select
            value={capa.familia}
            onChange={(e) => set({ familia: e.target.value } as Partial<Capa>)}
            className="max-w-[140px] rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          >
            {familias.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
            {/* Si la capa usa una familia que ya no está en la lista, la mostramos igual. */}
            {!familias.includes(capa.familia) && (
              <option value={capa.familia}>{capa.familia}</option>
            )}
          </select>
        </Campo>
        <Campo etiqueta="Alineación">
          <select
            value={capa.alineacion}
            onChange={(e) => set({ alineacion: e.target.value as CapaTexto["alineacion"] } as Partial<Capa>)}
            className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          >
            <option value="izquierda">Izquierda</option>
            <option value="centro">Centro</option>
            <option value="derecha">Derecha</option>
            <option value="justificado">Justificado</option>
          </select>
        </Campo>
        <Campo etiqueta="Interlineado">
          <Num valor={capa.interlineado} paso={0.05} onChange={(v) => set({ interlineado: v } as Partial<Capa>)} />
        </Campo>
      </Seccion>

      {/* TEXTO · AVANZADO: ajuste fino tipográfico, curvado, efectos (presets + manual),
          relleno degradado y detalles del chip. */}
      <Seccion titulo="Avanzado">
        <Campo etiqueta="Interletra">
          <Num valor={capa.interletra ?? 0} paso={0.5} onChange={(v) => set({ interletra: v } as Partial<Capa>)} />
        </Campo>
        <div className="grid grid-cols-2 gap-2">
          <Campo etiqueta="Máx. líneas">
            <Num
              valor={capa.auto_ajuste?.max_lineas ?? 4}
              onChange={(v) =>
                set({ auto_ajuste: { ...capa.auto_ajuste, max_lineas: Math.max(1, v) } } as Partial<Capa>)
              }
            />
          </Campo>
          <Campo etiqueta="Tamaño mínimo">
            <Num
              valor={capa.auto_ajuste?.tam_min ?? 40}
              onChange={(v) =>
                set({ auto_ajuste: { ...capa.auto_ajuste, tam_min: Math.max(1, v) } } as Partial<Capa>)
              }
            />
          </Campo>
        </div>
        {/* Texto curvo (en arco): el toggle activa una curva con radio por defecto; el slider lo
            ajusta (+ = sonrisa, - = ceño). Sin curva el texto es recto (camino legado). */}
        <Campo etiqueta="Curvar">
          <input
            type="checkbox"
            checked={!!capa.curva?.radio}
            onChange={(e) => set({ curva: e.target.checked ? { radio: 600 } : null } as Partial<Capa>)}
          />
        </Campo>
        {!!capa.curva?.radio && (
          <Campo etiqueta="Radio">
            <input
              type="range"
              min={-2000}
              max={2000}
              step={20}
              value={capa.curva?.radio ?? 600}
              onChange={(e) => {
                const r = Number(e.target.value);
                set({ curva: r === 0 ? null : { radio: r } } as Partial<Capa>);
              }}
              className="w-full"
            />
          </Campo>
        )}
        {/* Presets rápidos de efecto de texto: rellenan sombra/contorno de un clic (reusan los
            campos existentes, sin esquema nuevo). El "Glow" toma el color del texto. */}
        <div className="flex flex-wrap gap-1">
          {(() => {
            const colorTexto = capa.color || "#FFFFFF";
            const presets: { etiqueta: string; cambios: Partial<CapaTexto> }[] = [
              { etiqueta: "Glow", cambios: { sombra: { dx: 0, dy: 0, color: colorTexto, desenfoque: 24, opacidad: 0.9 } } },
              { etiqueta: "Neón", cambios: { sombra: { dx: 0, dy: 0, color: "#22D3EE", desenfoque: 28, opacidad: 0.95 }, contorno: { color: "#22D3EE", grosor: 2 } } },
              { etiqueta: "Contorno", cambios: { contorno: { color: "#000000", grosor: 8 } } },
              { etiqueta: "Sombra suave", cambios: { sombra: { dx: 0, dy: 8, color: "#000000", desenfoque: 16, opacidad: 0.5 } } },
              { etiqueta: "Quitar efectos", cambios: { sombra: null, contorno: null } },
            ];
            return presets.map((p) => (
              <button
                key={p.etiqueta}
                type="button"
                onClick={() => set(p.cambios as Partial<Capa>)}
                className="rounded border border-input bg-background px-1.5 py-0.5 text-[11px] hover:bg-accent"
              >
                {p.etiqueta}
              </button>
            ));
          })()}
        </div>
        <Campo etiqueta="Contorno">
          <input
            type="checkbox"
            checked={!!capa.contorno}
            onChange={(e) => set({ contorno: e.target.checked ? { color: "#000000", grosor: 6 } : null } as Partial<Capa>)}
          />
        </Campo>
        {capa.contorno && (
          <>
            <Campo etiqueta="Color del contorno">
              <ColorControl
                valor={capa.contorno.color}
                onChange={(c) => set({ contorno: { ...capa.contorno!, color: c } } as Partial<Capa>)}
              />
            </Campo>
            <Campo etiqueta="Grosor del contorno">
              <Num
                valor={capa.contorno.grosor}
                onChange={(v) => set({ contorno: { ...capa.contorno!, grosor: Math.max(0, v) } } as Partial<Capa>)}
              />
            </Campo>
          </>
        )}
        <Campo etiqueta="Sombra">
          <input
            type="checkbox"
            checked={!!capa.sombra}
            onChange={(e) => set({ sombra: e.target.checked ? { dx: 2, dy: 2, color: "#000000" } : null } as Partial<Capa>)}
          />
        </Campo>
        {capa.sombra && (
          <CamposSombra sombra={capa.sombra} onChange={(s) => set({ sombra: s } as Partial<Capa>)} />
        )}
        <Campo etiqueta="Relleno">
          <select
            value={capa.relleno_degradado ? "degradado" : "solido"}
            onChange={(e) =>
              set({
                relleno_degradado:
                  e.target.value === "degradado"
                    ? { desde: capa.color, hasta: "#111315", angulo: 180 }
                    : null,
              } as Partial<Capa>)
            }
            className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          >
            <option value="solido">Sólido</option>
            <option value="degradado">Degradado</option>
          </select>
        </Campo>
        {capa.relleno_degradado && (
          <CamposDegradado
            deg={capa.relleno_degradado}
            onChange={(d) => set({ relleno_degradado: d } as Partial<Capa>)}
          />
        )}
        {/* Detalles del chip (solo si está activo): margen y redondeo. El toggle + color están en Principal. */}
        {capa.chip && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Campo etiqueta="Margen X">
                <Num valor={capa.chip.pad_x} onChange={(v) => set({ chip: { ...capa.chip!, pad_x: Math.max(0, v) } } as Partial<Capa>)} />
              </Campo>
              <Campo etiqueta="Margen Y">
                <Num valor={capa.chip.pad_y} onChange={(v) => set({ chip: { ...capa.chip!, pad_y: Math.max(0, v) } } as Partial<Capa>)} />
              </Campo>
            </div>
            <Campo etiqueta="Redondeo">
              <Num valor={capa.chip.radio} onChange={(v) => set({ chip: { ...capa.chip!, radio: Math.max(0, v) } } as Partial<Capa>)} />
            </Campo>
          </>
        )}
      </Seccion>
    </>
  );
}
