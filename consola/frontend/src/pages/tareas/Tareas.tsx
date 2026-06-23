import { ListChecks, Plus } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, type OpcionToggle } from "@/components/ui/toggle-group";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { mensajeError } from "@/lib/api";
import { posicionTemporal } from "@/lib/fecha";
import { PropuestasCalendario } from "@/pages/rota/PropuestasCalendario";

import { DialogoCrearTarea } from "./DialogoCrearTarea";
import { VistaEquipo } from "./equipo";
import { KpiCobertura } from "./KpiCobertura";
import { PanoramaAgenda } from "./PanoramaAgenda";
import { TarjetaCoberturaMia, TarjetaEventoLibre, TarjetaTarea } from "./tarjetas";
import { type Item } from "./tipos";
import { useTablero } from "./useTablero";

/** Segmento «Todo | Mis tareas | Equipo» sobre la MISMA lista: «Todo» es la agenda de equipo;
 * «Mis tareas» es lo mío agrupado; «Equipo» (solo manager) desglosa lo de cada persona. «Por
 * cubrir» NO es un segmento: vive como el chip ámbar dentro de «Todo». El valor interno «panorama»
 * se conserva; solo la etiqueta es «Todo». */
type Lente = "panorama" | "mias" | "equipo";

/**
 * TABLERO de Tareas del equipo: la lista compartida que sustituye al WhatsApp. Cuerpo reutilizable
 * (sin título) para montarlo en su página suelta (`/operacion/tareas`) o dentro de Turnos
 * (pestaña «Cobertura»). La derivación de datos vive en `useTablero` (compartida con la home «Hoy»).
 *
 * `acciones`: dónde va «Añadir». "barra" lo portaliza arriba; "inline" lo pinta junto al segmento.
 */
export function TareasBoard({ acciones = "barra" }: { acciones?: "barra" | "inline" }) {
  const { marcaActiva } = useMarcaActiva();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  // «Equipo» es una lente de coordinación: la ve quien reparte (mismo gate que «Asignar a…»).
  const esManager = usuario?.rol === "admin";
  const marca = marcaActiva && marcaActiva !== MARCA_ACTIVA_TODAS ? marcaActiva : undefined;
  const [lente, setLente] = React.useState<Lente>("panorama");
  const [crearAbierto, setCrearAbierto] = React.useState(false);
  const [filtroPanorama, setFiltroPanorama] = React.useState<string | null>(null);

  const {
    cargando, hayError, sinDatos, reintentar, error, isFetching,
    catalogos, tareas, eventosCoverables, cubiertosPorTurno, ausencias,
    eventosHoy, claimsCobertura, turnosHoy, franjasHoy, hechasHoy,
    items, esPorCubrir, esMio,
  } = useTablero(marca, usuario?.id ?? null);

  const visibles = items.filter((i) => (lente === "mias" ? esMio(i) : true));

  // PROPUESTAS de calendario: tareas sueltas CON fecha (sin evento) aún sin terminar. Esperan en
  // la campana hasta que un coordinador las ACEPTA (se promueven a evento «Por cubrir»). Es el
  // mismo criterio que el `aceptar` del backend; antes vivía en la cabecera del calendario de
  // Turnos, ahora aquí (los eventos/tareas viven en «Trabajo»). Solo manager.
  const propuestas = React.useMemo(
    () =>
      tareas.filter(
        (t) => !t.evento_id && (t.fecha_objetivo || "").trim() !== "" && t.estado !== "hecha",
      ),
    [tareas],
  );
  const campanaPropuestas = esManager ? <PropuestasCalendario propuestas={propuestas} /> : null;

  // Una cobertura cuyo evento YA pasó está hecha: cae a «Hechas», no «En marcha».
  const coberturaPasada = (i: Item) =>
    i.kind === "cobertura" && posicionTemporal(i.cobertura.orden, i.cobertura.hora) === "despues";

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
        cubridoresPorTurno={i.cubridoresPorTurno ?? []}
      />
    ) : i.kind === "cobertura" ? (
      <TarjetaCoberturaMia key={i.clave} cobertura={i.cobertura} />
    ) : (
      <TarjetaTarea key={i.clave} tarea={i.tarea} catalogos={catalogos} />
    );

  const listaAgrupada =
    visibles.length === 0 ? (
      <EstadoVacio
        icono={ListChecks}
        titulo="No tienes nada asignado"
        texto="Ve a «Todo» y pulsa «Por cubrir» para cubrir trabajo del equipo."
        accion={
          <Button size="sm" variant="outline" onClick={() => setLente("panorama")}>
            Ver todo
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

  const opcionesLente: OpcionToggle<Lente>[] = [
    { valor: "panorama", etiqueta: "Todo" },
    { valor: "mias", etiqueta: "Mis tareas" },
    ...(esManager ? [{ valor: "equipo" as const, etiqueta: "Equipo" }] : []),
  ];

  return (
    <>
      {acciones === "barra" && (
        <AccionesPagina>
          {campanaPropuestas}
          {botonAnadir}
        </AccionesPagina>
      )}

      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <ToggleGroup
            ariaLabel="Vista de cobertura"
            valor={lente}
            onCambio={setLente}
            opciones={opcionesLente}
          />
          <div className="flex items-center gap-3">
            {/* «Cobertura de hoy» como lectura inline colgada del margen de las pestañas (sustituye
                la tarjeta-KPI suelta de antes). Solo con datos ya cargados: durante la carga aún no
                hay resumen, y con error-sin-caché manda el bloque de error. */}
            {!cargando && !(hayError && sinDatos) && (
              <KpiCobertura
                variant="linea"
                eventos={eventosHoy}
                claims={claimsCobertura}
                turnos={turnosHoy}
                franjas={franjasHoy}
                ausencias={ausencias}
                hechas={hechasHoy}
                onIrASinCubrir={() => {
                  setLente("panorama");
                  setFiltroPanorama("__pool__");
                }}
              />
            )}
            {acciones === "inline" && campanaPropuestas}
            {acciones === "inline" && botonAnadir}
          </div>
        </div>

        {hayError && sinDatos ? (
          <BloqueError
            titulo="No se pudo cargar el tablero"
            mensaje={mensajeError(error)}
            onReintentar={reintentar}
            cargando={isFetching}
          />
        ) : cargando ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        ) : lente === "panorama" ? (
          <PanoramaAgenda
            tareas={tareas}
            eventos={eventosCoverables}
            catalogos={catalogos}
            marca={marca}
            cubiertosPorTurno={cubiertosPorTurno}
            filtro={filtroPanorama}
            setFiltro={setFiltroPanorama}
          />
        ) : lente === "equipo" ? (
          <VistaEquipo items={items} />
        ) : (
          listaAgrupada
        )}
      </div>

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
