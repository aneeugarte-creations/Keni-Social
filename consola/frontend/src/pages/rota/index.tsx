import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  CalendarCheck,
  CalendarDays,
  ClipboardList,
  Settings2,
} from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { PestanasSeccion, type PestanaSeccion } from "@/components/layout/encabezado";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { lunesDeSemana } from "@/lib/rota-calendario";
import { TareasBoard } from "@/pages/tareas/Tareas";
import type { FiltrosSwaps } from "@/types";

import { Calendario } from "./Calendario";
import { CambiosYAusencias } from "./CambiosYAusencias";
import { Hoy } from "./Hoy";
import { PanelCoordinacion } from "./PanelCoordinacion";
import { contarSwapsPendientes } from "./comun";


// ===========================================================================

/** Valores válidos de pestaña (orden = el de la barra). «Hoy» es la home (default). «Gestión» es
 *  admin-only. «Mi jornada» dejó de ser pestaña: es el modo «Mes» del Calendario; el legacy
 *  `mis-turnos` se normaliza abajo. */
const VALORES_PESTANA = ["hoy", "calendario", "cobertura", "gestion", "cambios-ausencias"];

/** El deep-link legacy a la antigua pestaña «Mi jornada» (`?tab=mis-turnos`) cae en el
 *  Calendario abierto en su modo «Mes» (la misma vista mensual de jornada). */
function normalizarTab(tab: string | null): { pestania: string; vistaCalendario: "semana" | "mes" } {
  if (tab === "mis-turnos") return { pestania: "calendario", vistaCalendario: "mes" };
  if (tab && VALORES_PESTANA.includes(tab)) return { pestania: tab, vistaCalendario: "semana" };
  return { pestania: "hoy", vistaCalendario: "semana" };
}

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
    // Solo alimenta la insignia de la pestaña «Cambios y ausencias» (no-admin). El admin ya no
    // tiene esa pestaña; ve sus cambios pendientes en el panel de Gestión (CambiosYAusencias).
    enabled: usuario !== null && !esAdmin,
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
  // Pestaña activa (controlada). Aquí el Calendario es solo turnos + su cobertura derivada.
  //
  // La inicial puede venir por `?tab=` (deep-link desde la campana de notificaciones de un
  // cambio de turno); si no hay `?tab=` o el valor no es válido, cae a «Hoy» (la home). El valor
  // legacy `mis-turnos` (antigua pestaña «Mi jornada») se normaliza a Calendario en modo «Mes».
  const [params] = useSearchParams();
  const tabParam = params.get("tab");
  const [pestania, setPestania] = React.useState(() => normalizarTab(tabParam).pestania);
  // «Gestión» es admin-only: un no-admin que llegue con `?tab=gestion` cae en «Hoy» (la pestaña
  // no existe para él). El resto de deep-links (`cobertura`/`cambios-ausencias`/`mis-turnos`) intacto.
  // «Gestión» es admin-only (no-admin → «Hoy»). «Cambios y ausencias» ya NO es pestaña para el
  // admin (vive en su panel de Gestión): un deep-link admin a ese tab cae en «Gestión».
  const pestaniaEfectiva =
    pestania === "gestion" && !esAdmin
      ? "hoy"
      : pestania === "cambios-ausencias" && esAdmin
        ? "gestion"
        : pestania;
  // Modo de apertura del Calendario para los deep-links legacy a «Mi jornada».
  const [vistaCalendario, setVistaCalendario] = React.useState<"semana" | "mes">(
    () => normalizarTab(tabParam).vistaCalendario,
  );
  // Si el `?tab=` cambia con la página ya montada (clic en la campana estando en Turnos),
  // sincroniza la pestaña activa (y el modo del Calendario para el deep-link legacy).
  React.useEffect(() => {
    const { pestania: p, vistaCalendario: v } = normalizarTab(tabParam);
    if (tabParam) {
      setPestania(p);
      setVistaCalendario(v);
    }
  }, [tabParam]);

  // La subnav vive en el topbar (como Métricas). «Gestión» es admin-only; la insignia de
  // «Cambios y ausencias» cuelga de su pestaña (nº de cambios que esperan MI acción).
  const pestanas: PestanaSeccion[] = [
    { valor: "hoy", etiqueta: "Hoy", icono: CalendarCheck },
    { valor: "calendario", etiqueta: "Calendario", icono: CalendarDays },
    { valor: "cobertura", etiqueta: "Cobertura", icono: ClipboardList },
    // Admin → «Gestión» (que ya incluye «Cambios y ausencias» en su panel). Trabajador → la
    // pestaña «Cambios y ausencias» (su único sitio para pedir/responder cambios y ausencias,
    // porque «Gestión» es admin-only). Son excluyentes: cada rol ve una de las dos.
    ...(esAdmin
      ? [{ valor: "gestion", etiqueta: "Gestión", icono: Settings2 }]
      : [
          {
            valor: "cambios-ausencias",
            etiqueta: "Cambios y ausencias",
            icono: ArrowLeftRight,
            insignia:
              pendientesCambios > 0 ? (
                <span
                  className="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold leading-none text-white tabular-nums"
                  aria-label={`${pendientesCambios} pendientes`}
                >
                  {pendientesCambios > 99 ? "99+" : pendientesCambios}
                </span>
              ) : undefined,
          },
        ]),
  ];

  return (
    <>
      <PestanasSeccion pestanas={pestanas} activo={pestaniaEfectiva} onSelect={setPestania} />

      {/* «Hoy»: home del trabajador (próximo turno + por-cubrir-hoy + lo-mío-hoy). «Ver toda
          la agenda» y el «N sin cubrir» del KPI saltan a «Cobertura». */}
      {pestaniaEfectiva === "hoy" && <Hoy onVerAgenda={() => setPestania("cobertura")} />}

      {/* `key`={vistaCalendario}: un deep-link legacy a «Mi jornada» (?tab=mis-turnos) que llegue con
          la página ya montada fuerza el remonte del Calendario en modo «Mes» (su `vistaInicial` solo
          se lee al montar). El uso normal no cambia este valor. */}
      {pestaniaEfectiva === "calendario" && (
        <Calendario
          key={vistaCalendario}
          lunes={lunes}
          setLunes={setLunes}
          esAdmin={esAdmin}
          vistaInicial={vistaCalendario}
        />
      )}

      {/* «Cobertura»: el tablero de Tareas (Panorama/Por cubrir/Mis tareas) embebido, con el botón
          «Añadir» inline para no colgar acciones en la barra de Turnos. El Calendario queda intacto;
          son planos hermanos (capacidad vs cobertura). */}
      {pestaniaEfectiva === "cobertura" && <TareasBoard acciones="inline" />}

      {/* «Gestión» (admin): el Panel de coordinación reúne arriba las señales de la semana que piden
          decisión (huecos sin cubrir, cambios/ausencias, conflictos), y debajo el Calendario, que
          ABRE en modo «Mes» (overview mensual del equipo). El conmutador Semana|Mes salta a la
          rejilla SEMANAL, que trae el panel de reparto (asignar/franjas/copiar/carga/export). Ambos
          comparten `lunes`/`marcaActiva` con el Calendario.
          Gestión CABE en una pantalla: columna que llena el alto útil de `<main>` (= 100dvh − topbar
          `h-12` − padding pt/pb del contenedor ≈ 5.5rem). `overflow-hidden` corta el scroll de
          PÁGINA; el «Necesita tu decisión» va arriba a su alto natural y el calendario rellena el
          resto con scroll INTERNO. */}
      {pestaniaEfectiva === "gestion" && (
        <div className="flex h-[calc(100dvh-5.5rem)] flex-col gap-4 overflow-hidden">
          <PanelCoordinacion
            lunes={lunes}
            marcaActiva={marcaActiva}
            esAdmin={esAdmin}
            usuarioId={usuario?.id ?? ""}
            onIr={setPestania}
          />
          <div className="min-h-0 flex-1">
            <Calendario
              lunes={lunes}
              setLunes={setLunes}
              esAdmin={esAdmin}
              modo="gestion"
              vistaInicial="mes"
            />
          </div>
        </div>
      )}

      {/* «Cambios y ausencias»: una sola vista que mezcla cambios de turno y ausencias en una lista
          cronológica única, con filtros por tipo y estado. Sin sub-tabs. */}
      {pestaniaEfectiva === "cambios-ausencias" && <CambiosYAusencias esAdmin={esAdmin} />}
    </>
  );
}
