import * as React from "react";

/**
 * Re-renderiza cada `intervaloMs` para que el semáforo de cobertura avance con el reloj
 * (PRE-LIVE → «En vivo» → «Terminado») sin esperar al refetch del tablero: la fase se deriva de
 * `Date.now()` en cada render, así que basta forzar un render periódico. Lo usan el Panorama y
 * `TareasBoard` (para que el KPI «Cobertura de hoy», hermano del Panorama, también avance).
 */
export function useRelojVivo(intervaloMs = 30_000) {
  const [, setTick] = React.useState(0);
  React.useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), intervaloMs);
    return () => clearInterval(id);
  }, [intervaloMs]);
}
