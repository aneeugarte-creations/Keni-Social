import { useQueries, useQuery } from "@tanstack/react-query";
import { ListChecks, Plus } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { derivarCoberturaEvento } from "@/lib/cobertura";
import { hoyCDMX, posicionTemporal } from "@/lib/fecha";
import { lunesSiguiente } from "@/lib/rota-calendario";
import type { RotaSemana } from "@/types";

import { CLAVE_TAREAS } from "./claves";
import { DialogoCrearTarea } from "./DialogoCrearTarea";
import { IconoEvento } from "./icono-evento";
import { KpiCobertura } from "./KpiCobertura";
import { PanoramaAgenda } from "./PanoramaAgenda";
import { TarjetaCobertura, TarjetaEventoLibre, TarjetaTarea } from "./tarjetas";
import { agrupar, type Item } from "./tipos";

// El tablero es COMPARTIDO: late al mismo pulso para que el claim/asignación de un compañero
// se vea sin recargar (igual que el reparto del feed que esto sustituye).
const REFRESCO = { refetchInterval: 45_000, refetchOnWindowFocus: true };

/** Lente sobre la MISMA lista: el panorama (agenda de equipo) o lo mío. «Por cubrir» NO es una
 * lente: ya vive como el chip ámbar dentro de Panorama (que filtra a lo pendiente, por día). */
type Lente = "panorama" | "mias";
const LENTES: { id: Lente; etiqueta: string }[] = [
  { id: "panorama", etiqueta: "Panorama" },
  { id: "mias", etiqueta: "Mis tareas" },
];

/**
 * TABLERO de Tareas del equipo (ClaroSports): la lista compartida que sustituye al WhatsApp.
 * Es el CUERPO reutilizable —SIN título de página— para montarlo tanto en su página suelta
 * (`/operacion/tareas`) como dentro de Turnos (pestaña «Cobertura»).
 *
 * Se LLENA SOLA con los eventos/partidos a cubrir (los que entran por Fuentes o se añaden aquí)
 * y los muestra ordenados por fecha como «Por cubrir»; el equipo los coge o el coordinador de la rota los reparte.
 * Conviven los encargos sueltos (tareas sin evento). El dueño de una cobertura se registra como
 * una tarea (clase='tarea') enlazada al evento: el evento es la unidad canónica, sin duplicar.
 *
 * `acciones`: dónde va el botón «Añadir». "barra" (default, página suelta) lo portaliza a la
 * barra superior vía AccionesPagina; "inline" (dentro de Turnos) lo pinta junto a las pestañas.
 */
export function TareasBoard({ acciones = "barra" }: { acciones?: "barra" | "inline" }) {
  const { marcaActiva } = useMarcaActiva();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const [lente, setLente] = React.useState<Lente>("panorama");
  const [crearAbierto, setCrearAbierto] = React.useState(false);
  // Filtro del Panorama (id de persona, "__pool__" o null), aquí arriba para que el KPI de cabecera
  // pueda activar «Por cubrir» («N sin cubrir») y el Panorama lo lea controlado.
  const [filtroPanorama, setFiltroPanorama] = React.useState<string | null>(null);

  const marca = marcaActiva && marcaActiva !== MARCA_ACTIVA_TODAS ? marcaActiva : undefined;
  // El día de HOY en CDMX (no el UTC): `new Date().toISOString()` da el día UTC, que de 18:00 a
  // medianoche CDMX (UTC-6) ya es MAÑANA — justo el horario de partidos — y filtraría `desde` a
  // mañana, perdiendo los eventos de hoy del fetch.
  const hoy = hoyCDMX();

  const tareasQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marca ?? "todas"],
    queryFn: ({ signal }) => api.contenido({ clase: "tarea", marca }, signal),
    ...REFRESCO,
  });
  const eventosQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "eventos", marca ?? "todas"],
    queryFn: ({ signal }) => api.rotaEventos({ desde: hoy, marca }, signal),
    ...REFRESCO,
  });

  const tareas = tareasQuery.data?.contenidos ?? [];
  const catalogos = tareasQuery.data?.catalogos;
  const cargando = tareasQuery.isLoading || eventosQuery.isLoading;

  // Este tablero SUSTITUYE al WhatsApp: un fetch fallido NO puede disfrazarse de «todo cubierto»
  // (las listas caen a [] y se pinta «no hay nada que cubrir»). Si alguna query falla y aún no hay
  // datos cacheados que mostrar, pintamos error + reintento en vez de un tablero engañosamente vacío.
  const hayError = tareasQuery.isError || eventosQuery.isError;
  const sinDatos = !tareasQuery.data || !eventosQuery.data;
  const reintentar = () => {
    void tareasQuery.refetch();
    void eventosQuery.refetch();
  };

  // Reparte en coberturas (evento con ≥1 cubridor), encargos sueltos y eventos por cubrir.
  const eventosCoverables = eventosQuery.data?.eventos ?? [];
  const { coberturas, encargos, eventosLibres, recuperables } = agrupar(tareas, eventosCoverables);

  // Cobertura por TURNO (misma lógica que el calendario): el Panorama es multi-semana y no carga
  // turnos, así que pedimos los turnos de las (pocas) semanas que tocan los eventos mostrados. La
  // derivación cubierto-por-turno / hueco la hace el selector canónico (`derivarCoberturaEvento`);
  // carga parcial → se trata como NO cubierto («Sin cubrir») hasta que llega la semana.
  const semanasEventos = Array.from(
    new Set(eventosCoverables.filter((e) => e.fecha).map((e) => lunesSiguiente(e.fecha, 0))),
  );
  const semanasTurnos = useQueries({
    queries: semanasEventos.map((lunes) => ({
      queryKey: ["rota", "turnos", lunes, marca ?? "todas"],
      queryFn: ({ signal }: { signal?: AbortSignal }) => api.listarTurnos({ lunes, marca }, signal),
      ...REFRESCO,
    })),
  });
  const porLunes = new Map<string, RotaSemana>();
  semanasTurnos.forEach((q, i) => {
    if (q.data) porLunes.set(semanasEventos[i], q.data);
  });
  // Cobertura por turno de UN evento, vía el selector canónico y la rota de SU semana (las franjas
  // tienen id por semana, así que el bucketing y el solape se hacen sobre la semana del evento, no
  // mezclando semanas). Reusa `derivarCoberturaEvento`: nada de turno/franja reconstruido a mano.
  const rotaDe = (e: { fecha: string }): RotaSemana | undefined =>
    e.fecha ? porLunes.get(lunesSiguiente(e.fecha, 0)) : undefined;
  const cubiertosPorTurno = new Set<string>();
  for (const e of eventosCoverables) {
    const semana = rotaDe(e);
    if (!semana) continue;
    const d = derivarCoberturaEvento(e, [], semana.turnos, semana.franjas);
    if (d.estado === "cubierto-turno") cubiertosPorTurno.add(e.id);
  }
  // KPI de cabecera «Cobertura de hoy»: el resumen del selector sobre los eventos de HOY (CDMX).
  // Todos los de hoy comparten UNA semana, así que su rota (turnos+franjas) es una sola y el
  // `resumenCobertura` plano es exacto (los ids de franja son por semana). Sin fetches nuevos:
  // reusa eventos, claims (tareas con `evento_id`) y la rota ya cargada.
  const eventosHoy = eventosCoverables.filter((e) => e.fecha === hoy);
  const claimsCobertura = tareas.filter((t) => t.evento_id);
  const semanaHoy = porLunes.get(lunesSiguiente(hoy, 0));
  const turnosHoy = semanaHoy?.turnos ?? [];
  const franjasHoy = semanaHoy?.franjas ?? [];

  // «Hechas hoy» = trabajo del día ya resuelto, como dato NEUTRO secundario del KPI (no otra barra):
  // una cobertura cuyo partido YA pasó (mismo criterio temporal que el semáforo «Cubierto») o un
  // encargo/recuperable de hoy en «hecha». Mide otra cosa que `cubiertos` (titularidad), por eso va
  // aparte. Sin el filtro de persona: es un marcador estable de «cómo va el día».
  const esDeHoy = (fecha?: string | null) => (fecha || "").slice(0, 10) === hoy;
  const hechasHoy =
    coberturas.filter((c) => esDeHoy(c.orden) && posicionTemporal(c.orden, c.hora) === "despues")
      .length +
    [...encargos, ...recuperables].filter(
      (t) => esDeHoy(t.fecha_objetivo) && t.estado === "hecha",
    ).length;

  // Lista unificada, ordenada por fecha (las sin fecha, al final).
  const conOrden = (f: string) => f || "9999-99-99";
  const items: Item[] = [
    ...coberturas.map((c) => ({
      kind: "cobertura" as const,
      clave: `c-${c.eventoId}`,
      orden: conOrden(c.orden),
      cobertura: c,
    })),
    ...[...encargos, ...recuperables].map((t) => ({
      kind: "tarea" as const,
      clave: `t-${t.id}`,
      orden: conOrden(t.fecha_objetivo),
      tarea: t,
    })),
    ...eventosLibres.map((e) => ({
      kind: "evento" as const,
      clave: `e-${e.id}`,
      orden: conOrden(e.fecha),
      evento: e,
      cubiertoPorTurno: cubiertosPorTurno.has(e.id),
    })),
  ].sort((a, b) => a.orden.localeCompare(b.orden));

  // ¿«por cubrir»? (evento sin cubridores o encargo sin dueño). ¿«mío»? (cobertura que cubro o
  // encargo mío) — una cobertura es mía si soy UNO de sus cubridores (multi-cobertura).
  const esPorCubrir = (i: Item) =>
    (i.kind === "evento" && !i.cubiertoPorTurno) || (i.kind === "tarea" && !i.tarea.responsable_id);
  const esMio = (i: Item) => {
    if (!usuario) return false;
    return i.kind === "cobertura"
      ? i.cobertura.cubridores.some((t) => t.responsable_id === usuario.id)
      : i.kind === "tarea" && i.tarea.responsable_id === usuario.id;
  };

  const cumpleLente = (i: Item) => {
    if (lente === "mias") return esMio(i);
    return true;
  };
  const visibles = items.filter(cumpleLente);

  // Una cobertura cuyo evento YA pasó está hecha (se cubrió): cae a «Hechas», no «En marcha» —
  // mismo criterio temporal con el que el Panorama la saca de la carga activa.
  const coberturaPasada = (i: Item) =>
    i.kind === "cobertura" && posicionTemporal(i.cobertura.orden, i.cobertura.hora) === "despues";

  // Tres grupos para que «se organice»: lo que falta por cubrir, lo que está en marcha, lo hecho.
  const grupos: { etiqueta: string; items: Item[] }[] = [
    { etiqueta: "Sin cubrir", items: visibles.filter(esPorCubrir) },
    {
      etiqueta: "En marcha",
      items: visibles.filter(
        (i) =>
          (i.kind === "cobertura" && !coberturaPasada(i)) ||
          (i.kind === "evento" && i.cubiertoPorTurno) ||
          (i.kind === "tarea" && i.tarea.responsable_id && i.tarea.estado !== "hecha"),
      ),
    },
    {
      etiqueta: "Hechas",
      items: visibles.filter(
        (i) => coberturaPasada(i) || (i.kind === "tarea" && i.tarea.estado === "hecha"),
      ),
    },
  ];

  const pintar = (i: Item) =>
    i.kind === "evento" ? (
      <TarjetaEventoLibre
        key={i.clave}
        evento={i.evento}
        catalogos={catalogos}
        cubiertoPorTurno={i.cubiertoPorTurno ?? false}
      />
    ) : i.kind === "cobertura" ? (
      <div key={i.clave} className="rounded-lg border border-border bg-card p-3 shadow-sm">
        <div className="mb-2 flex items-center gap-2">
          <IconoEvento titulo={i.cobertura.titulo} className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="font-medium">{i.cobertura.titulo}</span>
        </div>
        <TarjetaCobertura cobertura={i.cobertura} catalogos={catalogos} />
      </div>
    ) : (
      <TarjetaTarea key={i.clave} tarea={i.tarea} catalogos={catalogos} />
    );

  // Lista agrupada (Por cubrir / En marcha / Hechas) que comparten «Por cubrir» y «Mis tareas».
  const listaAgrupada =
    visibles.length === 0 ? (
      <EstadoVacio
        icono={ListChecks}
        titulo="No tienes nada asignado"
        texto="Ve a Panorama y pulsa «Por cubrir» para cubrir trabajo del equipo."
        accion={
          <Button size="sm" variant="outline" onClick={() => setLente("panorama")}>
            Ver Panorama
          </Button>
        }
      />
    ) : (
      grupos.map((g) =>
        g.items.length === 0 ? null : (
          <section key={g.etiqueta} className="space-y-2">
            <h2 className="text-sm font-medium text-muted-foreground">
              {g.etiqueta}
              <span className="ml-1.5 tabular-nums">({g.items.length})</span>
            </h2>
            <div className="space-y-2">{g.items.map(pintar)}</div>
          </section>
        ),
      )
    );

  const botonAnadir = (
    <Button size="sm" variant="outline" onClick={() => setCrearAbierto(true)}>
      <Plus className="mr-1 h-4 w-4" />
      Añadir
    </Button>
  );

  return (
    <>
      {acciones === "barra" && <AccionesPagina>{botonAnadir}</AccionesPagina>}

      <Tabs value={lente} onValueChange={(v) => setLente(v as Lente)} className="space-y-4">
        <div className="flex items-center justify-between gap-2">
          <TabsList>
            {LENTES.map((l) => (
              <TabsTrigger key={l.id} value={l.id}>
                {l.etiqueta}
              </TabsTrigger>
            ))}
          </TabsList>
          {acciones === "inline" && botonAnadir}
        </div>

        {hayError && sinDatos ? (
          <BloqueError
            titulo="No se pudo cargar el tablero"
            mensaje={mensajeError(tareasQuery.error ?? eventosQuery.error)}
            onReintentar={reintentar}
            cargando={tareasQuery.isFetching || eventosQuery.isFetching}
          />
        ) : cargando ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        ) : (
          <>
            <TabsContent value="panorama" className="space-y-4">
              <KpiCobertura
                eventos={eventosHoy}
                claims={claimsCobertura}
                turnos={turnosHoy}
                franjas={franjasHoy}
                hechas={hechasHoy}
                onIrASinCubrir={() => setFiltroPanorama("__pool__")}
              />
              <PanoramaAgenda
                tareas={tareas}
                eventos={eventosCoverables}
                catalogos={catalogos}
                marca={marca}
                cubiertosPorTurno={cubiertosPorTurno}
                filtro={filtroPanorama}
                setFiltro={setFiltroPanorama}
              />
            </TabsContent>
            <TabsContent value="mias" className="space-y-4">
              {listaAgrupada}
            </TabsContent>
          </>
        )}
      </Tabs>

      <DialogoCrearTarea
        abierto={crearAbierto}
        onOpenChange={setCrearAbierto}
        catalogos={catalogos}
        marca={marca}
      />
    </>
  );
}

/** Página suelta `/operacion/tareas`: el tablero con su título en la barra superior. */
export default function Tareas() {
  return (
    <>
      <TituloPagina titulo="Tareas del equipo" icono={ListChecks} />
      <TareasBoard />
    </>
  );
}
