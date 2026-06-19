import { useQuery } from "@tanstack/react-query";
import { HardDrive, Plug, Server, ShieldAlert } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PestanasSeccion, type PestanaSeccion } from "@/components/layout/encabezado";
import { ApiError, api } from "@/lib/api";

import { SeccionMetricool } from "@/pages/configuracion/SeccionMetricool";
import { SeccionPostproxy } from "@/pages/configuracion/SeccionPostproxy";

import { AvisosDoctor } from "./Doctor";
import { SeccionCuentaClaude } from "./SeccionCuentaClaude";
import { SeccionGitHub } from "./SeccionGitHub";
import { SeccionDaemons } from "./SeccionDaemons";
import { SeccionNavegadorS3 } from "./NavegadorS3";
import { SeccionBackups } from "./SeccionBackups";
import { SeccionRecursos } from "./SeccionRecursos";
import { SeccionRendimiento } from "./SeccionRendimiento";
import { SeccionS3 } from "./SeccionS3";
import { INTERVALO_RECURSOS_MS } from "./lib";

/**
 * Página SISTEMA (admin, dropdown del avatar): el HARDWARE, el ALMACENAMIENTO y los SERVICIOS DE
 * SISTEMA que sostienen la consola. Repartido en tres pestañas:
 * - Proveedores: las conexiones a proveedores externos — la cuenta de Claude (auth, estado del
 *   token, uso) que alimenta la generación y Metricool (token por marca) del que se leen las
 *   métricas de audiencia.
 * - Servidor: recursos del servidor (CPU/RAM/disco), daemons de pura infraestructura
 *   (clase=sistema: limpiador, GC de media, métricas, alertas, patrones), backups y
 *   latencias de la API.
 * - S3: almacenamiento de media (Garage) — estado + explorador.
 * Los agentes IA y los servicios de la máquina de contenido (ingesta/trends/programador/…) viven
 * en los cockpits de la sección Máquina. Arriba de las pestañas, los chequeos de operador del
 * doctor (`/api/estado`) que requieran atención (sustituyen al viejo BannerAlertas: el juicio vive
 * en el back, no en umbrales del front).
 *
 * El backend devuelve 403 si quien entra no es admin; se avisa de forma unificada
 * (la entrada del avatar ya se oculta a un editor, esto cubre la URL directa /sistema).
 */
const PESTANAS: PestanaSeccion[] = [
  { valor: "proveedores", etiqueta: "Proveedores", icono: Plug },
  { valor: "servidor", etiqueta: "Servidor", icono: Server },
  { valor: "s3", etiqueta: "S3", icono: HardDrive },
];

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

  // La sección activa viaja en `?tab=` (deep-link), reflejada por la subnav del topbar.
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab = PESTANAS.some((p) => p.valor === tabParam) ? (tabParam as string) : "proveedores";
  const cambiarTab = (valor: string) =>
    setSearchParams(
      (prev) => {
        prev.set("tab", valor);
        return prev;
      },
      { replace: true },
    );

  if (esProhibido) {
    return <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />;
  }
  return (
    <>
      <PestanasSeccion pestanas={PESTANAS} activo={tab} onSelect={cambiarTab} />
      <div className="space-y-6">
        <AvisosDoctor />
        {/* PROVEEDORES: conexiones a servicios externos. La cuenta de Claude que alimenta la
            generación de copy y Metricool (token por marca) del que se leen las métricas de
            audiencia. Metricool se gestiona aquí (antes vivía en el «⋮» de Analíticas). */}
        {tab === "proveedores" && (
          <div className="space-y-6">
            <SeccionCuentaClaude />
            <SeccionGitHub />
            <SeccionMetricool />
            <SeccionPostproxy />
          </div>
        )}
        {/* SERVIDOR: hardware + servicios de sistema (clase=sistema): pura infraestructura
            (limpiador, GC de media, métricas, alertas, patrones). Los servicios de la
            máquina de contenido (clase=maquina) viven en los cockpits; los agentes IA (clase=ia)
            son los cockpits. Más backups y latencias de la API. */}
        {tab === "servidor" && (
          <div className="space-y-6">
            <SeccionRecursos />
            <SeccionDaemons clases={["sistema"]} titulo="Servicios de sistema" />
            <SeccionBackups />
            <SeccionRendimiento />
          </div>
        )}
        {/* S3: almacenamiento de media (Garage) — estado + explorador. */}
        {tab === "s3" && (
          <div className="space-y-6">
            <SeccionS3 />
            <SeccionNavegadorS3 />
          </div>
        )}
      </div>
    </>
  );
}
