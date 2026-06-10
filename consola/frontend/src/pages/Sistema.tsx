import { useQuery } from "@tanstack/react-query";
import { Server, ShieldAlert } from "lucide-react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TituloPagina } from "@/components/layout/encabezado";
import { ApiError, api } from "@/lib/api";

import { SeccionNavegadorS3 } from "./sistema/NavegadorS3";
import { SeccionDaemons } from "./sistema/SeccionDaemons";
import { SeccionRecursos } from "./sistema/SeccionRecursos";
import { SeccionS3 } from "./sistema/SeccionS3";
import { INTERVALO_RECURSOS_MS } from "./sistema/lib";

/**
 * Panel de SISTEMA (admin): monitorización del servidor (CPU/RAM/disco, auto-refresco)
 * y estado/gestión del almacenamiento S3/Garage (uso del bucket + probar conexión + explorador
 * de carpetas/objetos, solo lectura). El backend devuelve 403 si quien entra no es admin;
 * aquí lo avisamos al llegar por URL directa (el nav ya oculta la página para no-admin).
 */
export default function Sistema() {
  // Una sonda inicial para detectar el 403 y mostrar el aviso de permiso de forma unificada.
  const guardia = useQuery({
    queryKey: ["sistema", "recursos"],
    queryFn: ({ signal }) => api.sistemaRecursos(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });
  const esProhibido =
    guardia.isError &&
    guardia.error instanceof ApiError &&
    guardia.error.status === 403;

  return (
    <>
      <TituloPagina titulo="Sistema" icono={Server} />
      {esProhibido ? (
        <EstadoVacio
          icono={ShieldAlert}
          titulo="No tienes permiso"
          texto="Solo los administradores pueden ver el estado del sistema."
        />
      ) : (
        <div className="space-y-6">
          <SeccionRecursos />
          <SeccionDaemons />
          <SeccionS3 />
          <SeccionNavegadorS3 />
        </div>
      )}
    </>
  );
}
