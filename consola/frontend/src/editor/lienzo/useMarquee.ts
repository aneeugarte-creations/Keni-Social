// SELECCIÓN POR RECTÁNGULO (marquee), extraída como hook. Owns la caja del marquee (coords del
// DOCUMENTO) y el manejador de mousedown sobre el fondo vacío del Stage. Arranca SOLO desde el fondo
// (target === stage), con botón izquierdo, sin espacio (eso es pan) y fuera de los modos de imagen.
// Si no hay arrastre real => clic seco => deselección. Con shift, añade.

import type Konva from "konva";
import type { RefObject } from "react";
import { useState } from "react";

import { cajaVisual, type Capa } from "../documento";
import type { StoreEditor } from "../store";

export function useMarquee({
  stageRef,
  espacioRef,
  modoImagen,
  escala,
  store,
  salirDeModoImagen,
}: {
  stageRef: RefObject<Konva.Stage | null>;
  espacioRef: RefObject<boolean>;
  modoImagen: Capa | null;
  escala: number;
  store: StoreEditor;
  // Sale del modo de imagen activo (encuadre/recorte). Se llama al clicar en el VACÍO durante ese
  // modo, para salir y deseleccionar "clicando fuera de la foto" (como en Canva), no solo con Esc.
  salirDeModoImagen?: () => void;
}) {
  // Selección por rectángulo (marquee): caja en coordenadas del DOCUMENTO (mismo sistema que el Stage
  // escalado). `null` = inactiva. Se dibuja en su propia Layer no interactiva.
  const [marquee, setMarquee] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  const onMouseDownStage = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const stage = stageRef.current;
    if (!stage || espacioRef.current) return;
    if (e.evt.button !== 0 || e.target !== stage) return;
    // Editando la foto (encuadre/recorte): un clic en el VACÍO —fuera de la foto, cuyo gesto captura
    // su propio overlay— sale del modo y deselecciona, como clicar fuera en Canva (además de Esc o
    // el botón "Listo").
    if (modoImagen) {
      salirDeModoImagen?.();
      store.getState().seleccionar(null);
      return;
    }
    const rect = stage.container().getBoundingClientRect();
    const aDoc = (cx: number, cy: number) => ({ x: (cx - rect.left) / escala, y: (cy - rect.top) / escala });
    const inicio = aDoc(e.evt.clientX, e.evt.clientY);
    const shift = e.evt.shiftKey;
    const base = shift ? store.getState().seleccionMulti.slice() : [];
    let fin = inicio;
    let movido = false;
    setMarquee({ x0: inicio.x, y0: inicio.y, x1: inicio.x, y1: inicio.y });
    const onMove = (ev: MouseEvent) => {
      fin = aDoc(ev.clientX, ev.clientY);
      if (Math.abs(fin.x - inicio.x) * escala > 3 || Math.abs(fin.y - inicio.y) * escala > 3) movido = true;
      setMarquee({ x0: inicio.x, y0: inicio.y, x1: fin.x, y1: fin.y });
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setMarquee(null);
      const st = store.getState();
      if (!movido) {
        // Clic seco en el vacío: deselecciona (salvo shift, que conserva la selección).
        if (!shift) st.seleccionar(null);
        return;
      }
      const x0 = Math.min(inicio.x, fin.x);
      const y0 = Math.min(inicio.y, fin.y);
      const x1 = Math.max(inicio.x, fin.x);
      const y1 = Math.max(inicio.y, fin.y);
      const hits = st.documento.capas
        .filter((c) => {
          if (!c.visible || c.bloqueada) return false;
          // Intersección contra la caja VISIBLE (banda del overlay).
          // AABB sin rotar.
          const v = cajaVisual(c);
          return !(v.x > x1 || v.x + v.w < x0 || v.y > y1 || v.y + v.h < y0);
        })
        .map((c) => c.id);
      const ids = shift ? Array.from(new Set([...base, ...hits])) : hits;
      st.seleccionarMuchas(ids);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return { marquee, onMouseDownStage };
}
