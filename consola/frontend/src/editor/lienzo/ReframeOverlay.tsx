// Capa HTML transparente sobre la imagen en reencuadre. Arrastrar mueve el FOCO (qué parte de la
// foto se ve en el marco) y la rueda ajusta el ZOOM. Todo el gesto cuenta como un paso de
// deshacer. El mapeo de arrastre es "una anchura de marco = recorrido completo del foco": natural
// y acotado (arrastrar a la derecha muestra más del lado izquierdo).

import {
  type PointerEvent as PointerEventReact,
  type WheelEvent as WheelEventReact,
  useRef,
} from "react";

import type { Capa, CapaImagen } from "../documento";
import type { StoreEditor } from "../store";

export function ReframeOverlay({
  capa,
  escala,
  store,
}: {
  capa: CapaImagen;
  escala: number;
  store: StoreEditor;
}) {
  const drag = useRef<{ fx: number; fy: number; px: number; py: number } | null>(null);
  const gestoActivo = useRef(false);
  const finZoom = useRef<number | undefined>(undefined);

  const comenzar = () => {
    if (!gestoActivo.current) {
      store.getState().comenzarGesto();
      gestoActivo.current = true;
    }
  };
  const actual = () => store.getState().documento.capas.find((c) => c.id === capa.id) as CapaImagen | undefined;

  const onPointerDown = (e: PointerEventReact) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    comenzar();
    const c = actual();
    if (!c) return;
    drag.current = { fx: c.foco[0] ?? 0.5, fy: c.foco[1] ?? 0.5, px: e.clientX, py: e.clientY };
  };
  const onPointerMove = (e: PointerEventReact) => {
    if (!drag.current) return;
    const dx = (e.clientX - drag.current.px) / (capa.w * escala);
    const dy = (e.clientY - drag.current.py) / (capa.h * escala);
    const fx = Math.max(0, Math.min(1, drag.current.fx - dx));
    const fy = Math.max(0, Math.min(1, drag.current.fy - dy));
    store.getState().actualizar(capa.id, { foco: [fx, fy] } as Partial<Capa>, false);
  };
  const onPointerUp = () => {
    drag.current = null;
    gestoActivo.current = false;
  };
  const onWheel = (e: WheelEventReact) => {
    e.preventDefault();
    comenzar();
    const c = actual();
    if (!c) return;
    const z = Math.max(1, Math.min(6, (c.zoom || 1) * (e.deltaY < 0 ? 1.06 : 0.94)));
    store.getState().actualizar(capa.id, { zoom: z } as Partial<Capa>, false);
    // Cierra el gesto (un paso de deshacer) tras una ráfaga de rueda.
    window.clearTimeout(finZoom.current);
    finZoom.current = window.setTimeout(() => { gestoActivo.current = false; }, 350);
  };

  return (
    <div
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
      className="absolute cursor-move touch-none ring-2 ring-primary"
      style={{ left: capa.x * escala, top: capa.y * escala, width: capa.w * escala, height: capa.h * escala }}
    />
  );
}
