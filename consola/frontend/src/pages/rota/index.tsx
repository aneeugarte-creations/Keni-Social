import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  CalendarCheck,
  CalendarDays,
  CheckCircle2,
  Settings2,
} from "lucide-react";
import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { PestanasSeccion, type PestanaSeccion } from "@/components/layout/encabezado";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { lunesDeSemana } from "@/lib/rota-calendario";
import type { FiltrosSwaps } from "@/types";

import { Calendario } from "./Calendario";
import { CambiosYAusencias } from "./CambiosYAusencias";
import { Hoy } from "./Hoy";
import { PanelCoordinacion, useSenalesCoordinacion } from "./PanelCoordinacion";
import { contarSwapsPendientes } from "./comun";


// ===========================================================================

/** Valores válidos de pestaña (orden = el de la barra). «Horario» (el calendario) es la home
 *  (default). «Gestión» es admin-only. «Mi jornada» dejó de ser pestaña: es el modo «Mes» del
 *  calendario; el legacy `mis-turnos` se normaliza abajo. El TRABAJO (eventos/tareas/cobertura)
 *  ya no es pestaña: vive en su propio destino del sidebar (`/operacion/trabajo`). */
const VALORES_PESTANA = ["hoy", "calendario", "gestion", "cambios-ausencias"];

/** El deep-link legacy a la antigua pestaña «Mi jornada» (`?tab=mis-turnos`) cae en el
 *  calendario abierto en su modo «Mes» (la misma vista mensual de jornada). */
function normalizarTab(tab: string | null): { pestania: string; vistaCalendario: "semana" | "mes" } {
  if (tab === "mis-turnos") return { pestania: "calendario", vistaCalendario: "mes" };
  if (tab && VALORES_PESTANA.includes(tab)) return { pestania: tab, vistaCalendario: "semana" };
  return { pestania: "calendario", vistaCalendario: "semana" };
}

export default function Rota() {
  const { usuario } = useSesion();
  const { marcaActiva } = useMarcaActiva();
  const navigate = useNavigate();
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
  // Pestaña activa (controlada). Esta sección es SOLO el calendario de turnos (Horario/Hoy/Gestión);
  // el trabajo (eventos/tareas/cobertura) vive en su propio destino del sidebar.
  //
  // La inicial puede venir por `?tab=` (deep-link desde la campana de notificaciones de un
  // cambio de turno); si no hay `?tab=` o el valor no es válido, cae a «Horario» (el calendario, la
  // home). El valor legacy `mis-turnos` (antigua pestaña «Mi jornada») se normaliza al modo «Mes».
  const [params] = useSearchParams();
  const tabParam = params.get("tab");
  const [pestania, setPestania] = React.useState(() => normalizarTab(tabParam).pestania);
  // «Gestión» es admin-only: un no-admin que llegue con `?tab=gestion` cae en «Hoy». «Cambios y
  // ausencias» ya NO es pestaña para el admin (vive en su panel de Gestión): un deep-link admin a
  // ese tab cae en «Gestión».
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

  // Señales de coordinación de la semana (huecos/cambios/conflictos): solo se derivan en «Gestión».
  // Alimentan el `PanelCoordinacion` (que solo se pinta si hay pendientes) y, cuando NO hay nada, el
  // marcador ✓ «Al día» de la cabecera del calendario — el cockpit desaparece y el mes sube (SOSIEGO).
  const senalesCoord = useSenalesCoordinacion({
    lunes,
    marcaActiva,
    usuarioId: usuario?.id ?? "",
    esAdmin,
    activo: pestaniaEfectiva === "gestion",
  });
  const marcadorSalud =
    !senalesCoord.cargando && senalesCoord.todoEnOrden ? (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground">
        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
        Al día
      </span>
    ) : undefined;

  // La subnav vive en el topbar (como Métricas). «Gestión» es admin-only; la insignia de
  // «Cambios y ausencias» cuelga de su pestaña (nº de cambios que esperan MI acción).
  const pestanas: PestanaSeccion[] = [
    // «Horario» = el calendario de turnos (Yo/Equipo · Semana/Mes); es la home de esta sección.
    { valor: "calendario", etiqueta: "Horario", icono: CalendarDays },
    { valor: "hoy", etiqueta: "Hoy", icono: CalendarCheck },
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

      {/* «Hoy»: resumen del día (próximo turno + por-cubrir-hoy + lo-mío-hoy). «Ver toda la
          agenda» salta al destino «Trabajo» (eventos/tareas/cobertura), ya fuera de esta sección. */}
      {pestaniaEfectiva === "hoy" && <Hoy onVerAgenda={() => navigate("/operacion/trabajo")} />}

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
            senales={senalesCoord.senales}
            cargando={senalesCoord.cargando}
            onIr={(destino) =>
              destino === "cobertura" ? navigate("/operacion/trabajo") : setPestania(destino)
            }
          />
          <div className="min-h-0 flex-1">
            <Calendario
              lunes={lunes}
              setLunes={setLunes}
              esAdmin={esAdmin}
              modo="gestion"
              vistaInicial="mes"
              marcadorSalud={marcadorSalud}
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
