// Página «Turnos» (rota): shell de pestañas. Partido mecánicamente de pages/Rota.tsx
// en pages/rota/* (como feed/ y publicaciones/), sin cambios de comportamiento.
import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
} from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { TituloPagina } from "@/components/layout/encabezado";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { lunesDeSemana } from "@/lib/rota-calendario";
import { TareasBoard } from "@/pages/tareas/Tareas";
import type { FiltrosSwaps } from "@/types";

import { Calendario } from "./Calendario";
import { CambiosYAusencias } from "./CambiosYAusencias";
import { contarSwapsPendientes } from "./comun";
import { MisTurnos } from "./MisTurnos";


// ===========================================================================

/** Valores válidos de pestaña (orden = el de la barra). */
const PESTANAS = ["calendario", "cobertura", "mis-turnos", "cambios-ausencias"];

export default function Rota() {
  const { usuario } = useSesion();
  const { marcaActiva } = useMarcaActiva();
  const esAdmin = usuario?.rol === "admin";

  // Badge de la pestaña «Cambios y ausencias»: nº de cambios de turno que esperan MI
  // acción (responder como destinatario o, si soy admin, aprobar). Comparte la queryKey
  // con CambiosYAusencias para no duplicar la petición; se actualiza al invalidar swaps.
  const filtrosSwaps: FiltrosSwaps = {
    ...(esAdmin ? {} : { mio: true }),
    ...(marcaActiva ? { marca: marcaActiva } : {}),
  };
  const swapsPendientesQ = useQuery({
    enabled: usuario !== null,
    queryKey: ["rota", "swaps", filtrosSwaps] as const,
    queryFn: ({ signal }) => api.listarSwaps(filtrosSwaps, signal),
  });
  const pendientesCambios = contarSwapsPendientes(
    swapsPendientesQ.data?.swaps ?? [],
    usuario?.id ?? "",
    esAdmin,
  );
  // Por defecto: la semana ACTUAL (la que contiene hoy, en zona CDMX).
  const [lunes, setLunes] = React.useState(() => lunesDeSemana(new Date()));
  // Pestaña activa (controlada). La gestión de EVENTOS se mudó al hub de Fuentes
  // (ola "Calendario = turnos / Fuentes = eventos"); aquí el Calendario es solo turnos
  // + su cobertura derivada.
  //
  // La inicial puede venir por `?tab=` (deep-link desde la campana de notificaciones de
  // un cambio de turno); si el valor no es válido, cae a "calendario".
  const [params] = useSearchParams();
  const tabParam = params.get("tab");
  const [pestania, setPestania] = React.useState(() =>
    tabParam && PESTANAS.includes(tabParam) ? tabParam : "calendario",
  );
  // Si el `?tab=` cambia con la página ya montada (clic en la campana estando en Turnos),
  // sincroniza la pestaña activa.
  React.useEffect(() => {
    if (tabParam && PESTANAS.includes(tabParam)) setPestania(tabParam);
  }, [tabParam]);

  return (
    <>
      <TituloPagina titulo="Turnos" icono={CalendarClock} />
      <Tabs value={pestania} onValueChange={setPestania} className="space-y-4">
        <TabsList>
          <TabsTrigger value="calendario">Calendario</TabsTrigger>
          <TabsTrigger value="cobertura">Cobertura</TabsTrigger>
          <TabsTrigger value="mis-turnos">Mis turnos</TabsTrigger>
          <TabsTrigger value="cambios-ausencias">
            Cambios y ausencias
            {pendientesCambios > 0 && (
              <span
                className="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-none text-primary-foreground tabular-nums"
                aria-label={`${pendientesCambios} pendientes`}
              >
                {pendientesCambios > 99 ? "99+" : pendientesCambios}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="calendario">
          <Calendario lunes={lunes} setLunes={setLunes} esAdmin={esAdmin} />
        </TabsContent>
        {/* «Cobertura»: el tablero de Tareas (Panorama/Por cubrir/Mis tareas) embebido,
            con el botón «Añadir» inline para no colgar acciones en la barra de Turnos.
            El Calendario de arriba queda intacto; son planos hermanos (capacidad vs cobertura). */}
        <TabsContent value="cobertura">
          <TareasBoard acciones="inline" />
        </TabsContent>
        <TabsContent value="mis-turnos">
          <MisTurnos
            lunes={lunes}
            setLunes={setLunes}
            esAdmin={esAdmin}
            onVerCalendario={() => setPestania("calendario")}
          />
        </TabsContent>
        <TabsContent value="cambios-ausencias">
          {/* Ola "fusion real": una sola vista que mezcla cambios de turno y
              ausencias en una lista cronologica unica, con filtros por tipo y
              estado. Sin sub-tabs. */}
          <CambiosYAusencias esAdmin={esAdmin} />
        </TabsContent>
      </Tabs>
    </>
  );
}

