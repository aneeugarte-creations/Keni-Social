// Fragmento del cliente API: dominio «programación» (mejor hora para publicar).
// A diferencia del resto de fragmentos, aquí el fetch DEGRADA a null ante cualquier fallo
// (el endpoint puede no existir aún) y se acompaña de su hook react-query; ambos los consume
// el editor de hora del calendario, no el objeto `api` compuesto.
import { useQuery } from "@tanstack/react-query";

import { peticion, query } from "./_core";

/** Respuesta de `/api/programacion/mejor-hora`: hora ya en CDMX, o null si no hay señal. */
interface RespuestaMejorHora {
  hora: string | null;
}

const UNA_HORA_MS = 60 * 60 * 1000;

/**
 * Mejor hora sugerida ("HH:mm" CDMX) para publicar en `red` de `marca`, o null si el
 * backend no tiene señal. DEGRADA con elegancia: ante red caída, 404 (endpoint aún no
 * desplegado) o `hora: null` devuelve null para que la UI simplemente no muestre la sugerencia.
 */
export async function fetchMejorHora(
  marca: string,
  red: string,
  signal?: AbortSignal,
): Promise<string | null> {
  if (!marca || !red) return null;
  try {
    const res = await peticion<RespuestaMejorHora>(
      `/programacion/mejor-hora${query({ marca, red })}`,
      { signal },
    );
    return res?.hora ?? null;
  } catch (e) {
    // react-query canceló la petición: propaga para que gestione la cancelación.
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    return null;
  }
}

/**
 * Hook de la mejor hora sugerida para (marca, red). La clave incluye marca y red, así que
 * react-query cachea por par y el calendario puede pedirla por cada pieza sin disparar
 * peticiones idénticas. `staleTime` de 1h: la señal cambia despacio.
 */
export function useMejorHora(
  marca: string | null | undefined,
  red: string | null | undefined,
) {
  return useQuery({
    queryKey: ["mejor-hora", marca ?? "", red ?? ""],
    queryFn: ({ signal }) => fetchMejorHora(marca ?? "", red ?? "", signal),
    enabled: Boolean(marca && red),
    staleTime: UNA_HORA_MS,
  });
}
