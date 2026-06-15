import { useQuery } from "@tanstack/react-query";
import { ServerCog, ShieldAlert } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TituloPagina } from "@/components/layout/encabezado";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api } from "@/lib/api";

import { SeccionMetricool } from "@/pages/configuracion/SeccionMetricool";
import { SeccionPostproxy } from "@/pages/configuracion/SeccionPostproxy";

import { AvisosDoctor } from "./Doctor";
import { SeccionCuentaClaude } from "./SeccionCuentaClaude";
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
 *   (clase=sistema: limpiador, GC de media, métricas, alertas, patrones, comercial), backups y
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
const PESTANAS = [
  { valor: "proveedores", etiqueta: "Proveedores" },
  { valor: "servidor", etiqueta: "Servidor" },
  { valor: "s3", etiqueta: "S3" },
] as const;

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

  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tabInicial = PESTANAS.some((p) => p.valor === tabParam)
    ? (tabParam as string)
    : "proveedores";

  if (esProhibido) {
    return <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />;
  }
  return (
    <>
      <TituloPagina titulo="Sistema" icono={ServerCog} />
      <div className="space-y-6">
        <AvisosDoctor />
        <Tabs defaultValue={tabInicial} className="space-y-4">
          <TabsList>
            {PESTANAS.map((p) => (
              <TabsTrigger key={p.valor} value={p.valor}>
                {p.etiqueta}
              </TabsTrigger>
            ))}
          </TabsList>
          {/* PROVEEDORES: conexiones a servicios externos. La cuenta de Claude que alimenta la
              generación de copy y Metricool (token por marca) del que se leen las métricas de
              audiencia. Metricool se gestiona aquí (antes vivía en el «⋮» de Analíticas). */}
          <TabsContent value="proveedores" className="space-y-6">
            <SeccionCuentaClaude />
            <SeccionMetricool />
            <SeccionPostproxy />
          </TabsContent>
          {/* SERVIDOR: hardware + servicios de sistema (clase=sistema): pura infraestructura
              (limpiador, GC de media, métricas, alertas, patrones, comercial). Los servicios de la
              máquina de contenido (clase=maquina) viven en los cockpits; los agentes IA (clase=ia)
              son los cockpits. Más backups y latencias de la API. */}
          <TabsContent value="servidor" className="space-y-6">
            <SeccionRecursos />
            <SeccionDaemons clases={["sistema"]} titulo="Servicios de sistema" />
            <SeccionBackups />
            <SeccionRendimiento />
          </TabsContent>
          {/* S3: almacenamiento de media (Garage) — estado + explorador. */}
          <TabsContent value="s3" className="space-y-6">
            <SeccionS3 />
            <SeccionNavegadorS3 />
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
}
