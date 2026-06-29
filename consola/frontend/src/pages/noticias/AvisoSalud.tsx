/**
 * AvisoSalud — señal MÍNIMA y condicional de la salud del motor en la página de curación.
 *
 * La página de Noticias es para CURAR; la salud de fuentes tiene su pantalla (Fuentes).
 * Aquí solo aparece UNA línea ámbar cuando algo requiere atención (fuentes con error);
 * si todo está bien, no se muestra nada.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Aviso } from "@/components/comunes/Aviso";
import { api } from "@/lib/api";

export function AvisoSalud() {
  const query = useQuery({
    queryKey: ["noticias", "cobertura"],
    queryFn: ({ signal }) => api.noticias.cobertura(signal),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const errores = query.data?.feeds_con_error ?? 0;
  if (query.isError || query.isPending || errores <= 0) return null;

  return (
    <Aviso className="mb-3" data-testid="aviso-salud">
      {errores} fuente{errores !== 1 ? "s" : ""} con fallas —{" "}
      <Link to="/operacion/investigacion/fuentes" className="underline">
        revisar en Fuentes
      </Link>
    </Aviso>
  );
}
