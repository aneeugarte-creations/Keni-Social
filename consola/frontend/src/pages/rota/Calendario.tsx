// Pestaña CALENDARIO de la rota (rejilla semanal de turnos + cobertura derivada).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BellRing,
  CalendarPlus,
  Sparkles,
  Sunrise,
  Sunset,
  UserPlus,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Tooltip } from "@/components/ui/tooltip";
import { BloqueError } from "@/components/comunes/BloqueError";
import { ImportarDocumentoParrilla } from "@/components/parrilla/ImportarDocumentoParrilla";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup } from "@/components/ui/toggle-group";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { resumenCobertura } from "@/lib/cobertura";
import {
  diaCorto,
  diasDeSemana,
  esFinDeSemana,
  lunesSiguiente,
} from "@/lib/rota-calendario";
import { hoyCDMX } from "@/lib/fecha";
import type {
  AusenciaRota,
  EventoRota,
  FranjaSemana,
  TurnoRota,
} from "@/types";

import { CeldaDeRejilla, cmsDeMarca, DialogCargaEquipo } from "./CalendarioPiezas";
import { ChipEventoCalendario } from "./calendario/chips";
import {
  AyudaLeyenda,
  ChipAusenciaDia,
  MasAusencias,
  MenuMasAcciones,
  NavegadorSemana,
  ausenciaTocaDia,
  eventosFueraDeFranja,
  filtrarEquipoPorMarca,
  formatearFechaCorta,
  franjaIdParaHoraEvento,
  franjasSolapan,
  presentacionFranja,
  type ConflictoCandidato,
  type CubridorEvento,
  type ItemEventoCalendario,
} from "./comun";
import { DialogoAsignarTurnos } from "./DialogoAsignarTurnos";
import { CambiosYAusencias } from "./CambiosYAusencias";
import { ResumenDia } from "./ResumenDia";
import { DialogFranjas } from "./Franjas";
import { VistaMensualTurnos } from "./MisTurnos";
import { PropuestasCalendario } from "./PropuestasCalendario";
import { CLAVE_TAREAS } from "@/pages/tareas/claves";
import { TarjetaCobertura, TarjetaEventoLibre } from "@/pages/tareas/tarjetas";
import { agrupar, type Cobertura } from "@/pages/tareas/tipos";
import { interaccionEnCapaHija } from "./coberturaDialogo";


/** Modo de vista del Calendario: la rejilla SEMANAL (franjas×días) o el calendario MENSUAL
 *  de jornada (la antigua «Mi jornada», con su Yo/Equipo e imprimir/PDF). */
type VistaCalendario = "semana" | "mes";

export function Calendario({
  lunes,
  setLunes,
  esAdmin,
  vistaInicial = "semana",
  modo = "calendario",
}: {
  lunes: string;
  setLunes: (l: string) => void;
  esAdmin: boolean;
  /** Modo de apertura. Por defecto «Semana» (rejilla actual); «mes» lo usan los deep-links
   *  legacy a la antigua pestaña «Mi jornada». */
  vistaInicial?: VistaCalendario;
  /** "calendario" = rejilla de consulta (edición inline de celdas para admin). "gestion" = panel
   *  admin de la semana (asignar/franjas/copiar/carga/export). Lo monta
   *  index.tsx en su pestaña admin-only; comparte `lunes`/`marcaActiva` y la misma queryKey de turnos. */
  modo?: "calendario" | "gestion";
}) {
  // Conmutador Semana|Mes: la rejilla semanal vive aquí; el modo «Mes» reutiliza la vista
  // mensual de jornada. Su valor inicial puede venir de un deep-link legacy (?tab=mis-turnos).
  const [vista, setVista] = React.useState<VistaCalendario>(vistaInicial);
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  // GRID POR MARCA: la marca activa entra en las queryKeys (refresca al cambiar de workspace)
  // y en cada lectura/escritura del grid (turnos, franjas, coordinación, aprobar, copiar...).
  const claveTurnos = ["rota", "turnos", lunes, marcaActiva] as const;
  // El rango (lun→dom) de la semana en vista para acotar las consultas.
  const desde = lunes;
  const hasta = lunesSiguiente(lunes, 1); // exclusivo
  // La cobertura se acota a la marca activa (multi-tenant por `rota_eventos.marca`); la
  // marca entra en la queryKey para refrescar al cambiar de workspace. `null` ("Todas",
  // admin) = sin filtro -> `marca` ausente en la query.
  // La rejilla (capacidad + cobertura + ausencias) se pinta tanto en «Calendario» como en
  // «Gestión» (junto al panel de asignar), así que cobertura/tareas/ausencias cargan en ambos.
  const coberturaQ = useQuery({
    queryKey: ["rota", "cobertura", lunes, marcaActiva] as const,
    queryFn: ({ signal }) =>
      api.cobertura({ lunes, marca: marcaActiva ?? undefined }, signal),
  });
  // Tareas de cobertura (clase='tarea' con evento_id): la TITULARIDAD real, quién COGIÓ
  // cada evento. Es la MISMA fuente que el Panorama (mismo queryKey → cache compartida y se
  // invalida igual al coger/soltar), así calendario y Panorama dicen lo mismo.
  const tareasQ = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marcaActiva ?? "todas"],
    queryFn: ({ signal }) =>
      api.contenido({ clase: "tarea", marca: marcaActiva ?? undefined }, signal),
  });
  const turnosQ = useQuery({
    queryKey: claveTurnos,
    queryFn: ({ signal }) =>
      api.listarTurnos({ lunes, marca: marcaActiva ?? undefined }, signal),
  });
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"] as const,
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
  });

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: ["rota"] });

  // `equipo` para la edición avanzada del chip (DialogEditarTurno admite reasignar a
  // cualquier miembro de la rota), y `cms` para el dropdown «Añadir turno»: el equipo de
  // cobertura de la marca activa (coordinadores incluidos), en paridad con los carriles por
  // persona del Panorama.
  const equipo = filtrarEquipoPorMarca(equipoQ.data?.equipo ?? [], marcaActiva);
  const cms = cmsDeMarca(equipoQ.data?.equipo ?? [], marcaActiva);
  const semana = turnosQ.data;
  const turnos = React.useMemo(() => semana?.turnos ?? [], [semana?.turnos]);
  // Franjas vivas de la semana, ordenadas por `orden` (la franja Descanso suele ir al
  // final con orden=999). Memo para evitar re-cálculos.
  const franjasSemana = React.useMemo(
    () => (semana?.franjas ?? []).slice().sort((a, b) => a.orden - b.orden),
    [semana?.franjas],
  );

  // Las 7 fechas de la semana (lun → dom). Memo para estabilidad referencial.
  // `diasDeSemana` ancla a mediodía UTC, siguiendo la convención CDMX de lib/fecha +
  // rota-calendario (el resto de helpers de fecha).
  const dias = React.useMemo(() => diasDeSemana(lunes), [lunes]);

  // Diálogo de cobertura: clicar un chip de evento abre su tarjeta de cobertura (la MISMA del
  // Panorama) para coger/«Asignar a…»/soltar/editar sin salir del calendario. La edición del
  // evento vive ahora en el kebab de esa tarjeta, no en un modal de edición aparte.
  const [eventoCobertura, setEventoCobertura] = React.useState<EventoRota | null>(null);
  // «Resumen del día»: pulsar la cabecera de un día abre un panel con TODO lo de esa jornada
  // (eventos+cobertura, personal de turno, huecos/tareas, horas y avisos). Guarda la fecha abierta.
  const [diaResumen, setDiaResumen] = React.useState<string | null>(null);
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  // Diálogo de franjas (unificado): un solo «Franjas» en el menú «Más» con dos pestañas
  // (esta semana / plantilla por defecto).
  const [abrirFranjas, setAbrirFranjas] = React.useState(false);
  // Resumen "Carga del equipo": se abre bajo demanda desde el menú "Más" (popup), para no
  // alargar la vista.
  const [abrirCarga, setAbrirCarga] = React.useState(false);
  // «Asignar turnos»: reparte la semana (persona → franja → días) sin ir celda por celda. En la
  // rejilla SEMANAL de «Gestión» el panel arranca ABIERTO (columna lateral): al pasar del overview
  // mensual a «Semana», repartir es la acción directa, sin un clic previo. El botón de la cabecera
  // solo lo oculta/muestra.
  const [abrirAsignar, setAbrirAsignar] = React.useState(modo === "gestion");

  // Copiar la semana anterior. GRID POR MARCA: muta UNA rejilla -> exige marca concreta; en
  // "Todas" (marcaActiva null) mandamos "" y el backend responde 400 accionable.
  const marcaRejilla = marcaActiva ?? "";
  const copiarAnterior = useMutation({
    mutationFn: () =>
      api.copiarSemana({
        de_lunes: lunesSiguiente(lunes, -1),
        a_lunes: lunes,
        reemplazar: false,
        marca: marcaRejilla,
      }),
    onSuccess: (res) => {
      toast.success(`Copiados ${res.copiados ?? 0} turnos de la semana anterior.`);
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Eventos con su cobertura derivada (el backend ya excluyó los `no_cubrir`).
  const eventosCobertura = React.useMemo(
    () => (coberturaQ.data?.eventos ?? []).filter((e) => e.fecha >= desde && e.fecha < hasta),
    [coberturaQ.data?.eventos, desde, hasta],
  );

  // Personas que trabajan cada (franja_id, fecha) según los turnos publicados.
  const personasPorCelda = React.useMemo(() => {
    const m = new Map<string, TurnoRota[]>();
    for (const t of turnos) {
      const k = `${t.franja_id}|${t.fecha}`;
      const lista = m.get(k) ?? [];
      lista.push(t);
      m.set(k, lista);
    }
    // Orden estable por nombre para que los recuadros no salten entre renders.
    for (const lista of m.values()) {
      lista.sort((a, b) => a.miembro_nombre.localeCompare(b.miembro_nombre));
    }
    return m;
  }, [turnos]);

  // Ausencias que solapan con la semana.
  const finSemana = dias[6] ?? desde;
  const ausenciasSemana = (ausenciasQ.data?.ausencias ?? []).filter(
    (a) => a.desde <= finSemana && a.hasta >= desde,
  );
  const ausenciasPorDia = new Map<string, AusenciaRota[]>();
  for (const fecha of dias) {
    const lista = ausenciasSemana.filter((a) => ausenciaTocaDia(a, fecha));
    if (lista.length > 0) {
      lista.sort((x, y) => {
        if (x.tipo !== y.tipo) return x.tipo.localeCompare(y.tipo);
        return (x.miembro_nombre || "").localeCompare(y.miembro_nombre || "");
      });
      ausenciasPorDia.set(fecha, lista);
    }
  }

  // Índice por miembro para resolver rápido "¿esta persona tiene ausencia este día?".
  const ausenciasPorMiembro = React.useMemo(() => {
    const m = new Map<string, AusenciaRota[]>();
    for (const a of ausenciasQ.data?.ausencias ?? []) {
      const lista = m.get(a.miembro_id) ?? [];
      lista.push(a);
      m.set(a.miembro_id, lista);
    }
    return m;
  }, [ausenciasQ.data?.ausencias]);
  const ausenciaDe = React.useCallback(
    (miembroId: string, fecha: string): AusenciaRota | undefined =>
      (ausenciasPorMiembro.get(miembroId) ?? []).find(
        (a) => a.desde <= fecha && fecha <= a.hasta,
      ),
    [ausenciasPorMiembro],
  );

  // Turnos indexados por (miembro_id, fecha): base para detectar SOLAPES (la misma
  // persona ya con un turno ese día en otra franja que comparte horas con la candidata).
  const turnosPorMiembroFecha = React.useMemo(() => {
    const m = new Map<string, TurnoRota[]>();
    for (const t of turnos) {
      const k = `${t.miembro_id}|${t.fecha}`;
      const lista = m.get(k) ?? [];
      lista.push(t);
      m.set(k, lista);
    }
    return m;
  }, [turnos]);
  const franjaPorId = React.useMemo(() => {
    const m = new Map<string, FranjaSemana>();
    for (const f of franjasSemana) m.set(f.id, f);
    return m;
  }, [franjasSemana]);

  // Aviso inline NO bloqueante al asignar: ¿la persona está de ausencia ese día, o ya
  // tiene un turno que solapa? El admin lo ve en el dropdown y puede forzar igualmente.
  const conflictoCandidato = React.useCallback(
    (miembroId: string, fecha: string, franja: FranjaSemana): ConflictoCandidato => {
      const ausencia = ausenciaDe(miembroId, fecha);
      let solapa = false;
      if (!franja.es_descanso) {
        const susTurnos = turnosPorMiembroFecha.get(`${miembroId}|${fecha}`) ?? [];
        solapa = susTurnos.some((t) => {
          if (t.franja_id === franja.id) return false; // misma celda: no es un solape nuevo
          const otra = franjaPorId.get(t.franja_id);
          return Boolean(otra && !otra.es_descanso && franjasSolapan(franja, otra));
        });
      }
      return { ausencia, solapa };
    },
    [ausenciaDe, turnosPorMiembroFecha, franjaPorId],
  );

  // TITULARIDAD: quién COGIÓ cada evento, derivada de las tareas de cobertura (la MISMA
  // fuente que el Panorama) y NO de quién está de turno. La cobertura derivada de turnos
  // (`evento.cobertura`) metería el evento bajo CADA persona de la franja, duplicándolo y
  // descuadrándolo respecto al Panorama; así ambos coinciden.
  // Ref estable (no un literal nuevo por render) para no invalidar los memos que dependen de ella.
  const tareas = React.useMemo(() => tareasQ.data?.contenidos ?? [], [tareasQ.data?.contenidos]);
  // PROPUESTAS de calendario: tareas sueltas CON fecha (sin evento) aún sin terminar. No entran
  // directas a la rejilla como un evento; esperan en la bandeja de notificaciones del calendario
  // hasta que alguien las ACEPTA (se promueven a evento «Por cubrir»). Mismo criterio que el
  // `aceptar` del backend (clase=tarea + fecha_objetivo + sin evento_id).
  const propuestas = React.useMemo(
    () =>
      tareas.filter(
        (t) => !t.evento_id && (t.fecha_objetivo || "").trim() !== "" && t.estado !== "hecha",
      ),
    [tareas],
  );
  // Catálogos (usuarios) para las tarjetas de cobertura del diálogo del chip.
  const catalogos = tareasQ.data?.catalogos;
  // Una sola pasada de `agrupar`: de ella derivamos los cubridores por evento (para el chip) y
  // la cobertura completa por evento (para la tarjeta del diálogo, igual que el Panorama).
  const coberturas = React.useMemo(
    () => agrupar(tareas, eventosCobertura).coberturas,
    [tareas, eventosCobertura],
  );
  const cubridoresPorEvento = React.useMemo(() => {
    const m = new Map<string, CubridorEvento[]>();
    for (const c of coberturas) {
      m.set(
        c.eventoId,
        c.cubridores.map((t) => ({ id: t.responsable_id, nombre: t.responsable_nombre })),
      );
    }
    return m;
  }, [coberturas]);
  const coberturaPorEventoId = React.useMemo(() => {
    const m = new Map<string, Cobertura>();
    for (const c of coberturas) m.set(c.eventoId, c);
    return m;
  }, [coberturas]);

  // Cada evento UNA sola vez en su celda: franja por su HORA, día por su FECHA. Con su
  // titularidad real; sin cubridores = «Por cubrir» (lo pinta el chip). Si la semana aún no
  // tiene franjas (race) o la hora no cae en ninguna, el evento se pierde de la rejilla.
  const eventosPorCelda = React.useMemo(() => {
    const m = new Map<string, ItemEventoCalendario[]>(); // clave: `${franja_id}|${fecha}`
    for (const evento of eventosCobertura) {
      const franjaId = franjaIdParaHoraEvento(evento.hora, franjasSemana);
      if (!franjaId) continue;
      const clave = `${franjaId}|${evento.fecha}`;
      const lista = m.get(clave) ?? [];
      lista.push({ evento, cubridores: cubridoresPorEvento.get(evento.id) ?? [] });
      m.set(clave, lista);
    }
    // Orden estable por hora dentro de la celda.
    for (const lista of m.values()) {
      lista.sort((a, b) => (a.evento.hora || "").localeCompare(b.evento.hora || ""));
    }
    return m;
  }, [eventosCobertura, franjasSemana, cubridoresPorEvento]);

  // Eventos que no caen en ninguna franja (la semana aún no tiene franjas): en vez de perderlos,
  // van a una fila «Sin franja» por día, donde siguen siendo cubribles. Clave: fecha.
  const eventosSinFranjaPorDia = React.useMemo(() => {
    const m = new Map<string, ItemEventoCalendario[]>();
    for (const evento of eventosFueraDeFranja(eventosCobertura, franjasSemana)) {
      const lista = m.get(evento.fecha) ?? [];
      lista.push({ evento, cubridores: cubridoresPorEvento.get(evento.id) ?? [] });
      m.set(evento.fecha, lista);
    }
    for (const lista of m.values()) {
      lista.sort((a, b) => (a.evento.hora || "").localeCompare(b.evento.hora || ""));
    }
    return m;
  }, [eventosCobertura, franjasSemana, cubridoresPorEvento]);

  const inicio = semana?.inicio ?? coberturaQ.data?.inicio ?? dias[0] ?? "";
  const fin = semana?.fin ?? coberturaQ.data?.fin ?? dias[6] ?? "";
  const nCambiados = eventosCobertura.filter((e) => e.cambiado).length;
  // «Sin cubrir» = hueco REAL: ni lo cogió nadie NI hay turno en su franja ese día. Si hay turno,
  // lo cubre quien esté de turno (no cuenta como hueco). Lo deriva el selector canónico
  // (`resumenCobertura` → estado `sin-cubrir`), la misma fuente que el Panorama; el calendario
  // muestra UNA semana, así que sus `turnos`/`franjas` (ids por semana) son seguros para el
  // bucketing plano. Mismo criterio que pinta el chip.
  const nSinCubrir = resumenCobertura(
    eventosCobertura,
    tareas,
    turnos,
    franjasSemana,
    undefined,
    ausenciasSemana,
  ).sinCubrir;
  const hoy = hoyCDMX();
  // `editable` = admin (la edición de la rota es solo-coordinador; sin paso de aprobación, lo
  // asignado ya lo ve el equipo). Los CMs no admin ven la vista en solo-lectura. La edición es
  // inline: «Añadir turno» da de alta capacidad y el chip de turno abre su menú
  // (Editar/Duplicar/Eliminar). La COBERTURA se asigna desde el Panorama.
  const editable = esAdmin;
  const cargando =
    coberturaQ.isPending ||
    turnosQ.isPending ||
    ausenciasQ.isPending ||
    equipoQ.isPending;
  const error =
    coberturaQ.error || turnosQ.error || ausenciasQ.error || equipoQ.error;

  // Conmutador Semana|Mes (palabras, outline gris): visible en ambos modos.
  const conmutadorVista = (
    <ToggleGroup
      ariaLabel="Vista del calendario"
      valor={vista}
      onCambio={setVista}
      opciones={[
        { valor: "semana", etiqueta: "Semana" },
        { valor: "mes", etiqueta: "Mes" },
      ]}
    />
  );

  // «Gestión» (admin) comparte el MISMO render que «Calendario» (abajo): la rejilla viva, pero con
  // cabecera de gestión (asignar/franjas/copiar/carga/export) y el panel de reparto como columna
  // lateral junto a la rejilla para repartir mirando el calendario en vivo. Ramas por `esGestion`
  // dentro del return común.
  const esGestion = modo === "gestion";

  // Modo «Mes»: el calendario MENSUAL de jornada (la antigua «Mi jornada»), con su Yo/Equipo e
  // imprimir/PDF intactos. Es la vista de APERTURA de «Gestión» (overview del mes): ahí llena el
  // alto de su contenedor con el conmutador fijo arriba y el mes con scroll interno; en
  // «Calendario» crece a su alto natural y la página hace scroll. El vacío de «Yo» salta a «Semana».
  if (vista === "mes") {
    const mensual = <VistaMensualTurnos esAdmin={esAdmin} onVerSemana={() => setVista("semana")} />;
    return esGestion ? (
      <div className="flex h-full min-h-0 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">{conmutadorVista}</div>
        <div className="min-h-0 flex-1 overflow-auto">{mensual}</div>
      </div>
    ) : (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">{conmutadorVista}</div>
        {mensual}
      </div>
    );
  }

  return (
    // En AMBOS modos el componente RELLENA el viewport (columna flex, cabecera arriba y la
    // rejilla ocupando el resto con scroll interno). «Gestión» hereda el alto de su contenedor
    // (`h-full`, lo acota index.tsx); «Calendario» lo fija él mismo a `calc(100dvh-5.5rem)` (=
    // 100dvh − topbar `h-12` − padding del `<main>`), el mismo presupuesto que Gestión, para que
    // la rejilla baje hasta el pie de la pantalla y no deje hueco muerto debajo.
    <div className={`flex min-h-0 flex-col gap-4 ${esGestion ? "h-full" : "h-[calc(100dvh-5.5rem)]"}`}>
      {/* Cabecera. En «Gestión», el conmutador Semana|Mes (para volver al overview mensual) +
          navegador de semana + el toggle del panel de reparto + el menú «Más»; en «Calendario», el
          conmutador Semana|Mes + navegador + avisos de la semana. La leyenda se ofrece con el "?". */}
      {esGestion ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {conmutadorVista}
            <NavegadorSemana lunes={lunes} setLunes={setLunes} inicio={inicio} fin={fin} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* Oculta/muestra el panel de reparto (columna lateral, no un modal). Arranca abierto:
                lo asignado ya lo ve el equipo (sin paso de aprobación), así que repartir es la
                acción directa de esta pestaña. */}
            <Button
              variant="outline"
              onClick={() => setAbrirAsignar((v) => !v)}
              aria-pressed={abrirAsignar}
            >
              <CalendarPlus className="h-4 w-4" /> Asignar turnos
            </Button>
            <MenuMasAcciones
              esAdmin={esAdmin}
              semanaAprobada={false}
              copiarPendiente={copiarAnterior.isPending}
              onCopiarAnterior={() => copiarAnterior.mutate()}
              onAbrirFranjas={() => setAbrirFranjas(true)}
              onAbrirCarga={() => setAbrirCarga(true)}
              onExportExcel={() => api.exportarRota("xlsx", { lunes, marca: marcaActiva ?? undefined })}
              onExportCsv={() => api.exportarRota("csv", { lunes, marca: marcaActiva ?? undefined })}
            />
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {conmutadorVista}
            <NavegadorSemana lunes={lunes} setLunes={setLunes} inicio={inicio} fin={fin} />
            <AyudaLeyenda />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* Bandeja de propuestas: aceptar una promueve a evento «Por cubrir» (acción de
                coordinador) → solo admin. El estado de la semana (Borrador/Publicada) vive en Gestión. */}
            {esAdmin && <PropuestasCalendario propuestas={propuestas} />}
            {/* Aviso de coordinador (reprogramados sin avisar): solo admin; el trabajador no lo acciona. */}
            {esAdmin && nCambiados > 0 && (
              <Tooltip
                label={`${nCambiados} evento${nCambiados === 1 ? "" : "s"} reprogramado${
                  nCambiados === 1 ? "" : "s"
                } sin aviso.`}
              >
                <Badge variant="aviso" className="gap-1 font-normal">
                  <BellRing className="h-3.5 w-3.5" /> {nCambiados}
                </Badge>
              </Tooltip>
            )}
            {nSinCubrir > 0 && (
              <Tooltip
                label={`${nSinCubrir} evento${nSinCubrir === 1 ? "" : "s"} sin cubrir esta semana (sin nadie de turno en su franja).`}
              >
                <Badge
                  variant="outline"
                  className="gap-1 border-yellow-500/50 font-normal text-yellow-700 dark:text-yellow-300"
                >
                  <UserPlus className="h-3.5 w-3.5" /> {nSinCubrir} sin cubrir
                </Badge>
              </Tooltip>
            )}
            {/* Asignar/Aprobar/Despublicar/Franjas/Copiar/Carga/Export viven en la pestaña
                «Gestión» (admin); el Calendario es consulta + edición de celdas. */}
          </div>
        </div>
      )}
      {/* Split: la rejilla ocupa el ancho (flex-1) y crece en vertical (min-h-0 flex-1) hasta el pie.
          En Gestión con el panel abierto, el reparto se acomoda a la derecha SIN tapar la rejilla (la
          columna lateral); cerrado, la rejilla vuelve a ancho completo. En «Calendario» no hay panel:
          es solo la rejilla. */}
      <div className="flex min-h-0 flex-1 gap-4">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {cargando ? (
        <Skeleton className="h-[60vh] w-full rounded-md" />
      ) : error ? (
        <BloqueError
          titulo="No se pudo cargar el calendario"
          mensaje={mensajeError(error)}
          // `invalidar` invalida la clave `["rota"]` -> refetch de todas las queries activas
          // de la rota, así el reintento recarga toda la familia (cobertura/turnos/ausencias/
          // equipo) y no deja ninguna atascada.
          onReintentar={invalidar}
          cargando={
            coberturaQ.isFetching ||
            turnosQ.isFetching ||
            ausenciasQ.isFetching ||
            equipoQ.isFetching
          }
        />
      ) : (
        <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <CardContent className="flex min-h-0 flex-1 flex-col p-0">
            {/* Rejilla principal: 1 cabecera con días + 1 fila por franja viva. En AMBOS modos
                rellena (`flex-1`) el hueco que le deja la columna flex y guarda su scroll interno;
                las franjas laborales crecen (`grow`) y reparten el sobrante. En «Calendario»
                `min-w-[56rem]` mantiene legibilidad horizontal; en «Gestión» NO hay ancho mínimo
                (`min-w-0`) para que la rejilla quepa junto al panel sin scroll lateral. */}
            <div className="min-h-0 flex-1 overflow-auto">
              <div className={esGestion ? "flex min-h-full min-w-0 flex-col" : "flex min-h-full min-w-[56rem] flex-col"}>
                {/* Cabecera de días (sticky para que no se pierda al hacer scroll). */}
                <div className="sticky top-0 z-10 grid grid-cols-[8rem_repeat(7,minmax(0,1fr))] gap-px border-b bg-background">
                  <div className="bg-background px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Franja
                  </div>
                  {dias.map((fecha) => {
                    const ausDia = ausenciasPorDia.get(fecha) ?? [];
                    const finde = esFinDeSemana(fecha);
                    const esHoy = fecha === hoy;
                    return (
                      <div
                        key={fecha}
                        className={`flex flex-col gap-1 px-2 py-2 ${
                          esHoy
                            ? "bg-keni-50/70 ring-1 ring-inset ring-keni-500/40 dark:bg-keni-900/20"
                            : finde
                              ? "bg-muted/60 dark:bg-muted/30"
                              : "bg-background"
                        }`}
                      >
                        {/* La cabecera (nombre + número) es un botón: abre el «Resumen del día». La
                            fila de ausencias queda FUERA del botón (no anidar interactivos). */}
                        <button
                          type="button"
                          onClick={() => setDiaResumen(fecha)}
                          aria-label={`Ver el resumen del ${formatearFechaCorta(fecha) || fecha}`}
                          className="-mx-1 flex items-baseline justify-between rounded px-1 py-0.5 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <span
                            className={`text-xs font-semibold capitalize ${
                              esHoy ? "text-keni-700 dark:text-keni-300" : ""
                            }`}
                          >
                            {diaCorto(fecha)}
                            {esHoy && (
                              <span className="ml-1 font-normal normal-case text-keni-600 dark:text-keni-300">
                                · Hoy
                              </span>
                            )}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {fecha.slice(8, 10)}
                          </span>
                        </button>
                        {ausDia.length > 0 && (
                          <div
                            className="flex flex-wrap gap-1"
                            aria-label={`Ausencias del ${fecha}`}
                          >
                            {ausDia.slice(0, 2).map((a) => (
                              <ChipAusenciaDia key={a.id} ausencia={a} />
                            ))}
                            {ausDia.length > 2 && (
                              <MasAusencias ausencias={ausDia.slice(2)} />
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Filas: una por franja viva. Borde superior grueso para marcar el cambio. */}
                {(() => {
                  let indiceLaboral = 0;
                  return franjasSemana.map((franja, idx) => {
                    const idxLab = franja.es_descanso ? -1 : indiceLaboral++;
                    const meta = presentacionFranja(franja, idxLab);
                    return (
                      <div
                        key={franja.id}
                        className={`grid grid-cols-[8rem_repeat(7,minmax(0,1fr))] gap-px ${
                          franja.es_descanso ? "" : "grow"
                        } ${idx > 0 ? "border-t-4 border-t-border" : ""}`}
                      >
                        {/* Etiqueta de franja (sticky a la izquierda para scroll horizontal). */}
                        <div
                          className={`sticky left-0 z-[1] flex flex-col justify-center border-l-4 px-3 py-3 text-sm font-semibold ${meta.banda} ${meta.fondo}`}
                        >
                          <span className="flex items-center gap-1.5">
                            {franja.es_descanso ? (
                              <Sunset className="h-3.5 w-3.5 text-muted-foreground" />
                            ) : idxLab === 0 ? (
                              <Sunrise className="h-3.5 w-3.5 text-muted-foreground" />
                            ) : (
                              <Sunset className="h-3.5 w-3.5 text-muted-foreground" />
                            )}
                            {franja.nombre}
                          </span>
                          <span className="text-xs font-normal text-muted-foreground">
                            {franja.es_descanso
                              ? "(descanso)"
                              : `${franja.inicio}–${franja.fin}`}
                          </span>
                          {/* GRID POR MARCA: en "Todas" (marcaActiva null) se apilan las rejillas
                              de varias marcas; etiquetamos cada franja (columna) con su marca. */}
                          {marcaActiva === null && franja.marca_nombre ? (
                            <Badge
                              variant="outline"
                              className="mt-1 w-fit px-1.5 py-0 text-[10px] font-normal"
                            >
                              {franja.marca_nombre}
                            </Badge>
                          ) : null}
                        </div>
                        {dias.map((fecha) => {
                          const personas =
                            personasPorCelda.get(`${franja.id}|${fecha}`) ?? [];
                          const eventos =
                            eventosPorCelda.get(`${franja.id}|${fecha}`) ?? [];
                          // CMs que se pueden añadir aquí: los de la marca que no estén ya
                          // de turno en esta celda. La franja Descanso también admite alta
                          // (turno de no-laboral explícito).
                          const yaEnCelda = new Set(personas.map((t) => t.miembro_id));
                          const cmsDisponibles = cms.filter((m) => !yaEnCelda.has(m.id));
                          return (
                            <CeldaDeRejilla
                              key={`${franja.id}-${fecha}`}
                              lunes={lunes}
                              fecha={fecha}
                              franja={franja}
                              franjasSemana={franjasSemana}
                              personas={personas}
                              /* «Gestión» = rejilla de CAPACIDAD pura: solo turnos, sin los chips
                                 de eventos/cobertura (esos viven en «Calendario»/«Cobertura»). */
                              eventos={esGestion ? [] : eventos}
                              equipo={equipo}
                              cmsDisponibles={cmsDisponibles}
                              editable={editable}
                              finde={esFinDeSemana(fecha)}
                              ausenciaDe={ausenciaDe}
                              conflictoCandidato={conflictoCandidato}
                              onEditarEvento={(e) => setEventoCobertura(e)}
                              onCambio={invalidar}
                            />
                          );
                        })}
                      </div>
                    );
                  });
                })()}
                {/* Eventos que no caen en ninguna franja (semana sin franjas configuradas): se
                    muestran aquí en vez de perderse, y siguen siendo cubribles desde su chip. En
                    «Gestión» no se pintan eventos (rejilla de turnos pura). */}
                {!esGestion && eventosSinFranjaPorDia.size > 0 && (
                  <div className="grid grid-cols-[8rem_repeat(7,minmax(0,1fr))] gap-px border-t-4 border-t-amber-300 dark:border-t-amber-700">
                    <div className="sticky left-0 z-[1] flex flex-col justify-center border-l-4 border-l-amber-400 bg-amber-50/40 px-3 py-3 text-sm font-semibold dark:bg-amber-950/15">
                      <span className="flex items-center gap-1.5">
                        <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                        Sin franja
                      </span>
                      <span className="text-xs font-normal text-muted-foreground">
                        configura las franjas
                      </span>
                    </div>
                    {dias.map((fecha) => (
                      <div
                        key={`sinfranja-${fecha}`}
                        className={`flex min-h-[5rem] flex-col gap-1 border-l p-2 ${
                          esFinDeSemana(fecha) ? "bg-amber-50/20 dark:bg-amber-950/5" : ""
                        }`}
                      >
                        {(eventosSinFranjaPorDia.get(fecha) ?? []).map((item) => (
                          <ChipEventoCalendario
                            key={item.evento.id}
                            item={item}
                            cubrenPorTurno={[]}
                            onClick={() => setEventoCobertura(item.evento)}
                            onCambio={invalidar}
                          />
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
        </div>
        {/* Panel de Gestión como columna lateral (solo admin). Cerrado no pinta nada (la rejilla
            recupera el ancho). Tres bloques, de más usado a menos: reparto MANUAL (comparte estado
            con la rejilla → cada turno aparece al instante), «Cambios y ausencias», y al FINAL el
            reparto automático desde un documento (la última opción). */}
        {esGestion && abrirAsignar && (
          <aside
            aria-label="Asignar turnos"
            className="flex h-full min-h-0 w-[26rem] shrink-0 flex-col gap-4 overflow-y-auto"
          >
            <DialogoAsignarTurnos
              incrustado
              abierto
              onOpenChange={setAbrirAsignar}
              lunes={lunes}
              dias={dias}
              franjas={franjasSemana}
              cms={cms}
              onCambio={invalidar}
            />
            <section
              aria-label="Cambios y ausencias"
              className="rounded-lg border bg-card p-4 shadow-sm"
            >
              <h2 className="mb-3 text-base font-semibold">Cambios y ausencias</h2>
              <CambiosYAusencias esAdmin={esAdmin} />
            </section>
            {/* Reparto automático: la ÚLTIMA opción, al fondo. Sube una parrilla/Excel/foto y Keni
                propone los turnos; al aplicar, la rejilla se refresca (no cierra el panel). */}
            <div className="space-y-2 rounded-lg border border-dashed border-border p-4">
              <div className="flex items-center gap-1.5 text-sm font-medium">
                <Sparkles className="h-4 w-4 text-primary" />
                Automático: de un documento
              </div>
              <p className="text-xs text-muted-foreground">
                ¿Tienes una parrilla, un Excel o una foto? Súbela y Keni propone los turnos; los
                revisas antes de aplicar. Es la última opción si no quieres repartir a mano.
              </p>
              <ImportarDocumentoParrilla marca={marcaActiva ?? ""} onAplicado={invalidar} />
            </div>
          </aside>
        )}
      </div>

      {/* Modales solo de «Gestión»: editar franjas y ver la carga del equipo. */}
      {esGestion && abrirFranjas && (
        <DialogFranjas
          lunes={lunes}
          onCerrar={() => setAbrirFranjas(false)}
          onAsignar={
            editable
              ? () => {
                  setAbrirFranjas(false);
                  setAbrirAsignar(true);
                }
              : undefined
          }
        />
      )}
      {esGestion && abrirCarga && (
        <DialogCargaEquipo lunes={lunes} onCerrar={() => setAbrirCarga(false)} />
      )}

      {/* Diálogo de cobertura del chip: la MISMA tarjeta del Panorama (coger/«Asignar a…»/
          soltar/editar/borrar en su kebab). Si el evento ya tiene cubridores → TarjetaCobertura;
          si no → TarjetaEventoLibre. Ambas invalidan CLAVE_TAREAS al mutar, así `tareasQ` (misma
          clave) se refresca y el chip se actualiza solo. */}
      {eventoCobertura && (
        <Dialog open onOpenChange={(o) => !o && setEventoCobertura(null)}>
          <DialogContent
            // El kebab, el sub-diálogo «Asignar a…»/«Editar» y la confirmación de borrado se
            // portalizan a <body>: una interacción que venga de ellos no debe cerrar este diálogo.
            onInteractOutside={(e) => {
              const t = e.detail.originalEvent.target as HTMLElement | null;
              if (interaccionEnCapaHija(t)) e.preventDefault();
            }}
          >
            <DialogHeader>
              <DialogTitle>{eventoCobertura.titulo}</DialogTitle>
            </DialogHeader>
            {coberturaPorEventoId.get(eventoCobertura.id) ? (
              <TarjetaCobertura
                cobertura={coberturaPorEventoId.get(eventoCobertura.id)!}
                catalogos={catalogos}
              />
            ) : (
              <TarjetaEventoLibre evento={eventoCobertura} catalogos={catalogos} />
            )}
          </DialogContent>
        </Dialog>
      )}

      {/* «Resumen del día»: panel con todo lo de la jornada pulsada (su propia derivación de
          cobertura por fecha vía `useTablero`). */}
      {diaResumen && (
        <ResumenDia
          fecha={diaResumen}
          marca={marcaActiva ?? undefined}
          usuarioId={usuario?.id ?? null}
          onClose={() => setDiaResumen(null)}
        />
      )}

    </div>
  );
}
