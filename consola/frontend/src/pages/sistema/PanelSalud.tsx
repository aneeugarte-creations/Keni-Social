import { useQuery } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { ApiError, api } from "@/lib/api";

import { BannerAlertas } from "./BannerAlertas";
import { SeccionNavegadorS3 } from "./NavegadorS3";
import { SeccionBackups } from "./SeccionBackups";
import { SeccionDaemons } from "./SeccionDaemons";
import { SeccionRecursos } from "./SeccionRecursos";
import { SeccionRendimiento } from "./SeccionRendimiento";
import { SeccionS3 } from "./SeccionS3";
import { INTERVALO_RECURSOS_MS } from "./lib";

/**
 * Pestaña «Salud» del Monitor (admin): la infraestructura que sostiene la consola —
 * recursos del servidor (CPU/RAM/disco), salud de daemons (latidos), backups, latencias
 * de la API y S3/Garage (estado + explorador). Era la página «Sistema» del avatar;
 * CONSOLIDADA aquí: una sola superficie de monitorización (En vivo = la cola; Salud =
 * la infra). La síntesis de cola/gasto que duplicaba al propio Monitor se retiró.
 *
 * El backend devuelve 403 si quien entra no es admin; se avisa de forma unificada
 * (la pestaña ya se oculta a un editor, esto cubre la URL directa ?tab=salud).
 */
export function PanelSalud() {
  // Una sonda inicial para detectar el 403 y mostrar el aviso de permiso unificado.
  const guardia = useQuery({
    queryKey: ["sistema", "recursos"],
    queryFn: ({ signal }) => api.sistemaRecursos(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });
  const esProhibido =
    guardia.isError &&
    guardia.error instanceof ApiError &&
    guardia.error.status === 403;

  if (esProhibido) {
    return (
      <EstadoVacio
        icono={ShieldAlert}
        titulo="No tienes permiso"
        texto="Solo los administradores pueden ver la salud del sistema."
      />
    );
  }
  return (
    <div className="space-y-6">
      <BannerAlertas />
      <SeccionRecursos />
      <SeccionDaemons />
      <SeccionBackups />
      <SeccionRendimiento />
      <SeccionS3 />
      <SeccionNavegadorS3 />
    </div>
  );
}
