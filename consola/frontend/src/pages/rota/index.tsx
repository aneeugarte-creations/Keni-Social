// Página «Turnos» (rota): shell de pestañas. Partido mecánicamente de pages/Rota.tsx
// en pages/rota/* (como feed/ y publicaciones/), sin cambios de comportamiento.
import {
  CalendarClock,
} from "lucide-react";
import * as React from "react";

import { TituloPagina } from "@/components/layout/encabezado";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSesion } from "@/hooks/sesion-contexto";
import {
  lunesDeSemana,
  lunesSiguiente,
} from "@/lib/rota-calendario";
import { TareasBoard } from "@/pages/tareas/Tareas";

import { Calendario } from "./Calendario";
import { CambiosYAusencias } from "./CambiosYAusencias";
import { MisTurnos } from "./MisTurnos";


// ===========================================================================

export default function Rota() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  // Por defecto: la próxima semana (la que más le importa al equipo, B4).
  const [lunes, setLunes] = React.useState(() => lunesSiguiente(lunesDeSemana(new Date()), 1));
  // Pestaña activa (controlada). La gestión de EVENTOS se mudó al hub de Fuentes
  // (ola "Calendario = turnos / Fuentes = eventos"); aquí el Calendario es solo turnos
  // + su cobertura derivada.
  const [pestania, setPestania] = React.useState("calendario");

  return (
    <>
      <TituloPagina titulo="Turnos" icono={CalendarClock} />
      <Tabs value={pestania} onValueChange={setPestania} className="space-y-4">
        <TabsList>
          <TabsTrigger value="calendario">Calendario</TabsTrigger>
          <TabsTrigger value="cobertura">Cobertura</TabsTrigger>
          <TabsTrigger value="mis-turnos">Mis turnos</TabsTrigger>
          <TabsTrigger value="cambios-ausencias">Cambios y ausencias</TabsTrigger>
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

