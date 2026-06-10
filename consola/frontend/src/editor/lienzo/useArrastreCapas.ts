// Arrastre de capas con SMART GUIDES nivel Canva y movimiento en grupo (selección múltiple),
// extraído como hook. Owns el ref `multiDrag` y devuelve los tres manejadores
// (`onDragStart`/`onDragMove`/`onDragEnd`) más el estado `arrastrando`/`guias`. Toda la lógica de
// imán/espaciado-igual/rejilla/dentro-del-marco vive aquí (los cálculos puros en `imanes.ts`); el
// componente solo le pasa el contexto vivo.
//
//   · Imán: snap a bordes/centros del lienzo, márgenes y otras capas, con umbral CONSTANTE en
//     píxeles de PANTALLA. Junto a cada guía, una etiqueta con la distancia (px del documento) a
//     la capa alineada — overlay HTML mutado directamente (sin setState por frame), como las
//     etiquetas vivas del gesto.
//   · ESPACIADO IGUAL (estilo Canva): al arrastrar entre capas alineadas, snap cuando la
//     separación iguala la de otro par, con guías con topes + etiquetas px en cada hueco.
//   · Ctrl (o ⌘ en Mac) MANTENIDA durante el arrastre SUSPENDE imán y rejilla (movimiento libre).

import type Konva from "konva";
import { type RefObject, useRef, useState } from "react";

import type { Documento } from "../documento";
import type { StoreEditor } from "../store";
import {
  type CajaIman,
  type ObjetivoIman,
  type SnapEspaciado,
  UMBRAL_IMAN_PANTALLA,
  calcularEspaciado,
  calcularImanEje,
  huecoPerpendicular,
} from "./imanes";
import { clampMarco } from "./lib";

export interface GuiasArrastre {
  x: number | null;
  y: number | null;
  espX: SnapEspaciado | null;
  espY: SnapEspaciado | null;
}

const SIN_GUIAS: GuiasArrastre = { x: null, y: null, espX: null, espY: null };

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
  etiquetasRef,
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
  // Contenedor de las etiquetas de distancia (overlay HTML sobre el lienzo, en px de pantalla):
  // el hook lo muta directamente por frame (textContent/left/top), sin setState.
  etiquetasRef?: RefObject<HTMLDivElement | null>;
}) {
  // Arrastre múltiple: posiciones iniciales de todas las capas seleccionadas al empezar a mover.
  const multiDrag = useRef<{ dragId: string; ini: Map<string, { x: number; y: number }> } | null>(null);
  const [guias, setGuias] = useState<GuiasArrastre>(SIN_GUIAS);
  const [arrastrando, setArrastrando] = useState(false);

  // Pinta (o borra, con lista vacía) las etiquetas de distancia por mutación directa del DOM.
  const pintarEtiquetas = (items: { x: number; y: number; texto: string }[]) => {
    const cont = etiquetasRef?.current;
    if (!cont) return;
    if (items.length === 0) {
      if (cont.childElementCount > 0) cont.replaceChildren();
      return;
    }
    cont.replaceChildren(
      ...items.map((it) => {
        const el = document.createElement("div");
        el.className =
          "absolute -translate-x-1/2 -translate-y-1/2 rounded bg-pink-500 px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-white shadow-md";
        el.style.left = `${Math.round(it.x)}px`;
        el.style.top = `${Math.round(it.y)}px`;
        el.textContent = it.texto;
        return el;
      }),
    );
  };

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
    setGuias(SIN_GUIAS);
    pintarEtiquetas([]);
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
      setGuias(SIN_GUIAS);
      pintarEtiquetas([]);
      return;
    }
    const capa = documento.capas.find((c) => c.id === nodo.id());
    if (!capa) return;
    // Umbral del imán CONSTANTE en píxeles de PANTALLA: a cualquier zoom se "siente" igual.
    const umbral = UMBRAL_IMAN_PANTALLA / escala;
    // Ctrl (o ⌘) mantenida SUSPENDE imán y rejilla durante el arrastre (movimiento libre, estilo
    // Canva). Se evalúa por evento: basta pulsarla a mitad de gesto para liberar el snap.
    const suspendido = !!(e.evt && (e.evt.ctrlKey || e.evt.metaKey));
    let lx: number | null = null;
    let ly: number | null = null;
    let espX: SnapEspaciado | null = null;
    let espY: SnapEspaciado | null = null;
    const etiquetas: { x: number; y: number; texto: string }[] = [];
    // IMÁN (si está activo): snap a objetos + bordes/centro del lienzo + 4 líneas de margen. Tiene
    // PRIORIDAD sobre el espaciado igual y la rejilla. Apagado => sin guías ni ajuste magnético.
    if (iman && !suspendido) {
      const objX: ObjetivoIman[] = [{ t: 0 }, { t: w / 2 }, { t: w }];
      const objY: ObjetivoIman[] = [{ t: 0 }, { t: h / 2 }, { t: h }];
      // Líneas de margen como objetivos de snap (x = safe_left y w - safe_right; y análogo).
      if (safeLeft > 0) objX.push({ t: safeLeft });
      if (safeRight > 0) objX.push({ t: w - safeRight });
      if (safeTop > 0) objY.push({ t: safeTop });
      if (safeBottom > 0) objY.push({ t: h - safeBottom });
      const otras: CajaIman[] = [];
      for (const c of documento.capas) {
        if (c.id === capa.id) continue;
        const cajaC: CajaIman = { x: c.x, y: c.y, w: c.w, h: c.h };
        objX.push({ t: c.x, ref: cajaC }, { t: c.x + c.w / 2, ref: cajaC }, { t: c.x + c.w, ref: cajaC });
        objY.push({ t: c.y, ref: cajaC }, { t: c.y + c.h / 2, ref: cajaC }, { t: c.y + c.h, ref: cajaC });
        otras.push(cajaC);
      }
      const sx = calcularImanEje(nodo.x(), capa.w, objX, umbral);
      if (sx) {
        nodo.x(sx.pos);
        lx = sx.guia;
      }
      const sy = calcularImanEje(nodo.y(), capa.h, objY, umbral);
      if (sy) {
        nodo.y(sy.pos);
        ly = sy.guia;
      }
      const cajaActual = (): CajaIman => ({ x: nodo.x(), y: nodo.y(), w: capa.w, h: capa.h });
      // ESPACIADO IGUAL (estilo Canva): solo en el eje que el imán NO haya fijado.
      if (lx === null) {
        espX = calcularEspaciado(cajaActual(), otras, "x", umbral);
        if (espX) nodo.x(espX.pos);
      }
      if (ly === null) {
        espY = calcularEspaciado(cajaActual(), otras, "y", umbral);
        if (espY) nodo.y(espY.pos);
      }
      // Etiquetas de distancia (px del documento): junto a la guía del imán, la separación con la
      // capa alineada; en el espaciado igual, el tamaño (idéntico) de cada hueco.
      if (sx?.ref && lx !== null) {
        const hx = huecoPerpendicular(cajaActual(), sx.ref, "x");
        if (hx) etiquetas.push({ x: lx * escala, y: hx.centro * escala, texto: `${Math.round(hx.gap)} px` });
      }
      if (sy?.ref && ly !== null) {
        const hy = huecoPerpendicular(cajaActual(), sy.ref, "y");
        if (hy) etiquetas.push({ x: hy.centro * escala, y: ly * escala, texto: `${Math.round(hy.gap)} px` });
      }
      if (espX) {
        for (const s of espX.segmentos) {
          etiquetas.push({ x: ((s.desde + s.hasta) / 2) * escala, y: s.perp * escala, texto: `${Math.round(espX.gap)} px` });
        }
      }
      if (espY) {
        for (const s of espY.segmentos) {
          etiquetas.push({ x: s.perp * escala, y: ((s.desde + s.hasta) / 2) * escala, texto: `${Math.round(espY.gap)} px` });
        }
      }
    }
    // Snap a la rejilla POR UMBRAL (no redondeo duro): solo cuando el borde superior-izquierdo está
    // cerca de una línea de rejilla, y en los ejes que el imán/espaciado NO hayan fijado. Entre
    // líneas el movimiento es libre y no pelea con el imán.
    if (grid && !suspendido) {
      if (lx === null && !espX) {
        const linea = Math.round(nodo.x() / paso) * paso;
        if (Math.abs(nodo.x() - linea) <= umbral) nodo.x(linea);
      }
      if (ly === null && !espY) {
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
    setGuias({ x: lx, y: ly, espX, espY });
    pintarEtiquetas(etiquetas);
  };

  return { arrastrando, guias, onDragStart, onDragMove, onDragEnd };
}
