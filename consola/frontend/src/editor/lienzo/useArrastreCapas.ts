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
//   · MULTI-selección: el rect que se imanta es la CAJA ENVOLVENTE del grupo (bordes y centro del
//     conjunto contra página, márgenes y capas NO seleccionadas), y el ajuste se aplica como delta
//     a todas las capas del grupo. Mismas guías, etiquetas y suspensión con Ctrl/⌘.

import type Konva from "konva";
import { type RefObject, useRef, useState } from "react";

import type { Capa, CapaMarco, Documento } from "../documento";
import { cajaVisual } from "../documento";
import type { StoreEditor } from "../store";
import {
  type CajaIman,
  type ObjetivoIman,
  type SnapEspaciado,
  UMBRAL_IMAN_PANTALLA,
  cajaEnvolvente,
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

// Conversión posición de NODO Konva <-> posición del MODELO (la x/y almacenada). Para casi todas
// las capas coinciden; las excepciones: la ELIPSE (Konva la posiciona por su CENTRO, el modelo por
// la esquina sup-izq) y el GRUPO (su nodo vive en (0,0) y se mueve como DELTA sobre la bbox del
// modelo). Volcar el nodo "a pelo" corrompía la y/x de esas capas en cada multi-arrastre.
function modeloDesdeNodo(c: Capa, nx: number, ny: number): { x: number; y: number } {
  if (c.tipo === "marco" && (c as CapaMarco).forma === "elipse") return { x: nx - c.w / 2, y: ny - c.h / 2 };
  if (c.tipo === "grupo") return { x: c.x + nx, y: c.y + ny };
  return { x: nx, y: ny };
}

function nodoDesdeModelo(c: Capa, mx: number, my: number): { x: number; y: number } {
  if (c.tipo === "marco" && (c as CapaMarco).forma === "elipse") return { x: mx + c.w / 2, y: my + c.h / 2 };
  if (c.tipo === "grupo") return { x: mx - c.x, y: my - c.y };
  return { x: mx, y: my };
}

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
  // Arrastre múltiple: instantánea al empezar a mover, por capa seleccionada — posición del NODO
  // (nx,ny), posición del MODELO (cx,cy) y caja VISIBLE (vis). El volcado final escribe
  // modelo_inicial + delta_de_nodo (no la posición cruda del nodo, que para elipse/overlay/grupo
  // no es la x/y del modelo) y el imán trabaja sobre la caja visible inicial + delta.
  const multiDrag = useRef<{
    dragId: string;
    ini: Map<string, { nx: number; ny: number; cx: number; cy: number; vis: CajaIman }>;
  } | null>(null);
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
      const ini = new Map<string, { nx: number; ny: number; cx: number; cy: number; vis: CajaIman }>();
      for (const sid of st.seleccionMulti) {
        const n = stageRef.current?.findOne<Konva.Node>(`#${sid}`);
        const c = st.documento.capas.find((x) => x.id === sid);
        if (n && c) ini.set(sid, { nx: n.x(), ny: n.y(), cx: c.x, cy: c.y, vis: cajaVisual(c) });
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
      const st = store.getState();
      const pos: { id: string; x: number; y: number }[] = [];
      const resetear: Konva.Node[] = [];
      md.ini.forEach((p, sid) => {
        // La capa AGARRADA ya horneó en su propio onDragEnd (CapaNodo convierte nodo -> modelo,
        // y onDragEndGrupo además resetea su nodo a (0,0)): re-escribirla aquí con la posición
        // cruda del nodo la corrompía (elipse/overlay) o la devolvía al origen (grupo reseteado).
        if (sid === md.dragId) return;
        const n = stage?.findOne<Konva.Node>(`#${sid}`);
        if (!n) return;
        // Posición final = modelo inicial + delta del nodo: válido para TODA capa (también las
        // que viven en otro origen: elipse en su centro, grupo en (0,0)).
        const dx = n.x() - p.nx;
        const dy = n.y() - p.ny;
        if (dx === 0 && dy === 0) return;
        pos.push({ id: sid, x: p.cx + dx, y: p.cy + dy });
        // El nodo Group del grupo "pasajero" quedó desplazado imperativamente: tras hornear el
        // delta en el modelo hay que devolverlo a (0,0) — react-konva no re-aplica x=0/y=0
        // porque los props no cambian, y sin reset el grupo se pintaría desplazado DOBLE.
        if (st.documento.capas.find((c) => c.id === sid)?.tipo === "grupo") resetear.push(n);
      });
      if (pos.length) st.aplicarPosiciones(pos);
      for (const n of resetear) n.position({ x: 0, y: 0 });
      multiDrag.current = null;
    }
  };

  // SMART GUIDES al arrastrar: con UNA capa se imanta su caja; con selección MÚLTIPLE, la CAJA
  // ENVOLVENTE del grupo (y el ajuste se reparte como delta a todas las capas seleccionadas).
  const onDragMove = (e: Konva.KonvaEventObject<DragEvent>) => {
    const nodo = e.target;
    const md = multiDrag.current;
    const esMulti = !!(md && md.dragId === nodo.id());

    // Posiciona TODAS las capas del grupo en su posición inicial + delta (incluida la arrastrada,
    // por si el imán ajustó la envolvente).
    const aplicarDeltaGrupo = (dx: number, dy: number) => {
      if (!md) return;
      const stage = stageRef.current;
      md.ini.forEach((p, sid) => {
        const n = sid === nodo.id() ? nodo : stage?.findOne<Konva.Node>(`#${sid}`);
        if (n) {
          n.x(p.nx + dx);
          n.y(p.ny + dy);
        }
      });
    };

    // Rect que se IMANTA (caja de la capa o envolvente del grupo) y capas EXCLUIDAS como objetivo
    // (la arrastrada, o todas las del grupo: una capa seleccionada no es objetivo de otra).
    let caja: CajaIman;
    let excluidas: ReadonlySet<string>;
    let dxBase = 0;
    let dyBase = 0;
    if (esMulti && md) {
      const start = md.ini.get(nodo.id());
      if (!start) return;
      dxBase = nodo.x() - start.nx;
      dyBase = nodo.y() - start.ny;
      // La envolvente se construye con las cajas VISIBLES iniciales + delta (la banda del overlay,
      // el bloque del texto legado, la bbox del grupo): la del modelo metía cajas fantasma que
      // desbordaban (h - banda) por abajo y el imán/clamp se disparaba donde no hay nada.
      const cajas: CajaIman[] = [];
      md.ini.forEach((p) => {
        cajas.push({ x: p.vis.x + dxBase, y: p.vis.y + dyBase, w: p.vis.w, h: p.vis.h });
      });
      const env = cajaEnvolvente(cajas);
      if (!env) {
        // Grupo sin cajas conocidas (degenerado): movimiento en bloque sin imán.
        aplicarDeltaGrupo(dxBase, dyBase);
        setGuias(SIN_GUIAS);
        pintarEtiquetas([]);
        return;
      }
      caja = env;
      excluidas = new Set(md.ini.keys());
    } else {
      const capa = documento.capas.find((c) => c.id === nodo.id());
      if (!capa) return;
      // Caja VISIBLE en la posición VIVA del nodo: nodo -> modelo (elipse/grupo viven en otro
      // origen) y modelo -> caja visible (overlay/texto legado pintan desplazados de su x/y).
      const m = modeloDesdeNodo(capa, nodo.x(), nodo.y());
      const vis = cajaVisual(capa);
      caja = { x: m.x + (vis.x - capa.x), y: m.y + (vis.y - capa.y), w: vis.w, h: vis.h };
      excluidas = new Set([capa.id]);
    }
    // Umbral del imán CONSTANTE en píxeles de PANTALLA: a cualquier zoom se "siente" igual.
    const umbral = UMBRAL_IMAN_PANTALLA / escala;
    // Ctrl (o ⌘) mantenida SUSPENDE imán y rejilla durante el arrastre (movimiento libre, estilo
    // Canva). Se evalúa por evento: basta pulsarla a mitad de gesto para liberar el snap.
    const suspendido = !!(e.evt && (e.evt.ctrlKey || e.evt.metaKey));
    // Posición AJUSTADA del rect (la caja o la envolvente): el imán/espaciado/rejilla la van
    // refinando y al final se vuelca al nodo (o como delta a todo el grupo).
    let px = caja.x;
    let py = caja.y;
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
        if (excluidas.has(c.id)) continue;
        // Objetivos = cajas VISIBLES: el overlay ofrece como imán su banda (no el tope/centro de
        // una caja invisible) y el texto legado su bloque; el resto, su caja del modelo.
        const v = cajaVisual(c);
        const cajaC: CajaIman = { x: v.x, y: v.y, w: v.w, h: v.h };
        objX.push({ t: v.x, ref: cajaC }, { t: v.x + v.w / 2, ref: cajaC }, { t: v.x + v.w, ref: cajaC });
        objY.push({ t: v.y, ref: cajaC }, { t: v.y + v.h / 2, ref: cajaC }, { t: v.y + v.h, ref: cajaC });
        otras.push(cajaC);
      }
      const sx = calcularImanEje(px, caja.w, objX, umbral);
      if (sx) {
        px = sx.pos;
        lx = sx.guia;
      }
      const sy = calcularImanEje(py, caja.h, objY, umbral);
      if (sy) {
        py = sy.pos;
        ly = sy.guia;
      }
      const cajaActual = (): CajaIman => ({ x: px, y: py, w: caja.w, h: caja.h });
      // ESPACIADO IGUAL (estilo Canva): solo en el eje que el imán NO haya fijado.
      if (lx === null) {
        espX = calcularEspaciado(cajaActual(), otras, "x", umbral);
        if (espX) px = espX.pos;
      }
      if (ly === null) {
        espY = calcularEspaciado(cajaActual(), otras, "y", umbral);
        if (espY) py = espY.pos;
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
        const linea = Math.round(px / paso) * paso;
        if (Math.abs(px - linea) <= umbral) px = linea;
      }
      if (ly === null && !espY) {
        const linea = Math.round(py / paso) * paso;
        if (Math.abs(py - linea) <= umbral) py = linea;
      }
    }
    // MANTENER DENTRO DEL MARCO: acota la caja (o la envolvente del grupo) al lienzo. Si es mayor
    // que el lienzo en un eje, no se fuerzan negativos absurdos (rango [w - cw, 0], invertido).
    if (dentroMarco) {
      px = clampMarco(px, caja.w, w);
      py = clampMarco(py, caja.h, h);
    }
    if (esMulti) {
      // Delta final del grupo = delta del puntero + el ajuste que el imán aplicó a la envolvente.
      aplicarDeltaGrupo(dxBase + px - caja.x, dyBase + py - caja.y);
    } else {
      // Deshace la conversión: caja visible ajustada -> modelo -> posición del nodo.
      const capa = documento.capas.find((c) => c.id === nodo.id());
      if (capa) {
        const vis = cajaVisual(capa);
        const n = nodoDesdeModelo(capa, px - (vis.x - capa.x), py - (vis.y - capa.y));
        nodo.x(n.x);
        nodo.y(n.y);
      } else {
        nodo.x(px);
        nodo.y(py);
      }
    }
    setGuias({ x: lx, y: ly, espX, espY });
    pintarEtiquetas(etiquetas);
  };

  return { arrastrando, guias, onDragStart, onDragMove, onDragEnd };
}
