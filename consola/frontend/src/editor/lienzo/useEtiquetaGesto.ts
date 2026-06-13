// Etiqueta VIVA del gesto del Transformer ("W × H px" al redimensionar, grados al rotar), extraída
// como hook. Owns el ref del overlay HTML y lo mueve por MUTACIÓN DIRECTA del DOM (textContent/
// transform) durante el gesto, sin setState por frame (60 fps). El componente le pasa los refs del
// Transformer/Stage y el documento, y monta el ref en el div del overlay.

import type Konva from "konva";
import type { RefObject } from "react";
import { useRef } from "react";

import { cajaVisual, type Documento } from "../documento";
import { etiquetaGrados, etiquetaTamano } from "./lib";

export function useEtiquetaGesto({
  trRef,
  stageRef,
  documento,
}: {
  trRef: RefObject<Konva.Transformer | null>;
  stageRef: RefObject<Konva.Stage | null>;
  documento: Documento;
}) {
  // Etiqueta VIVA del gesto ("W × H px" al redimensionar, grados al rotar): overlay HTML ligero
  // actualizado por mutación directa del DOM (textContent/transform), sin setState por frame.
  const etiquetaGestoRef = useRef<HTMLDivElement | null>(null);

  // Durante el gesto el Transformer muta scaleX/Y y rotation del nodo (w/h se hornean al soltar
  // en onTransformEnd), así que las dimensiones vivas del DOCUMENTO son tamaño base × escala viva.
  const moverEtiquetaGesto = () => {
    const div = etiquetaGestoRef.current;
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!div || !tr || !stage) return;
    const pos = stage.getPointerPosition();
    const nodos = tr.nodes();
    if (!pos || nodos.length === 0) return;
    let texto: string;
    if (tr.getActiveAnchor() === "rotater") {
      texto = etiquetaGrados(nodos[0].rotation());
    } else if (nodos.length === 1) {
      const capa = documento.capas.find((c) => c.id === nodos[0].id());
      if (!capa) return;
      // Alto VISIBLE como base (banda del overlay, línea del texto sin caja): es lo que abraza el
      // Transformer; con el h del modelo el rótulo decía 1350 mientras la caja medía ~607.
      const hBase = cajaVisual(capa).h;
      texto = etiquetaTamano(Math.abs(capa.w * nodos[0].scaleX()), Math.abs(hBase * nodos[0].scaleY()));
    } else {
      // Multi-selección: caja envolvente del conjunto en coords del documento.
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const n of nodos) {
        const r = n.getClientRect({ relativeTo: stage, skipShadow: true, skipStroke: true });
        x0 = Math.min(x0, r.x);
        y0 = Math.min(y0, r.y);
        x1 = Math.max(x1, r.x + r.width);
        y1 = Math.max(y1, r.y + r.height);
      }
      texto = etiquetaTamano(x1 - x0, y1 - y0);
    }
    // Mutación directa del DOM (sin setState): 60 fps durante el gesto.
    div.textContent = texto;
    div.style.display = "block";
    div.style.transform = `translate(${Math.round(pos.x + 14)}px, ${Math.round(pos.y + 18)}px)`;
  };
  const ocultarEtiquetaGesto = () => {
    const div = etiquetaGestoRef.current;
    if (div) div.style.display = "none";
  };

  return { etiquetaGestoRef, moverEtiquetaGesto, ocultarEtiquetaGesto };
}
