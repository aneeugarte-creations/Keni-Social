/**
 * Historial de DESHACER/REHACER para el documento de vídeo.
 *
 * Mantiene dos pilas (pasado y futuro) con snapshots del `doc`. La pila de pasado se
 * rellena con `registrar(doc)` antes de cada mutación real; `deshacer`/`rehacer` devuelven
 * el snapshot correspondiente. El límite evita que composiciones largas consuman demasiada
 * memoria.
 */
import * as React from "react";

import type { ComposicionVideo } from "@/lib/video";

const LIMITE = 50;

export interface HistorialDoc {
  /** Guarda el doc actual en la pila de pasado (llámalo ANTES de mutar). */
  registrar: (doc: ComposicionVideo) => void;
  /** Deshace: devuelve el snapshot anterior y lo aplica internamente. `null` si no hay nada. */
  deshacer: () => ComposicionVideo | null;
  /** Rehace: devuelve el snapshot siguiente. `null` si no hay nada. */
  rehacer: () => ComposicionVideo | null;
  /** Hay al menos un paso de deshacer disponible. */
  puedeDeshacer: boolean;
  /** Hay al menos un paso de rehacer disponible. */
  puedeRehacer: boolean;
}

export function useHistorialDoc(docActual: ComposicionVideo): HistorialDoc {
  // Cada entrada de pasado es un snapshot que se restaura al deshacer.
  const pasado = React.useRef<ComposicionVideo[]>([]);
  // Al deshacer se empuja el doc activo al futuro; rehacer lo saca.
  const futuro = React.useRef<ComposicionVideo[]>([]);

  // Exponer puedeDeshacer/puedeRehacer como estado reactivo para que el componente re-renderice.
  const [puedeDeshacer, setPuedeDeshacer] = React.useState(false);
  const [puedeRehacer, setPuedeRehacer] = React.useState(false);

  const sincronizarFlags = React.useCallback(() => {
    setPuedeDeshacer(pasado.current.length > 0);
    setPuedeRehacer(futuro.current.length > 0);
  }, []);

  const registrar = React.useCallback(
    (doc: ComposicionVideo) => {
      pasado.current = [...pasado.current, doc].slice(-LIMITE);
      // Una nueva edición descarta el futuro (no hay rehacer tras una acción nueva).
      futuro.current = [];
      sincronizarFlags();
    },
    [sincronizarFlags],
  );

  const deshacer = React.useCallback((): ComposicionVideo | null => {
    if (pasado.current.length === 0) return null;
    const anterior = pasado.current[pasado.current.length - 1];
    pasado.current = pasado.current.slice(0, -1);
    // El doc vigente (antes de deshacer) va al futuro.
    futuro.current = [docActual, ...futuro.current];
    sincronizarFlags();
    return anterior;
  }, [docActual, sincronizarFlags]);

  const rehacer = React.useCallback((): ComposicionVideo | null => {
    if (futuro.current.length === 0) return null;
    const siguiente = futuro.current[0];
    futuro.current = futuro.current.slice(1);
    // El doc vigente (antes de rehacer) vuelve al pasado.
    pasado.current = [...pasado.current, docActual].slice(-LIMITE);
    sincronizarFlags();
    return siguiente;
  }, [docActual, sincronizarFlags]);

  return { registrar, deshacer, rehacer, puedeDeshacer, puedeRehacer };
}
