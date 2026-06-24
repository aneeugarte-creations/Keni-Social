import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Send } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { Aviso } from "@/components/comunes/Aviso";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FILTRO_TODOS, useFiltrosPublicacion } from "@/hooks/filtros-contenido-contexto";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import {
  PublicacionPestanaVista,
  ESTADO_SERVIDOR_DE_VISTA,
  useConteosFeed,
  VISTAS,
  vistaDesdeParam,
  type Vista,
} from "@/pages/feed/vistas";
import { CLAVE_PIEZAS } from "@/pages/piezas/claves";
import { DialogoEditar } from "@/pages/piezas/DialogoEditar";
import { VistaCalendario, rangoVisibleCalendario } from "@/pages/piezas/VistaCalendario";
import { VistaLista } from "@/pages/piezas/VistaLista";
import {
  PanelFiltrosLimpieza,
  type FiltrosLimpieza,
} from "@/pages/piezas/PanelFiltrosLimpieza";
import type { CategoriaPlanOpcion, FiltrosPiezas, OpcionesPiezas, Pieza } from "@/types";

const TAM_PAGINA = 30;

/** Filtros base de la LISTA (sin paginación): globales + los de limpieza por lotes. */
type FiltrosBase = Pick<
  FiltrosPiezas,
  | "marca"
  | "red"
  | "estado"
  | "origen"
  | "categoria"
  | "tipo"
  | "fuente"
  | "fase"
  | "antiguedad_h"
>;

/**
 * Parámetros de UNA página del FEED (lista, keyset/scroll infinito). La 1ª página llega con
 * `cursor` vacío: `feed:"1"` activa el modo keyset (sin él caería al modo COMPLETO y traería
 * todo de golpe). Pura y exportada para testear el cableado sin montar la página entera.
 */
export function paramsPaginaFeed(
  filtrosBase: FiltrosBase,
  cursor: string,
  tamPagina: number = TAM_PAGINA,
): FiltrosPiezas {
  return {
    ...filtrosBase,
    feed: "1",
    limite: String(tamPagina),
    cursor: cursor || undefined,
  };
}

/**
 * ¿Mostrar el banner "Publicación automática desactivada"? Solo con el posteo real APAGADO
 * y existiendo AL MENOS una pieza programada. Se basa en el TOTAL del servidor (no en las
 * páginas ya cargadas: con keyset la 1ª página puede no traer ninguna programada aunque las
 * haya). Pura y exportada para testearla sin montar la página.
 */
export function debeAvisarProgramadasSinSalir(
  publicarReal: boolean,
  totalProgramadas: number,
): boolean {
  return !publicarReal && totalProgramadas > 0;
}

/**
 * ¿Avisar de que el usuario no tiene marca asignada? Solo no-admins con la lista de
 * marcas CONOCIDA y vacía. OJO: `marcas` solo viaja en GET /auth/me; el login devuelve
 * la forma mínima SIN esa clave, así que `undefined` = "aún no lo sé" (sesión recién
 * creada), NO "sin marcas" — sin esta distinción todo editor veía el falso aviso
 * durante toda su sesión tras iniciarla. Pura y exportada para testearla sin montar.
 */
export function faltaMarcaAsignada(
  usuario: { rol: string; marcas?: string[] } | null,
): boolean {
  return (
    usuario !== null &&
    usuario.rol !== "admin" &&
    usuario.marcas !== undefined &&
    usuario.marcas.length === 0
  );
}

/**
 * GESTIÓN de piezas en dos modos: `lista` (paginada, con aprobar/editar) y
 * `calendario` (rejilla mensual de programadas, sin paginación ni filtro de estado).
 *
 * Lee `/api/piezas` (misma BD que `/api/publicaciones`: una publicación ES una fila
 * `pieza` de un `contenido`) y reutiliza el editor rico
 * (`VistaLista`/`VistaCalendario`/`DialogoEditar`).
 *
 * MARCA, RED y LÍNEA editorial vienen TODAS de los selectores GLOBALES de la barra
 * superior (`useMarcaActiva` + `useFiltrosPublicacion`); esta página ya no tiene
 * dropdowns de filtro propios.
 */
export function GestionPiezas({
  modo,
  onConfigurarHorarios,
}: {
  modo: "lista" | "calendario";
  onConfigurarHorarios?: () => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const calendario = modo === "calendario";

  const opcionesQuery = useQuery({
    queryKey: ["piezas", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });

  if (opcionesQuery.isPending) {
    return (
      <div className="mt-4 space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (opcionesQuery.isError) {
    return (
      <BloqueError
        titulo="No se pudieron cargar las piezas"
        mensaje={mensajeError(opcionesQuery.error)}
        onReintentar={() => void opcionesQuery.refetch()}
        cargando={opcionesQuery.isFetching}
      />
    );
  }

  return (
    <Cuerpo
      calendario={calendario}
      opciones={opcionesQuery.data}
      marcaActiva={marcaActiva}
      onConfigurarHorarios={onConfigurarHorarios}
    />
  );
}

function Cuerpo({
  calendario,
  opciones,
  marcaActiva,
  onConfigurarHorarios,
}: {
  calendario: boolean;
  opciones: OpcionesPiezas;
  marcaActiva: string | null;
  onConfigurarHorarios?: () => void;
}) {
  // La RED la manda el selector GLOBAL de la topbar; la MARCA, el switch de marca. La LÍNEA del
  // plan se filtra con el dropdown de Categoría de los filtros de limpieza (eje `categoria`).
  const { red } = useFiltrosPublicacion();
  const [editando, setEditando] = React.useState<Pieza | null>(null);
  // Filtros de LIMPIEZA por lotes (solo en modo lista): antigüedad/fase/tipo/categoría/fuente.
  // Acotan la lista —y por tanto lo que la selección múltiple borra— para barrer lo viejo o
  // incompleto sin tocar lo completado.
  const [limpieza, setLimpieza] = React.useState<FiltrosLimpieza>({});

  // CATEGORÍAS del plan para el dropdown de limpieza: del CATÁLOGO (`{id, nombre}`), no de los
  // ids crudos de las piezas cargadas. Con una marca activa, las suyas; en la vista "Todas",
  // la unión de todas (dedupe por id, primer nombre que aparezca). Misma fuente que «Crear
  // post» y Programa › Plan, así el dropdown muestra el nombre legible y filtra por el id.
  const categoriasPlan = React.useMemo<CategoriaPlanOpcion[]>(() => {
    const porMarca = opciones.categorias ?? {};
    if (marcaActiva) return porMarca[marcaActiva] ?? [];
    const mapa = new Map<string, CategoriaPlanOpcion>();
    for (const lista of Object.values(porMarca)) {
      for (const c of lista) if (!mapa.has(c.id)) mapa.set(c.id, c);
    }
    return [...mapa.values()];
  }, [opciones.categorias, marcaActiva]);

  // `usuario` solo para avisar al editor sin marca asignada (abajo). El reparto de TAREAS
  // (coger/asignar) se mudó a su propia página (/operacion/tareas): el Feed es SOLO piezas.
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;

  // Usuario (no admin) sin marca asignada: cae a la vista agregada sin saber por qué.
  // Lo avisamos suave: el arreglo es de datos (un admin le asigna su marca en Usuarios).
  const sinMarcaAsignada = faltaMarcaAsignada(usuario);

  // PARTICIÓN por estado (solo en modo lista; el calendario muestra las programadas): las
  // MISMAS pestañas y vocabulario del feed (Pendientes · Publicadas · Todas, ver vistas.tsx),
  // en la URL (`?vista=`) para que sobreviva al refresco y sea compartible. Por defecto
  // "Pendientes" (lo que queda por trabajar); el SERVIDOR filtra por el pseudo-estado, así la
  // paginación keyset y el total siguen exactos.
  const [searchParams, setSearchParams] = useSearchParams();
  const vista = vistaDesdeParam(searchParams.get("vista"), "pendiente");
  const estadoVista = calendario ? undefined : ESTADO_SERVIDOR_DE_VISTA[vista];
  const cambiarVista = (v: Vista) => {
    setSearchParams(
      (prev) => {
        if (v === "pendiente") prev.delete("vista");
        else prev.set("vista", v);
        return prev;
      },
      { replace: true },
    );
  };

  const filtrosBase: FiltrosBase = {
    marca: marcaActiva ?? undefined,
    red: red === FILTRO_TODOS ? undefined : red,
    estado: estadoVista,
    // Los filtros de limpieza solo aplican a la LISTA (el calendario es la programación).
    ...(calendario ? {} : limpieza),
  };
  // Conteos exactos para los badges de las pestañas (mismos que el feed; ver vistas.tsx).
  const { conteoVista } = useConteosFeed(filtrosBase);

  // CALENDARIO: la ANCLA (mes/semana/día visible) se eleva aquí para pedir a la API SOLO el
  // rango visible (`?desde=&hasta=`) en vez del conjunto completo —que el cap de 1000 filas
  // truncaba en silencio, haciendo mentir al calendario por omisión—. La navegación dentro
  // del calendario actualiza esta ancla y, con ella, el rango y el refetch.
  const [anclaCalendario, setAnclaCalendario] = React.useState(() => new Date());
  const rangoCal = React.useMemo(
    () => rangoVisibleCalendario(anclaCalendario),
    [anclaCalendario],
  );

  // CALENDARIO: rejilla mensual; pide solo la ventana visible (mes ancla ± 1 semana). Es la
  // FOTO COMPLETA de la programación (los huecos del plan y la no-doble-reserva de franjas).
  const calendarioQuery = useQuery({
    queryKey: [
      ...CLAVE_PIEZAS,
      "calendario",
      filtrosBase.marca ?? "",
      filtrosBase.red ?? "",
      rangoCal.desde,
      rangoCal.hasta,
    ],
    queryFn: ({ signal }) =>
      api.piezas(
        { ...filtrosBase, desde: rangoCal.desde, hasta: rangoCal.hasta },
        signal,
      ),
    enabled: calendario,
    // Navegar de mes refetcha el nuevo rango: mantener la rejilla previa visible (en vez de
    // parpadear a skeleton y perder los controles) mientras llega la del mes destino.
    placeholderData: keepPreviousData,
  });

  // LISTA: paginación KEYSET (modo `feed` del backend). Cada página devuelve
  // `paginacion.cursor_siguiente` y la siguiente se pide con `cursor=` desde la última fila
  // vista. El offset (`limite`+`desplazamiento`) saltaría piezas cuando el conjunto encoge
  // en vivo (lente "Por coger" + claims de compañeros); el cursor es inmune a eso.
  // `paginacion.total` sigue llegando para el "Mostrando X de Y". Cambiar los filtros
  // (incluida la vista de estado) cambia la queryKey, que resetea las páginas sola.
  const listaQuery = useInfiniteQuery({
    queryKey: [
      ...CLAVE_PIEZAS,
      "lista",
      filtrosBase.marca ?? "",
      filtrosBase.red ?? "",
      estadoVista ?? "todos",
      limpieza.antiguedad_h ?? "",
      limpieza.fase ?? "",
      limpieza.tipo ?? "",
      limpieza.categoria ?? "",
      limpieza.fuente ?? "",
    ],
    // Primera página: sin cursor (pero con `feed: "1"` para activar el modo keyset).
    initialPageParam: "",
    queryFn: ({ pageParam, signal }) =>
      api.piezas(paramsPaginaFeed(filtrosBase, pageParam), signal),
    getNextPageParam: (ultima, paginas) => {
      // El backend emite cursor cuando la página viene LLENA, incluida la última si el
      // total es múltiplo exacto: con el total fresco ya cubierto no hay más que pedir
      // (evita el "Cargar más" fantasma junto a "Mostrando 30 de 30").
      const cargadas = paginas.reduce((n, p) => n + p.piezas.length, 0);
      const total = ultima.paginacion?.total;
      if (total != null && cargadas >= total) return undefined;
      return ultima.paginacion?.cursor_siguiente || undefined;
    },
    enabled: !calendario,
  });

  // BANNER de seguridad (posteo real apagado): ¿hay piezas PROGRAMADAS que no saldrán solas?
  // Conteo LIGERO en el servidor (`limite:"1"`, solo importa `paginacion.total`): basarlo en
  // las páginas YA cargadas mentía con keyset —la 1ª página podía no traer ninguna programada
  // aunque las hubiera—. Solo se pide con el posteo real APAGADO (si está ON no hay banner).
  const programadasQuery = useQuery({
    queryKey: [
      ...CLAVE_PIEZAS,
      "conteo-programadas",
      filtrosBase.marca ?? "",
    ],
    queryFn: ({ signal }) =>
      api.piezas(
        { marca: filtrosBase.marca, estado: "programado", limite: "1" },
        signal,
      ),
    enabled: !opciones.publicar_real,
  });
  const totalProgramadas = programadasQuery.data?.paginacion?.total ?? 0;

  const query = calendario ? calendarioQuery : listaQuery;
  const piezas = React.useMemo(
    () =>
      calendario
        ? calendarioQuery.data?.piezas ?? []
        : (listaQuery.data?.pages ?? []).flatMap((p) => p.piezas),
    [calendario, calendarioQuery.data, listaQuery.data],
  );
  const total = calendario
    ? piezas.length
    : listaQuery.data?.pages.at(-1)?.paginacion?.total ?? piezas.length;
  // CALENDARIO truncado: el backend capa el listado a `tope_listado` (1000) incluso dentro
  // del rango visible; `paginacion.total` trae el conteo REAL sin cap. Si excede lo cargado,
  // la rejilla está pintando solo una parte del rango: lo decimos en vez de mentir por omisión.
  const totalRangoCalendario = calendarioQuery.data?.paginacion?.total ?? 0;
  const calendarioTruncado = calendario && totalRangoCalendario > piezas.length;
  const hayMas = !calendario && Boolean(listaQuery.hasNextPage);
  const filtrando =
    red !== FILTRO_TODOS ||
    estadoVista != null ||
    (!calendario && Object.values(limpieza).some(Boolean));

  // Aviso de seguridad: si el posteo real esta APAGADO y hay piezas programadas, al publicarlas
  // solo se previsualizan (no salen a redes). Es justo el fallo que dejaba piezas sin publicar en
  // silencio; lo hacemos visible. Se basa en el TOTAL del servidor, no en las páginas cargadas
  // (con keyset la 1ª página podía no traer ninguna programada).
  const hayProgramadasSinSalir = debeAvisarProgramadasSinSalir(
    opciones.publicar_real,
    totalProgramadas,
  );

  return (
    <div className="mt-2">
      {sinMarcaAsignada && (
        <div className="mb-3 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          No tienes marca asignada: pide a un admin que te asigne tu marca en Usuarios para
          ver tu espacio de trabajo.
        </div>
      )}
      {/* PARTICIÓN por estado: las MISMAS pestañas del feed (Pendientes · Publicadas · Todas),
          solo en la lista. El calendario muestra las programadas y no se filtra por estado. */}
      {!calendario && (
        <div className="mb-3 overflow-x-auto">
          <Tabs value={vista} onValueChange={(v) => cambiarVista(v as Vista)}>
            <TabsList className="w-fit" aria-label="Vista de la lista">
              {VISTAS.map((v) => (
                <TabsTrigger key={v.id} value={v.id} className="gap-1.5">
                  <PublicacionPestanaVista vista={v} conteo={conteoVista[v.id]} />
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      )}
      {/* Filtros de LIMPIEZA por lotes (antigüedad/fase/tipo/categoría/fuente): acotan la lista
          —y lo que la selección múltiple borra— para barrer lo viejo o incompleto. Solo lista. */}
      {!calendario && (
        <PanelFiltrosLimpieza
          valor={limpieza}
          onCambio={setLimpieza}
          categorias={categoriasPlan}
          piezas={piezas}
        />
      )}
      {calendarioTruncado && (
        <Aviso role="alert" className="mb-3">
          <strong>Calendario incompleto.</strong> En este rango hay {totalRangoCalendario}{" "}
          piezas y se muestran las primeras {piezas.length}. Acota por marca, red o
          línea, o navega a una ventana más corta para verlas todas.
        </Aviso>
      )}
      {hayProgramadasSinSalir && (
        <Aviso role="alert" className="mb-3">
          <strong>Publicación automática desactivada.</strong> Hay piezas programadas que{" "}
          <strong>no saldrán solas</strong>: con el posteo real apagado el sistema solo las
          previsualiza. Actívalo en el servidor (<code>KENI_PUBLICAR_REAL</code>) o publícalas a
          mano antes de su hora.
        </Aviso>
      )}
      {query.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudieron cargar las piezas"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : calendario ? (
        <VistaCalendario
          piezas={piezas}
          onEditar={setEditando}
          marca={marcaActiva}
          ancla={anclaCalendario}
          onAncla={setAnclaCalendario}
          // Los huecos del plan van POR RED: se le pasa la red activa para acotarlos (sin riesgo
          // de doble-reserva). `null` = sin filtro → huecos de todas las redes del plan.
          mostrarHuecosPlan
          filtroRed={red === FILTRO_TODOS ? null : red}
        />
      ) : piezas.length === 0 ? (
        <EstadoVacio
          icono={Send}
          titulo={filtrando ? "Sin resultados con estos filtros" : "Sin piezas"}
          texto={
            filtrando
              ? "Prueba a cambiar o limpiar los filtros."
              : "Vuelca material en Fuentes (cajones y clips) o crea una pieza a mano desde Publicacion."
          }
        />
      ) : (
        <>
          <VistaLista
            piezas={piezas}
            onEditar={setEditando}
            onConfigurarHorarios={onConfigurarHorarios ?? (() => {})}
          />
          {hayMas && (
            <div className="mt-4 flex flex-col items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void listaQuery.fetchNextPage()}
                disabled={listaQuery.isFetchingNextPage}
              >
                {listaQuery.isFetchingNextPage ? "Cargando…" : "Cargar más"}
              </Button>
              <p className="text-xs text-muted-foreground">
                Mostrando {piezas.length} de {total}
              </p>
            </div>
          )}
        </>
      )}

      <DialogoEditar
        pieza={editando}
        onCerrar={() => setEditando(null)}
      />
    </div>
  );
}
