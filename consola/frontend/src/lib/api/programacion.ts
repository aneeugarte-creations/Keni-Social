// Fragmento del cliente API: dominio «programación» (mejor hora para publicar).
// A diferencia del resto de fragmentos, aquí el fetch DEGRADA a null ante cualquier fallo
// (el endpoint puede no existir aún) y se acompaña de su hook react-query; ambos los consume
// el editor de hora del calendario, no el objeto `api` compuesto.
import { useQuery } from "@tanstack/react-query";

import { peticion, query } from "./_core";

/**
 * Respuesta de `/api/programacion/mejor-hora`: mejor franja para publicar. `hora` en CDMX
 * ("HH:mm") y `dia` de la semana en minúscula ("martes"); ambos null si no hay señal.
 */
export interface MejorHora {
  hora: string | null;
  dia: string | null;
}

const UNA_HORA_MS = 60 * 60 * 1000;

/**
 * Mejor franja sugerida para publicar en `red` de `marca` (`{hora, dia}`, ambos null si el
 * backend no tiene señal). DEGRADA con elegancia: ante red caída, 404 (endpoint aún no
 * desplegado) o campos null devuelve `{hora: null, dia: null}` para que la UI simplemente no
 * muestre la sugerencia.
 */
export async function fetchMejorHora(
  marca: string,
  red: string,
  signal?: AbortSignal,
): Promise<MejorHora> {
  if (!marca || !red) return { hora: null, dia: null };
  try {
    const res = await peticion<MejorHora>(
      `/programacion/mejor-hora${query({ marca, red })}`,
      { signal },
    );
    return { hora: res?.hora ?? null, dia: res?.dia ?? null };
  } catch (e) {
    // react-query canceló la petición: propaga para que gestione la cancelación.
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    return { hora: null, dia: null };
  }
}

/**
 * Etiqueta legible de una mejor franja: "martes · 19:00" cuando hay día y hora, "19:00" si
 * solo hay hora, o null si no hay hora que mostrar.
 */
export function etiquetaMejorHora(franja: MejorHora | null | undefined): string | null {
  const hora = franja?.hora;
  if (!hora) return null;
  return franja?.dia ? `${franja.dia} · ${hora}` : hora;
}

/**
 * Hook de la mejor franja sugerida para (marca, red). La clave incluye marca y red, así que
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
