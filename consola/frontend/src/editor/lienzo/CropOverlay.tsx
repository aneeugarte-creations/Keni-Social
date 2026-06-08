// Capa HTML sobre la imagen en MODO RECORTE (crop visual). Muestra la imagen COMPLETA dentro de la
// caja (object-contain), atenúa lo que queda FUERA del recorte y dibuja un rectángulo con 8
// tiradores (4 esquinas + 4 lados) + área central para mover. Arrastrar actualiza `capa.crop` en
// fracciones 0..1 de la FUENTE (= fracciones de la imagen mostrada, que se ve entera). Todo el
// gesto cuenta como UN paso de deshacer (como el reencuadre).

import { type PointerEvent as PointerEventReact, useRef } from "react";

import type { Capa, CapaImagen, Crop } from "../documento";
import { type AsaRecorte, moverAsa } from "../recorte";
import type { StoreEditor } from "../store";
import { useImagen } from "../useImagen";

export function CropOverlay({
  capa,
  escala,
  store,
}: {
  capa: CapaImagen;
  escala: number;
  store: StoreEditor;
}) {
  const img = useImagen(capa.objeto || null);
  const drag = useRef<{ asa: AsaRecorte; crop: Crop; px: number; py: number } | null>(null);
  const gestoActivo = useRef(false);

  const W = capa.w * escala;
  const H = capa.h * escala;
  // La imagen completa se muestra con `contain` dentro de la caja: rect mostrado (letterbox) en px.
  let imgW = W, imgH = H, imgL = 0, imgT = 0;
  if (img && img.width > 0 && img.height > 0) {
    const k = Math.min(W / img.width, H / img.height);
    imgW = img.width * k;
    imgH = img.height * k;
    imgL = (W - imgW) / 2;
    imgT = (H - imgH) / 2;
  }
  const crop: Crop = capa.crop ?? { cx: 0, cy: 0, cw: 1, ch: 1 };
  // Rectángulo de recorte en px DENTRO de la imagen mostrada.
  const rx = imgL + crop.cx * imgW;
  const ry = imgT + crop.cy * imgH;
  const rw = crop.cw * imgW;
  const rh = crop.ch * imgH;

  const comenzar = () => {
    if (!gestoActivo.current) {
      store.getState().comenzarGesto();
      gestoActivo.current = true;
    }
  };
  const actual = () => store.getState().documento.capas.find((c) => c.id === capa.id) as CapaImagen | undefined;

  const onDown = (asa: AsaRecorte) => (e: PointerEventReact) => {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    comenzar();
    const c = actual();
    if (!c) return;
    drag.current = { asa, crop: c.crop ?? { cx: 0, cy: 0, cw: 1, ch: 1 }, px: e.clientX, py: e.clientY };
  };
  const onMove = (e: PointerEventReact) => {
    if (!drag.current || imgW <= 0 || imgH <= 0) return;
    const dfx = (e.clientX - drag.current.px) / imgW;
    const dfy = (e.clientY - drag.current.py) / imgH;
    const next = moverAsa(drag.current.crop, drag.current.asa, dfx, dfy);
    store.getState().actualizar(capa.id, { crop: next } as Partial<Capa>, false);
  };
  const onUp = () => {
    drag.current = null;
    gestoActivo.current = false;
  };

  // Definición de los 8 tiradores: posición (en px relativos a la caja) y cursor.
  const asas: { asa: AsaRecorte; x: number; y: number; cursor: string }[] = [
    { asa: "nw", x: rx, y: ry, cursor: "nwse-resize" },
    { asa: "n", x: rx + rw / 2, y: ry, cursor: "ns-resize" },
    { asa: "ne", x: rx + rw, y: ry, cursor: "nesw-resize" },
    { asa: "e", x: rx + rw, y: ry + rh / 2, cursor: "ew-resize" },
    { asa: "se", x: rx + rw, y: ry + rh, cursor: "nwse-resize" },
    { asa: "s", x: rx + rw / 2, y: ry + rh, cursor: "ns-resize" },
    { asa: "sw", x: rx, y: ry + rh, cursor: "nesw-resize" },
    { asa: "w", x: rx, y: ry + rh / 2, cursor: "ew-resize" },
  ];

  return (
    <div
      onPointerMove={onMove}
      onPointerUp={onUp}
      className="absolute touch-none"
      style={{ left: capa.x * escala, top: capa.y * escala, width: W, height: H }}
    >
      {/* Imagen COMPLETA (sin recortar) de referencia. */}
      {img && (
        <img
          src={img.src}
          alt=""
          draggable={false}
          className="pointer-events-none absolute select-none"
          style={{ left: imgL, top: imgT, width: imgW, height: imgH }}
        />
      )}
      {/* Atenuación del exterior del recorte: 4 bandas translúcidas (arriba/abajo/izq/der). */}
      <div className="pointer-events-none absolute bg-black/55" style={{ left: 0, top: 0, width: W, height: Math.max(0, ry) }} />
      <div className="pointer-events-none absolute bg-black/55" style={{ left: 0, top: ry + rh, width: W, height: Math.max(0, H - (ry + rh)) }} />
      <div className="pointer-events-none absolute bg-black/55" style={{ left: 0, top: ry, width: Math.max(0, rx), height: rh }} />
      <div className="pointer-events-none absolute bg-black/55" style={{ left: rx + rw, top: ry, width: Math.max(0, W - (rx + rw)), height: rh }} />
      {/* Rectángulo de recorte: marco + área de arrastre (mover todo). */}
      <div
        onPointerDown={onDown("mover")}
        className="absolute cursor-move ring-2 ring-primary"
        style={{ left: rx, top: ry, width: rw, height: rh }}
      />
      {/* Tiradores. */}
      {asas.map((a) => (
        <div
          key={a.asa}
          onPointerDown={onDown(a.asa)}
          className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-sm border border-primary bg-background shadow"
          style={{ left: a.x, top: a.y, cursor: a.cursor }}
        />
      ))}
    </div>
  );
}
