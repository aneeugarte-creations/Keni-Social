import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";
import {
  BarChart3,
  CalendarClock,
  CalendarDays,
  Check,
  ChevronDown,
  ClipboardList,
  Eye,
  FileText,
  Hash,
  Heart,
  Image as ImageIcon,
  Loader2,
  LayoutGrid,
  ListTodo,
  MessageSquare,
  Pencil,
  Plus,
  Rows3,
  Send,
  Smartphone,
  Sparkles,
  Tag,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import * as React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { PanelColaboracion } from "@/components/contenido/PanelColaboracion";
import { EditorImagen } from "@/components/media/EditorImagen";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { MarcaIA } from "@/components/comunes/MarcaIA";
import { ContadorCaracteres } from "@/components/editor/ContadorCaracteres";
import { PageHeader } from "@/components/layout/PageHeader";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip } from "@/components/ui/tooltip";
import { useGeneracion } from "@/hooks/use-generacion";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import { limiteRed } from "@/pages/publicaciones/meta";
import { GestionFranjas } from "@/pages/publicaciones/GestionFranjas";
import { GestionHashtags } from "@/pages/publicaciones/GestionHashtags";
import { PanelReciclaje } from "@/pages/publicaciones/PanelReciclaje";
import { PreviewRed } from "@/pages/publicaciones/PreviewRed";
import { VistaCalendario } from "@/pages/publicaciones/VistaCalendario";
import { DialogoEditar } from "@/pages/publicaciones/DialogoEditar";
import { VistaLista } from "@/pages/publicaciones/VistaLista";
import { DialogoDuplicar } from "@/pages/publicaciones/DialogoDuplicar";
import { DialogoImportarCalendario } from "@/pages/publicaciones/DialogoImportarCalendario";
import { FILTRO_TODOS, FiltrosPublicaciones } from "@/pages/publicaciones/Filtros";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import { cn } from "@/lib/utils";
import type {
  CatalogosContenido,
  Contenido,
  ContenidoPlataforma,
  CuerpoCrearContenido,
  EstadoContenidoPlataforma,
  Etiqueta,
  EtiquetaCatalogo,
  MetricaPieza,
  ModoAsistenteContenido,
  OpcionesPublicaciones,
  PiezaGenerada,
  Publicacion,
  RespuestaContenido,
  TipoContenido,
  VariableCopy,
} from "@/types";

const CLAVE = ["contenido"] as const;
const CLAVE_METRICAS = ["contenido", "metricas"] as const;

/** Formatea un entero grande de forma compacta (es-MX): 1.2M, 340 mil, 850. */
function formatearCifra(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${Math.round(n / 1000)} mil`;
  return String(n);
}

const CABECERA = {
  titulo: "Tablero de contenido",
  descripcion:
    "La parrilla del día del equipo: lo importante del día, contenido evergreen y la cobertura de eventos previstos. Cada contenido lleva su estado y checklist por plataforma.",
};

const SIN_RESPONSABLE = "__sin_asignar__";
const SIN_EVENTO = "__sin_evento__";
const TODOS = "__todos__";

/** Etiqueta legible de un evento del catálogo: "titulo · fecha". */
function etiquetaEvento(e: { titulo: string; fecha: string }): string {
  return [e.titulo, e.fecha].filter(Boolean).join(" · ") || "(evento)";
}
/** Workspace "todas las marcas" (sin aislar). */
const WORKSPACE_TODAS = "__todas__";
/** localStorage: workspace (marca) activo + vista del tablero, para que sobrevivan al refresco. */
const CLAVE_WORKSPACE = "keni.tablero.workspace";
const CLAVE_VISTA = "keni.tablero.vista";
const CLAVE_MODO = "keni.tablero.modo";

/** Densidad de la sección del tablero: lista / cuadrícula / feed. */
type Vista = "lista" | "grid" | "feed";

/**
 * MODO del tablero (superficie única de contenido, #fase2):
 *   - `tablero`: el contenido del día por flujo (importante/evergreen/evento) + tareas.
 *   - `publicaciones`: las PUBLICACIONES (es_publicacion) en lista, con su gestión completa.
 *   - `calendario`: las publicaciones PROGRAMADAS en una rejilla mensual.
 *
 * Las publicaciones y el contenido del tablero comparten el MISMO dato (una publicación es
 * una fila `contenido_plataforma` con `es_publicacion=1`). El modo solo cambia la lente:
 * `tablero` lee `/api/contenido`; `publicaciones`/`calendario` leen `/api/publicaciones`
 * (misma BD, forma `Publicacion` con su editor rico ya existente).
 */
type Modo = "tablero" | "publicaciones" | "calendario";

/** Secciones del tablero por flujo (el orden manda en pantalla). */
const SECCIONES: { flujo: Contenido["flujo"]; titulo: string }[] = [
  { flujo: "importante", titulo: "Importante del día" },
  { flujo: "evergreen", titulo: "Evergreen" },
  { flujo: "evento", titulo: "Eventos previstos" },
];

const PRIORIDAD_VARIANTE: Record<string, "error" | "aviso" | "secondary"> = {
  alta: "error",
  media: "aviso",
  baja: "secondary",
};

const ESTADO_PLAT_LABEL: Record<string, string> = {
  pendiente: "Pendiente",
  en_curso: "En curso",
  en_revision: "En revisión",
  aprobado: "Aprobado",
  programado: "Programado",
  publicado: "Publicado",
};

const ESTADO_PLAT_VARIANTE: Record<string, "secondary" | "aviso" | "ok"> = {
  pendiente: "aviso",
  en_curso: "aviso",
  en_revision: "secondary",
  aprobado: "secondary",
  programado: "secondary",
  publicado: "ok",
};

/** Etiqueta humana del eje de una etiqueta editorial (para agrupar el catálogo). */
const CLASE_ETIQUETA_LABEL: Record<string, string> = {
  campania: "Campaña",
  vertical: "Vertical",
  tipo: "Tipo",
};

/** Items del checklist por plataforma: campo (falta_X) ↔ etiqueta del check (hecho = !falta). */
const CHECKS: { campo: keyof ContenidoPlataforma; etiqueta: string }[] = [
  { campo: "falta_copy", etiqueta: "Copy" },
  { campo: "falta_imagen", etiqueta: "Imagen" },
  { campo: "falta_revision", etiqueta: "Revisión" },
  { campo: "falta_publicar", etiqueta: "Publicar" },
];

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

function formatearFecha(iso: string): string {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "short" });
}

function leerLS(clave: string, defecto: string): string {
  try {
    return localStorage.getItem(clave) ?? defecto;
  } catch {
    return defecto;
  }
}

/** Lee una clave de localStorage devolviendo `null` si NO existe (sin valor por defecto). */
function leerLSOpcional(clave: string): string | null {
  try {
    return localStorage.getItem(clave);
  } catch {
    return null;
  }
}

export default function Tablero() {
  const query = useQuery({
    queryKey: CLAVE,
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  // Rendimiento real (Metricool) por pieza publicada: query SEPARADA para que el tablero
  // pinte al instante y las métricas (más lentas: golpean Metricool) lleguen después.
  const metricasQuery = useQuery({
    queryKey: CLAVE_METRICAS,
    queryFn: ({ signal }) => api.metricasContenido(signal),
    // Frescas 5 min en cliente; el back ya cachea con su propio TTL.
    staleTime: 5 * 60 * 1000,
  });
  const [dialogoAbierto, setDialogoAbierto] = React.useState(false);
  const [importarAbierto, setImportarAbierto] = React.useState(false);
  const [gestionEtiquetas, setGestionEtiquetas] = React.useState(false);
  const [gestionFranjas, setGestionFranjas] = React.useState(false);
  const [gestionHashtags, setGestionHashtags] = React.useState(false);
  const [filtroResponsable, setFiltroResponsable] = React.useState(TODOS);
  const [filtroEtiqueta, setFiltroEtiqueta] = React.useState(TODOS);
  // Deep-link opcional: `?marca=` fija el workspace y `?modo=` el modo (lo usa, p.ej.,
  // la pestaña Contenido de un agente para abrir el tablero ya filtrado por esa marca).
  const location = useLocation();
  const navigate = useNavigate();
  const { usuario } = useSesion();
  // Workspace por defecto = la MARCA del usuario. Si la persona pertenece a una sola
  // marca, el tablero nace aislado en ella (y el contenido nuevo también); si pertenece
  // a varias (p. ej. Yustine) o a ninguna, arranca en "Todas". El `?marca=` y la última
  // elección guardada mandan sobre ese defecto. `sinPreferenciaInicial` recuerda si al
  // montar NO había ni `?marca=` ni elección previa, para poder adoptar la marca del
  // usuario cuando la sesión resuelve DESPUÉS del primer render (el `me` es asíncrono).
  const sinPreferenciaInicial = React.useRef(
    leerLSOpcional(CLAVE_WORKSPACE) === null &&
      !new URLSearchParams(location.search).get("marca"),
  );
  const [workspace, setWorkspace] = React.useState<string>(() => {
    const desdeUrl = new URLSearchParams(location.search).get("marca");
    if (desdeUrl) return desdeUrl;
    const guardado = leerLSOpcional(CLAVE_WORKSPACE);
    if (guardado) return guardado;
    const marcas = usuario?.marcas ?? [];
    return marcas.length === 1 ? marcas[0] : WORKSPACE_TODAS;
  });
  // La sesión puede resolver tras el montaje: si no había preferencia previa y el usuario
  // es monomarca, adopta su marca una sola vez (sin pisar una elección deliberada).
  React.useEffect(() => {
    if (!sinPreferenciaInicial.current) return;
    const marcas = usuario?.marcas ?? [];
    if (marcas.length === 1 && workspace === WORKSPACE_TODAS) {
      setWorkspace(marcas[0]);
    }
    if (usuario) sinPreferenciaInicial.current = false;
  }, [usuario, workspace]);
  const [vista, setVista] = React.useState<Vista>(
    () => leerLS(CLAVE_VISTA, "lista") as Vista,
  );
  const [modo, setModo] = React.useState<Modo>(() => {
    const desdeUrl = new URLSearchParams(location.search).get("modo");
    if (desdeUrl === "publicaciones" || desdeUrl === "calendario" || desdeUrl === "tablero") {
      return desdeUrl;
    }
    // Deep-link `?abrir=<id>` abre el detalle de un contenido: vive en el modo Tablero.
    if (new URLSearchParams(location.search).get("abrir")) return "tablero";
    return leerLS(CLAVE_MODO, "tablero") as Modo;
  });
  // Deep-link `?abrir=<contenido_id>` (p.ej. desde el Panel): abre el detalle de ESE
  // contenido en el tablero. Lo pasamos a la tarjeta correspondiente, que se auto-abre.
  // Se limpia de la URL al consumirlo (replace) para no re-abrir al navegar/refrescar.
  // Capturado una sola vez al montar (no se vuelve a leer de la URL): el valor sobrevive a
  // que limpiemos `?abrir` de la URL, dándole a la tarjeta tiempo de consumirlo.
  const [abrirId] = React.useState<string | null>(
    () => new URLSearchParams(location.search).get("abrir"),
  );

  React.useEffect(() => {
    try {
      localStorage.setItem(CLAVE_WORKSPACE, workspace);
    } catch {
      /* localStorage no disponible: no es crítico */
    }
  }, [workspace]);
  React.useEffect(() => {
    try {
      localStorage.setItem(CLAVE_VISTA, vista);
    } catch {
      /* idem */
    }
  }, [vista]);
  React.useEffect(() => {
    try {
      localStorage.setItem(CLAVE_MODO, modo);
    } catch {
      /* idem */
    }
  }, [modo]);

  const contenidos = React.useMemo(() => query.data?.contenidos ?? [], [query.data]);
  const catalogos = query.data?.catalogos;

  // Una vez resuelta la query con un `?abrir=` pendiente, limpiamos el parámetro de la URL
  // (replace) para que el detalle no se re-abra al refrescar o navegar atrás. `abrirId`
  // sobrevive en estado el tiempo justo para que la tarjeta lo consuma y se auto-abra; si
  // el id no está en la lista cargada, simplemente no abre nada (no-op).
  React.useEffect(() => {
    if (!abrirId || !query.isSuccess) return;
    const params = new URLSearchParams(location.search);
    if (params.has("abrir")) {
      params.delete("abrir");
      const qs = params.toString();
      navigate({ pathname: location.pathname, search: qs ? `?${qs}` : "" }, { replace: true });
    }
  }, [abrirId, query.isSuccess, location.pathname, location.search, navigate]);
  const metricas = metricasQuery.data?.metricas;
  const etiquetas = React.useMemo<EtiquetaCatalogo[]>(
    () => catalogos?.etiquetas ?? [],
    [catalogos],
  );
  const etiquetaPorId = React.useMemo(
    () => new Map(etiquetas.map((e) => [e.id, e])),
    [etiquetas],
  );

  // Etiquetas del selector de filtro: las del workspace activo + las globales (marca="").
  const etiquetasWorkspace = React.useMemo(
    () =>
      etiquetas.filter(
        (e) =>
          workspace === WORKSPACE_TODAS || e.marca === "" || e.marca === workspace,
      ),
    [etiquetas, workspace],
  );

  const visibles = React.useMemo(() => {
    let lista = contenidos;
    if (workspace !== WORKSPACE_TODAS) lista = lista.filter((c) => c.marca === workspace);
    if (filtroResponsable === SIN_RESPONSABLE)
      lista = lista.filter((c) => !c.responsable_id);
    else if (filtroResponsable !== TODOS)
      lista = lista.filter((c) => c.responsable_id === filtroResponsable);
    if (filtroEtiqueta !== TODOS)
      lista = lista.filter((c) => (c.etiquetas ?? []).includes(filtroEtiqueta));
    return lista;
  }, [contenidos, workspace, filtroResponsable, filtroEtiqueta]);

  const tareas = visibles.filter((c) => c.clase === "tarea");

  const renderItem = (c: Contenido) =>
    vista === "feed" ? (
      <TarjetaFeed key={c.id} contenido={c} />
    ) : (
      <TarjetaContenido
        key={c.id}
        contenido={c}
        catalogos={catalogos!}
        etiquetaPorId={etiquetaPorId}
        etiquetasWorkspace={etiquetasWorkspace}
        compacta={vista === "grid"}
        metricas={metricas}
        abrirDetalle={c.id === abrirId}
      />
    );

  const contenedorClase =
    vista === "lista"
      ? "space-y-3"
      : vista === "feed"
        ? "space-y-4"
        : "grid gap-3 sm:grid-cols-2 xl:grid-cols-3";

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" asChild title="Catálogo de plantillas de contenido">
              <Link to="/activos/plantillas">
                <FileText className="h-4 w-4" />
                Plantillas
              </Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setGestionHashtags(true)}
              title="Gestionar grupos de hashtags"
            >
              <Hash className="h-4 w-4" />
              Hashtags
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setGestionFranjas(true)}
              title="Gestionar franjas de la cola de publicación"
            >
              <CalendarClock className="h-4 w-4" />
              Franjas
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setGestionEtiquetas(true)}
              disabled={query.isPending}
            >
              <Tag className="h-4 w-4" />
              Etiquetas
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setImportarAbierto(true)}
              title="Importar un calendario (.xlsx/.csv) al tablero"
            >
              <Upload className="h-4 w-4" />
              Importar
            </Button>
            <Button size="sm" onClick={() => setDialogoAbierto(true)} disabled={query.isPending}>
              <Plus className="h-4 w-4" />
              Nuevo contenido
            </Button>
          </div>
        }
      />

      {/* Selector de MODO: la lente sobre el MISMO dato (contenido vs publicaciones). */}
      <div className="mb-3 mt-1">
        <Tabs value={modo} onValueChange={(v) => setModo(v as Modo)}>
          <TabsList>
            <TabsTrigger value="tablero" className="gap-1.5">
              <ListTodo className="h-4 w-4" />
              Tablero
            </TabsTrigger>
            <TabsTrigger value="publicaciones" className="gap-1.5">
              <Send className="h-4 w-4" />
              Publicaciones
            </TabsTrigger>
            <TabsTrigger value="calendario" className="gap-1.5">
              <CalendarDays className="h-4 w-4" />
              Calendario
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Sugerencias proactivas de reciclaje (#110): visibles en cualquier modo;
          se ocultan solas si no hay candidatas. Respetan el workspace activo. */}
      <PanelReciclaje
        filtros={{ marca: workspace === WORKSPACE_TODAS ? undefined : workspace }}
        onGestionarFranjas={() => setGestionFranjas(true)}
      />

      {modo !== "tablero" ? (
        <VistaPublicaciones
          modo={modo}
          workspace={workspace}
          onGestionarFranjas={() => setGestionFranjas(true)}
        />
      ) : (
        <ModoTablero
          query={query}
          catalogos={catalogos}
          contenidos={contenidos}
          visibles={visibles}
          tareas={tareas}
          renderItem={renderItem}
          contenedorClase={contenedorClase}
          workspace={workspace}
          onWorkspace={setWorkspace}
          filtroResponsable={filtroResponsable}
          onResponsable={setFiltroResponsable}
          filtroEtiqueta={filtroEtiqueta}
          onEtiqueta={setFiltroEtiqueta}
          etiquetasWorkspace={etiquetasWorkspace}
          vista={vista}
          onVista={setVista}
        />
      )}

      {catalogos && (
        <DialogoNuevo
          abierto={dialogoAbierto}
          onCerrar={() => setDialogoAbierto(false)}
          catalogos={catalogos}
          workspace={workspace}
          etiquetasWorkspace={etiquetasWorkspace}
        />
      )}
      <DialogoImportarCalendario
        abierto={importarAbierto}
        onCerrar={() => setImportarAbierto(false)}
        marcas={catalogos?.marcas ?? []}
        onImportado={(creados) => {
          toast.success(
            creados === 1 ? "1 contenido importado al tablero." : `${creados} contenidos importados al tablero.`,
          );
          void query.refetch();
        }}
      />
      <DialogoEtiquetas
        abierto={gestionEtiquetas}
        onCerrar={() => setGestionEtiquetas(false)}
        marcas={catalogos?.marcas ?? []}
      />
      <GestionFranjas
        abierto={gestionFranjas}
        onCerrar={() => setGestionFranjas(false)}
        marcas={catalogos?.marcas ?? []}
        redes={catalogos?.redes ?? []}
      />
      <GestionHashtags
        abierto={gestionHashtags}
        onCerrar={() => setGestionHashtags(false)}
        marcas={catalogos?.marcas ?? []}
      />
    </>
  );
}

/** El MODO tablero: secciones por flujo + tareas (la vista original del tablero). */
function ModoTablero({
  query,
  catalogos,
  contenidos,
  visibles,
  tareas,
  renderItem,
  contenedorClase,
  workspace,
  onWorkspace,
  filtroResponsable,
  onResponsable,
  filtroEtiqueta,
  onEtiqueta,
  etiquetasWorkspace,
  vista,
  onVista,
}: {
  query: UseQueryResult<RespuestaContenido>;
  catalogos: CatalogosContenido | undefined;
  contenidos: Contenido[];
  visibles: Contenido[];
  tareas: Contenido[];
  renderItem: (c: Contenido) => React.ReactNode;
  contenedorClase: string;
  workspace: string;
  onWorkspace: (v: string) => void;
  filtroResponsable: string;
  onResponsable: (v: string) => void;
  filtroEtiqueta: string;
  onEtiqueta: (v: string) => void;
  etiquetasWorkspace: EtiquetaCatalogo[];
  vista: Vista;
  onVista: (v: Vista) => void;
}) {
  return (
    <>
      {catalogos && (
        <BarraControles
          catalogos={catalogos}
          workspace={workspace}
          onWorkspace={onWorkspace}
          filtroResponsable={filtroResponsable}
          onResponsable={onResponsable}
          filtroEtiqueta={filtroEtiqueta}
          onEtiqueta={onEtiqueta}
          etiquetasWorkspace={etiquetasWorkspace}
          vista={vista}
          onVista={onVista}
        />
      )}

      {query.isPending ? (
        <div className="mt-4 space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-md" />
          ))}
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar el tablero"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : contenidos.length === 0 ? (
        <EstadoVacio
          icono={ListTodo}
          titulo="Tablero vacío"
          texto="Crea el primer contenido con el botón «Nuevo contenido»."
        />
      ) : visibles.length === 0 ? (
        <EstadoVacio
          icono={ListTodo}
          titulo="Nada que mostrar"
          texto="Ningún contenido coincide con el workspace o los filtros activos."
        />
      ) : (
        <div className="mt-4 space-y-8">
          {SECCIONES.map((s) => {
            const items = visibles.filter(
              (c) => c.clase === "contenido" && c.flujo === s.flujo,
            );
            return (
              <Seccion key={s.flujo} titulo={s.titulo} cantidad={items.length}>
                <div className={contenedorClase}>{items.map(renderItem)}</div>
              </Seccion>
            );
          })}
          {tareas.length > 0 && (
            <Seccion titulo="Tareas del equipo" cantidad={tareas.length}>
              <div className={contenedorClase}>{tareas.map(renderItem)}</div>
            </Seccion>
          )}
        </div>
      )}
    </>
  );
}

/**
 * Modos PUBLICACIONES y CALENDARIO del tablero (superficie única, #fase2).
 *
 * Lee `/api/publicaciones` (misma BD que `/api/contenido`: una publicación ES una fila
 * `contenido_plataforma` con `es_publicacion=1`) y reutiliza el editor rico ya existente
 * (`VistaLista`/`VistaCalendario`/`DialogoEditar`/`DialogoDuplicar`) en vez de duplicarlo.
 * Su query está gateada por modo: en modo `tablero` no se monta, así el resto del tablero
 * sigue dependiendo solo de `/api/contenido`.
 */
function VistaPublicaciones({
  modo,
  workspace,
  onGestionarFranjas,
}: {
  modo: Exclude<Modo, "tablero">;
  workspace: string;
  onGestionarFranjas: () => void;
}) {
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
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
        titulo="No se pudieron cargar las publicaciones"
        mensaje={mensajeError(opcionesQuery.error)}
        onReintentar={() => void opcionesQuery.refetch()}
        cargando={opcionesQuery.isFetching}
      />
    );
  }

  return (
    <GestionPublicaciones
      modo={modo}
      workspace={workspace}
      opciones={opcionesQuery.data}
      onGestionarFranjas={onGestionarFranjas}
    />
  );
}

const TAM_PAGINA_PUB = 30;

function GestionPublicaciones({
  modo,
  workspace,
  opciones,
  onGestionarFranjas,
}: {
  modo: Exclude<Modo, "tablero">;
  workspace: string;
  opciones: OpcionesPublicaciones;
  onGestionarFranjas: () => void;
}) {
  // El workspace activo del tablero PRE-FILTRA por marca; aún se puede afinar marca/red/estado.
  const marcaWorkspace = workspace === WORKSPACE_TODAS ? FILTRO_TODOS : workspace;
  const [marca, setMarca] = React.useState(marcaWorkspace);
  const [red, setRed] = React.useState(FILTRO_TODOS);
  const [estado, setEstado] = React.useState(FILTRO_TODOS);
  const [soloPerennes, setSoloPerennes] = React.useState(false);
  const [paginas, setPaginas] = React.useState(1);
  const [editando, setEditando] = React.useState<Publicacion | null>(null);
  const [duplicando, setDuplicando] = React.useState<Publicacion | null>(null);

  // Si cambia el workspace del tablero, adopta su marca (a menos que el usuario ya afinó).
  React.useEffect(() => {
    setMarca(marcaWorkspace);
  }, [marcaWorkspace]);

  const calendario = modo === "calendario";
  const limite = calendario ? undefined : paginas * TAM_PAGINA_PUB;

  const filtros = {
    marca: marca === FILTRO_TODOS ? undefined : marca,
    red: red === FILTRO_TODOS ? undefined : red,
    estado: calendario || estado === FILTRO_TODOS ? undefined : estado,
    evergreen: soloPerennes ? "1" : undefined,
    limite: limite != null ? String(limite) : undefined,
    desplazamiento: undefined,
  };

  React.useEffect(() => {
    setPaginas(1);
  }, [marca, red, estado, soloPerennes, modo]);

  const query = useQuery({
    queryKey: [
      ...CLAVE_PUBLICACIONES,
      "lista",
      filtros.marca ?? "",
      filtros.red ?? "",
      filtros.estado ?? "",
      filtros.evergreen ?? "",
      filtros.limite ?? "",
    ],
    queryFn: ({ signal }) => api.publicaciones(filtros, signal),
  });

  const publicaciones = query.data?.publicaciones ?? [];
  const total = query.data?.paginacion?.total ?? publicaciones.length;
  const hayMas = !calendario && publicaciones.length < total;
  const filtrando =
    marca !== FILTRO_TODOS || red !== FILTRO_TODOS || estado !== FILTRO_TODOS || soloPerennes;

  return (
    <div className="mt-2">
      <div className="mb-4">
        <FiltrosPublicaciones
          opciones={opciones}
          marca={marca}
          red={red}
          estado={estado}
          soloPerennes={soloPerennes}
          onMarca={setMarca}
          onRed={setRed}
          onEstado={setEstado}
          onSoloPerennes={setSoloPerennes}
        />
      </div>

      {query.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudieron cargar las publicaciones"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : calendario ? (
        <VistaCalendario publicaciones={publicaciones} onEditar={setEditando} />
      ) : publicaciones.length === 0 ? (
        <EstadoVacio
          icono={Send}
          titulo={filtrando ? "Sin resultados con estos filtros" : "Aún no hay publicaciones"}
          texto={
            filtrando
              ? "Prueba a cambiar o limpiar los filtros."
              : "Genera un copy y guárdalo como publicación, o créalo en el tablero."
          }
        />
      ) : (
        <>
          <VistaLista
            publicaciones={publicaciones}
            onEditar={setEditando}
            onDuplicar={setDuplicando}
            onGestionarFranjas={onGestionarFranjas}
          />
          {hayMas && (
            <div className="mt-4 flex flex-col items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPaginas((p) => p + 1)}
                disabled={query.isFetching}
              >
                {query.isFetching ? "Cargando…" : "Cargar más"}
              </Button>
              <p className="text-xs text-muted-foreground">
                Mostrando {publicaciones.length} de {total}
              </p>
            </div>
          )}
        </>
      )}

      <DialogoEditar
        publicacion={editando}
        estados={opciones.estados}
        onCerrar={() => setEditando(null)}
      />
      <DialogoDuplicar
        publicacion={duplicando}
        marcas={opciones.marcas}
        redes={opciones.redes}
        onCerrar={() => setDuplicando(null)}
      />
    </div>
  );
}

function BarraControles({
  catalogos,
  workspace,
  onWorkspace,
  filtroResponsable,
  onResponsable,
  filtroEtiqueta,
  onEtiqueta,
  etiquetasWorkspace,
  vista,
  onVista,
}: {
  catalogos: CatalogosContenido;
  workspace: string;
  onWorkspace: (v: string) => void;
  filtroResponsable: string;
  onResponsable: (v: string) => void;
  filtroEtiqueta: string;
  onEtiqueta: (v: string) => void;
  etiquetasWorkspace: EtiquetaCatalogo[];
  vista: Vista;
  onVista: (v: Vista) => void;
}) {
  // Al cambiar de workspace, si la etiqueta del filtro deja de pertenecer, se resetea.
  React.useEffect(() => {
    if (
      filtroEtiqueta !== TODOS &&
      !etiquetasWorkspace.some((e) => e.id === filtroEtiqueta)
    ) {
      onEtiqueta(TODOS);
    }
  }, [etiquetasWorkspace, filtroEtiqueta, onEtiqueta]);

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex items-center gap-2">
        <Label htmlFor="filtro-workspace" className="text-sm text-muted-foreground">
          Workspace
        </Label>
        <Select value={workspace} onValueChange={onWorkspace}>
          <SelectTrigger
            id="filtro-workspace"
            aria-label="Workspace (marca)"
            className="h-8 w-48"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={WORKSPACE_TODAS}>Todas las marcas</SelectItem>
            {catalogos.marcas.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <Label htmlFor="filtro-resp" className="text-sm text-muted-foreground">
          Responsable
        </Label>
        <Select value={filtroResponsable} onValueChange={onResponsable}>
          <SelectTrigger
            id="filtro-resp"
            aria-label="Filtrar por responsable"
            className="h-8 w-48"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todos</SelectItem>
            <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
            {catalogos.usuarios.map((u) => (
              <SelectItem key={u.id} value={u.id}>
                {u.usuario}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <Label htmlFor="filtro-etiqueta" className="text-sm text-muted-foreground">
          Etiqueta
        </Label>
        <Select value={filtroEtiqueta} onValueChange={onEtiqueta}>
          <SelectTrigger
            id="filtro-etiqueta"
            aria-label="Filtrar por etiqueta"
            className="h-8 w-48"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todas</SelectItem>
            {etiquetasWorkspace.map((e) => (
              <SelectItem key={e.id} value={e.id}>
                {e.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Vista del tablero: lista / grid / feed-preview. */}
      <div
        className="ml-auto inline-flex items-center rounded-lg bg-muted p-0.5"
        role="group"
        aria-label="Vista del tablero"
      >
        {(
          [
            { v: "lista", icono: Rows3, etiqueta: "Lista" },
            { v: "grid", icono: LayoutGrid, etiqueta: "Cuadrícula" },
            { v: "feed", icono: Smartphone, etiqueta: "Feed" },
          ] as const
        ).map(({ v, icono: Icono, etiqueta }) => (
          <Tooltip key={v} label={etiqueta}>
            <button
              type="button"
              aria-label={etiqueta}
              aria-pressed={vista === v}
              onClick={() => onVista(v)}
              className={cn(
                "inline-flex h-7 w-9 items-center justify-center rounded-md transition-colors",
                vista === v
                  ? "bg-background text-foreground shadow"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icono className="h-4 w-4" />
            </button>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}

function Seccion({
  titulo,
  cantidad,
  children,
}: {
  titulo: string;
  cantidad: number;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold tracking-tight text-muted-foreground">
        {titulo}
        <Badge variant="outline" className="font-normal">
          {cantidad}
        </Badge>
      </h3>
      {cantidad === 0 ? (
        <p className="text-sm text-muted-foreground/70">Nada por aquí todavía.</p>
      ) : (
        children
      )}
    </section>
  );
}

/** Chip de una etiqueta editorial (con color opcional). `onQuitar` lo vuelve removible. */
function ChipEtiqueta({
  etiqueta,
  onQuitar,
}: {
  etiqueta: EtiquetaCatalogo;
  onQuitar?: () => void;
}) {
  const estilo = etiqueta.color
    ? { borderColor: etiqueta.color, color: etiqueta.color }
    : undefined;
  return (
    <Badge variant="outline" className="gap-1 font-normal" style={estilo}>
      <Tag className="h-3 w-3" />
      {etiqueta.nombre}
      {onQuitar && (
        <button
          type="button"
          aria-label={`Quitar etiqueta ${etiqueta.nombre}`}
          onClick={onQuitar}
          className="-mr-0.5 ml-0.5 rounded-sm opacity-60 hover:opacity-100"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </Badge>
  );
}

/**
 * Barra de ACCIONES de una pieza, COMPARTIDA por todas las vistas del tablero
 * (lista/cuadrícula/feed) para que ninguna vista pierda funcionalidad: prioridad,
 * asistente IA (generar/mejorar copy), Detalle (comentarios + versiones de copy +
 * cadena de aprobación) y borrar. Autocontenida: trae sus mutaciones, su invalidación
 * y sus diálogos (`DialogoAsistente`/`PanelColaboracion`). Las acciones de IA/Detalle
 * solo aplican a `contenido` (las tareas del equipo no tienen copy ni aprobación).
 */
function BarraAccionesPieza({
  contenido,
  abrirDetalle = false,
}: {
  contenido: Contenido;
  /** Deep-link `?abrir=`: si es esta pieza, abre su panel de detalle al montar. */
  abrirDetalle?: boolean;
}) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE });
  const [asistenteAbierto, setAsistenteAbierto] = React.useState(false);
  const [colaboracionAbierta, setColaboracionAbierta] = React.useState(false);
  const esContenido = contenido.clase === "contenido";

  // Deep-link `?abrir=<id>` (desde el Panel): abre el detalle de la pieza apuntada.
  React.useEffect(() => {
    if (abrirDetalle && esContenido) setColaboracionAbierta(true);
  }, [abrirDetalle, esContenido]);

  const cambiarPrioridad = useMutation({
    mutationFn: (prioridad: Contenido["prioridad"]) =>
      api.actualizarContenido(contenido.id, { prioridad }),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarContenido(contenido.id),
    onSuccess: () => {
      invalidar();
      toast.success("Contenido borrado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <Select
        value={contenido.prioridad}
        onValueChange={(v) => cambiarPrioridad.mutate(v as Contenido["prioridad"])}
        disabled={cambiarPrioridad.isPending}
      >
        <SelectTrigger aria-label="Prioridad" className="h-7 w-24 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(["alta", "media", "baja"] as const).map((p) => (
            <SelectItem key={p} value={p}>
              <Badge variant={PRIORIDAD_VARIANTE[p]} className="font-normal">
                {p}
              </Badge>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {esContenido && (
        <Tooltip label="Generar / mejorar copy con IA (voz de marca + verificación)">
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-primary"
            onClick={() => setAsistenteAbierto(true)}
          >
            <MarcaIA />
            IA
          </Button>
        </Tooltip>
      )}
      {esContenido && (
        <Tooltip label="Detalle de la pieza: comentarios, versiones de copy y cadena de aprobación">
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1 px-2 text-xs text-muted-foreground"
            onClick={() => setColaboracionAbierta(true)}
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Detalle
          </Button>
        </Tooltip>
      )}
      <Tooltip label="Borrar">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Borrar contenido"
          className="text-muted-foreground hover:text-destructive"
          onClick={() => borrar.mutate()}
          disabled={borrar.isPending}
        >
          {borrar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
        </Button>
      </Tooltip>
      {esContenido && (
        <DialogoAsistente
          abierto={asistenteAbierto}
          onCerrar={() => setAsistenteAbierto(false)}
          contenido={contenido}
          onAplicado={invalidar}
        />
      )}
      <PanelColaboracion
        contenido={contenido}
        abierto={colaboracionAbierta}
        onCerrar={() => setColaboracionAbierta(false)}
      />
    </div>
  );
}

function TarjetaContenido({
  contenido,
  catalogos,
  etiquetaPorId,
  etiquetasWorkspace,
  compacta = false,
  metricas,
  abrirDetalle = false,
}: {
  contenido: Contenido;
  catalogos: CatalogosContenido;
  etiquetaPorId: Map<string, EtiquetaCatalogo>;
  etiquetasWorkspace: EtiquetaCatalogo[];
  compacta?: boolean;
  metricas?: Record<string, MetricaPieza>;
  /** Deep-link `?abrir=`: si es esta pieza, abre su panel de detalle al montar. */
  abrirDetalle?: boolean;
}) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE });

  const reasignar = useMutation({
    mutationFn: (responsable_id: string) =>
      api.actualizarContenido(contenido.id, { responsable_id }),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const cambiarEvento = useMutation({
    mutationFn: (evento_id: string) =>
      api.actualizarContenido(contenido.id, { evento_id }),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const agregarRed = useMutation({
    mutationFn: (red: string) => api.agregarPlataforma(contenido.id, red),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const asignarEtiqueta = useMutation({
    mutationFn: (etiquetaId: string) =>
      api.asignarEtiquetaContenido(contenido.id, etiquetaId),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const quitarEtiqueta = useMutation({
    mutationFn: (etiquetaId: string) =>
      api.quitarEtiquetaContenido(contenido.id, etiquetaId),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });

  const redesUsadas = new Set(contenido.plataformas.map((p) => p.red));
  const redesDisponibles = catalogos.redes.filter((r) => !redesUsadas.has(r.id));
  const asignadas = contenido.etiquetas ?? [];
  const etiquetasDisponibles = etiquetasWorkspace.filter((e) => !asignadas.includes(e.id));

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium leading-snug">{contenido.titulo}</span>
              {contenido.plataformas.some((p) => p.es_publicacion) && (
                <Badge
                  variant="outline"
                  className="gap-1 border-sky-500/40 font-normal text-sky-700 dark:text-sky-300"
                  title="Esta pieza es una publicación (gestionable también en el modo Publicaciones/Calendario)"
                >
                  <Send className="h-3 w-3" />
                  Publicación
                </Badge>
              )}
              {contenido.marca_nombre && (
                <Badge variant="outline" className="font-normal">
                  {contenido.marca_nombre}
                </Badge>
              )}
              {contenido.fecha_entrega && (
                <Badge
                  variant={contenido.vencido ? "error" : "outline"}
                  className="gap-1 font-normal"
                >
                  <CalendarClock className="h-3 w-3" />
                  {contenido.vencido ? "Venció " : "Entrega "}
                  {formatearFecha(contenido.fecha_entrega)}
                </Badge>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {contenido.autor_nombre && (
                <Autor nombre={contenido.autor_nombre} className="text-xs" />
              )}
            </div>
          </div>
          <BarraAccionesPieza contenido={contenido} abrirDetalle={abrirDetalle} />
        </div>

        {contenido.descripcion && (
          <p
            className={cn(
              "whitespace-pre-wrap text-sm text-muted-foreground",
              compacta && "line-clamp-2",
            )}
          >
            {contenido.descripcion}
          </p>
        )}

        {/* Etiquetas editoriales (chips removibles + selector para añadir). */}
        <div className="flex flex-wrap items-center gap-1.5">
          {asignadas.map((id) => {
            const et = etiquetaPorId.get(id);
            if (!et) return null;
            return (
              <ChipEtiqueta
                key={id}
                etiqueta={et}
                onQuitar={
                  quitarEtiqueta.isPending ? undefined : () => quitarEtiqueta.mutate(id)
                }
              />
            );
          })}
          {etiquetasDisponibles.length > 0 && (
            <Select value="" onValueChange={(id) => asignarEtiqueta.mutate(id)}>
              <SelectTrigger
                aria-label="Añadir etiqueta"
                className="h-6 w-auto gap-1 border-dashed px-2 text-xs text-muted-foreground"
              >
                <Tag className="h-3 w-3" />
                <SelectValue placeholder="Etiqueta" />
              </SelectTrigger>
              <SelectContent>
                {etiquetasDisponibles.map((e) => (
                  <SelectItem key={e.id} value={e.id}>
                    {e.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Filas por plataforma (clase=contenido). */}
        {contenido.clase === "contenido" && (
          <div className="space-y-2 rounded-md border border-border/60 p-2">
            {contenido.plataformas.length === 0 ? (
              <p className="px-1 text-xs text-muted-foreground/70">
                Sin plataformas. Añade una red abajo.
              </p>
            ) : (
              contenido.plataformas.map((p) => (
                <FilaPlataforma
                  key={p.id}
                  contenidoId={contenido.id}
                  plataforma={p}
                  variables={catalogos.variables}
                  metrica={metricas?.[p.id]}
                  tipoContenido={contenido.tipo_contenido}
                />
              ))
            )}
            {redesDisponibles.length > 0 && (
              <Select value="" onValueChange={(red) => agregarRed.mutate(red)}>
                <SelectTrigger aria-label="Añadir plataforma" className="h-7 w-44 text-xs">
                  <SelectValue placeholder="+ Añadir plataforma" />
                </SelectTrigger>
                <SelectContent>
                  {redesDisponibles.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        )}

        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Responsable</span>
          <Select
            value={contenido.responsable_id || SIN_RESPONSABLE}
            onValueChange={(v) => reasignar.mutate(v === SIN_RESPONSABLE ? "" : v)}
            disabled={reasignar.isPending}
          >
            <SelectTrigger aria-label="Responsable del contenido" className="h-7 w-48 text-xs">
              <SelectValue placeholder="Sin asignar" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
              {catalogos.usuarios.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.usuario}
                </SelectItem>
              ))}
              {contenido.responsable_id &&
                !catalogos.usuarios.some((u) => u.id === contenido.responsable_id) && (
                  <SelectItem value={contenido.responsable_id}>
                    {contenido.responsable_nombre || "desconocido"}
                  </SelectItem>
                )}
            </SelectContent>
          </Select>
        </div>

        {/* Evento (cobertura): atar/desatar la pieza a un evento del catálogo. Visible en el
            flujo de eventos, o si la pieza ya trae un evento (para poder cambiarlo/quitarlo). */}
        {contenido.clase === "contenido" &&
          (contenido.flujo === "evento" || contenido.evento_id) && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Evento</span>
              <Select
                value={contenido.evento_id || SIN_EVENTO}
                onValueChange={(v) => cambiarEvento.mutate(v === SIN_EVENTO ? "" : v)}
                disabled={cambiarEvento.isPending}
              >
                <SelectTrigger aria-label="Evento del contenido" className="h-7 w-48 text-xs">
                  <SelectValue placeholder="(ninguno)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SIN_EVENTO}>(ninguno)</SelectItem>
                  {catalogos.eventos.map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {etiquetaEvento(e)}
                    </SelectItem>
                  ))}
                  {contenido.evento_id &&
                    !catalogos.eventos.some((e) => e.id === contenido.evento_id) && (
                      <SelectItem value={contenido.evento_id}>(evento)</SelectItem>
                    )}
                </SelectContent>
              </Select>
            </div>
          )}
      </CardContent>
    </Card>
  );
}

/**
 * Modo "Feed": un BLOQUE por pieza con (a) su barra de acciones COMPARTIDA (la misma
 * que lista/cuadrícula: prioridad, IA, Detalle, borrar — sin perder funcionalidad al
 * cambiar de vista) y (b) una vista previa POR RED, una `PreviewRed` por plataforma con
 * la relación de aspecto y el tope de caracteres de cada red. Las tareas del equipo
 * (sin copy ni redes) muestran solo su barra de acciones, sin previa social.
 */
function TarjetaFeed({ contenido }: { contenido: Contenido }) {
  const plats = contenido.plataformas;
  const marca = contenido.marca_nombre || "";
  const esContenido = contenido.clase === "contenido";

  return (
    <section className="space-y-3 rounded-lg border border-border/60 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium leading-snug">{contenido.titulo}</p>
          <p className="truncate text-xs text-muted-foreground">{marca || "Sin marca"}</p>
        </div>
        <BarraAccionesPieza contenido={contenido} />
      </div>

      {!esContenido ? (
        <p className="text-xs italic text-muted-foreground/70">
          Tarea del equipo (sin vista previa de red).
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {plats.length === 0 ? (
            <PreviewRed
              red=""
              marcaNombre={marca}
              copy={contenido.descripcion || contenido.titulo}
              titulo={contenido.titulo}
            />
          ) : (
            plats.map((p) => (
              <PreviewRed
                key={p.id}
                red={p.red}
                marcaNombre={marca}
                copy={p.copy || contenido.descripcion || contenido.titulo}
                imagenUrl={p.imagen_url || undefined}
                titulo={contenido.titulo}
              />
            ))
          )}
        </div>
      )}
    </section>
  );
}

function FilaPlataforma({
  contenidoId,
  plataforma,
  variables,
  metrica,
  tipoContenido,
}: {
  contenidoId: string;
  plataforma: ContenidoPlataforma;
  variables: VariableCopy[];
  metrica?: MetricaPieza;
  /** De dónde sale la imagen de la pieza (IA / galería / fuente original). */
  tipoContenido: TipoContenido;
}) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE });
  const [editorAbierto, setEditorAbierto] = React.useState(false);
  const [imagenAbierta, setImagenAbierta] = React.useState(false);
  const tieneImagen = !!(plataforma.imagen || plataforma.imagen_fuente);

  const actualizar = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.actualizarPlataforma>[2]) =>
      api.actualizarPlataforma(contenidoId, plataforma.id, cuerpo),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarPlataforma(contenidoId, plataforma.id),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="space-y-1.5 rounded-md bg-muted/30 px-2 py-1.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <Badge variant="outline" className="w-20 justify-center font-normal">
        {plataforma.red_nombre}
      </Badge>
      <Select
        value={plataforma.estado}
        onValueChange={(estado) =>
          actualizar.mutate({ estado: estado as EstadoContenidoPlataforma })
        }
        disabled={actualizar.isPending}
      >
        <SelectTrigger
          aria-label={`Estado en ${plataforma.red_nombre}`}
          className="h-7 w-32 text-xs"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.keys(ESTADO_PLAT_LABEL).map((e) => (
            <SelectItem key={e} value={e}>
              {ESTADO_PLAT_LABEL[e]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Badge
        variant={ESTADO_PLAT_VARIANTE[plataforma.estado] ?? "secondary"}
        className="font-normal"
      >
        {ESTADO_PLAT_LABEL[plataforma.estado] ?? plataforma.estado}
      </Badge>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {CHECKS.map(({ campo, etiqueta }) => {
          const hecho = !plataforma[campo];
          return (
            <label
              key={campo}
              className="flex items-center gap-1.5 text-xs text-muted-foreground"
            >
              <Checkbox
                checked={hecho}
                onCheckedChange={(c) => actualizar.mutate({ [campo]: !c })}
                aria-label={etiqueta}
                disabled={actualizar.isPending}
              />
              <span className={cn(hecho && "line-through opacity-60")}>{etiqueta}</span>
            </label>
          );
        })}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="ml-auto h-7 gap-1 px-2 text-xs text-muted-foreground"
        onClick={() => setEditorAbierto((v) => !v)}
        aria-expanded={editorAbierto}
      >
        <ChevronDown
          className={cn("h-3.5 w-3.5 transition-transform", editorAbierto && "rotate-180")}
        />
        Copy
        {plataforma.copy ? (
          <Badge variant="ok" className="h-4 px-1 font-normal">
            <Check className="h-3 w-3" />
          </Badge>
        ) : null}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 gap-1 px-2 text-xs text-muted-foreground"
        onClick={() => setImagenAbierta((v) => !v)}
        aria-expanded={imagenAbierta}
      >
        <ImageIcon className="h-3.5 w-3.5" />
        Imagen
        {tieneImagen ? (
          <Badge variant="ok" className="h-4 px-1 font-normal">
            <Check className="h-3 w-3" />
          </Badge>
        ) : null}
      </Button>
      <Tooltip label="Quitar plataforma">
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Quitar ${plataforma.red_nombre}`}
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() => borrar.mutate()}
          disabled={borrar.isPending}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </Tooltip>
      </div>
      {editorAbierto && (
        <EditorCopy
          contenidoId={contenidoId}
          plataforma={plataforma}
          variables={variables}
          guardando={actualizar.isPending}
          onGuardar={(copy) => actualizar.mutate({ copy })}
        />
      )}
      {imagenAbierta && (
        <EditorImagenPlataforma
          plataforma={plataforma}
          tipoContenido={tipoContenido}
          guardando={actualizar.isPending}
          onGuardarImagen={(imagen) => actualizar.mutate({ imagen })}
          onGuardarFuente={(imagen_fuente) => actualizar.mutate({ imagen_fuente })}
        />
      )}
      <RendimientoPieza plataforma={plataforma} metrica={metrica} />
    </div>
  );
}

/** Sub-fila de rendimiento real (Metricool) de una pieza ya publicada.
 *
 * Solo aparece si la fila tiene `id_post_metricool` (ya se empujó a Metricool). Mientras
 * llegan las métricas, o si Metricool aún no tiene datos del post, muestra un texto
 * honesto en vez de ceros falsos. Las cifras son las que Metricool —la fuente pagada—
 * ya consolidó; no hay adaptador por red.
 */
function RendimientoPieza({
  plataforma,
  metrica,
}: {
  plataforma: ContenidoPlataforma;
  metrica?: MetricaPieza;
}) {
  // Sin id_post_metricool no hay nada que medir todavía (no publicada vía Metricool).
  if (!plataforma.id_post_metricool) return null;

  const base = "flex flex-wrap items-center gap-x-3 gap-y-0.5 pl-[5.5rem] text-xs";

  if (!metrica) {
    return (
      <div className={cn(base, "text-muted-foreground/70")}>
        <BarChart3 className="h-3 w-3" />
        <span>Cargando rendimiento…</span>
      </div>
    );
  }
  if (!metrica.encontrado) {
    return (
      <div className={cn(base, "text-muted-foreground/70")}>
        <BarChart3 className="h-3 w-3" />
        <span>Sin datos de rendimiento todavía</span>
      </div>
    );
  }
  const esMuestra = metrica.fuente === "muestra";
  return (
    <div className={cn(base, "text-muted-foreground")}>
      <Tooltip label="Visualizaciones">
        <span className="flex items-center gap-1">
          <Eye className="h-3 w-3" />
          {formatearCifra(metrica.visualizaciones)}
        </span>
      </Tooltip>
      <Tooltip label="Interacciones">
        <span className="flex items-center gap-1">
          <Heart className="h-3 w-3" />
          {formatearCifra(metrica.interacciones)}
        </span>
      </Tooltip>
      <Tooltip label="Engagement">
        <span className="flex items-center gap-1 font-medium text-foreground">
          {metrica.engagement_pct.toFixed(1)}% eng.
        </span>
      </Tooltip>
      {esMuestra && (
        <Badge variant="aviso" className="h-4 px-1 text-[10px] font-normal">
          muestra
        </Badge>
      )}
    </div>
  );
}

/**
 * Editor del copy de UNA fila por plataforma: variantes por red con contador/límite de
 * caracteres, inserción de variables `{...}` y previa con las variables ya sustituidas
 * (vía `POST /api/contenido/{id}/preview`). Guarda en `contenido_plataforma.copy`.
 */
function EditorCopy({
  contenidoId,
  plataforma,
  variables,
  guardando,
  onGuardar,
}: {
  contenidoId: string;
  plataforma: ContenidoPlataforma;
  variables: VariableCopy[];
  guardando: boolean;
  onGuardar: (copy: string) => void;
}) {
  const [texto, setTexto] = React.useState(plataforma.copy);
  const [verPrevia, setVerPrevia] = React.useState(false);
  const areaRef = React.useRef<HTMLTextAreaElement>(null);
  const limite = limiteRed(plataforma.red);
  const sucio = texto !== plataforma.copy;

  // El copy del servidor cambió (p.ej. lo rellenó el asistente IA): si NO hay edición
  // local sin guardar respecto al valor anterior del servidor, adoptamos el nuevo. Así no
  // pisamos lo que el usuario está escribiendo, pero sí reflejamos un relleno externo.
  const servidorRef = React.useRef(plataforma.copy);
  React.useEffect(() => {
    if (plataforma.copy !== servidorRef.current) {
      setTexto((prev) => (prev === servidorRef.current ? plataforma.copy : prev));
      servidorRef.current = plataforma.copy;
    }
  }, [plataforma.copy]);

  // Previa: expande las variables del texto contra el contexto del contenido. Debounced.
  const previa = useQuery({
    queryKey: ["contenido-preview", contenidoId, texto],
    queryFn: ({ signal }) => api.previewContenido(contenidoId, texto, signal),
    enabled: verPrevia && texto.includes("{"),
    staleTime: 30_000,
  });

  const insertarVariable = (ejemplo: string) => {
    const area = areaRef.current;
    if (!area) {
      setTexto((t) => t + ejemplo);
      return;
    }
    const inicio = area.selectionStart ?? texto.length;
    const fin = area.selectionEnd ?? texto.length;
    setTexto(texto.slice(0, inicio) + ejemplo + texto.slice(fin));
    requestAnimationFrame(() => {
      area.focus();
      const pos = inicio + ejemplo.length;
      area.setSelectionRange(pos, pos);
    });
  };

  const previaTexto = previa.data?.preview ?? texto;

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-background/60 p-2">
      <div className="flex items-center justify-between">
        <Label htmlFor={`copy-${plataforma.id}`} className="text-xs text-muted-foreground">
          Copy para {plataforma.red_nombre}
        </Label>
        <ContadorCaracteres caracteres={texto.length} limite={limite} />
      </div>
      <AutoTextarea
        ref={areaRef}
        id={`copy-${plataforma.id}`}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder={`Escribe el copy para ${plataforma.red_nombre}. Usa {marca}, {fecha}…`}
        maxHeight={320}
        className="min-h-[5rem] font-mono text-sm"
      />
      {variables.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">Insertar:</span>
          {variables.map((v) => (
            <Tooltip key={v.clave} label={v.etiqueta}>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-6 px-1.5 font-mono text-[11px]"
                onClick={() => insertarVariable(v.ejemplo)}
              >
                {v.ejemplo}
              </Button>
            </Tooltip>
          ))}
        </div>
      )}
      {verPrevia && (
        <div className="rounded-md bg-muted/50 p-2">
          <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Previa (variables sustituidas)
          </p>
          <p className="whitespace-pre-wrap text-sm">
            {previaTexto || <span className="text-muted-foreground/60">Sin copy.</span>}
          </p>
        </div>
      )}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          className="h-7"
          onClick={() => onGuardar(texto)}
          disabled={!sucio || guardando}
        >
          {guardando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
          Guardar copy
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1"
          onClick={() => setVerPrevia((v) => !v)}
        >
          <Eye className="h-3.5 w-3.5" />
          {verPrevia ? "Ocultar previa" : "Previa"}
        </Button>
      </div>
    </div>
  );
}

/**
 * Editor de la IMAGEN de una fila por plataforma, con la afordancia según el TIPO de
 * contenido de la pieza:
 *   - `fuente`: pega la URL de la imagen del artículo/clip original (`imagen_fuente`).
 *   - `ia` / `galeria`: genera con IA o sube/adjunta (reutiliza `EditorImagen`).
 * En todos los casos la imagen mostrada en el feed sale de `imagen_url` (media adjunta o,
 * en su defecto, la URL de la fuente).
 */
function EditorImagenPlataforma({
  plataforma,
  tipoContenido,
  guardando,
  onGuardarImagen,
  onGuardarFuente,
}: {
  plataforma: ContenidoPlataforma;
  tipoContenido: TipoContenido;
  guardando: boolean;
  onGuardarImagen: (imagen: string) => void;
  onGuardarFuente: (imagenFuente: string) => void;
}) {
  const [urlFuente, setUrlFuente] = React.useState(plataforma.imagen_fuente);
  React.useEffect(() => {
    setUrlFuente(plataforma.imagen_fuente);
  }, [plataforma.imagen_fuente]);
  const sucioFuente = urlFuente.trim() !== plataforma.imagen_fuente;

  if (tipoContenido === "fuente") {
    return (
      <div className="space-y-2 rounded-md border border-border/60 bg-background/60 p-2">
        <Label htmlFor={`fuente-${plataforma.id}`} className="text-xs text-muted-foreground">
          Imagen de la fuente original (URL) para {plataforma.red_nombre}
        </Label>
        {plataforma.imagen_url && (
          <img
            src={plataforma.imagen_url}
            alt="Imagen de la fuente"
            className="max-h-40 w-auto rounded-md border border-border object-contain"
          />
        )}
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            id={`fuente-${plataforma.id}`}
            value={urlFuente}
            onChange={(e) => setUrlFuente(e.target.value)}
            placeholder="https://…/imagen-del-articulo.jpg"
            disabled={guardando}
          />
          <Button
            size="sm"
            className="h-9 shrink-0"
            onClick={() => onGuardarFuente(urlFuente.trim())}
            disabled={!sucioFuente || guardando}
          >
            {guardando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            Guardar
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Pega la URL de la imagen del artículo o clip de origen.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-1.5 rounded-md border border-border/60 bg-background/60 p-2">
      <EditorImagen
        imagen={plataforma.imagen}
        imagenUrl={plataforma.imagen_url}
        onCambio={(nombre) => onGuardarImagen(nombre)}
        idPrefijo={`img-${plataforma.id}`}
        red={plataforma.red}
        copy={plataforma.copy}
        disabled={guardando}
      />
      <p className="text-xs text-muted-foreground">
        {tipoContenido === "galeria"
          ? "Sube una imagen o adjúntala desde tu equipo."
          : "Genera la imagen con IA (o súbela si ya la tienes)."}
      </p>
    </div>
  );
}

function DialogoNuevo({
  abierto,
  onCerrar,
  catalogos,
  workspace,
  etiquetasWorkspace,
}: {
  abierto: boolean;
  onCerrar: () => void;
  catalogos: CatalogosContenido;
  workspace: string;
  etiquetasWorkspace: EtiquetaCatalogo[];
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [clase, setClase] = React.useState<"contenido" | "tarea">("contenido");
  const [flujo, setFlujo] = React.useState<Contenido["flujo"]>("importante");
  // Por defecto el workspace activo (si hay uno fijado), para que la pieza nazca en él.
  const [marca, setMarca] = React.useState(workspace === WORKSPACE_TODAS ? "" : workspace);
  const [evento, setEvento] = React.useState(SIN_EVENTO);
  const [prioridad, setPrioridad] = React.useState<Contenido["prioridad"]>("media");
  const [fechaEntrega, setFechaEntrega] = React.useState("");
  const [responsable, setResponsable] = React.useState(SIN_RESPONSABLE);
  const [descripcion, setDescripcion] = React.useState("");
  const [tipoContenido, setTipoContenido] = React.useState<TipoContenido>("ia");
  const [redes, setRedes] = React.useState<string[]>([]);
  const [etiquetas, setEtiquetas] = React.useState<string[]>([]);

  // Al abrir, preselecciona la marca del workspace activo.
  React.useEffect(() => {
    if (abierto) setMarca(workspace === WORKSPACE_TODAS ? "" : workspace);
  }, [abierto, workspace]);

  const reiniciar = () => {
    setTitulo("");
    setClase("contenido");
    setFlujo("importante");
    setMarca(workspace === WORKSPACE_TODAS ? "" : workspace);
    setEvento(SIN_EVENTO);
    setPrioridad("media");
    setFechaEntrega("");
    setResponsable(SIN_RESPONSABLE);
    setDescripcion("");
    setTipoContenido("ia");
    setRedes([]);
    setEtiquetas([]);
  };

  // Etiquetas elegibles: las globales + las de la marca seleccionada.
  const etiquetasElegibles = etiquetasWorkspace.filter(
    (e) => e.marca === "" || e.marca === marca,
  );

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearContenido = {
        titulo: titulo.trim(),
        clase,
        prioridad,
        fecha_entrega: fechaEntrega,
        descripcion: descripcion.trim(),
        responsable_id: responsable === SIN_RESPONSABLE ? "" : responsable,
      };
      if (clase === "contenido") {
        cuerpo.flujo = flujo;
        cuerpo.marca = marca;
        cuerpo.tipo_contenido = tipoContenido;
        cuerpo.redes = redes;
        cuerpo.etiquetas = etiquetas;
        // Solo tiene sentido atar a un evento en el flujo de cobertura de eventos.
        if (flujo === "evento") cuerpo.evento_id = evento === SIN_EVENTO ? "" : evento;
      }
      return api.crearContenido(cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE });
      toast.success("Contenido creado.");
      reiniciar();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const toggleRed = (id: string) =>
    setRedes((rs) => (rs.includes(id) ? rs.filter((r) => r !== id) : [...rs, id]));
  const toggleEtiqueta = (id: string) =>
    setEtiquetas((es) => (es.includes(id) ? es.filter((e) => e !== id) : [...es, id]));

  const puedeCrear = titulo.trim().length > 0 && !crear.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ClipboardList className="h-4 w-4" />
            Nuevo contenido
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="nc-titulo">Título</Label>
            <Input
              id="nc-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Ej. Cobertura del partido de las 8"
              maxLength={300}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="nc-clase">Tipo</Label>
              <Select value={clase} onValueChange={(v) => setClase(v as "contenido" | "tarea")}>
                <SelectTrigger id="nc-clase" aria-label="Tipo">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="contenido">Contenido</SelectItem>
                  <SelectItem value="tarea">Tarea del equipo</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nc-prioridad">Prioridad</Label>
              <Select
                value={prioridad}
                onValueChange={(v) => setPrioridad(v as Contenido["prioridad"])}
              >
                <SelectTrigger id="nc-prioridad" aria-label="Prioridad">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(["alta", "media", "baja"] as const).map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {clase === "contenido" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="nc-flujo">Flujo</Label>
                <Select value={flujo} onValueChange={(v) => setFlujo(v as Contenido["flujo"])}>
                  <SelectTrigger id="nc-flujo" aria-label="Flujo">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="importante">Importante del día</SelectItem>
                    <SelectItem value="evergreen">Evergreen</SelectItem>
                    <SelectItem value="evento">Evento previsto</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nc-marca">
                  Marca <span className="font-normal text-muted-foreground">(opcional)</span>
                </Label>
                <Select
                  value={marca || "__sin__"}
                  onValueChange={(v) => setMarca(v === "__sin__" ? "" : v)}
                >
                  <SelectTrigger id="nc-marca" aria-label="Marca">
                    <SelectValue placeholder="(sin marca)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__sin__">(sin marca)</SelectItem>
                    {catalogos.marcas.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.nombre}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {/* Tipo de contenido: de dónde sale la IMAGEN de la pieza. Determina la
              afordancia de imagen en el editor por plataforma (IA / galería / fuente). */}
          {clase === "contenido" && (
            <div className="space-y-1.5">
              <Label htmlFor="nc-tipo">Imagen</Label>
              <Select
                value={tipoContenido}
                onValueChange={(v) => setTipoContenido(v as TipoContenido)}
              >
                <SelectTrigger id="nc-tipo" aria-label="Tipo de imagen">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ia">Generada por IA</SelectItem>
                  <SelectItem value="galeria">De galería (subir)</SelectItem>
                  <SelectItem value="fuente">De la fuente original</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Evento: solo en el flujo de cobertura de eventos. Ata la pieza a un evento
              del catálogo (`catalogos.eventos`); opcional ("(ninguno)"). */}
          {clase === "contenido" && flujo === "evento" && (
            <div className="space-y-1.5">
              <Label htmlFor="nc-evento">
                Evento <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <Select value={evento} onValueChange={setEvento}>
                <SelectTrigger id="nc-evento" aria-label="Evento">
                  <SelectValue placeholder="(ninguno)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SIN_EVENTO}>(ninguno)</SelectItem>
                  {catalogos.eventos.map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {etiquetaEvento(e)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="nc-entrega">
                Deadline <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <Input
                id="nc-entrega"
                type="date"
                value={fechaEntrega}
                onChange={(e) => setFechaEntrega(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nc-resp">
                Responsable <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <Select value={responsable} onValueChange={setResponsable}>
                <SelectTrigger id="nc-resp" aria-label="Responsable">
                  <SelectValue placeholder="Sin asignar" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
                  {catalogos.usuarios.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {u.usuario}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {clase === "contenido" && (
            <div className="space-y-1.5">
              <Label>
                Plataformas <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <div className="flex flex-wrap gap-2">
                {catalogos.redes.map((r) => (
                  <label key={r.id} className="flex items-center gap-1.5 text-sm">
                    <Checkbox
                      checked={redes.includes(r.id)}
                      onCheckedChange={() => toggleRed(r.id)}
                      aria-label={r.nombre}
                    />
                    {r.nombre}
                  </label>
                ))}
              </div>
            </div>
          )}

          {clase === "contenido" && etiquetasElegibles.length > 0 && (
            <div className="space-y-1.5">
              <Label>
                Etiquetas <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <div className="flex flex-wrap gap-2">
                {etiquetasElegibles.map((e) => (
                  <label key={e.id} className="flex items-center gap-1.5 text-sm">
                    <Checkbox
                      checked={etiquetas.includes(e.id)}
                      onCheckedChange={() => toggleEtiqueta(e.id)}
                      aria-label={e.nombre}
                    />
                    {e.nombre}
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="nc-desc">
              Notas / brief <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Textarea
              id="nc-desc"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              placeholder="Contexto, enlaces o qué hay que sacar."
              rows={4}
              maxLength={8000}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Crear
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Gestión del CATÁLOGO de etiquetas (crear/editar/borrar). Lee de `/api/etiquetas`. */
function DialogoEtiquetas({
  abierto,
  onCerrar,
  marcas,
}: {
  abierto: boolean;
  onCerrar: () => void;
  marcas: { id: string; nombre: string }[];
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["etiquetas"],
    queryFn: ({ signal }) => api.etiquetas({}, signal),
    enabled: abierto,
  });
  const [nombre, setNombre] = React.useState("");
  const [clase, setClase] = React.useState("campania");
  const [marca, setMarca] = React.useState("");

  // Edición en línea de una etiqueta existente (renombrar / cambiar eje / marca).
  const [editandoId, setEditandoId] = React.useState<string | null>(null);
  const [editNombre, setEditNombre] = React.useState("");
  const [editClase, setEditClase] = React.useState("campania");
  const [editMarca, setEditMarca] = React.useState("");

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: ["etiquetas"] });
    // El catálogo de etiquetas del tablero viaja dentro de /api/contenido.
    void queryClient.invalidateQueries({ queryKey: CLAVE });
  };

  const empezarEdicion = (e: Etiqueta) => {
    setEditandoId(e.id);
    setEditNombre(e.nombre);
    setEditClase(e.clase);
    setEditMarca(e.marca || "");
  };
  const cancelarEdicion = () => setEditandoId(null);

  const crear = useMutation({
    mutationFn: () =>
      api.crearEtiqueta({ nombre: nombre.trim(), clase: clase as never, marca }),
    onSuccess: () => {
      invalidar();
      setNombre("");
      toast.success("Etiqueta creada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const actualizar = useMutation({
    mutationFn: (id: string) =>
      api.actualizarEtiqueta(id, {
        nombre: editNombre.trim(),
        clase: editClase as never,
        marca: editMarca,
      }),
    onSuccess: () => {
      invalidar();
      setEditandoId(null);
      toast.success("Etiqueta actualizada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: (id: string) => api.eliminarEtiqueta(id),
    onSuccess: () => {
      invalidar();
      toast.success("Etiqueta borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const etiquetas = query.data?.etiquetas ?? [];

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tag className="h-4 w-4" />
            Etiquetas editoriales
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Alta de etiqueta. */}
          <div className="grid grid-cols-[1fr_auto_auto_auto] items-end gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="et-nombre">Nombre</Label>
              <Input
                id="et-nombre"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Ej. Mundial 2026"
                maxLength={60}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="et-clase">Eje</Label>
              <Select value={clase} onValueChange={setClase}>
                <SelectTrigger id="et-clase" aria-label="Eje" className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CLASE_ETIQUETA_LABEL).map(([v, l]) => (
                    <SelectItem key={v} value={v}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="et-marca">Marca</Label>
              <Select value={marca || "__global__"} onValueChange={(v) => setMarca(v === "__global__" ? "" : v)}>
                <SelectTrigger id="et-marca" aria-label="Marca" className="w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__global__">Global</SelectItem>
                  {marcas.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={() => crear.mutate()}
              disabled={nombre.trim().length === 0 || crear.isPending}
            >
              {crear.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Añadir
            </Button>
          </div>

          {/* Listado del catálogo. */}
          {query.isPending ? (
            <Skeleton className="h-24 w-full rounded-md" />
          ) : etiquetas.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Aún no hay etiquetas. Crea la primera arriba.
            </p>
          ) : (
            <div className="space-y-1.5">
              {etiquetas.map((e) =>
                editandoId === e.id ? (
                  <div
                    key={e.id}
                    className="grid grid-cols-[1fr_auto_auto_auto_auto] items-end gap-2 rounded-md border border-border/60 px-2 py-1.5"
                  >
                    <div className="space-y-1.5">
                      <Label htmlFor={`et-edit-nombre-${e.id}`} className="sr-only">
                        Nombre
                      </Label>
                      <Input
                        id={`et-edit-nombre-${e.id}`}
                        value={editNombre}
                        onChange={(ev) => setEditNombre(ev.target.value)}
                        maxLength={60}
                      />
                    </div>
                    <Select value={editClase} onValueChange={setEditClase}>
                      <SelectTrigger aria-label="Eje" className="w-32">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(CLASE_ETIQUETA_LABEL).map(([v, l]) => (
                          <SelectItem key={v} value={v}>
                            {l}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select
                      value={editMarca || "__global__"}
                      onValueChange={(v) => setEditMarca(v === "__global__" ? "" : v)}
                    >
                      <SelectTrigger aria-label="Marca" className="w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__global__">Global</SelectItem>
                        {marcas.map((m) => (
                          <SelectItem key={m.id} value={m.id}>
                            {m.nombre}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      size="icon"
                      aria-label={`Guardar etiqueta ${e.nombre}`}
                      className="h-9 w-9"
                      onClick={() => actualizar.mutate(e.id)}
                      disabled={editNombre.trim().length === 0 || actualizar.isPending}
                    >
                      {actualizar.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Check className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Cancelar edición"
                      className="h-9 w-9"
                      onClick={cancelarEdicion}
                      disabled={actualizar.isPending}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ) : (
                  <div
                    key={e.id}
                    className="flex items-center gap-2 rounded-md border border-border/60 px-2 py-1.5 text-sm"
                  >
                    <Tag className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-medium">{e.nombre}</span>
                    <Badge variant="secondary" className="font-normal">
                      {CLASE_ETIQUETA_LABEL[e.clase] ?? e.clase}
                    </Badge>
                    <Badge variant="outline" className="font-normal">
                      {e.marca_nombre || "Global"}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Editar etiqueta ${e.nombre}`}
                      className="ml-auto h-7 w-7 text-muted-foreground hover:text-foreground"
                      onClick={() => empezarEdicion(e)}
                      disabled={borrar.isPending}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Borrar etiqueta ${e.nombre}`}
                      className="h-7 w-7 text-muted-foreground hover:text-destructive"
                      onClick={() => borrar.mutate(e.id)}
                      disabled={borrar.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ),
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Modos del asistente IA con su etiqueta y descripción para la UI. */
const MODOS_ASISTENTE: { modo: ModoAsistenteContenido; etiqueta: string; ayuda: string }[] = [
  { modo: "generar", etiqueta: "Generar copy", ayuda: "Una variante por red, lista para revisar." },
  { modo: "variantes", etiqueta: "3 variantes", ayuda: "Tres enfoques alternativos para elegir." },
  { modo: "resumir", etiqueta: "Resumir", ayuda: "Condensa el brief a lo esencial por red." },
];

/**
 * Asistente IA del tablero sobre un `contenido`: genera / resume / 3 variantes
 * reutilizando las skills de copy (voz de marca + tropicalización MX + verificación).
 * Lanza un trabajo en segundo plano, lo sigue token a token y, al completarse, ofrece
 * APLICAR cada pieza generada al `copy` de su fila `contenido_plataforma`.
 */
function DialogoAsistente({
  abierto,
  onCerrar,
  contenido,
  onAplicado,
}: {
  abierto: boolean;
  onCerrar: () => void;
  contenido: Contenido;
  onAplicado: () => void;
}) {
  const [modo, setModo] = React.useState<ModoAsistenteContenido>("generar");
  const seguimiento = useGeneracion();
  const { generacion, ejecutando, iniciar, limpiar } = seguimiento;

  const lanzar = useMutation({
    mutationFn: () => api.asistenteContenido(contenido.id, { modo }),
    onSuccess: (r) => iniciar(r.generacion),
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Filas por red del contenido: mapa red -> fila, para aplicar la pieza correcta.
  const filaPorRed = React.useMemo(() => {
    const m = new Map<string, ContenidoPlataforma>();
    for (const p of contenido.plataformas) m.set(p.red, p);
    return m;
  }, [contenido.plataformas]);

  const aplicar = useMutation({
    mutationFn: ({ plataformaId, copy }: { plataformaId: string; copy: string }) =>
      api.actualizarPlataforma(contenido.id, plataformaId, { copy }),
    onSuccess: () => {
      onAplicado();
      toast.success("Copy aplicado a la plataforma.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const piezas: PiezaGenerada[] = generacion?.resultado?.piezas ?? [];
  const errorGen = generacion?.estado === "error";

  const cerrar = () => {
    limpiar();
    onCerrar();
  };

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && cerrar()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Asistente IA · {contenido.titulo}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2">
            {MODOS_ASISTENTE.map((m) => (
              <button
                key={m.modo}
                type="button"
                onClick={() => setModo(m.modo)}
                disabled={ejecutando || lanzar.isPending}
                className={cn(
                  "rounded-md border p-2 text-left text-xs transition",
                  modo === m.modo ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50",
                )}
              >
                <span className="block font-medium">{m.etiqueta}</span>
                <span className="text-muted-foreground">{m.ayuda}</span>
              </button>
            ))}
          </div>

          <Button
            onClick={() => lanzar.mutate()}
            disabled={ejecutando || lanzar.isPending}
            className="w-full"
          >
            {ejecutando || lanzar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <MarcaIA />
            )}
            {ejecutando ? "Generando…" : "Generar con IA"}
          </Button>

          {errorGen && (
            <p className="text-sm text-red-600 dark:text-red-400">
              {generacion?.error || "No se pudo generar. Inténtalo de nuevo."}
            </p>
          )}

          {ejecutando && generacion?.salida && (
            <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-md bg-muted/50 p-2 text-xs">
              {generacion.salida}
            </pre>
          )}

          {generacion?.resultado?.verdicto && (
            <p className="text-xs text-muted-foreground">
              Auto-verificación: {generacion.resultado.verdicto}
            </p>
          )}

          {piezas.length > 0 && (
            <div className="space-y-3">
              <p className="text-sm font-medium">Copy generado por red</p>
              {piezas.map((pieza) => {
                const fila = filaPorRed.get(pieza.red);
                const limite = limiteRed(pieza.red);
                return (
                  <div key={pieza.red} className="space-y-1.5 rounded-md border p-2">
                    <div className="flex items-center justify-between">
                      <Badge variant="outline" className="font-normal">
                        {fila?.red_nombre ?? pieza.red}
                      </Badge>
                      <ContadorCaracteres caracteres={pieza.contenido.length} limite={limite} />
                    </div>
                    <p className="whitespace-pre-wrap text-sm">{pieza.contenido}</p>
                    {fila ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7"
                        onClick={() =>
                          aplicar.mutate({ plataformaId: fila.id, copy: pieza.contenido })
                        }
                        disabled={aplicar.isPending}
                      >
                        <Check className="h-3.5 w-3.5" />
                        Aplicar a {fila.red_nombre}
                      </Button>
                    ) : (
                      <p className="text-xs text-muted-foreground/70">
                        Añade {pieza.red} al contenido para aplicar este copy.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={cerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
