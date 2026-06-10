// Inspector de propiedades: edita la capa seleccionada (texto, imagen, marco, overlay, logo) o, sin
// selección, el lienzo y el fondo del documento. Opera sobre el store del documento via contexto.
// El bloque común (opacidad/geometría/mezcla/estilos) vive aquí; lo específico de cada tipo en su
// `Cuerpo*`.

import type { Capa, CapaImagen, CapaLogo, CapaMarco, CapaOverlay, CapaTexto, TipoMezcla } from "../documento";
import { CATALOGO_FUENTES, ETIQUETA_MEZCLA } from "../documento";
import { Seccion } from "../Seccion";
import { useEditor, useStoreEditor } from "../usarEditor";

import { Campo, Num } from "./Campos";
import { CuerpoImagen } from "./CuerpoImagen";
import { CuerpoLienzo } from "./CuerpoLienzo";
import { CuerpoLogo } from "./CuerpoLogo";
import { CuerpoMarco } from "./CuerpoMarco";
import { CuerpoOverlay } from "./CuerpoOverlay";
import { CuerpoTexto } from "./CuerpoTexto";
import { EstilosCapa } from "./EstilosCapa";
import { ETIQUETA_TIPO } from "./lib";

export function Inspector({ fuentesExtra = [], onRecortar }: { fuentesExtra?: string[]; onRecortar?: () => void }) {
  const store = useStoreEditor();
  const capa = useEditor((s) => s.documento.capas.find((c) => c.id === s.seleccion) ?? null);
  const marca = useEditor((s) => s.documento.marca);
  // Familias disponibles: catálogo embebido + tipografías propias de la marca (sin duplicar).
  const familias = [...CATALOGO_FUENTES, ...fuentesExtra.filter((f) => !CATALOGO_FUENTES.includes(f as never))];

  // Sin capa seleccionada: editar el LIENZO (tamaño/aspect ratio) y el FONDO del documento.
  if (!capa) {
    return <CuerpoLienzo />;
  }

  const set = (cambios: Partial<Capa>) => store.getState().actualizar(capa.id, cambios);

  return (
    <div className="flex flex-col gap-3 p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {ETIQUETA_TIPO[capa.tipo]}
      </div>

      {/* BLOQUE COMÚN. Principal: nada imprescindible (lo específico va por tipo más abajo).
          ASPECTO: Opacidad. POSICIÓN Y ESTILOS: geometría (X/Y/Ancho/Alto), rotación, mezcla y
          Estilos guardados. (Antes «Más»/«Avanzado»: jerarquía vacía que no decía nada.) */}
      <Seccion titulo="Aspecto" defaultAbierta>
        <Campo etiqueta="Opacidad">
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={capa.opacidad}
            onChange={(e) => set({ opacidad: Number(e.target.value) } as Partial<Capa>)}
            className="w-20"
          />
        </Campo>
      </Seccion>

      <Seccion titulo="Posición y estilos">
        <div className="grid grid-cols-2 gap-2">
          <Campo etiqueta="X"><Num valor={capa.x} onChange={(v) => set({ x: v } as Partial<Capa>)} /></Campo>
          <Campo etiqueta="Y"><Num valor={capa.y} onChange={(v) => set({ y: v } as Partial<Capa>)} /></Campo>
          <Campo etiqueta="Ancho"><Num valor={capa.w} onChange={(v) => set({ w: v } as Partial<Capa>)} /></Campo>
          <Campo etiqueta="Alto"><Num valor={capa.h} onChange={(v) => set({ h: v } as Partial<Capa>)} /></Campo>
          <Campo etiqueta="Rotación"><Num valor={capa.rotacion} onChange={(v) => set({ rotacion: v } as Partial<Capa>)} /></Campo>
          <Campo etiqueta="Mezcla">
            <select
              value={capa.mezcla ?? "normal"}
              onChange={(e) => set({ mezcla: e.target.value as TipoMezcla } as Partial<Capa>)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              {(Object.keys(ETIQUETA_MEZCLA) as TipoMezcla[]).map((m) => (
                <option key={m} value={m}>
                  {ETIQUETA_MEZCLA[m]}
                </option>
              ))}
            </select>
          </Campo>
        </div>
        {/* Copiar/pegar estilo + estilos guardados (grupo/overlay/logo solo comparten opacidad/mezcla,
            igual de válido). */}
        <EstilosCapa capa={capa} marca={marca} />
      </Seccion>

      {capa.tipo === "texto" && <CuerpoTexto capa={capa as CapaTexto} set={set} familias={familias} />}
      {capa.tipo === "imagen" && <CuerpoImagen capa={capa as CapaImagen} set={set} familias={familias} onRecortar={onRecortar} />}
      {capa.tipo === "marco" && <CuerpoMarco capa={capa as CapaMarco} set={set} familias={familias} />}
      {capa.tipo === "overlay" && <CuerpoOverlay capa={capa as CapaOverlay} set={set} familias={familias} />}
      {capa.tipo === "logo" && <CuerpoLogo capa={capa as CapaLogo} set={set} familias={familias} />}
    </div>
  );
}
