// Inspector · capa de MARCO (forma): forma, relleno sólido/degradado, borde, esquinas, sombra y
// conversión a hueco de foto.

import { ColorControl } from "../ColorControl";

import type { Capa, CapaMarco } from "../documento";
import { CATALOGO_FORMAS, ETIQUETA_FORMA } from "../documento";
import { Seccion } from "../Seccion";
import { useStoreEditor } from "../usarEditor";

import { Campo, CamposDegradado, CamposSombra, Num, RadioEsquinas } from "./Campos";
import type { PropsCuerpoCapa } from "./tipos";

export function CuerpoMarco({ capa, set }: PropsCuerpoCapa<CapaMarco>) {
  const store = useStoreEditor();
  return (
    <>
      {/* MARCO · PRINCIPAL: forma, color de relleno sólido y borde (color + grosor). El relleno
          degradado se gestiona en Avanzado. */}
      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <Campo etiqueta="Forma">
          <select
            value={capa.forma}
            onChange={(e) => set({ forma: e.target.value as CapaMarco["forma"] } as Partial<Capa>)}
            className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          >
            {CATALOGO_FORMAS.map((f) => (
              <option key={f} value={f}>{ETIQUETA_FORMA[f]}</option>
            ))}
            <option value="linea">Línea</option>
          </select>
        </Campo>
        {/* Color de relleno sólido: solo cuando NO hay relleno degradado activo (Avanzado). */}
        {!capa.relleno_degradado && (
          <Campo etiqueta="Color de relleno">
            <ColorControl valor={capa.relleno ?? "#000000"} onChange={(c) => set({ relleno: c } as Partial<Capa>)} />
          </Campo>
        )}
        <Campo etiqueta="Borde">
          <ColorControl
            valor={capa.borde?.color ?? "#FFFFFF"}
            onChange={(c) => set({ borde: { color: c, grosor: capa.borde?.grosor ?? 6 } } as Partial<Capa>)}
          />
        </Campo>
        <Campo etiqueta="Grosor">
          <Num
            valor={capa.borde?.grosor ?? 0}
            onChange={(v) =>
              set({
                // Grosor <= 0: el back descarta el borde (borde:null); el front hace lo mismo.
                borde: v > 0 ? { color: capa.borde?.color ?? "#FFFFFF", grosor: v } : null,
              } as Partial<Capa>)
            }
          />
        </Campo>
      </div>

      {/* MARCO · AVANZADO: relleno degradado, esquinas, sombra y conversión a foto. */}
      <Seccion titulo="Avanzado">
        <Campo etiqueta="Relleno">
          <select
            value={capa.relleno_degradado ? "degradado" : "solido"}
            onChange={(e) =>
              set({
                relleno_degradado:
                  e.target.value === "degradado"
                    ? { desde: capa.relleno ?? "#E30613", hasta: "#111315", angulo: 180 }
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
        {/* Esquinas: radio uniforme o independiente por esquina (solo rect). */}
        {capa.forma === "rect" && (
          <RadioEsquinas
            radio={capa.radio}
            radios={capa.radios}
            onChange={(cambios) => set(cambios as Partial<Capa>)}
          />
        )}
        <Campo etiqueta="Sombra">
          <input
            type="checkbox"
            checked={!!capa.sombra}
            onChange={(e) => set({ sombra: e.target.checked ? { dx: 0, dy: 12, color: "#000000", desenfoque: 24, opacidad: 0.5 } : null } as Partial<Capa>)}
          />
        </Campo>
        {capa.sombra && (
          <CamposSombra sombra={capa.sombra} onChange={(s) => set({ sombra: s } as Partial<Capa>)} />
        )}
        {/* Convertir la forma en un hueco de FOTO (capa imagen), conservando su silueta. */}
        <button
          type="button"
          onClick={() => store.getState().convertirEnImagen(capa.id)}
          className="self-start rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
        >
          Convertir en foto
        </button>
      </Seccion>
    </>
  );
}
