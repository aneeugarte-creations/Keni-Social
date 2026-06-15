// Capa HTML sobre un OBJETO no-imagen (forma, línea, logo) en MODO RECORTE. Como no tiene píxeles
// que recortar (eso es el crop de la imagen), "recortar" aquí ENCOGE el RECUADRO desde un borde: se
// arrastra un tirador y el borde opuesto queda fijo. Fuera del recuadro se OSCURECE (mismo lenguaje
// que el recorte de foto). Todo el gesto cuenta como UN paso de deshacer. Confirmar/cancelar viven
// fuera (banner Hecho/Cancelar + Enter/Esc en el Lienzo), igual que el recorte de imagen.

import { type PointerEvent as PointerEventReact, useRef } from "react";

import type { Capa } from "../documento";
import { type AsaRecorte, type CajaRecorte, recortarCaja } from "../recorte";
import type { StoreEditor } from "../store";

export function RecorteCajaOverlay({
  capa,
  escala,
  store,
}: {
  capa: Capa;
  escala: number;
  store: StoreEditor;
}) {
  const drag = useRef<{ asa: AsaRecorte; caja: CajaRecorte; px: number; py: number } | null>(null);
  const gestoActivo = useRef(false);

  const comenzar = () => {
    if (!gestoActivo.current) {
      store.getState().comenzarGesto();
      gestoActivo.current = true;
    }
  };
  const actual = () => store.getState().documento.capas.find((c) => c.id === capa.id);

  const onDown = (asa: AsaRecorte) => (e: PointerEventReact) => {
    e.stopPropagation();
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* jsdom / navegadores sin pointer capture: el gesto sigue por los listeners del propio asa */
    }
    comenzar();
    const c = actual();
    if (!c) return;
    drag.current = { asa, caja: { x: c.x, y: c.y, w: c.w, h: c.h }, px: e.clientX, py: e.clientY };
  };
  const onMove = (e: PointerEventReact) => {
    const d = drag.current;
    if (!d) return;
    const dx = (e.clientX - d.px) / escala;
    const dy = (e.clientY - d.py) / escala;
    store.getState().actualizar(capa.id, recortarCaja(d.caja, d.asa, dx, dy) as Partial<Capa>, false);
  };
  const onUp = () => {
    drag.current = null;
    gestoActivo.current = false;
  };

  const W = capa.w * escala;
  const H = capa.h * escala;
  // 8 tiradores (4 esquinas + 4 lados) en coords RELATIVAS al recuadro.
  const asas: { asa: AsaRecorte; x: number; y: number; cursor: string }[] = [
    { asa: "nw", x: 0, y: 0, cursor: "nwse-resize" },
    { asa: "n", x: W / 2, y: 0, cursor: "ns-resize" },
    { asa: "ne", x: W, y: 0, cursor: "nesw-resize" },
    { asa: "e", x: W, y: H / 2, cursor: "ew-resize" },
    { asa: "se", x: W, y: H, cursor: "nwse-resize" },
    { asa: "s", x: W / 2, y: H, cursor: "ns-resize" },
    { asa: "sw", x: 0, y: H, cursor: "nesw-resize" },
    { asa: "w", x: 0, y: H / 2, cursor: "ew-resize" },
  ];

  return (
    // Contenedor sobre el recuadro; sin eventos (los clics fuera del recuadro siguen llegando al
    // Stage para "clicar fuera = salir"). Solo los tiradores capturan el puntero.
    <div
      role="group"
      aria-label="Recortar objeto"
      className="pointer-events-none absolute"
      style={{ left: capa.x * escala, top: capa.y * escala, width: W, height: H }}
    >
      {/* Oscurecido de TODO lo de fuera del recuadro (sombra gigante) + contorno del recuadro. */}
      <div
        className="absolute inset-0 ring-2 ring-primary"
        style={{ boxShadow: "0 0 0 9999px rgba(0,0,0,0.45)" }}
      />
      {asas.map((a) => (
        <div
          key={a.asa}
          role="button"
          aria-label={`Recortar borde ${a.asa}`}
          onPointerDown={onDown(a.asa)}
          onPointerMove={onMove}
          onPointerUp={onUp}
          className="pointer-events-auto absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 touch-none rounded-sm border border-primary bg-background shadow"
          style={{ left: a.x, top: a.y, cursor: a.cursor }}
        />
      ))}
    </div>
  );
}
