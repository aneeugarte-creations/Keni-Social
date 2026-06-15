// Pestaña CALENDARIO de la rota (rejilla semanal de turnos + cobertura derivada).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  CalendarOff,
  CheckCircle2,
  Loader2,
  Sunrise,
  Sunset,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Tooltip } from "@/components/ui/tooltip";
import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import {
  diaCorto,
  diasDeSemana,
  esFinDeSemana,
  lunesSiguiente,
} from "@/lib/rota-calendario";
import { ImportarDocumentoParrilla } from "@/components/parrilla/ImportarDocumentoParrilla";
import type {
  AusenciaRota,
  CoordinacionTurno,
  EventoRota,
  FranjaSemana,
  TurnoRota,
} from "@/types";

import { CeldaDeRejilla, cmsDeMarca, DialogCargaEquipo, DialogEditarEvento } from "./CalendarioPiezas";
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
  type RecuadroPersona,
} from "./comun";
import { DialogConfigFranjas, DialogFranjasDeSemana } from "./Franjas";


export function Calendario({
  lunes,
  setLunes,
  esAdmin,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  esAdmin: boolean;
}) {
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
  const turnosQ = useQuery({
    queryKey: claveTurnos,
    queryFn: ({ signal }) =>
      api.listarTurnos({ lunes, marca: marcaActiva ?? undefined }, signal),
  });
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });
  // Equipo completo (incluye sin cobertura): necesario para resolver candidatos a
  // coordinador (ola "coord") como la coordinadora operativa o fotografía/QA, que tienen `cobertura=false`.
  const equipoTodosQ = useQuery({
    queryKey: ["rota", "equipo", "todos"],
    queryFn: ({ signal }) => api.rotaEquipoTodos(signal),
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"] as const,
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
  });
  // Coordinador por celda (ola "coord"): un PUT por celda, lista por semana.
  const coordinacionQ = useQuery({
    queryKey: ["rota", "coordinacion", lunes, marcaActiva] as const,
    queryFn: ({ signal }) =>
      api.listarCoordinacionSemana(lunes, marcaActiva ?? undefined, signal),
  });

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: ["rota"] });

  // `equipo` para la edición avanzada del chip (DialogEditarTurno admite reasignar a
  // cualquier miembro de la rota), y `cms` para el dropdown "+ Añadir persona" (sólo
  // CMs activos de la marca activa). Mismo desglose que la rejilla Turnos anterior.
  const equipo = filtrarEquipoPorMarca(equipoQ.data?.equipo ?? [], marcaActiva);
  const cms = cmsDeMarca(equipoQ.data?.equipo ?? [], marcaActiva);
  // Candidatos a coordinador (ola "coord"): usuarios con `puede_coordinar=true`. Se
  // sacan del equipo COMPLETO (no solo cobertura) porque hoy son el coordinador de redes
  // (cubre), fotografía/QA y la coordinadora operativa (NO cubren). El admin gestiona el flag desde /usuarios.
  const candidatosCoordinador = React.useMemo(
    () => (equipoTodosQ.data?.equipo ?? []).filter((m) => m.puede_coordinar),
    [equipoTodosQ.data?.equipo],
  );
  // Index de coordinaciones por (fecha|franja_id) -> CoordinacionTurno.
  const coordinacionPorCelda = React.useMemo(() => {
    const m = new Map<string, CoordinacionTurno>();
    for (const c of coordinacionQ.data?.coordinacion ?? []) {
      m.set(`${c.fecha}|${c.franja_id}`, c);
    }
    return m;
  }, [coordinacionQ.data?.coordinacion]);
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

  // Modal de edición rápida (chip click → edita el evento sin salir del calendario).
  const [eventoSeleccionado, setEventoSeleccionado] = React.useState<EventoRota | null>(null);
  // Diálogos de franjas: antes los abrían sus propios botones (BotonConfigFranjas /
  // BotonFranjasDeSemana). Tras la slimificación de la cabecera ahora se invocan desde
  // el menú "Más", así que la apertura se gobierna desde aquí.
  const [abrirFranjasSemana, setAbrirFranjasSemana] = React.useState(false);
  const [abrirPlantillaFranjas, setAbrirPlantillaFranjas] = React.useState(false);
  // Resumen "Carga del equipo": antes vivía como panel colapsable bajo el calendario;
  // ahora se abre bajo demanda desde el menú "Más" (popup), para no alargar la vista.
  const [abrirCarga, setAbrirCarga] = React.useState(false);

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

  // Turnos indexados por (franja_id, fecha, miembro_id) → TurnoRota. Sirve para que el
  // recuadro persona conserve el id del turno (para borrar/duplicar) sin volver a
  // buscar. También lo usamos para construir la lista de personas por celda.
  const turnoPorCelda = React.useMemo(() => {
    const m = new Map<string, TurnoRota>();
    for (const t of turnos) m.set(`${t.franja_id}|${t.fecha}|${t.miembro_id}`, t);
    return m;
  }, [turnos]);

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

  // Itera los eventos y los reparte en su (franja_id, fecha) → persona/sin-cubrir.
  // - Con cobertura: cada cubridor entra en el recuadro de su persona (su `franja_id`
  //   ya viene resuelto por el backend, así que la asignación es directa).
  // - Sin turno a esa hora: el evento cae en un recuadro etiquetado "Sin turno a esa
  //   hora" en la franja que su hora resuelve contra las franjas vivas de la semana.
  //   Mide CAPACIDAD (nadie trabaja esa franja), NO es el "Por cubrir" del tablero
  //   Cobertura (evento que nadie ha reclamado). Si la semana aún no tiene franjas
  //   (race), el evento se pierde de la rejilla — caso raro, sin franjas no hay rejilla.
  const recuadrosPorCelda = React.useMemo(() => {
    const m = new Map<string, RecuadroPersona[]>(); // clave: `${franja_id}|${fecha}`
    // Primero las personas que trabajan cada celda (aunque no tengan eventos).
    for (const franja of franjasSemana) {
      for (const fecha of dias) {
        const personas = personasPorCelda.get(`${franja.id}|${fecha}`) ?? [];
        const lista: RecuadroPersona[] = personas.map((t) => ({
          miembro_id: t.miembro_id,
          miembro_nombre: t.miembro_nombre,
          turno: t,
          sinCubrir: false,
          eventos: [],
        }));
        m.set(`${franja.id}|${fecha}`, lista);
      }
    }
    // Coloca cada evento en su recuadro.
    for (const evento of eventosCobertura) {
      if (evento.cobertura.length === 0) {
        const franjaId = franjaIdParaHoraEvento(evento.hora, franjasSemana);
        if (!franjaId) continue;
        const clave = `${franjaId}|${evento.fecha}`;
        const lista = m.get(clave) ?? [];
        let recuadroSin = lista.find((r) => r.sinCubrir);
        if (!recuadroSin) {
          recuadroSin = {
            miembro_id: "",
            // Etiqueta no mostrada (el render usa copy fijo "Sin turno a esa hora"); se
            // deja coherente para no reintroducir el ambiguo "Sin cubrir" por grep.
            miembro_nombre: "Sin turno a esa hora",
            turno: null,
            sinCubrir: true,
            eventos: [],
          };
          lista.push(recuadroSin);
        }
        recuadroSin.eventos.push({ evento, cobertura: [] });
        m.set(clave, lista);
        continue;
      }

      for (const cob of evento.cobertura) {
        const clave = `${cob.franja_id}|${evento.fecha}`;
        const lista = m.get(clave) ?? [];
        const recuadro = lista.find(
          (r) => !r.sinCubrir && r.miembro_id === cob.miembro_id,
        );
        if (recuadro) {
          recuadro.eventos.push({ evento, cobertura: evento.cobertura });
        } else {
          // El backend devolvió una cobertura cuyo miembro no aparece en `turnosQ`
          // para esa (franja_id, fecha). Caso raro (carrera de invalidaciones); lo
          // metemos como persona del cubridor para no perder el dato. `turno` queda
          // null porque no tenemos el TurnoRota local; el menú de CRUD del recuadro
          // se desactiva (sólo se ven los chips de evento).
          const turnoLocal =
            turnoPorCelda.get(`${cob.franja_id}|${evento.fecha}|${cob.miembro_id}`) ??
            null;
          lista.push({
            miembro_id: cob.miembro_id,
            miembro_nombre: cob.miembro_nombre,
            turno: turnoLocal,
            sinCubrir: false,
            eventos: [{ evento, cobertura: evento.cobertura }],
          });
        }
        m.set(clave, lista);
      }
    }
    return m;
  }, [eventosCobertura, dias, personasPorCelda, franjasSemana, turnoPorCelda]);

  const inicio = semana?.inicio ?? coberturaQ.data?.inicio ?? dias[0] ?? "";
  const fin = semana?.fin ?? coberturaQ.data?.fin ?? dias[6] ?? "";
  const nCambiados = eventosCobertura.filter((e) => e.cambiado).length;
  // `editable` requiere admin + semana no aprobada. Los CMs no admin siempre ven la vista
  // en solo-lectura. La edición es inline: click en el chip abre el menú (Editar/Duplicar/
  // Eliminar); click en "Sin turno asignado" o "Sin turno a esa hora" abre el dropdown.
  const editable = esAdmin && !semana?.aprobada;
  const cargando =
    coberturaQ.isPending ||
    turnosQ.isPending ||
    ausenciasQ.isPending ||
    equipoQ.isPending ||
    coordinacionQ.isPending;
  const error =
    coberturaQ.error || turnosQ.error || ausenciasQ.error || equipoQ.error ||
    coordinacionQ.error;

  return (
    <div className="space-y-4">
      {/* Cabecera SLIM (ola "cabecera-slim"): NavegadorSemana + ayuda a la izquierda; a la
          derecha el estado de la semana, el aviso de reprogramaciones, la accion primaria
          (Aprobar/Despublicar) y un menu "Mas" con el resto. La leyenda dejo de vivir
          siempre visible bajo la cabecera; se ofrece bajo demanda con el icono "?". */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <NavegadorSemana lunes={lunes} setLunes={setLunes} inicio={inicio} fin={fin} />
          <AyudaLeyenda />
        </div>
        <div className="flex flex-wrap items-center gap-2">
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
          {esAdmin && (
            <ImportarDocumentoParrilla onAplicado={invalidar} />
          )}
          <MenuMasAcciones
            esAdmin={esAdmin}
            semanaAprobada={Boolean(semana?.aprobada)}
            copiarPendiente={copiarAnterior.isPending}
            onCopiarAnterior={() => copiarAnterior.mutate()}
            onAbrirFranjasSemana={() => setAbrirFranjasSemana(true)}
            onAbrirPlantillaFranjas={() => setAbrirPlantillaFranjas(true)}
            onAbrirCarga={() => setAbrirCarga(true)}
            onExportExcel={() => api.exportarRota("xlsx", { lunes, marca: marcaActiva ?? undefined })}
            onExportCsv={() => api.exportarRota("csv", { lunes, marca: marcaActiva ?? undefined })}
          />
        </div>
      </div>

      {abrirFranjasSemana && (
        <DialogFranjasDeSemana
          lunes={lunes}
          onCerrar={() => setAbrirFranjasSemana(false)}
        />
      )}
      {abrirPlantillaFranjas && (
        <DialogConfigFranjas onCerrar={() => setAbrirPlantillaFranjas(false)} />
      )}

      {cargando ? (
        <Skeleton className="h-[60vh] w-full rounded-md" />
      ) : error ? (
        <BloqueError
          titulo="No se pudo cargar el calendario"
          mensaje={mensajeError(error)}
          // `error` incluye `coordinacionQ.error`, así que el reintento debe recargar TODA la
          // familia de queries de la rota (incl. coordinación): refetchear solo cobertura/
          // turnos/ausencias/equipo dejaba el error de coordinación atascado. `invalidar`
          // invalida la clave `["rota"]` -> refetch de todas las queries activas.
          onReintentar={invalidar}
          cargando={
            coberturaQ.isFetching ||
            turnosQ.isFetching ||
            ausenciasQ.isFetching ||
            equipoQ.isFetching ||
            coordinacionQ.isFetching
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            {/* Rejilla principal: 1 cabecera con días + 1 fila por franja viva.
                `max-h-[calc(100vh-18rem)]` aprovecha el alto disponible con scroll interno
                si la semana se sale de pantalla; `min-w-[56rem]` mantiene legibilidad. */}
            <div className="overflow-auto" style={{ maxHeight: "calc(100dvh - 18rem)" }}>
              <div className="min-w-[56rem]">
                {/* Cabecera de días (sticky para que no se pierda al hacer scroll). */}
                <div className="sticky top-0 z-10 grid grid-cols-[8rem_repeat(7,minmax(0,1fr))] gap-px border-b bg-background">
                  <div className="bg-background px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Franja
                  </div>
                  {dias.map((fecha) => {
                    const ausDia = ausenciasPorDia.get(fecha) ?? [];
                    const finde = esFinDeSemana(fecha);
                    return (
                      <div
                        key={fecha}
                        className={`flex flex-col gap-1 px-2 py-2 ${
                          finde ? "bg-amber-50/40 dark:bg-amber-950/10" : "bg-background"
                        }`}
                      >
                        <div className="flex items-baseline justify-between">
                          <span className="text-xs font-semibold capitalize">
                            {diaCorto(fecha)}
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
                          idx > 0 ? "border-t-4 border-t-border" : ""
                        }`}
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
                          const recuadros =
                            recuadrosPorCelda.get(`${franja.id}|${fecha}`) ?? [];
                          // CMs disponibles para añadir aquí: los de ClaroSports que no
                          // estén ya asignados a esta celda. La franja Descanso también
                          // admite asignaciones (turno de no-laboral explícito).
                          const yaEnCelda = new Set(
                            recuadros
                              .filter((r) => !r.sinCubrir && r.miembro_id)
                              .map((r) => r.miembro_id),
                          );
                          const cmsDisponibles = cms.filter(
                            (m) => !yaEnCelda.has(m.id),
                          );
                          const coordinacionCelda = coordinacionPorCelda.get(
                            `${fecha}|${franja.id}`,
                          );
                          return (
                            <CeldaDeRejilla
                              key={`${franja.id}-${fecha}`}
                              lunes={lunes}
                              fecha={fecha}
                              franja={franja}
                              recuadros={recuadros}
                              equipo={equipo}
                              cmsDisponibles={cmsDisponibles}
                              editable={editable}
                              finde={esFinDeSemana(fecha)}
                              ausenciaDe={ausenciaDe}
                              conflictoCandidato={conflictoCandidato}
                              coordinacion={coordinacionCelda}
                              candidatosCoordinador={candidatosCoordinador}
                              coordinacionEditable={esAdmin && !semana?.aprobada}
                              onEditarEvento={(e) => setEventoSeleccionado(e)}
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

      {eventoSeleccionado && (
        <DialogEditarEvento
          evento={eventoSeleccionado}
          onCerrar={() => setEventoSeleccionado(null)}
          onCambio={invalidar}
        />
      )}

      {abrirCarga && (
        <DialogCargaEquipo lunes={lunes} onCerrar={() => setAbrirCarga(false)} />
      )}
    </div>
  );
}

/**
 * Badge de COORDINADOR por celda (ola "coord"): muestra "Coord: <nombre>" o "Sin coord".
 * Click (si editable) abre un Select con los candidatos (`puede_coordinar=true`); la X
 * inline (solo si hay coordinador y editable) borra la asignación. Si la semana está
 * aprobada o el usuario no es admin, queda en modo solo-lectura (sin Select ni X).
 */
