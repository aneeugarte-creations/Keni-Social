// Atajos de teclado del Lienzo, extraídos como hook. Mantiene EXACTAMENTE el comportamiento previo:
// mismo handler `keydown` sobre `window`, mismas dependencias del efecto y mismo orden de ramas.
// Ignora si el foco está en un campo editable o un <select>.

import type { Dispatch, SetStateAction } from "react";
import { useEffect } from "react";

import type { Capa } from "../documento";
import { aplicarEstilo } from "../estilo";
import { copiarEstiloPortapapeles, estiloPortapapeles } from "../estilos-guardados";
import type { StoreEditor } from "../store";
import { ZOOM_MAX, ZOOM_MIN, portapapeles } from "./lib";

export function useAtajosTeclado({
  store,
  setZoom,
  reencuadreId,
  onSalirReencuadre,
  recorteId,
  onSalirRecorte,
}: {
  store: StoreEditor;
  setZoom: Dispatch<SetStateAction<number>>;
  reencuadreId: string | null;
  onSalirReencuadre?: () => void;
  recorteId: string | null;
  onSalirRecorte?: () => void;
}) {
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
      // Zoom: ⌘0 ajusta a pantalla (escala = baseFit => zoom 1), ⌘+ acerca, ⌘− aleja.
      if (meta && e.key === "0") { e.preventDefault(); return setZoom(1); }
      if (meta && (e.key === "+" || e.key === "=")) {
        e.preventDefault();
        return setZoom((z) => Math.min(ZOOM_MAX, z * 1.1));
      }
      if (meta && (e.key === "-" || e.key === "_")) {
        e.preventDefault();
        return setZoom((z) => Math.max(ZOOM_MIN, z * 0.9));
      }
      if (e.key === "Escape") {
        if (recorteId) return onSalirRecorte?.();
        if (reencuadreId) return onSalirReencuadre?.();
        return st.seleccionar(null);
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
        const t0 = Date.now().toString(36);
        const copias = portapapeles.capas.map((c, i) => ({
          ...structuredClone(c),
          id: `${c.tipo}-${t0}-${i}-${Math.floor(performance.now())}`,
          x: c.x + 24,
          y: c.y + 24,
          z: ++z,
        })) as Capa[];
        for (const copia of copias) st.agregar(copia);
        st.seleccionarMuchas(copias.map((c) => c.id));
        return;
      }
      if (meta && (e.key === "d" || e.key === "D")) { e.preventDefault(); return st.duplicarMulti(); }
      if (meta && e.key === "]") { e.preventDefault(); return st.traerAlFrente(sel); }
      if (meta && e.key === "[") { e.preventDefault(); return st.enviarAlFondo(sel); }
      if (capa && e.key.startsWith("Arrow")) {
        e.preventDefault();
        const d = e.shiftKey ? 10 : 1;
        const dx = e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0;
        const dy = e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0;
        const ids = st.seleccionMulti.length > 1 ? st.seleccionMulti : [sel];
        st.aplicarPosiciones(
          ids
            .map((id) => st.documento.capas.find((c) => c.id === id))
            .filter((c): c is Capa => !!c)
            .map((c) => ({ id: c.id, x: c.x + dx, y: c.y + dy })),
        );
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [store, setZoom, reencuadreId, onSalirReencuadre, recorteId, onSalirRecorte]);
}
