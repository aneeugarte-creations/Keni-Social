// Arrastre de capas con SMART GUIDES y movimiento en grupo (selección múltiple), extraído como hook.
// Mantiene EXACTAMENTE el comportamiento previo: owns el ref `multiDrag` y devuelve los tres
// manejadores (`onDragStart`/`onDragMove`/`onDragEnd`) más el estado `arrastrando`/`guias`. Toda la
// lógica de imán/rejilla/dentro-del-marco vive aquí; el componente solo le pasa el contexto vivo.

import type Konva from "konva";
import { type RefObject, useRef, useState } from "react";

import type { Documento } from "../documento";
import type { StoreEditor } from "../store";
import { clampMarco } from "./lib";

export function useArrastreCapas({
  store,
  stageRef,
  documento,
  escala,
  iman,
  grid,
  paso,
  dentroMarco,
  w,
  h,
  safeTop,
  safeBottom,
  safeLeft,
  safeRight,
}: {
  store: StoreEditor;
  stageRef: RefObject<Konva.Stage | null>;
  documento: Documento;
  escala: number;
  iman: boolean;
  grid: boolean;
  paso: number;
  dentroMarco: boolean;
  w: number;
  h: number;
  safeTop: number;
  safeBottom: number;
  safeLeft: number;
  safeRight: number;
}) {
  // Arrastre múltiple: posiciones iniciales de todas las capas seleccionadas al empezar a mover.
  const multiDrag = useRef<{ dragId: string; ini: Map<string, { x: number; y: number }> } | null>(null);
  const [guias, setGuias] = useState<{ x: number | null; y: number | null }>({ x: null, y: null });
  const [arrastrando, setArrastrando] = useState(false);

  const onDragStart = (e: Konva.KonvaEventObject<DragEvent>) => {
    setArrastrando(true);
    const id = e.target.id();
    const st = store.getState();
    if (st.seleccionMulti.length > 1 && st.seleccionMulti.includes(id)) {
      const ini = new Map<string, { x: number; y: number }>();
      for (const sid of st.seleccionMulti) {
        const n = stageRef.current?.findOne<Konva.Node>(`#${sid}`);
        if (n) ini.set(sid, { x: n.x(), y: n.y() });
      }
      multiDrag.current = { dragId: id, ini };
    } else {
      multiDrag.current = null;
    }
  };

  const onDragEnd = () => {
    setArrastrando(false);
    setGuias({ x: null, y: null });
    const md = multiDrag.current;
    if (md) {
      const stage = stageRef.current;
      const pos: { id: string; x: number; y: number }[] = [];
      md.ini.forEach((_p, sid) => {
        const n = stage?.findOne<Konva.Node>(`#${sid}`);
        if (n) pos.push({ id: sid, x: n.x(), y: n.y() });
      });
      store.getState().aplicarPosiciones(pos);
      multiDrag.current = null;
    }
  };

  // SMART GUIDES al arrastrar (y MOVER en grupo si hay selección múltiple).
  const onDragMove = (e: Konva.KonvaEventObject<DragEvent>) => {
    const nodo = e.target;
    const md = multiDrag.current;
    if (md && md.dragId === nodo.id()) {
      const start = md.ini.get(nodo.id());
      if (start) {
        const dx = nodo.x() - start.x;
        const dy = nodo.y() - start.y;
        const stage = stageRef.current;
        md.ini.forEach((p, sid) => {
          if (sid === nodo.id()) return;
          const n = stage?.findOne<Konva.Node>(`#${sid}`);
          if (n) {
            n.x(p.x + dx);
            n.y(p.y + dy);
          }
        });
      }
      setGuias({ x: null, y: null });
      return;
    }
    const capa = documento.capas.find((c) => c.id === nodo.id());
    if (!capa) return;
    const umbral = 6 / escala;
    let lx: number | null = null, ly: number | null = null;
    // IMÁN (si está activo): snap a objetos + bordes/centro del lienzo + 4 líneas de margen. Tiene
    // PRIORIDAD sobre la rejilla. Apagado => sin guías ni ajuste magnético.
    if (iman) {
      const objX: number[] = [0, w / 2, w];
      const objY: number[] = [0, h / 2, h];
      // Líneas de margen como objetivos de snap (x = safe_left y w - safe_right; y análogo).
      if (safeLeft > 0) objX.push(safeLeft);
      if (safeRight > 0) objX.push(w - safeRight);
      if (safeTop > 0) objY.push(safeTop);
      if (safeBottom > 0) objY.push(h - safeBottom);
      for (const c of documento.capas) {
        if (c.id === capa.id) continue;
        objX.push(c.x, c.x + c.w / 2, c.x + c.w);
        objY.push(c.y, c.y + c.h / 2, c.y + c.h);
      }
      const x = nodo.x(), y = nodo.y();
      const bx = [x, x + capa.w / 2, x + capa.w];
      const by = [y, y + capa.h / 2, y + capa.h];
      for (let i = 0; i < 3 && lx === null; i++) for (const t of objX) if (Math.abs(bx[i] - t) <= umbral) { nodo.x(x + (t - bx[i])); lx = t; break; }
      for (let i = 0; i < 3 && ly === null; i++) for (const t of objY) if (Math.abs(by[i] - t) <= umbral) { nodo.y(y + (t - by[i])); ly = t; break; }
    }
    // Snap a la rejilla POR UMBRAL (no redondeo duro): solo cuando el borde superior-izquierdo está
    // cerca de una línea de rejilla, y en los ejes que el imán NO haya fijado. Entre líneas el
    // movimiento es libre y no pelea con el imán.
    if (grid) {
      if (lx === null) {
        const linea = Math.round(nodo.x() / paso) * paso;
        if (Math.abs(nodo.x() - linea) <= umbral) nodo.x(linea);
      }
      if (ly === null) {
        const linea = Math.round(nodo.y() / paso) * paso;
        if (Math.abs(nodo.y() - linea) <= umbral) nodo.y(linea);
      }
    }
    // MANTENER DENTRO DEL MARCO: acota la caja al lienzo. Si la capa es mayor que el lienzo en un
    // eje, no se fuerzan negativos absurdos (se permite el rango [w - cw, 0], que queda invertido).
    if (dentroMarco) {
      nodo.x(clampMarco(nodo.x(), capa.w, w));
      nodo.y(clampMarco(nodo.y(), capa.h, h));
    }
    setGuias({ x: lx, y: ly });
  };

  return { arrastrando, guias, onDragStart, onDragMove, onDragEnd };
}
