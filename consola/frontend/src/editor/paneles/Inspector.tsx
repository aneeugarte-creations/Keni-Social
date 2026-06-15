// Inspector de propiedades: edita la capa seleccionada (texto, imagen, marco, overlay, logo) o, sin
// selección, el lienzo y el fondo del documento. Opera sobre el store del documento via contexto.
// El bloque común (opacidad/geometría/mezcla/estilos) vive aquí; lo específico de cada tipo en su
// `Cuerpo*`.

import { useRef } from "react";

import type { Capa, CapaImagen, CapaLogo, CapaMarco, CapaOverlay, CapaTexto, TipoMezcla } from "../documento";
import { CATALOGO_FUENTES, ETIQUETA_MEZCLA, bandaOverlay, cajaVisual } from "../documento";
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
  // Última edición del inspector (capa + instante), para coalescer ráfagas en el historial.
  const ultimaEdicion = useRef<{ id: string; t: number } | null>(null);
  // Familias disponibles: catálogo embebido + tipografías propias de la marca (sin duplicar).
  const familias = [...CATALOGO_FUENTES, ...fuentesExtra.filter((f) => !CATALOGO_FUENTES.includes(f as never))];

  // Sin capa seleccionada: editar el LIENZO (tamaño/aspect ratio) y el FONDO del documento.
  if (!capa) {
    return <CuerpoLienzo />;
  }

  // Una RÁFAGA de ediciones sobre la misma capa (teclear "1080" = 4 eventos, arrastrar un slider
  // = decenas) cuenta como UN paso de deshacer: instantánea en el PRIMER cambio (no al enfocar,
  // que ensuciaría el redo) + actualizaciones sin registrar — el mismo patrón de coalescencia que
  // el nudge de flechas en `useAtajosTeclado`.
  const set = (cambios: Partial<Capa>) => {
    const ahora = Date.now();
    const st = store.getState();
    const u = ultimaEdicion.current;
    if (!u || u.id !== capa.id || ahora - u.t > 500) st.comenzarGesto();
    ultimaEdicion.current = { id: capa.id, t: ahora };
    st.actualizar(capa.id, cambios, false);
  };

  // El OVERLAY solo pinta su BANDA inferior: Y/Alto muestran y editan la banda VISIBLE (con el
  // modelo crudo los números no correspondían a nada en pantalla: Y=-700/Alto=1350 con la banda
  // arriba midiendo ~607). Al escribir se deshace la conversión — la `y` almacenada sigue siendo
  // el tope de la CAJA y `alto_frac` queda intacto: el contrato del export no cambia.
  const ov = capa.tipo === "overlay" ? (capa as CapaOverlay) : null;

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
          <Campo etiqueta="Y">
            <Num
              valor={ov ? cajaVisual(ov).y : capa.y}
              onChange={(v) => set({ y: ov ? v - (cajaVisual(ov).y - ov.y) : v } as Partial<Capa>)}
            />
          </Campo>
          <Campo etiqueta="Ancho"><Num valor={capa.w} onChange={(v) => set({ w: v } as Partial<Capa>)} /></Campo>
          <Campo etiqueta="Alto">
            <Num
              valor={ov ? bandaOverlay(ov) : capa.h}
              onChange={(v) => {
                if (!ov) return set({ h: v } as Partial<Capa>);
                // El Alto visible es la BANDA: se escala la caja (h' = banda'/alto_frac) anclando
                // su FONDO (la banda vive pegada abajo), sin tocar alto_frac.
                const frac = Math.min(1, Math.max(0.01, ov.alto_frac));
                const hN = Math.max(1, v) / frac;
                set({ h: hN, y: ov.y + ov.h - hN } as Partial<Capa>);
              }}
            />
          </Campo>
          {/* El lienzo no rota GRUPOS (política: se desagrupan para rotar; el Transformer los
              deshabilita) pero el export SÍ rotaría a las hijas: el campo se oculta para no fijar
              una rotación que el editor no enseña. Documentos ya guardados no se tocan. */}
          {capa.tipo !== "grupo" && (
            <Campo etiqueta="Rotación"><Num valor={capa.rotacion} onChange={(v) => set({ rotacion: v } as Partial<Capa>)} /></Campo>
          )}
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
