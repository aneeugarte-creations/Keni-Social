// Capa HTML sobre la imagen en MODO RECORTE: se ve la imagen ORIGINAL COMPLETA —nítida dentro del
// marco, ATENUADA fuera— y los 8 tiradores van SOBRE EL MARCO. Arrastrar un tirador ENCOGE/AGRANDA
// el MARCO (la caja) y COMPENSA el crop para que los píxeles no se muevan ni cambien de escala: CORTA
// la foto (la franja fuera del marco queda atenuada por el velo), no la amplía. Arrastrar la IMAGEN
// la reencuadra (mueve cx/cy del crop) y la rueda hace ZOOM al centro. El crop sigue siendo
// {cx,cy,cw,ch} normalizado sobre la fuente: NUNCA destruye píxeles. Todo gesto cuenta como UN paso
// de deshacer. Confirmar/cancelar viven fuera (banner Hecho/Cancelar + Enter/Esc).

import {
  type PointerEvent as PointerEventReact,
  type WheelEvent as WheelEventReact,
  useEffect,
  useReducer,
  useRef,
  useState,
} from "react";

import type { Capa, CapaImagen, Crop } from "../documento";
import { fotoMuestra } from "../muestra";
import { type AsaRecorte, type GestoLateral, cajaConAspecto, encajarRecorte, escalarCrop, moverAsa, recorteMarco, vistaRecorte } from "../recorte";
import type { StoreEditor } from "../store";
import { useImagen } from "../useImagen";
import { aspectoRecorteStore } from "./aspectoRecorte";
import { RejillaTercios } from "./RejillaTercios";
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
  // Gesto en curso: PAN de la imagen (mueve cx/cy del crop) o MARCO (acerca/aleja la foto dentro del
  // marco FIJO). Se parte de la instantánea del inicio del gesto (los deltas no se acumulan sobre
  // estados intermedios).
  const drag = useRef<
    | { modo: "pan"; crop: Crop; px: number; py: number; fw: number; fh: number }
    | { modo: "marco"; asa: AsaRecorte; g: GestoLateral; x0: number; y0: number; px: number; py: number }
    | null
  >(null);
  // Rejilla de tercios activa solo DURANTE el gesto (arrastre de marco o de imagen).
  const [gesticulando, setGesticulando] = useState(false);

  // Registra que el objeto en recorte es una FOTO (reencuadra el crop). Al elegir un aspecto en el
  // banner, RE-ENCUADRA el MARCO a esa proporción (inscrito y centrado sobre la caja actual) para
  // que la relación fija se vea; el resto de gestos parte de ahí. "Original" = proporción de la
  // fuente. Suscripción al store de módulo (un solo recorte activo a la vez).
  useEffect(() => {
    const st = aspectoRecorteStore.getState();
    st.iniciar(true);
    const aplicar = (ratio: number | null, original: boolean) => {
      const c = store.getState().documento.capas.find((x) => x.id === capa.id) as CapaImagen | undefined;
      if (!c) return;
      let r = ratio;
      if (original && img && img.width > 0 && img.height > 0) r = img.width / img.height;
      if (!r || !(r > 0)) return;
      const nueva = cajaConAspecto(c.w, c.h, r);
      if (Math.abs(nueva.w - c.w) < 0.5 && Math.abs(nueva.h - c.h) < 0.5) return;
      // Re-encuadra el marco a la proporción RECORTANDO (compensa el crop para no mover ni ampliar
      // los píxeles), igual que arrastrar un tirador. Sin bitmap cae a solo re-encuadrar la caja.
      if (img && img.width > 0 && img.height > 0) {
        const g: GestoLateral = {
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
          caja: { x: 0, y: 0, w: c.w, h: c.h },
        };
        const res = encajarRecorte(g, nueva.x, nueva.y, nueva.w, nueva.h);
        if (res) {
          store.getState().actualizar(
            capa.id,
            { x: c.x + res.x, y: c.y + res.y, w: res.w, h: res.h, crop: res.crop, zoom: res.zoom, foco: res.foco } as Partial<Capa>,
          );
          return;
        }
      }
      store.getState().actualizar(
        capa.id,
        { x: c.x + nueva.x, y: c.y + nueva.y, w: nueva.w, h: nueva.h } as Partial<Capa>,
      );
    };
    const desuscribir = aspectoRecorteStore.subscribe((s, prev) => {
      if (s.clave !== prev.clave && (s.ratio !== null || s.clave === "original")) {
        aplicar(s.ratio, s.clave === "original");
      }
    });
    return () => {
      desuscribir();
      st.limpiar();
    };
    // El re-encuadre lee la capa fresca del store; solo re-suscribimos si cambia la identidad/fuente.
  }, [capa.id, img, store]);

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
    setGesticulando(true);
  };

  // Arrastrar un tirador del MARCO: ENCOGE/AGRANDA la caja moviendo ese borde (o los dos de una
  // esquina) y COMPENSA el crop → corta la foto sin ampliarla; la franja fuera del marco se atenúa.
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
    const g: GestoLateral = {
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
      caja: { x: 0, y: 0, w: c.w, h: c.h },
    };
    drag.current = { modo: "marco", asa, g, x0: c.x, y0: c.y, px: e.clientX, py: e.clientY };
    setGesticulando(true);
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
    const r = recorteMarco(d.g, d.asa, dx, dy);
    if (!r) return;
    store.getState().actualizar(
      capa.id,
      { x: d.x0 + r.x, y: d.y0 + r.y, w: r.w, h: r.h, crop: r.crop, zoom: r.zoom, foco: r.foco } as Partial<Capa>,
      false,
    );
  };

  const onUp = () => {
    drag.current = null;
    gestoActivo.current = false;
    setGesticulando(false);
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
          {/* Imagen ORIGINAL completa: se ve también FUERA del marco (estilo Canva) a opacidad plena;
              el VELO oscuro de abajo la atenúa fuera del marco (mismo lenguaje que el recorte de forma). */}
          <img
            src={img.src}
            alt=""
            draggable={false}
            className="pointer-events-none absolute max-w-none select-none"
            style={{ left: fL, top: fT, width: fW, height: fH }}
          />
          {/* VELO de "fuera de recorte": oscurece TODO menos el marco (agujero vía sombra gigante),
              igual que el recorte de forma. Unifica el lenguaje: dentro nítido, fuera atenuado. */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{ boxShadow: "0 0 0 9999px rgba(0,0,0,0.55)" }}
          />
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
          {/* Rejilla de tercios durante el gesto (guía de composición), ceñida al marco. */}
          <RejillaTercios visible={gesticulando} />
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
