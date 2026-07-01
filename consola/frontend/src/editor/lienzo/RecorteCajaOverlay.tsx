// Capa HTML sobre un OBJETO no-imagen (forma, línea, logo) en MODO RECORTE. Como no tiene píxeles
// que recortar (eso es el crop de la imagen), "recortar" aquí ENCOGE el RECUADRO desde un borde: se
// arrastra un tirador y el borde opuesto queda fijo. Fuera del recuadro se OSCURECE (mismo lenguaje
// que el recorte de foto). Todo el gesto cuenta como UN paso de deshacer. Confirmar/cancelar viven
// fuera (banner Hecho/Cancelar + Enter/Esc en el Lienzo), igual que el recorte de imagen.

import { type PointerEvent as PointerEventReact, useEffect, useRef, useState } from "react";

import type { Capa } from "../documento";
import { type AsaRecorte, type CajaRecorte, recortarCajaRotada } from "../recorte";
import type { StoreEditor } from "../store";
import { aspectoRecorteStore } from "./aspectoRecorte";
import { RejillaTercios } from "./RejillaTercios";
import { asasMarco, claseTirador, etiquetaAsa } from "./tiradoresRecorte";

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
  // Registra en el estado compartido que el objeto en recorte es una FORMA (encoge el recuadro): el
  // banner muestra su ayuda y los chips de aspecto acotan el recuadro a la proporción.
  useEffect(() => {
    aspectoRecorteStore.getState().iniciar(false);
    return () => aspectoRecorteStore.getState().limpiar();
  }, []);
  // Rejilla de tercios activa solo DURANTE el gesto (redibuja al empezar/soltar).
  const [gesticulando, setGesticulando] = useState(false);

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
    setGesticulando(true);
  };
  const onMove = (e: PointerEventReact) => {
    const d = drag.current;
    if (!d) return;
    const dx = (e.clientX - d.px) / escala;
    const dy = (e.clientY - d.py) / escala;
    // Recorta a lo largo de los ejes LOCALES del objeto (soporta rotación, p. ej. línea vertical).
    // La relación de aspecto activa (banner) acota el recuadro a esa proporción.
    const aspecto = aspectoRecorteStore.getState().ratio;
    const caja = recortarCajaRotada(d.caja, capa.rotacion || 0, d.asa, dx, dy, undefined, aspecto);
    store.getState().actualizar(capa.id, caja as Partial<Capa>, false);
  };
  const onUp = () => {
    drag.current = null;
    gestoActivo.current = false;
    setGesticulando(false);
  };

  const W = capa.w * escala;
  const H = capa.h * escala;

  return (
    // Contenedor sobre el recuadro; sin eventos (los clics fuera del recuadro siguen llegando al
    // Stage para "clicar fuera = salir"). Solo los tiradores capturan el puntero.
    <div
      role="group"
      aria-label="Recortar objeto"
      className="pointer-events-none absolute"
      style={{
        left: capa.x * escala,
        top: capa.y * escala,
        width: W,
        height: H,
        // Misma rotación y pivote que Konva (esquina sup-izq) para que el overlay calce con el objeto.
        transform: capa.rotacion ? `rotate(${capa.rotacion}deg)` : undefined,
        transformOrigin: "0 0",
      }}
    >
      {/* Oscurecido de TODO lo de fuera del recuadro (sombra gigante) + contorno del recuadro. */}
      <div
        className="absolute inset-0 ring-2 ring-primary"
        style={{ boxShadow: "0 0 0 9999px rgba(0,0,0,0.55)" }}
      />
      {/* Rejilla de tercios durante el gesto (guía de composición). */}
      <RejillaTercios visible={gesticulando} />
      {asasMarco(W, H).map((a) => (
        <div
          key={a.asa}
          role="button"
          aria-label={etiquetaAsa(a.asa)}
          onPointerDown={onDown(a.asa)}
          onPointerMove={onMove}
          onPointerUp={onUp}
          className={claseTirador(a.asa)}
          style={{ left: a.x, top: a.y, cursor: a.cursor }}
        />
      ))}
    </div>
  );
}
