/**
 * Recorte plegable de filas para las tablas de Métricas: muestra las primeras N y
 * permite desplegar el resto con "Mostrar más". Espejo de `useOrdenTabla` (lógica en un
 * hook, UI en un componente — ver `PieMostrarMas`): se alimenta del array YA ORDENADO,
 * así las filas visibles son siempre el "top N" del orden activo.
 *
 * No recorta si solo sobran `margen` filas o menos (un control para esconder 1-2 filas
 * molesta más de lo que aporta).
 */
import * as React from "react";

export interface FilasPlegables<Fila> {
  /** Subconjunto a renderizar: las primeras N si está plegado, todas si expandido. */
  visibles: Fila[];
  /** True si el usuario ha desplegado (se muestran todas). */
  expandido: boolean;
  /** Togglea expandido/plegado (handler del control del pie). */
  alternar: () => void;
  /** True si procede mostrar el control (hay filas de sobra por encima del margen). */
  hayMas: boolean;
  /** Total de filas de entrada (para el texto "Ver las N …"). */
  total: number;
}

export function useFilasPlegables<Fila>(
  filas: readonly Fila[],
  limite = 5,
  margen = 2,
): FilasPlegables<Fila> {
  const [expandido, setExpandido] = React.useState(false);
  const alternar = React.useCallback(() => setExpandido((v) => !v), []);

  const total = filas.length;
  // Solo recortamos si hay filas suficientes de sobra (no por 1-2).
  const recortar = total > limite + margen;
  const hayMas = recortar;

  const visibles = React.useMemo(
    () => (expandido || !recortar ? [...filas] : filas.slice(0, limite)),
    [filas, expandido, recortar, limite],
  );

  return { visibles, expandido, alternar, hayMas, total };
}
