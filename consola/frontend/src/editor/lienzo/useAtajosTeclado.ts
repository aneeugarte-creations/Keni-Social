// Atajos de teclado del Lienzo, extraídos como hook. Ignora si el foco está en un campo editable o un <select>.

import type { RefObject } from "react";
import { useEffect, useRef } from "react";

import type { Capa } from "../documento";
import { altoVisual, nuevoId, zTope } from "../documento";
import { crearElemento, type ElementoRapido } from "../elementos";
import { aplicarEstilo } from "../estilo";
import { copiarEstiloPortapapeles, estiloPortapapeles } from "../estilos-guardados";
import type { StoreEditor } from "../store";
import { portapapeles } from "./lib";

// Acciones de zoom que aporta el Lienzo (ya ancladas al centro del viewport y acotadas a los
// límites de escala). Van en un ref para que el efecto no se re-registre en cada render.
export type ZoomApi = {
  acercar: () => void;
  alejar: () => void;
  ajustar: () => void;
  real: () => void;
};

// Servicios del Lienzo para los atajos de CREACIÓN (T/R/C/L). En un ref por la misma razón que
// `ZoomApi`: el efecto no se re-registra, pero siempre ejecuta los handlers frescos.
export type LienzoApi = {
  // Centro del VIEWPORT visible, en coords del documento: los elementos nuevos nacen ahí.
  centroViewport: () => { x: number; y: number };
  // Abre la edición de texto EN LÍNEA sobre la capa (los textos nuevos entran directos a escribir).
  editarTexto: (id: string) => void;
};

// Tecla → elemento de creación rápida (estilo Canva): T texto, R rectángulo, C círculo, L línea.
const ELEMENTO_POR_TECLA: Record<string, ElementoRapido> = {
  t: "texto",
  r: "rect",
  c: "elipse",
  l: "linea",
};

export function useAtajosTeclado({
  store,
  zoom,
  lienzo,
  reencuadreId,
  onSalirReencuadre,
  recorteId,
  onCancelarRecorte,
  onConfirmarRecorte,
}: {
  store: StoreEditor;
  zoom: RefObject<ZoomApi>;
  lienzo?: RefObject<LienzoApi>;
  reencuadreId: string | null;
  onSalirReencuadre?: () => void;
  recorteId: string | null;
  // Modo recorte estilo Canva: Esc CANCELA (restaura el crop de entrada) y Enter CONFIRMA (Hecho).
  onCancelarRecorte?: () => void;
  onConfirmarRecorte?: () => void;
}) {
  const ultimoNudgeRef = useRef<number>(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      // No dispares atajos si el foco está en un campo editable o un <select> (con un select
      // enfocado, las flechas cambian la opción y Backspace no debe borrar la capa).
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable || t.closest("[contenteditable]"))) return;
      const st = store.getState();
      const sel = st.seleccion;
      const meta = e.metaKey || e.ctrlKey;
      if (meta && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        if (e.shiftKey) st.rehacer();
        else st.deshacer();
        return;
      }
      // Zoom: ⌘0 ajusta a pantalla (también ⌥⌘0, el alias estándar de Canva; con Alt pulsado
      // e.key puede no ser "0", por eso ahí se mira e.code), ⌘+ acerca, ⌘− aleja, ⇧0 = 100 %
      // (1 px del documento : 1 px de pantalla). ⇧0 usa e.code para ser independiente de la
      // distribución del teclado.
      if (meta && (e.key === "0" || (e.altKey && e.code === "Digit0"))) {
        e.preventDefault();
        return zoom.current?.ajustar();
      }
      if (meta && (e.key === "+" || e.key === "=")) {
        e.preventDefault();
        return zoom.current?.acercar();
      }
      if (meta && (e.key === "-" || e.key === "_")) {
        e.preventDefault();
        return zoom.current?.alejar();
      }
      if (!meta && !e.altKey && e.shiftKey && e.code === "Digit0") {
        e.preventDefault();
        return zoom.current?.real();
      }
      // Enter CONFIRMA el modo recorte (= botón "Hecho" del banner), estilo Canva.
      if (recorteId && e.key === "Enter") {
        e.preventDefault();
        return onConfirmarRecorte?.();
      }
      if (e.key === "Escape") {
        // CASCADA estilo Canva: cancelar el recorte (restaura el crop de entrada) → cerrar el
        // reencuadre → deseleccionar → (si no hay nada que hacer aquí) dejar pasar para que el
        // editor cierre paneles/overlays.
        if (recorteId) return onCancelarRecorte?.();
        if (reencuadreId) return onSalirReencuadre?.();
        if (st.seleccion || st.seleccionMulti.length > 0) return st.seleccionar(null);
        return;
      }
      // Copiar/pegar ESTILO (⌘⌥C / ⌘⌥V): subconjunto de estilo de la capa, no la capa entera.
      // Va ANTES de ⌘C/⌘V (que copian capas) porque añade Alt.
      if (meta && e.altKey && (e.key === "c" || e.key === "C" || e.code === "KeyC")) {
        e.preventDefault();
        const capa = st.documento.capas.find((c) => c.id === st.seleccion);
        if (capa) copiarEstiloPortapapeles(capa);
        return;
      }
      if (meta && e.altKey && (e.key === "v" || e.key === "V" || e.code === "KeyV")) {
        e.preventDefault();
        const estilo = estiloPortapapeles();
        if (!estilo) return;
        const ids = st.seleccionMulti.length ? st.seleccionMulti : st.seleccion ? [st.seleccion] : [];
        const objetivos = st.documento.capas.filter((c) => ids.includes(c.id));
        if (!objetivos.length) return;
        st.comenzarGesto();
        for (const c of objetivos) {
          const cambios = aplicarEstilo(c, estilo);
          if (Object.keys(cambios).length) st.actualizar(c.id, cambios, false);
        }
        return;
      }
      if (meta && (e.key === "a" || e.key === "A")) {
        e.preventDefault();
        return st.seleccionarMuchas(st.documento.capas.map((c) => c.id));
      }
      if (meta && (e.key === "g" || e.key === "G")) {
        e.preventDefault();
        if (e.shiftKey) {
          const c = st.documento.capas.find((x) => x.id === st.seleccion);
          if (c?.tipo === "grupo") st.desagrupar(c.id);
        } else {
          st.agrupar();
        }
        return;
      }
      // «Ordenar» (tidy up, ⌥⇧T): 3+ capas seleccionadas → espaciado uniforme en su eje dominante.
      // Con Alt pulsado e.key cambia en macOS ("ˇ" y similares), por eso se mira e.code.
      if (!meta && e.altKey && e.shiftKey && e.code === "KeyT") {
        e.preventDefault();
        // Mismo requisito que el botón de la barra: 3+ capas seleccionadas. `ordenarMulti` ya es
        // no-op interno con menos, pero el guard explícito deja el contrato a la vista en el atajo.
        if (st.seleccionMulti.length < 3) return;
        return st.ordenarMulti();
      }
      // CREACIÓN estilo Canva (T/R/C/L, sin modificadores y fuera de los modos de imagen): inserta
      // el MISMO elemento que el botón del panel «Elementos» (fábricas compartidas en
      // `elementos.ts`), centrado en el viewport actual, y lo deja seleccionado. El texto entra
      // directo en edición en línea (tras el commit de React, cuando su nodo ya existe en el Stage).
      if (!meta && !e.altKey && !e.shiftKey && !recorteId && !reencuadreId) {
        const tipo = ELEMENTO_POR_TECLA[e.key.toLowerCase()];
        if (tipo) {
          e.preventDefault();
          const capa = crearElemento(tipo);
          const centro = lienzo?.current?.centroViewport() ?? {
            x: st.documento.formato.w / 2,
            y: st.documento.formato.h / 2,
          };
          st.agregar({
            ...capa,
            x: Math.round(centro.x - capa.w / 2),
            y: Math.round(centro.y - altoVisual(capa) / 2),
            z: zTope(st.documento),
          } as Capa);
          st.seleccionar(capa.id);
          if (capa.tipo === "texto") requestAnimationFrame(() => lienzo?.current?.editarTexto(capa.id));
          return;
        }
      }
      if (!sel) return;
      const capa = st.documento.capas.find((c) => c.id === sel);
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); return st.quitarMulti(); }
      if (meta && (e.key === "c" || e.key === "C")) {
        // Copia TODA la selección múltiple (alineado con ⌘D duplicarMulti), no solo la primaria.
        const ids = st.seleccionMulti.length ? st.seleccionMulti : sel ? [sel] : [];
        const capas = st.documento.capas.filter((c) => ids.includes(c.id));
        if (capas.length) portapapeles.capas = capas.map((c) => structuredClone(c));
        return;
      }
      if (meta && (e.key === "v" || e.key === "V")) {
        if (!portapapeles.capas.length) return;
        e.preventDefault();
        let z = Math.max(0, ...st.documento.capas.map((c) => c.z));
        const copias = portapapeles.capas.map((c) => ({
          ...structuredClone(c),
          id: nuevoId(c.tipo),
          x: c.x + 24,
          y: c.y + 24,
          z: ++z,
        })) as Capa[];
        for (const copia of copias) st.agregar(copia);
        st.seleccionarMuchas(copias.map((c) => c.id));
        return;
      }
      if (meta && (e.key === "d" || e.key === "D")) { e.preventDefault(); return st.duplicarMulti(); }
      // Orden Z estilo Canva/Figma: ⌘] / ⌘[ mueven UN paso (adelante/atrás); con ⇧ saltan al
      // frente/fondo absolutos.
      if (meta && e.key === "]") {
        e.preventDefault();
        return e.shiftKey ? st.traerAlFrente(sel) : st.reordenar(sel, 1);
      }
      if (meta && e.key === "[") {
        e.preventDefault();
        return e.shiftKey ? st.enviarAlFondo(sel) : st.reordenar(sel, -1);
      }
      if (capa && e.key.startsWith("Arrow")) {
        e.preventDefault();
        const ahora = Date.now();
        // Coalesce por ráfaga: si han pasado >500ms desde el último nudge, comienza un gesto nuevo.
        if (ahora - ultimoNudgeRef.current > 500) {
          st.comenzarGesto();
        }
        ultimoNudgeRef.current = ahora;
        const d = e.shiftKey ? 10 : 1;
        const dx = e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0;
        const dy = e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0;
        const ids = st.seleccionMulti.length > 1 ? st.seleccionMulti : [sel];
        st.aplicarPosiciones(
          ids
            .map((id) => st.documento.capas.find((c) => c.id === id))
            .filter((c): c is Capa => !!c)
            .map((c) => ({ id: c.id, x: c.x + dx, y: c.y + dy })),
          false, // No registrar en historial: la ráfaga se trata como un gesto
        );
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [store, zoom, lienzo, reencuadreId, onSalirReencuadre, recorteId, onCancelarRecorte, onConfirmarRecorte]);
}
