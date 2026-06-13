import { useQuery } from "@tanstack/react-query";
import { ServerCog, ShieldAlert } from "lucide-react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TituloPagina } from "@/components/layout/encabezado";
import { ApiError, api } from "@/lib/api";

import { AvisosDoctor } from "./Doctor";
import { SeccionNavegadorS3 } from "./NavegadorS3";
import { SeccionBackups } from "./SeccionBackups";
import { SeccionRecursos } from "./SeccionRecursos";
import { SeccionRendimiento } from "./SeccionRendimiento";
import { SeccionS3 } from "./SeccionS3";
import { INTERVALO_RECURSOS_MS } from "./lib";

/**
 * Página SISTEMA (admin, dropdown del avatar): el HARDWARE y el ALMACENAMIENTO que sostienen
 * la consola — recursos del servidor (CPU/RAM/disco), backups, latencias de la API y S3/Garage
 * (estado + explorador). Los daemons (salud + encendido) ya NO viven aquí: se movieron a la
 * página Agentes (/maquina/agentes), su única casa, junto a los Workers. Arriba, los chequeos de
 * operador del doctor (`/api/estado`) que requieran atención (sustituyen al viejo
 * BannerAlertas: el juicio vive en el back, no en umbrales del front).
 *
 * El backend devuelve 403 si quien entra no es admin; se avisa de forma unificada
 * (la entrada del avatar ya se oculta a un editor, esto cubre la URL directa /sistema).
 */
export default function Sistema() {
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
    return <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />;
  }
  return (
    <>
      <TituloPagina titulo="Sistema" icono={ServerCog} />
      <div className="space-y-6">
        <AvisosDoctor />
        <SeccionRecursos />
        {/* Los daemons (TODOS los grupos, incluida la infraestructura) viven ahora en la página
            Agentes (/maquina/agentes), su única casa. Sistema se queda con hardware y
            almacenamiento: recursos, backups, rendimiento y S3. */}
        <SeccionBackups />
        <SeccionRendimiento />
        <SeccionS3 />
        <SeccionNavegadorS3 />
      </div>
    </>
  );
}
