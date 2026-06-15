import { useQuery } from "@tanstack/react-query";
import { ListChecks, Plus, Trophy } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { hoyCDMX } from "@/lib/fecha";

import { CLAVE_TAREAS } from "./claves";
import { DialogoCrearTarea } from "./DialogoCrearTarea";
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
    })),
  ].sort((a, b) => a.orden.localeCompare(b.orden));

  // ¿«por cubrir»? (evento sin cubridores o encargo sin dueño). ¿«mío»? (cobertura que cubro o
  // encargo mío) — una cobertura es mía si soy UNO de sus cubridores (multi-cobertura).
  const esPorCubrir = (i: Item) =>
    i.kind === "evento" || (i.kind === "tarea" && !i.tarea.responsable_id);
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

  // Tres grupos para que «se organice»: lo que falta por cubrir, lo que está en marcha, lo hecho.
  const grupos: { etiqueta: string; items: Item[] }[] = [
    { etiqueta: "Por cubrir", items: visibles.filter(esPorCubrir) },
    {
      etiqueta: "En marcha",
      items: visibles.filter(
        (i) =>
          i.kind === "cobertura" ||
          (i.kind === "tarea" && i.tarea.responsable_id && i.tarea.estado !== "hecha"),
      ),
    },
    {
      etiqueta: "Hechas",
      items: visibles.filter((i) => i.kind === "tarea" && i.tarea.estado === "hecha"),
    },
  ];

  const pintar = (i: Item) =>
    i.kind === "evento" ? (
      <TarjetaEventoLibre key={i.clave} evento={i.evento} catalogos={catalogos} />
    ) : i.kind === "cobertura" ? (
      <div key={i.clave} className="rounded-lg border border-border bg-card p-3 shadow-sm">
        <div className="mb-2 flex items-center gap-2">
          <Trophy className="h-4 w-4 shrink-0 text-muted-foreground" />
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
      <div className="rounded-lg border border-dashed border-border p-8 text-center">
        <p className="text-sm text-muted-foreground">
          No tienes nada asignado. Coge algo de «Por cubrir» en Panorama.
        </p>
      </div>
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
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : (
          <>
            <TabsContent value="panorama">
              <PanoramaAgenda
                tareas={tareas}
                eventos={eventosCoverables}
                catalogos={catalogos}
                marca={marca}
                esAdmin={usuario?.rol === "admin"}
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
