// ENCUADRE — controles independientes del lienzo (preferencias persistidas en localStorage),
// extraídos como hook. Owns el estado de los toggles y su persistencia; el componente solo lee.
//   · imán: ajuste magnético a objetos + bordes/centro del lienzo + márgenes. Por defecto ON.
//     Apagado => sin snap a objetos/márgenes.
//   · grid: rejilla visual + snap a línea de rejilla POR UMBRAL (no redondeo duro; entre líneas
//     el movimiento es libre). El imán tiene PRIORIDAD sobre la rejilla.
//   · tamCelda: tamaño de celda de la rejilla en px del documento (fina/media/gruesa).
//   · dentroMarco: al mover/transformar, acota la caja para que no se salga del lienzo.
//   · zonas: overlay de ZONAS SEGURAS del formato (patrón Canva/IG): vela las franjas donde la
//     UI de la plataforma tapa el diseño. Solo visual (Layer sin listening); el export renderiza
//     en el servidor desde el documento (render_node/dibujar.mjs), así que nunca sale al archivo.

import { useEffect, useState } from "react";

import { guardarPref, prefBool, prefNum } from "./lib";

export function useEncuadre() {
  const [iman, setIman] = useState(() => prefBool("keni.encuadre.iman", true));
  const [grid, setGrid] = useState(() => prefBool("keni.encuadre.grid", false));
  const [tamCelda, setTamCelda] = useState(() => prefNum("keni.encuadre.celda", 16));
  const [dentroMarco, setDentroMarco] = useState(() => prefBool("keni.encuadre.dentro", false));
  const [zonas, setZonas] = useState(() => prefBool("keni.encuadre.zonas", false));
  useEffect(() => guardarPref("keni.encuadre.iman", iman), [iman]);
  useEffect(() => guardarPref("keni.encuadre.grid", grid), [grid]);
  useEffect(() => guardarPref("keni.encuadre.celda", tamCelda), [tamCelda]);
  useEffect(() => guardarPref("keni.encuadre.dentro", dentroMarco), [dentroMarco]);
  useEffect(() => guardarPref("keni.encuadre.zonas", zonas), [zonas]);
  // Paso de la rejilla: tamaño de celda configurable (mín. 4px), no w/12.
  const paso = Math.max(4, Math.round(tamCelda));

  return {
    iman,
    setIman,
    grid,
    setGrid,
    tamCelda,
    setTamCelda,
    dentroMarco,
    setDentroMarco,
    zonas,
    setZonas,
    paso,
  };
}
