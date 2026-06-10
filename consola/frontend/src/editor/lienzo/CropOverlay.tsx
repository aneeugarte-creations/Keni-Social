// Capa HTML sobre la imagen en MODO RECORTE estilo Canva: el MARCO (la caja de la capa en el
// lienzo) queda FIJO y se ve la imagen ORIGINAL COMPLETA — nítida dentro del marco, ATENUADA
// fuera — posicionada exactamente donde el render la pinta (misma geometría que el lienzo/export).
// Arrastrar la imagen REENCUADRA (mueve cx/cy del crop); la rueda y los tiradores de esquina
// ESCALAN la imagen dentro del marco (cambian cw/ch alrededor de un ancla). El crop sigue siendo
// {cx,cy,cw,ch} normalizado sobre la fuente: NUNCA destruye píxeles. Todo gesto cuenta como UN
// paso de deshacer (como el reencuadre). Confirmar/cancelar viven fuera (banner Hecho/Cancelar +
// Enter/Esc en el Lienzo).

import {
  type PointerEvent as PointerEventReact,
  type WheelEvent as WheelEventReact,
  useReducer,
  useRef,
} from "react";

import type { Capa, CapaImagen, Crop } from "../documento";
import { fotoMuestra } from "../muestra";
import { escalarCrop, moverAsa, vistaRecorte } from "../recorte";
import type { StoreEditor } from "../store";
import { useImagen } from "../useImagen";

const SIN_CROP: Crop = { cx: 0, cy: 0, cw: 1, ch: 1 };

type Esquina = "nw" | "ne" | "se" | "sw";

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
  const contRef = useRef<HTMLDivElement | null>(null);
  const gestoActivo = useRef(false);
  const finZoom = useRef<number | undefined>(undefined);
  // Gesto en curso: MOVER la imagen (pan del crop) o ESCALAR desde una esquina. Se parte del crop
  // del inicio del gesto (los deltas no se acumulan sobre estados intermedios).
  const drag = useRef<
    | { modo: "mover"; crop: Crop; px: number; py: number; fw: number; fh: number }
    | { modo: "esquina"; crop: Crop; ax: number; ay: number; ancX: number; ancY: number; px: number; py: number }
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

  const onDownMover = (e: PointerEventReact) => {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    comenzar();
    const c = actual();
    if (!c || !v || fW <= 0 || fH <= 0) return;
    drag.current = { modo: "mover", crop: c.crop ?? SIN_CROP, px: e.clientX, py: e.clientY, fw: fW, fh: fH };
  };

  const onDownEsquina = (esq: Esquina) => (e: PointerEventReact) => {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    comenzar();
    const c = actual();
    const cont = contRef.current;
    if (!c || !v || !cont || fW <= 0 || fH <= 0) return;
    // Ancla = la esquina OPUESTA de la imagen (fracciones 0/1 de la fuente), como Canva.
    const ax = esq === "ne" || esq === "se" ? 0 : 1;
    const ay = esq === "se" || esq === "sw" ? 0 : 1;
    const rect = cont.getBoundingClientRect();
    drag.current = {
      modo: "esquina",
      crop: c.crop ?? SIN_CROP,
      ax,
      ay,
      ancX: rect.left + fL + ax * fW,
      ancY: rect.top + fT + ay * fH,
      px: e.clientX,
      py: e.clientY,
    };
  };

  const onMove = (e: PointerEventReact) => {
    const d = drag.current;
    if (!d) return;
    if (d.modo === "mover") {
      // Arrastre de la imagen: mover el contenido a la derecha = mover el crop a la IZQUIERDA en la
      // fuente. El delta en fracciones es directo: la imagen completa mide fw×fh px de pantalla.
      const dfx = -(e.clientX - d.px) / d.fw;
      const dfy = -(e.clientY - d.py) / d.fh;
      store.getState().actualizar(capa.id, { crop: moverAsa(d.crop, "mover", dfx, dfy) } as Partial<Capa>, false);
      return;
    }
    // Esquina: factor proporcional = cuánto se aleja el puntero del ancla respecto al inicio.
    const rx = d.px - d.ancX !== 0 ? (e.clientX - d.ancX) / (d.px - d.ancX) : 1;
    const ry = d.py - d.ancY !== 0 ? (e.clientY - d.ancY) / (d.py - d.ancY) : 1;
    const f = Math.max(0.05, rx, ry);
    store.getState().actualizar(capa.id, { crop: escalarCrop(d.crop, f, d.ax, d.ay) } as Partial<Capa>, false);
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

  // Tiradores de ESQUINA sobre la imagen completa (escala proporcional, ancla en la opuesta).
  const esquinas: { esq: Esquina; x: number; y: number; cursor: string; etiqueta: string }[] = v
    ? [
        { esq: "nw", x: fL, y: fT, cursor: "nwse-resize", etiqueta: "Escalar la imagen desde la esquina superior izquierda" },
        { esq: "ne", x: fL + fW, y: fT, cursor: "nesw-resize", etiqueta: "Escalar la imagen desde la esquina superior derecha" },
        { esq: "se", x: fL + fW, y: fT + fH, cursor: "nwse-resize", etiqueta: "Escalar la imagen desde la esquina inferior derecha" },
        { esq: "sw", x: fL, y: fT + fH, cursor: "nesw-resize", etiqueta: "Escalar la imagen desde la esquina inferior izquierda" },
      ]
    : [];

  return (
    <div
      ref={contRef}
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
            onPointerDown={onDownMover}
            className="absolute cursor-move"
            style={{ left: fL, top: fT, width: fW, height: fH }}
          />
          {/* Tiradores de esquina (círculo estilo Canva): escalan la imagen dentro del marco. */}
          {esquinas.map((a) => (
            <div
              key={a.esq}
              role="button"
              aria-label={a.etiqueta}
              onPointerDown={onDownEsquina(a.esq)}
              className="absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary bg-background shadow"
              style={{ left: a.x, top: a.y, cursor: a.cursor }}
            />
          ))}
        </>
      )}
      {/* MARCO del recorte: la caja de la capa, fija en el lienzo. */}
      <div className="pointer-events-none absolute inset-0 ring-2 ring-primary" />
    </div>
  );
}
