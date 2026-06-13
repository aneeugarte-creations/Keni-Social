// Recorte LATERAL estilo Canva (tiradores laterales del Transformer en imágenes), extraído como
// hook. En una capa de IMAGEN, los 4 tiradores laterales no estiran: RECORTAN desde ese borde (la
// foto mantiene su escala y encuadre; hacia fuera des-recortan hasta el material original). El gesto
// se deriva de una instantánea al inicio + el puntero en coords LOCALES de la capa (robusto ante
// rotación, flip y zoom del lienzo), se vuelca al store por frame SIN historial y cuenta como UN
// paso de deshacer (`comenzarGesto` en el primer movimiento; el `onTransformEnd` de la capa no
// hornea nada porque el nodo queda con escala 1 y attrs == capa). Las esquinas conservan el
// escalado proporcional de siempre (keepRatio); la geometría pura vive en `recorteLateral`.

import Konva from "konva";
import type { RefObject } from "react";
import { useRef } from "react";

import type { Capa, CapaImagen } from "../documento";
import { type GestoLateral, type LadoCaja, docALocal, localADoc, recorteLateral } from "../recorte";
import type { StoreEditor } from "../store";
import { ANCLA_LADO } from "./anclas";

export function useGestoLateral({
  trRef,
  stageRef,
  store,
  escala,
}: {
  trRef: RefObject<Konva.Transformer | null>;
  stageRef: RefObject<Konva.Stage | null>;
  store: StoreEditor;
  escala: number;
}) {
  const gestoLateral = useRef<{
    id: string;
    lado: LadoCaja;
    x0: number;
    y0: number;
    rot: number;
    // El borde se mueve RELATIVO a donde se agarró el tirador (borde inicial - puntero inicial),
    // como el arrastre nativo de las anclas: sin salto al primer movimiento.
    desfase: number;
    params: GestoLateral;
    registrado: boolean;
  } | null>(null);

  const iniciarGestoLateral = () => {
    gestoLateral.current = null;
    const tr = trRef.current;
    const stage = stageRef.current;
    const ancla = tr?.getActiveAnchor();
    const lado = ancla ? ANCLA_LADO[ancla] : undefined;
    if (!tr || !stage || !lado) return;
    const nodos = tr.nodes();
    if (nodos.length !== 1) return;
    const nodo = nodos[0];
    const capa = store.getState().documento.capas.find((c) => c.id === nodo.id());
    if (!capa || capa.tipo !== "imagen" || capa.bloqueada) return;
    const c = capa as CapaImagen;
    // Bitmap EFECTIVO realmente pintado (la foto real o la de muestra del hueco): sin él no hay
    // píxeles que recortar y el tirador cae al estiramiento por defecto (el placeholder vacío es
    // un Rect, no un Group con imagen). El cast es seguro: el lienzo solo pinta
    // HTMLImageElement/canvas (width/height numéricos), los mismos px que usa
    // `geometriaImagenEnCaja` en CapaNodo.
    const img =
      nodo instanceof Konva.Group
        ? (nodo.findOne<Konva.Image>("Image")?.image() as { width: number; height: number } | undefined)
        : undefined;
    if (!img || !(img.width > 0) || !(img.height > 0)) return;
    // Rect que abrazan los tiradores, en coords locales de la capa: la misma base que usa el
    // Transformer para su caja (clientRect local del nodo, sin sombra/trazo).
    const r = nodo.getClientRect({ skipTransform: true, skipShadow: true, skipStroke: true });
    const params: GestoLateral = {
      w: c.w,
      h: c.h,
      iw: img.width,
      ih: img.height,
      ajuste: c.ajuste,
      foco: c.foco,
      zoom: c.zoom,
      crop: c.crop,
      flipH: c.flip_h,
      flipV: c.flip_v,
      caja: { x: r.x, y: r.y, w: r.width, h: r.height },
    };
    // Valida con un gesto nulo (el borde en su posición actual): si la geometría no es recortable
    // (p. ej. contain con letterbox + forma: la foto no cubre la caja), no se arma y el tirador
    // estira como hasta ahora.
    const bordeActual =
      lado === "izq" ? r.x : lado === "der" ? r.x + r.width : lado === "arriba" ? r.y : r.y + r.height;
    if (!recorteLateral(params, lado, bordeActual)) return;
    const pos = stage.getPointerPosition();
    if (!pos) return;
    const rot = c.rotacion || 0;
    const local = docALocal(c.x, c.y, rot, pos.x / escala, pos.y / escala);
    const desfase = bordeActual - (lado === "izq" || lado === "der" ? local.x : local.y);
    gestoLateral.current = { id: c.id, lado, x0: c.x, y0: c.y, rot, desfase, params, registrado: false };
  };

  const moverGestoLateral = () => {
    const g = gestoLateral.current;
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!g || !tr || !stage) return;
    const nodo = tr.nodes()[0];
    if (!nodo || nodo.id() !== g.id) return;
    const pos = stage.getPointerPosition();
    if (!pos) return;
    // Puntero -> documento -> coords LOCALES de la capa al inicio del gesto (rotación incluida);
    // el eje del lado da la posición deseada del borde (con el desfase del agarre inicial).
    const local = docALocal(g.x0, g.y0, g.rot, pos.x / escala, pos.y / escala);
    const borde = (g.lado === "izq" || g.lado === "der" ? local.x : local.y) + g.desfase;
    const r = recorteLateral(g.params, g.lado, borde);
    if (!r) return;
    const origen = localADoc(g.x0, g.y0, g.rot, r.x, r.y);
    // Deshace SIEMPRE la escala que el Transformer aplicó este frame: la caja/foto nuevas las
    // pinta React desde el store (mismo patrón de escritura viva que el CropOverlay).
    nodo.setAttrs({ x: origen.x, y: origen.y, rotation: g.rot, scaleX: 1, scaleY: 1 });
    // Gesto totalmente CLAVADO (p. ej. hacia fuera sin material): ni historial ni escritura.
    const actual = store.getState().documento.capas.find((x) => x.id === g.id);
    if (!actual || actual.tipo !== "imagen") return;
    const cropActual = (actual as CapaImagen).crop ?? { cx: 0, cy: 0, cw: 1, ch: 1 };
    const sinCambio =
      actual.x === origen.x &&
      actual.y === origen.y &&
      actual.w === r.w &&
      actual.h === r.h &&
      cropActual.cx === r.crop.cx &&
      cropActual.cy === r.crop.cy &&
      cropActual.cw === r.crop.cw &&
      cropActual.ch === r.crop.ch;
    if (sinCambio) return;
    if (!g.registrado) {
      store.getState().comenzarGesto();
      g.registrado = true;
    }
    store.getState().actualizar(
      g.id,
      { x: origen.x, y: origen.y, w: r.w, h: r.h, crop: r.crop, zoom: r.zoom, foco: r.foco } as Partial<Capa>,
      false,
    );
  };

  // Desarma el gesto al soltar (onTransformEnd).
  const finalizarGestoLateral = () => {
    gestoLateral.current = null;
  };

  return { iniciarGestoLateral, moverGestoLateral, finalizarGestoLateral };
}
