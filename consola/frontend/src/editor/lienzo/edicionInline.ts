// Edición de texto EN LÍNEA sobre el lienzo (doble clic, patrón Canva): la lógica PURA vive aquí,
// separada del Lienzo, para poder testearla sin montar Konva.
//
// Dos decisiones:
//  · QUÉ texto se edita: el que se VE. Con binding y «Copy de muestra» activo el lienzo pinta el
//    copy de muestra (muestra.ts), así que la edición escribe AHÍ (antes escribía `capa.texto` y
//    el cambio no se reflejaba en el lienzo: la edición parecía rota). Sin muestra se edita
//    `capa.texto`, como siempre.
//  · QUÉ aspecto tiene el editor: los MISMOS estilos que el texto pintado (familia/peso/cursiva,
//    tamaño·escala, color, alineación, interlineado, interletra·escala, mayúsculas, valign y
//    rotación), para escribir "sobre la imagen" y no en una caja genérica. El contorno, la sombra
//    y el degradado del relleno no se replican (texto plano del color base mientras se edita); el
//    auto-encogido tampoco: divergencias asumidas solo durante la edición.

import type { CSSProperties } from "react";

import { tieneCursiva } from "../../lib/placa/dibujar.mjs";
import { familiaReal } from "../capas/tipografia";
import type { Alineacion, CapaTexto } from "../documento";
import { copyMuestra } from "../muestra";

/** Dónde guarda la edición: el texto de la capa, o el copy de muestra (titular / pleca). */
export type DestinoEdicion = "texto" | "muestra-titular" | "muestra-etiqueta";

export function destinoEdicion(c: CapaTexto, muestraCopy: boolean): DestinoEdicion {
  if (muestraCopy && c.binding === "copy_in") return "muestra-titular";
  if (muestraCopy && c.binding === "etiqueta_default") return "muestra-etiqueta";
  return "texto";
}

/** Texto con el que arranca la edición: exactamente el que el lienzo está pintando. */
export function textoInicial(c: CapaTexto, muestraCopy: boolean): string {
  if (destinoEdicion(c, muestraCopy) !== "texto") return copyMuestra(c.binding) ?? "";
  return c.texto;
}

const ALINEACION_CSS: Record<Alineacion, CSSProperties["textAlign"]> = {
  izquierda: "left",
  centro: "center",
  derecha: "right",
  justificado: "justify",
};

/**
 * Estilo del CONTENEDOR del editor inline, en px de TABLERO (posición/caja/valign/rotación de la
 * capa, escaladas). Es un flex columna: con caja (h>0) respeta el `valign` del documento mientras
 * se edita; sin caja el alto lo pone el propio texto. La rotación pivota en la esquina superior
 * izquierda, igual que Konva y el export.
 */
export function estiloCajaEdicion(c: CapaTexto, escala: number): CSSProperties {
  const enCaja = c.h > 0;
  return {
    position: "absolute",
    left: c.x * escala,
    top: c.y * escala,
    width: Math.max(40, c.w * escala),
    height: enCaja ? c.h * escala : undefined,
    display: "flex",
    flexDirection: "column",
    justifyContent: enCaja
      ? c.valign === "abajo"
        ? "flex-end"
        : c.valign === "centro"
          ? "center"
          : "flex-start"
      : "flex-start",
    transform: c.rotacion ? `rotate(${c.rotacion}deg)` : undefined,
    transformOrigin: "top left",
  };
}

/**
 * Estilo del TEXTO editable: espejo CSS de lo que pinta Konva (`estiloFuente`/`textoMuestra`),
 * a la escala actual del tablero. La cursiva solo si la familia real la tiene registrada (misma
 * regla que el render y el export: nada de oblicuas sintéticas).
 */
export function estiloTextoEdicion(c: CapaTexto, escala: number): CSSProperties {
  const cursiva = !!c.cursiva && tieneCursiva(familiaReal(c.familia));
  return {
    fontFamily: `"${familiaReal(c.familia)}", sans-serif`,
    fontWeight: c.peso || 700,
    fontStyle: cursiva ? "italic" : "normal",
    fontSize: c.tamano * escala,
    lineHeight: String(c.interlineado),
    letterSpacing: c.interletra ? `${c.interletra * escala}px` : undefined,
    color: c.color,
    caretColor: c.color,
    textAlign: ALINEACION_CSS[c.alineacion] ?? "left",
    textTransform: c.mayusculas ? "uppercase" : undefined,
  };
}
