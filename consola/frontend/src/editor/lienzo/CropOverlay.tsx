// Capa HTML sobre la imagen en MODO RECORTE estilo Canva: se ve la imagen ORIGINAL COMPLETA —nítida
// dentro del marco, ATENUADA fuera— y los 8 tiradores van SOBRE EL MARCO (como en Canva). Arrastrar
// un tirador del marco REDIMENSIONA EL RECORTE: mueve ese borde de la caja y compensa el crop para
// que los píxeles no se muevan (= recortar/des-recortar desde ese borde, hasta el material). Arrastrar
// la IMAGEN la reencuadra (mueve cx/cy del crop) y la rueda hace ZOOM dentro del marco. El crop sigue
// siendo {cx,cy,cw,ch} normalizado sobre la fuente: NUNCA destruye píxeles. Todo gesto cuenta como UN
// paso de deshacer. Confirmar/cancelar viven fuera (banner Hecho/Cancelar + Enter/Esc en el Lienzo).

import {
  type PointerEvent as PointerEventReact,
  type WheelEvent as WheelEventReact,
  useReducer,
  useRef,
} from "react";

import type { Capa, CapaImagen, Crop } from "../documento";
import { fotoMuestra } from "../muestra";
import { type AsaRecorte, type CajaRecorte, escalarCrop, moverAsa, recortarMarcoFoto, vistaRecorte } from "../recorte";
import type { StoreEditor } from "../store";
import { useImagen } from "../useImagen";
import { asasMarco, claseTirador, etiquetaAsa } from "./tiradoresRecorte";

const SIN_CROP: Crop = { cx: 0, cy: 0, cw: 1, ch: 1 };

export function CropOverlay({
  capa,
  escala,
  store,
  muestraFoto = false,
}: {
  capa: CapaImagen;
  escala: number;
  store: StoreEditor;
  // Si el hueco de foto está VACÍO pero la "Vista con muestra (foto)" está activa, recortamos sobre
  // la foto de muestra (lo mismo que pinta el lienzo), para que el recorte sea VISIBLE y se aplique.
  muestraFoto?: boolean;
}) {
  // Redibuja cuando la foto de muestra (generada/cargada async) ya está lista.
  const [, redibujar] = useReducer((n: number) => n + 1, 0);
  const imgReal = useImagen(capa.objeto || null);
  // Imagen EFECTIVA: la foto real del hueco o, si está vacío y la muestra está activa, la de muestra.
  const img = imgReal ?? (muestraFoto && capa.es_foto ? fotoMuestra(() => redibujar()) : null);
  const gestoActivo = useRef(false);
  const finZoom = useRef<number | undefined>(undefined);
  // Gesto en curso: PAN de la imagen (mueve cx/cy del crop) o MARCO (redimensiona el recorte desde un
  // borde). Se parte de la instantánea del inicio del gesto (los deltas no se acumulan sobre estados
  // intermedios).
  const drag = useRef<
    | { modo: "pan"; crop: Crop; px: number; py: number; fw: number; fh: number }
    | { modo: "marco"; asa: AsaRecorte; caja: CajaRecorte; img: CajaRecorte; flipH: boolean; flipV: boolean; px: number; py: number }
    | null
  >(null);

  const W = capa.w * escala;
  const H = capa.h * escala;
  // Imagen ORIGINAL COMPLETA en px de PANTALLA, relativa a la caja: la geometría REAL del render
  // (cover/contain + foco + zoom + crop) garantiza que lo que se ve dentro del marco es EXACTO.
  const v = img && img.width > 0 && img.height > 0
    ? vistaRecorte(img.width, img.height, capa.w, capa.h, capa.ajuste, capa.foco, capa.zoom, capa.crop)
    : null;
  const fL = v ? v.fx * escala : 0;
  const fT = v ? v.fy * escala : 0;
  const fW = v ? v.fw * escala : 0;
  const fH = v ? v.fh * escala : 0;

  const comenzar = () => {
    if (!gestoActivo.current) {
      store.getState().comenzarGesto();
      gestoActivo.current = true;
    }
  };
  const actual = () => store.getState().documento.capas.find((c) => c.id === capa.id) as CapaImagen | undefined;

  // Arrastrar la IMAGEN: pan (mover el contenido a la derecha = mover el crop a la IZQUIERDA en la
  // fuente). El delta en fracciones es directo: la imagen completa mide fw×fh px de pantalla.
  const onDownPan = (e: PointerEventReact) => {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    comenzar();
    const c = actual();
    if (!c || !v || fW <= 0 || fH <= 0) return;
    drag.current = { modo: "pan", crop: c.crop ?? SIN_CROP, px: e.clientX, py: e.clientY, fw: fW, fh: fH };
  };

  // Arrastrar un tirador del MARCO: redimensiona el recorte desde ese borde (caja + crop compensado).
  const onDownMarco = (asa: AsaRecorte) => (e: PointerEventReact) => {
    e.stopPropagation();
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* jsdom / navegadores sin pointer capture: el gesto sigue por los listeners del contenedor */
    }
    comenzar();
    const c = actual();
    if (!c || !img || !(img.width > 0) || !(img.height > 0)) return;
    const vv = vistaRecorte(img.width, img.height, c.w, c.h, c.ajuste, c.foco, c.zoom, c.crop);
    if (!(vv.fw > 0) || !(vv.fh > 0)) return;
    // Rect de la foto completa en px del documento, con el flip aplicado a su posición (como en
    // pantalla); `recortarMarcoFoto` mapea el crop deshaciendo el flip.
    const ix = c.flip_h ? c.w - vv.fx - vv.fw : vv.fx;
    const iy = c.flip_v ? c.h - vv.fy - vv.fh : vv.fy;
    drag.current = {
      modo: "marco",
      asa,
      caja: { x: c.x, y: c.y, w: c.w, h: c.h },
      img: { x: c.x + ix, y: c.y + iy, w: vv.fw, h: vv.fh },
      flipH: !!c.flip_h,
      flipV: !!c.flip_v,
      px: e.clientX,
      py: e.clientY,
    };
  };

  const onMove = (e: PointerEventReact) => {
    const d = drag.current;
    if (!d) return;
    if (d.modo === "pan") {
      const dfx = -(e.clientX - d.px) / d.fw;
      const dfy = -(e.clientY - d.py) / d.fh;
      store.getState().actualizar(capa.id, { crop: moverAsa(d.crop, "mover", dfx, dfy) } as Partial<Capa>, false);
      return;
    }
    const dx = (e.clientX - d.px) / escala;
    const dy = (e.clientY - d.py) / escala;
    const r = recortarMarcoFoto({ caja: d.caja, img: d.img, flipH: d.flipH, flipV: d.flipV }, d.asa, dx, dy);
    if (r) {
      store
        .getState()
        .actualizar(capa.id, { x: r.x, y: r.y, w: r.w, h: r.h, crop: r.crop, zoom: r.zoom, foco: r.foco } as Partial<Capa>, false);
    }
  };

  const onUp = () => {
    drag.current = null;
    gestoActivo.current = false;
  };

  // Rueda = escalar la imagen dentro del marco, anclada al CENTRO del marco (lo que hay bajo el
  // centro no se mueve). Una ráfaga de rueda cuenta como UN paso de deshacer (como el reencuadre).
  const onWheel = (e: WheelEventReact) => {
    e.preventDefault();
    const c = actual();
    if (!c || !img || img.width <= 0 || img.height <= 0) return;
    comenzar();
    // Geometría FRESCA del store (una ráfaga de rueda puede ir más rápida que el re-render).
    const vv = vistaRecorte(img.width, img.height, c.w, c.h, c.ajuste, c.foco, c.zoom, c.crop);
    const ax = vv.fw > 0 ? (c.w / 2 - vv.fx) / vv.fw : 0.5;
    const ay = vv.fh > 0 ? (c.h / 2 - vv.fy) / vv.fh : 0.5;
    const f = e.deltaY < 0 ? 1.06 : 1 / 1.06;
    store.getState().actualizar(capa.id, { crop: escalarCrop(c.crop ?? SIN_CROP, f, ax, ay) } as Partial<Capa>, false);
    window.clearTimeout(finZoom.current);
    finZoom.current = window.setTimeout(() => {
      gestoActivo.current = false;
    }, 350);
  };

  return (
    <div
      role="group"
      aria-label="Recorte de imagen"
      onPointerMove={onMove}
      onPointerUp={onUp}
      onWheel={onWheel}
      className="absolute touch-none"
      style={{ left: capa.x * escala, top: capa.y * escala, width: W, height: H }}
    >
      {img && v && (
        <>
          {/* Imagen ORIGINAL completa ATENUADA: se ve también FUERA del marco (estilo Canva). */}
          <img
            src={img.src}
            alt=""
            draggable={false}
            className="pointer-events-none absolute max-w-none select-none opacity-40"
            style={{ left: fL, top: fT, width: fW, height: fH }}
          />
          {/* Copia NÍTIDA recortada al marco: dentro del marco la foto se ve a opacidad plena
              (encima de la atenuada), exactamente donde el render la pinta. */}
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            <img
              src={img.src}
              alt=""
              draggable={false}
              className="absolute max-w-none select-none"
              style={{ left: fL, top: fT, width: fW, height: fH }}
            />
          </div>
          {/* Contorno de la imagen completa (referencia de hasta dónde llega la foto). */}
          <div
            className="pointer-events-none absolute border border-primary/50"
            style={{ left: fL, top: fT, width: fW, height: fH }}
          />
          {/* Superficie de arrastre: TODA la imagen (también la parte fuera del marco). El gesto es
              de puntero (sin teclado): role + label para que el lector de pantalla la identifique. */}
          <div
            role="button"
            aria-label="Mover la imagen dentro del marco"
            onPointerDown={onDownPan}
            className="absolute cursor-move"
            style={{ left: fL, top: fT, width: fW, height: fH }}
          />
          {/* Tiradores del MARCO (estilo Canva): redimensionan el recorte desde ese borde. Encima de
              la superficie de pan para que agarrar un borde no inicie un arrastre de imagen. */}
          {asasMarco(W, H).map((a) => (
            <div
              key={a.asa}
              role="button"
              aria-label={etiquetaAsa(a.asa)}
              onPointerDown={onDownMarco(a.asa)}
              className={claseTirador(a.asa)}
              style={{ left: a.x, top: a.y, cursor: a.cursor }}
            />
          ))}
        </>
      )}
      {/* MARCO del recorte: la caja de la capa. */}
      <div className="pointer-events-none absolute inset-0 ring-2 ring-primary" />
    </div>
  );
}
