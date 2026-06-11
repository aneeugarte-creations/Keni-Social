/**
 * AvisoSalud — señal MÍNIMA y condicional de la salud del motor en la página de curación.
 *
 * La página de Noticias es para CURAR; la salud de fuentes tiene su pantalla (Fuentes).
 * Aquí solo aparece UNA línea ámbar cuando algo requiere atención (fuentes con error);
 * si todo está bien, no se muestra nada — fuera los chips de "28 feeds activos / 219 en
 * 24 h" que eran ruido operacional.
 */

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { Link } from "react-router-dom";

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
    <p className="mb-3 flex items-center gap-1.5 text-xs text-amber-600" data-testid="aviso-salud">
      <AlertTriangle className="h-3.5 w-3.5" />
      {errores} fuente{errores !== 1 ? "s" : ""} con fallas —{" "}
      <Link to="/datos/investigacion/fuentes" className="underline hover:text-amber-700">
        revisar en Fuentes
      </Link>
    </p>
  );
}
