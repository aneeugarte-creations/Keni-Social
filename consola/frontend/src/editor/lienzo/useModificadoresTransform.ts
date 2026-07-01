// Modificadores VIVOS del Transformer mientras se redimensiona/escala/rota (memoria muscular
// universal de Figma/Canva/Illustrator):
//   · SHIFT invierte la proporción respecto a la base del tipo: en imágenes/logos (proporción fija
//     de serie) la LIBERA para estirar; en textos/formas (libre) la BLOQUEA para escalar proporcional.
//     Al ROTAR, Shift restringe el giro a incrementos de 15°.
//   · ALT escala desde el CENTRO (la caja crece/encoge simétrica en vez de anclarse en la esquina
//     opuesta).
//
// El estado del modificador se lee de eventos de teclado del documento (keydown/keyup) y se vuelca
// directamente al nodo Konva (`tr.keepRatio` / `tr.centeredScaling` / `tr.rotationSnaps`), no al
// store: es efímero, no altera el documento ni el historial. Konva consulta estos flags al arrancar
// cada gesto, así que pulsar/soltar el modificador antes o durante el arrastre del tirador surte efecto.

import type Konva from "konva";
import { type RefObject, useEffect } from "react";

// Snaps de rotación: base SUAVE a 0/45/90… (fuera del umbral gira libre) y, con Shift, incrementos
// de 15° con umbral de medio paso para restringir SIEMPRE al múltiplo de 15 más cercano.
const SNAPS_BASE = [0, 45, 90, 135, 180, 225, 270, 315];
const TOLERANCIA_BASE = 5;
const SNAPS_SHIFT = Array.from({ length: 24 }, (_, i) => i * 15);
const TOLERANCIA_SHIFT = 7.5;

export function useModificadoresTransform({
  trRef,
  ratioBase,
  activo,
}: {
  trRef: RefObject<Konva.Transformer | null>;
  // Proporción por defecto del tipo seleccionado (imagen/logo => true, texto/forma => false).
  ratioBase: boolean;
  // El Transformer está adjunto y visible (hay selección y no estamos en un modo de imagen).
  activo: boolean;
}) {
  useEffect(() => {
    const tr = trRef.current;
    if (!tr || !activo) return;

    // Aplica el estado de los modificadores al Transformer. Se ejecuta al montar y en cada
    // pulsación/liberación de Shift/Alt (no solo en su transición: teclas de repetición y
    // combinaciones dejan `keepRatio`/`centeredScaling` siempre sincronizados con el estado real).
    const aplicar = (shift: boolean, alt: boolean) => {
      tr.keepRatio(shift ? !ratioBase : ratioBase);
      tr.centeredScaling(alt);
      tr.rotationSnaps(shift ? SNAPS_SHIFT : SNAPS_BASE);
      tr.rotationSnapTolerance(shift ? TOLERANCIA_SHIFT : TOLERANCIA_BASE);
    };
    aplicar(false, false);

    const onKeyDown = (e: KeyboardEvent) => aplicar(e.shiftKey, e.altKey);
    const onKeyUp = (e: KeyboardEvent) => aplicar(e.shiftKey, e.altKey);
    // La ventana puede perder el foco con una tecla aún pulsada (Alt+Tab): al volver, sin keyup, el
    // modificador quedaría "trabado". Resetear a la base cuando el documento deja de tener foco.
    const onBlur = () => aplicar(false, false);

    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
      // Al desmontar/desactivar deja el Transformer en su base (el próximo montaje parte limpio).
      tr.keepRatio(ratioBase);
      tr.centeredScaling(false);
      tr.rotationSnaps(SNAPS_BASE);
      tr.rotationSnapTolerance(TOLERANCIA_BASE);
    };
  }, [trRef, ratioBase, activo]);
}
