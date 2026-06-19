// Pestaña CALENDARIO de la rota (rejilla semanal de turnos + cobertura derivada).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  CalendarOff,
  CalendarPlus,
  CheckCircle2,
  Loader2,
  Sunrise,
  Sunset,
  UserPlus,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Tooltip } from "@/components/ui/tooltip";
import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
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
import {
  AyudaLeyenda,
  BadgeEstadoSemana,
  ChipAusenciaDia,
  MasAusencias,
  MenuMasAcciones,
  NavegadorSemana,
  ausenciaTocaDia,
  filtrarEquipoPorMarca,
  franjaIdParaHoraEvento,
  franjasSolapan,
  presentacionFranja,
  type ConflictoCandidato,
  type CubridorEvento,
  type ItemEventoCalendario,
} from "./comun";
import { DialogoAsignarTurnos } from "./DialogoAsignarTurnos";
import { DialogFranjas } from "./Franjas";
import { VistaMensualTurnos } from "./MisTurnos";
import { PropuestasCalendario } from "./PropuestasCalendario";
import { CLAVE_TAREAS } from "@/pages/tareas/claves";
import { TarjetaCobertura, TarjetaEventoLibre } from "@/pages/tareas/tarjetas";
import { agrupar, type Cobertura } from "@/pages/tareas/tipos";


/** Modo de vista del Calendario: la rejilla SEMANAL (franjas×días) o el calendario MENSUAL
 *  de jornada (la antigua «Mi jornada», con su Yo/Equipo e imprimir/PDF). */
type VistaCalendario = "semana" | "mes";

export function Calendario({
  lunes,
  setLunes,
  esAdmin,
  vistaInicial = "semana",
}: {
  lunes: string;
  setLunes: (l: string) => void;
  esAdmin: boolean;
  /** Modo de apertura. Por defecto «Semana» (rejilla actual); «mes» lo usan los deep-links
   *  legacy a la antigua pestaña «Mi jornada». */
  vistaInicial?: VistaCalendario;
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
  // `diasDeSemana` ancla a mediodía UTC (antes aquí se parseaba T00:00:00 en zona
  // LOCAL del navegador, a diferencia del resto de helpers de fecha: corregido a la
  // convención CDMX de lib/fecha + rota-calendario).
  const dias = React.useMemo(() => diasDeSemana(lunes), [lunes]);

  // Diálogo de cobertura: clicar un chip de evento abre su tarjeta de cobertura (la MISMA del
  // Panorama) para coger/«Asignar a…»/soltar/editar sin salir del calendario. La edición del
  // evento vive ahora en el kebab de esa tarjeta, no en un modal de edición aparte.
  const [eventoCobertura, setEventoCobertura] = React.useState<EventoRota | null>(null);
  // Diálogo de franjas (unificado): un solo «Franjas» en el menú «Más» con dos pestañas
  // (esta semana / plantilla por defecto). Antes eran dos items sueltos que se confundían.
  const [abrirFranjas, setAbrirFranjas] = React.useState(false);
  // Resumen "Carga del equipo": antes vivía como panel colapsable bajo el calendario;
  // ahora se abre bajo demanda desde el menú "Más" (popup), para no alargar la vista.
  const [abrirCarga, setAbrirCarga] = React.useState(false);
  // «Asignar turnos»: reparte la semana (persona → franja → días) desde la cabecera, sin ir
  // celda por celda. Solo admin + semana en borrador (mismo gating que el resto de edición).
  const [abrirAsignar, setAbrirAsignar] = React.useState(false);

  // Mutaciones de cabecera (de la antigua pestaña Turnos): aprobar / despublicar /
  // copiar semana anterior. Sin cambios funcionales — sólo migradas aquí.
  // GRID POR MARCA: aprobar/despublicar/copiar mutan UNA rejilla -> exigen marca concreta.
  // En "Todas" (marcaActiva null) mandamos "" y el backend responde 400 accionable.
  const marcaRejilla = marcaActiva ?? "";
  const aprobar = useMutation({
    mutationFn: () => api.aprobarTurnos({ lunes, marca: marcaRejilla }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveTurnos, res);
      toast.success(res.mensaje ?? "Turnos publicados al equipo.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const despublicar = useMutation({
    mutationFn: () => api.despublicarTurnos({ lunes, marca: marcaRejilla }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveTurnos, res);
      toast.success(res.mensaje ?? "Semana despublicada: vuelve a borrador.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

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
  // fuente que el Panorama) y NO de quién está de turno. Antes el calendario usaba la
  // cobertura DERIVADA de turnos (`evento.cobertura`): metía el evento bajo CADA persona
  // de la franja → salía duplicado y no coincidía con el Panorama. Ahora coinciden.
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
  ).sinCubrir;
  const hoy = hoyCDMX();
  // `editable` requiere admin + semana no aprobada. Los CMs no admin siempre ven la vista
  // en solo-lectura. La edición es inline: «Añadir turno» da de alta capacidad y el chip de
  // turno abre su menú (Editar/Duplicar/Eliminar). La COBERTURA se asigna desde el Panorama.
  const editable = esAdmin && !semana?.aprobada;
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

  // Modo «Mes»: el calendario MENSUAL de jornada (la antigua «Mi jornada»), con su Yo/Equipo e
  // imprimir/PDF intactos. El conmutador queda arriba; el vacío de «Yo» salta a «Semana».
  if (vista === "mes") {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">{conmutadorVista}</div>
        <VistaMensualTurnos esAdmin={esAdmin} onVerSemana={() => setVista("semana")} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Cabecera SLIM (ola "cabecera-slim"): conmutador Semana|Mes + NavegadorSemana + ayuda a
          la izquierda; a la derecha el estado de la semana, el aviso de reprogramaciones, la
          accion primaria (Aprobar/Despublicar) y un menu "Mas" con el resto. La leyenda dejo de
          vivir siempre visible bajo la cabecera; se ofrece bajo demanda con el icono "?". */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {conmutadorVista}
          <NavegadorSemana lunes={lunes} setLunes={setLunes} inicio={inicio} fin={fin} />
          <AyudaLeyenda />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Bandeja de propuestas: tareas con fecha esperando entrar al calendario. Solo se
              pinta si hay alguna; aceptar una la promueve a evento «Por cubrir». */}
          <PropuestasCalendario propuestas={propuestas} />
          <BadgeEstadoSemana
            aprobada={Boolean(semana?.aprobada)}
            hayTurnos={turnos.length > 0}
          />
          {nCambiados > 0 && (
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
                className="gap-1 border-amber-500/50 font-normal text-amber-700 dark:text-amber-300"
              >
                <UserPlus className="h-3.5 w-3.5" /> {nSinCubrir} sin cubrir
              </Badge>
            </Tooltip>
          )}
          {/* «Asignar turnos» (reparto de la semana) es botón primario junto a Aprobar; el «⋯»
              queda para acciones secundarias. */}
          {esAdmin && !semana?.aprobada && (
            <Button variant="outline" onClick={() => setAbrirAsignar(true)}>
              <CalendarPlus className="h-4 w-4" /> Asignar turnos
            </Button>
          )}
          {esAdmin && !semana?.aprobada && (
            <Button
              variant="secondary"
              onClick={() => aprobar.mutate()}
              disabled={aprobar.isPending || turnos.length === 0}
            >
              {aprobar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              Aprobar y publicar
            </Button>
          )}
          {esAdmin && semana?.aprobada && (
            <Button
              variant="outline"
              onClick={async () => {
                if (
                  await confirmar({
                    mensaje:
                      "La semana volverá a ser editable. ¿Despublicar los turnos?",
                    destructivo: true,
                    textoConfirmar: "Despublicar",
                  })
                )
                  despublicar.mutate();
              }}
              disabled={despublicar.isPending}
              title="Volver a borrador para editar"
            >
              {despublicar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CalendarOff className="h-4 w-4" />
              )}
              Despublicar
            </Button>
          )}
          {/* «Importar documento» ya no es un botón suelto aquí: vive dentro de «Asignar
              turnos» como su vía automática (ver DialogoAsignarTurnos). */}
          <MenuMasAcciones
            esAdmin={esAdmin}
            semanaAprobada={Boolean(semana?.aprobada)}
            copiarPendiente={copiarAnterior.isPending}
            onCopiarAnterior={() => copiarAnterior.mutate()}
            onAbrirFranjas={() => setAbrirFranjas(true)}
            onAbrirCarga={() => setAbrirCarga(true)}
            onExportExcel={() => api.exportarRota("xlsx", { lunes, marca: marcaActiva ?? undefined })}
            onExportCsv={() => api.exportarRota("csv", { lunes, marca: marcaActiva ?? undefined })}
          />
        </div>
      </div>

      {abrirFranjas && (
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
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            {/* Rejilla principal: 1 cabecera con días + 1 fila por franja viva.
                Altura FIJA `calc(100dvh-14rem)` (no `max-h`) para que la rejilla LLENE el alto
                disponible: las franjas laborales crecen (`grow`) y reparten el hueco sobrante en
                vez de dejar un vacío debajo. Si la semana es densa el contenido desborda y este
                contenedor hace scroll interno. `min-w-[56rem]` mantiene legibilidad horizontal. */}
            <div className="overflow-auto" style={{ height: "calc(100dvh - 14rem)" }}>
              <div className="flex min-h-full min-w-[56rem] flex-col">
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
                              ? "bg-amber-50/40 dark:bg-amber-950/10"
                              : "bg-background"
                        }`}
                      >
                        <div className="flex items-baseline justify-between">
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
                        </div>
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
                              eventos={eventos}
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
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Diálogo de cobertura del chip: la MISMA tarjeta del Panorama (coger/«Asignar a…»/
          soltar/editar/borrar en su kebab). Si el evento ya tiene cubridores → TarjetaCobertura;
          si no → TarjetaEventoLibre. Ambas invalidan CLAVE_TAREAS al mutar, así `tareasQ` (misma
          clave) se refresca y el chip se actualiza solo. */}
      {eventoCobertura && (
        <Dialog open onOpenChange={(o) => !o && setEventoCobertura(null)}>
          <DialogContent>
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

      {abrirCarga && (
        <DialogCargaEquipo lunes={lunes} onCerrar={() => setAbrirCarga(false)} />
      )}

      <DialogoAsignarTurnos
        abierto={abrirAsignar}
        onOpenChange={setAbrirAsignar}
        lunes={lunes}
        dias={dias}
        franjas={franjasSemana}
        cms={cms}
        marca={marcaActiva ?? ""}
        onCambio={invalidar}
      />
    </div>
  );
}
