// HOVER affordance (estilo Canva), extraído como hook. Owns la capa bajo el cursor (`hoverId`) y
// deriva su contorno (`hoverBox`) para dibujar un acento fino ANTES de seleccionar. Solo cambia al
// entrar/salir de un nodo (mouseover/mouseout burbujean), no en cada movimiento => coste
// despreciable. El componente le pasa el contexto vivo (refs, modos, selección, gesto en curso).

import Konva from "konva";
import type { RefObject } from "react";
import { useState } from "react";

import { cajaVisual, type Capa, type Documento } from "../documento";

export function useHover({
  stageRef,
  espacioRef,
  modoImagen,
  documento,
  seleccionMulti,
  arrastrando,
  marquee,
  reencuadreId,
  recorteActivoId,
  espacio,
}: {
  stageRef: RefObject<Konva.Stage | null>;
  espacioRef: RefObject<boolean>;
  modoImagen: Capa | null;
  documento: Documento;
  seleccionMulti: string[];
  arrastrando: boolean;
  marquee: { x0: number; y0: number; x1: number; y1: number } | null;
  reencuadreId: string | null;
  recorteActivoId: string | null;
  espacio: boolean;
}) {
  const [hoverId, setHoverId] = useState<string | null>(null);

  // Sube hasta el hijo directo de la Layer: las capas de primer nivel llevan ahí su id (las hijas
  // de un grupo resuelven al grupo). Fondo/Transformer no tienen id => null (sin hover).
  const onMouseOverStage = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const stage = stageRef.current;
    if (!stage || espacioRef.current || modoImagen) return;
    let n: Konva.Node | null = e.target === stage ? null : e.target;
    while (n && !(n.getParent() instanceof Konva.Layer)) n = n.getParent();
    const id = n?.id() || null;
    setHoverId(id && documento.capas.some((c) => c.id === id) ? id : null);
  };

  // Contorno de hover: caja de la capa bajo el cursor (si no está ya seleccionada ni hay gesto en
  // curso). Sin rotación usamos la caja REAL renderizada (clientRect del nodo: con imágenes
  // "contain" abraza la foto exacta, igual que el marco de selección); con rotación, la caja del
  // modelo rotada (overlay/texto sin caja ajustan su alto visual).
  const hoverBox = (() => {
    // Mira también los IDs de modo (no solo `modoImagen`): si `recorteId`/`reencuadreId` apuntan a
    // una capa ya inexistente (o no imagen), `modoImagen` resuelve a null pero el editor sigue "en
    // modo" y el contorno de hover no debe aparecer.
    if (!hoverId || arrastrando || marquee || modoImagen || reencuadreId || recorteActivoId || espacio) return null;
    if (seleccionMulti.includes(hoverId)) return null;
    const c = documento.capas.find((x) => x.id === hoverId);
    if (!c || c.visible === false) return null;
    if (!c.rotacion) {
      const stage = stageRef.current;
      const nodo = stage?.findOne<Konva.Node>(`#${c.id}`);
      if (stage && nodo) {
        const r = nodo.getClientRect({ relativeTo: stage, skipShadow: true, skipStroke: true });
        return { x: r.x, y: r.y, w: r.width, h: r.height, rot: 0 };
      }
    }
    // Caja VISIBLE (banda del overlay) rotada alrededor del ORIGEN de la
    // capa (c.x, c.y): es el pivote del nodo Konva y del export. El desplazamiento local del tope
    // visible (vis.y - c.y) se rota con la capa para colocar el contorno donde se pinta de verdad.
    const vis = cajaVisual(c);
    const d = vis.y - c.y;
    const rad = ((c.rotacion || 0) * Math.PI) / 180;
    return { x: c.x - d * Math.sin(rad), y: c.y + d * Math.cos(rad), w: vis.w, h: vis.h, rot: c.rotacion };
  })();

  return { hoverId, setHoverId, onMouseOverStage, hoverBox };
}
