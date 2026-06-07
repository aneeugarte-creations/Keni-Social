import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Building2,
  CheckCircle2,
  CircleSlash,
  CircleX,
  ExternalLink,
  Globe,
  Layers,
  Lightbulb,
  Link2,
  Loader2,
  Plus,
  Rss,
  Send,
  Trash2,
  TrendingUp,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRedMultiple } from "@/components/comunes/SelectorRedMultiple";
import { desdeMarca, marcaParam } from "@/components/comunes/selectores";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  FuenteRss,
  MarcaDisponible,
  Preset,
  RedPublicacion,
} from "@/types";

import {
  formatearFechaHora,
  ORDEN_REDES,
  tiempoRelativo,
} from "./publicaciones/meta";
import { TallerGreen } from "./fuentes/TallerGreen";
// Salud del motor de ingesta de feeds (antes sub-vista de Cobertura/Noticias): la
// observabilidad de los canales es configuración de Fuentes, no curación del pool.
import { SaludFeeds } from "./fuentes/SaludFeeds";
// Canales absorbidos al colapsar el hub Investigación a 3 piezas (Noticias ·
// Contenidos · Fuentes): los buzones del día, los agentes de investigación y los
// eventos/programas de cobertura dejan de ser pestañas sueltas del hub y pasan a
// ser TIPOS DE FUENTE aquí. Se componen sus páginas existentes (cada una trae su
// propia cabecera, datos y marca activa); la fusión fina vive en una fase posterior.
import CajonesDia from "./CajonesDia";
import AgentesInvestigacion from "./AgentesInvestigacion";
import EventosCobertura from "./EventosCobertura";

const CLAVE_FUENTES = ["rss", "fuentes"] as const;
const CLAVE_ITEMS = ["rss", "items"] as const;

const CABECERA = {
  titulo: "Fuentes",
  descripcion:
    "Los canales de los que se alimentan Noticias y Contenidos, todos en un sitio y por " +
    "marca: RSS y agencias, buzones del día (portal, corresponsales, reporteros, Excel), " +
    "agentes de investigación, eventos y programas, ideas, enlaces y el banco Green.",
};

/**
 * Taxonomía de TIPOS de fuente en UN SOLO sitio (item G): añadir un tipo nuevo es declarar
 * una entrada aquí + su componente de pestaña. Cada tipo decide su propia alta/edición.
 *
 *   - `standing`: fuentes CONFIGURABLES que se quedan dadas de alta (RSS, Trends, agencias).
 *   - `manual`:   APORTACIONES puntuales que producen un item REAL en Pendientes (ideas,
 *                 enlaces pegados, contenido interno), reusando `POST /api/fuentes/aportar`.
 */
type PestanaTipo = {
  valor: string;
  etiqueta: string;
};

const PESTANAS_TIPO: PestanaTipo[] = [
  { valor: "todas", etiqueta: "Todas" },
  { valor: "rss", etiqueta: "RSS" },
  { valor: "salud", etiqueta: "Salud de feeds" },
  { valor: "catalogo", etiqueta: "Catálogo" },
  // Canales que alimentan NOTICIAS, absorbidos del antiguo hub Investigación:
  { valor: "buzones", etiqueta: "Buzones" },
  { valor: "agentes", etiqueta: "Agentes" },
  { valor: "eventos", etiqueta: "Eventos" },
  // Aportaciones manuales (idea/enlace/interno) unificadas en una sola pestaña:
  { valor: "aportar", etiqueta: "Aportar" },
  // Canal que alimenta CONTENIDOS (evergreen):
  { valor: "green", etiqueta: "Green" },
];

/**
 * Pestaña "Aportar": una sola superficie para las aportaciones manuales (idea,
 * enlace, contenido interno), con un selector de tipo. Antes eran tres pestañas
 * sueltas; se unifican para calmar la barra. Reutiliza `AportarManual`.
 */
function AportarHub({
  marcas,
  redes,
}: {
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  const [tipo, setTipo] = React.useState<"idea" | "enlace" | "interna">("idea");
  const opciones: { valor: "idea" | "enlace" | "interna"; etiqueta: string }[] = [
    { valor: "idea", etiqueta: "Idea" },
    { valor: "enlace", etiqueta: "Enlace" },
    { valor: "interna", etiqueta: "Interno AMX" },
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1">
        {opciones.map((o) => (
          <Button
            key={o.valor}
            type="button"
            size="sm"
            variant={tipo === o.valor ? "default" : "outline"}
            onClick={() => setTipo(o.valor)}
          >
            {o.etiqueta}
          </Button>
        ))}
      </div>
      <AportarManual tipo={tipo} marcas={marcas} redes={redes} />
    </div>
  );
}

/**
 * Página de Fuentes: HUB multi-tipo de insumos.
 *
 * Pestaña por defecto "Todas": vista unificada de todas las fuentes configuradas (de
 * cualquier tipo) + estado de agencias. Luego, una pestaña INDEPENDIENTE por tipo, cada
 * una con su propia alta/edición coherente con el tipo. Los tipos MANUALES (ideas, enlaces,
 * interno) producen ítems reales en el pipeline con su fuente visible.
 */
export default function Fuentes() {
  // Las marcas y redes viven en el catálogo de opciones de publicaciones.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  const opcionesRedes = React.useMemo<RedPublicacion[]>(
    () =>
      opcionesQuery.data?.redes ??
      ORDEN_REDES.map((id) => ({ id, nombre: id, limite: null })),
    [opcionesQuery.data],
  );

  // Deep-link de pestaña: las rutas viejas del hub (cajones/agentes/eventos)
  // redirigen aquí con `?tab=` para abrir directamente su canal.
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tabInicial = PESTANAS_TIPO.some((p) => p.valor === tabParam)
    ? (tabParam as string)
    : "todas";

  return (
    <>
      <PageHeader {...CABECERA} />
      <Tabs defaultValue={tabInicial} className="space-y-4">
        <TabsList>
          {PESTANAS_TIPO.map((p) => (
            <TabsTrigger key={p.valor} value={p.valor}>
              {p.etiqueta}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="todas">
          <HubFuentes />
        </TabsContent>
        {/* RSS gestiona solo los FEEDS (config del canal). Los items que producen
            viven en Noticias (el pool), no se duplican aquí. */}
        <TabsContent value="rss">
          <GestionFuentes marcas={marcas} redes={opcionesRedes} />
        </TabsContent>
        {/* Salud del motor de ingesta de feeds (antes en Cobertura/Noticias). */}
        <TabsContent value="salud">
          <SaludFeeds />
        </TabsContent>
        <TabsContent value="catalogo">
          <CatalogoPresets marcas={marcas} />
        </TabsContent>
        {/* Buzones del día: portal/SMS, corresponsales, reporteros y Excel Claro.
            Canales manuales/estructurados que alimentan Noticias. */}
        <TabsContent value="buzones">
          <CajonesDia />
        </TabsContent>
        {/* Agentes de investigación: briefs reutilizables que buscan en la web y
            proponen candidatos al pool de Noticias. */}
        <TabsContent value="agentes">
          <AgentesInvestigacion soloBriefs />
        </TabsContent>
        {/* Eventos y programas de cobertura (agenda editorial → Noticias). */}
        <TabsContent value="eventos">
          <EventosCobertura />
        </TabsContent>
        {/* Aportar: una sola superficie para idea/enlace/interno (antes 3 pestañas). */}
        <TabsContent value="aportar">
          <AportarHub marcas={marcas} redes={opcionesRedes} />
        </TabsContent>
        <TabsContent value="green">
          <TallerGreen marcas={marcas} redes={opcionesRedes} />
        </TabsContent>
      </Tabs>
    </>
  );
}

// --- Hub de TODAS las fuentes (item G): RSS + API + galerías + ideas + internas ---

/** Etiqueta humana de un tipo de fuente del hub. */
const ETIQUETA_TIPO: Record<string, string> = {
  rss: "RSS",
  api: "API / Agencia",
  galeria: "Galería",
  idea: "Idea",
  interna: "Interna",
};

/**
 * Panel "Todas las fuentes": vista UNIFICADA del hub genérico (`/api/fuentes`).
 * Muestra todas las fuentes dadas de alta (de cualquier tipo, con su prioridad y
 * etiquetas) y el estado HONESTO de las agencias (Reuters/AFP): disponibles o
 * "pendientes / no configuradas" según haya credencial, sin inventar nada.
 *
 * Esta vista es de LECTURA/visibilidad: el alta/edición de cada tipo vive en su pestaña
 * dedicada (RSS, Google Trends, Ideas, Enlaces, Interno AMX). Los feeds RSS dados de alta
 * se espejan automáticamente al hub y aparecen aquí.
 */
function HubFuentes() {
  const { marcaActiva } = useMarcaActiva();
  const query = useQuery({
    queryKey: ["fuentes", "hub", marcaActiva ?? ""],
    queryFn: ({ signal }) => api.fuentesHub(undefined, signal),
  });

  if (query.isPending) {
    return <Skeleton className="h-72 w-full rounded-md" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudieron cargar las fuentes"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const { fuentes, agencias, pendientes } = query.data;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <Card className="h-fit">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Layers className="h-4 w-4" />
            Fuentes dadas de alta
            <Badge variant="secondary" className="ml-1">
              {fuentes.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {fuentes.length === 0 ? (
            <EstadoVacioTexto
              texto="Aún no hay fuentes configuradas. Da de alta feeds en la pestaña RSS (se espejan aquí) o configura Google Trends."
              className="py-4"
            />
          ) : (
            <ul className="space-y-2">
              {fuentes.map((f) => (
                <li key={f.id} className="flex items-start justify-between gap-3 rounded-md border p-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{f.nombre}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <Badge variant="outline">{ETIQUETA_TIPO[f.tipo] ?? f.tipo}</Badge>
                      {f.marca_nombre && <Badge variant="secondary">{f.marca_nombre}</Badge>}
                      {f.prioridad !== 0 && <Badge variant="outline">Prioridad {f.prioridad}</Badge>}
                      {f.etiquetas.map((e) => (
                        <Badge key={e} variant="secondary">
                          {e}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  {f.activo ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <CircleSlash className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="h-fit">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Agencias de noticias</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ul className="space-y-2.5">
            {agencias.map((a) => (
              <li key={a.red} className="flex items-start gap-2 text-sm">
                {a.disponible ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <CircleX className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                )}
                <div className="min-w-0">
                  <p className="font-medium">{a.nombre}</p>
                  {!a.disponible && a.motivo && (
                    <p className="text-xs text-muted-foreground">{a.motivo}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {pendientes.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Las agencias pendientes necesitan credenciales (ver README) para empezar a traer
              notas. Hasta entonces aparecen aquí en claro, sin inventar contenido.
            </p>
          )}
          {/* Google Trends ya no tiene pestaña propia: era solo lectura de una config no
              editable. Se resume aquí como la señal built-in que es; su estado real se ve
              por fuente en el panel del Radar. */}
          <div className="flex items-start gap-2 border-t pt-3 text-sm">
            <TrendingUp className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <p className="font-medium">Google Trends</p>
              <p className="text-xs text-muted-foreground">
                Señal built-in del Radar (no se da de alta): se configura por entorno y alimenta
                el{" "}
                <Link
                  to="/datos/investigacion/descubrimiento"
                  className="underline hover:text-foreground"
                >
                  Descubrimiento
                </Link>{" "}
                y la auto-promoción. Su disponibilidad real se ve por fuente en el panel del Radar.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// --- Catálogo de presets (Ola 4) -------------------------------------------

/** Etiquetas humanas de las categorías de presets. */
const ETIQUETA_CATEGORIA: Record<string, string> = {
  mx: "México",
  internacional: "Internacional",
  deportes: "Deportes",
  "ciencia-tech": "Ciencia y Tech",
  gaming: "Gaming",
  tendencias: "Tendencias",
};

/**
 * Sección "Catálogo": lista presets curados de feeds agrupados por categoría,
 * con badges de idioma, región y marca sugerida; checkbox por preset y botón
 * "Activar seleccionadas". Al activar, invalida las queries de RSS/fuentes para
 * que los feeds nuevos aparezcan inmediatamente en la pestaña RSS.
 */
function CatalogoPresets({ marcas }: { marcas: MarcaDisponible[] }) {
  const { marcaActiva } = useMarcaActiva();
  const queryClient = useQueryClient();
  const [categoriaFiltro, setCategoriaFiltro] = React.useState<string>("todas");
  const [seleccionados, setSeleccionados] = React.useState<Set<string>>(() => new Set());

  const query = useQuery({
    queryKey: ["fuentes", "presets", categoriaFiltro, marcaActiva ?? ""],
    queryFn: ({ signal }) =>
      api.fuentesPresets(categoriaFiltro === "todas" ? undefined : categoriaFiltro, signal),
  });

  const activar = useMutation({
    // Al activar: si hay marca activa, úsala como destino por defecto (la preset puede tener
    // su propia marca_sugerida, pero en el contexto de la marca activa tiene precedencia).
    mutationFn: (ids: string[]) =>
      api.activarPresets({ ids, ...(marcaActiva ? { marca: marcaActiva } : {}) }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["fuentes", "presets"] });
      void queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES });
      void queryClient.invalidateQueries({ queryKey: ["fuentes", "hub"] });
      setSeleccionados(new Set());
      toast.success(
        data.creadas === 0
          ? "Los feeds ya estaban activos"
          : `${data.creadas} ${data.creadas === 1 ? "feed activado" : "feeds activados"}`,
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const presets = query.data?.presets ?? [];
  const categorias = query.data?.categorias ?? [];

  function alternarPreset(id: string) {
    setSeleccionados((prev) => {
      const siguiente = new Set(prev);
      if (siguiente.has(id)) siguiente.delete(id);
      else siguiente.add(id);
      return siguiente;
    });
  }

  // Agrupa los presets por categoría para mostrarlos en secciones.
  const porCategoria = React.useMemo(() => {
    const mapa = new Map<string, Preset[]>();
    for (const p of presets) {
      const cat = p.categoria;
      if (!mapa.has(cat)) mapa.set(cat, []);
      mapa.get(cat)!.push(p);
    }
    return mapa;
  }, [presets]);

  const seleccionadosArr = [...seleccionados];
  const haySeleccionados = seleccionadosArr.length > 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="max-w-2xl space-y-1">
          <p className="flex items-center gap-2 text-sm font-medium">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            Feeds curados listos para activar
          </p>
          <p className="text-sm text-muted-foreground">
            Selecciona uno o varios feeds del catálogo y actívalos con un clic. Aparecerán
            inmediatamente en la pestaña RSS y alimentarán el Radar.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Select value={categoriaFiltro} onValueChange={setCategoriaFiltro}>
            <SelectTrigger className="w-44" aria-label="Filtrar por categoría">
              <SelectValue placeholder="Categoría" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todas">Todas</SelectItem>
              {categorias.map((c) => (
                <SelectItem key={c} value={c}>
                  {ETIQUETA_CATEGORIA[c] ?? c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            onClick={() => activar.mutate(seleccionadosArr)}
            disabled={!haySeleccionados || activar.isPending}
          >
            {activar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Activar seleccionadas
            {haySeleccionados && (
              <Badge variant="secondary" className="ml-1">
                {seleccionadosArr.length}
              </Badge>
            )}
          </Button>
        </div>
      </div>

      {query.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-md" />
          ))}
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar el catálogo"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : presets.length === 0 ? (
        <EstadoVacioTexto
          texto="No hay presets disponibles para esta categoría."
          className="py-8"
        />
      ) : (
        <div className="space-y-8">
          {[...porCategoria.entries()].map(([cat, items]) => (
            <div key={cat} className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Globe className="h-4 w-4 text-muted-foreground" />
                {ETIQUETA_CATEGORIA[cat] ?? cat}
                <Badge variant="secondary">{items.length}</Badge>
              </h3>
              <ul className="space-y-2">
                {items.map((preset) => (
                  <FilaPreset
                    key={preset.id}
                    preset={preset}
                    seleccionado={seleccionados.has(preset.id)}
                    onAlternar={() => alternarPreset(preset.id)}
                    marcas={marcas}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Una fila del catálogo de presets. */
function FilaPreset({
  preset,
  seleccionado,
  onAlternar,
  marcas,
}: {
  preset: Preset;
  seleccionado: boolean;
  onAlternar: () => void;
  marcas: MarcaDisponible[];
}) {
  const marcaNombre = marcas.find((m) => m.id === preset.marca_sugerida)?.nombre ?? preset.marca_sugerida;

  return (
    <li
      className={cn(
        "flex items-start gap-3 rounded-md border border-border p-3 transition-colors",
        preset.activa && "opacity-60",
        seleccionado && !preset.activa && "border-primary/50 bg-primary/5",
      )}
    >
      <Checkbox
        id={`preset-${preset.id}`}
        checked={seleccionado}
        onCheckedChange={() => onAlternar()}
        disabled={preset.activa}
        aria-label={`Seleccionar ${preset.nombre}`}
        className="mt-0.5"
      />
      <div className="min-w-0 flex-1 space-y-1">
        <Label
          htmlFor={`preset-${preset.id}`}
          className={cn(
            "block cursor-pointer font-medium leading-snug",
            preset.activa && "cursor-default",
          )}
        >
          {preset.nombre}
          {preset.activa && (
            <Badge variant="ok" className="ml-2 font-normal">
              <CheckCircle2 className="mr-1 h-3 w-3" />
              Activo
            </Badge>
          )}
        </Label>
        {preset.descripcion && (
          <p className="text-xs text-muted-foreground">{preset.descripcion}</p>
        )}
        <div className="flex flex-wrap items-center gap-1.5">
          {preset.idioma && preset.idioma !== "es" && (
            <Badge variant="outline" className="font-normal">
              {preset.idioma.toUpperCase()}
            </Badge>
          )}
          {preset.region && (
            <Badge variant="secondary" className="font-normal">
              {preset.region}
            </Badge>
          )}
          {marcaNombre && (
            <Badge variant="secondary" className="font-normal">
              {marcaNombre}
            </Badge>
          )}
          {preset.linea_sugerida && (
            <Badge variant="outline" className="font-normal">
              {preset.linea_sugerida}
            </Badge>
          )}
        </div>
      </div>
      <a
        href={preset.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-0.5 shrink-0 text-muted-foreground hover:text-foreground"
        title={preset.url}
        aria-label={`Abrir ${preset.nombre}`}
        onClick={(e) => e.stopPropagation()}
      >
        <ExternalLink className="h-4 w-4" />
      </a>
    </li>
  );
}

// --- Aportación MANUAL (idea / enlace / interno) ----------------------------

/** Copys por tipo de aportación manual (taxonomía centralizada). */
const APORTAR_UI: Record<
  string,
  {
    icono: typeof Lightbulb;
    titulo: string;
    descripcion: string;
    placeholder: string;
    etiquetaCampo: string;
    multilinea: boolean;
    boton: string;
    nota?: string;
  }
> = {
  idea: {
    icono: Lightbulb,
    titulo: "Ideas del equipo",
    descripcion:
      "Escribe una idea en texto libre. Al enviarla se crea un ítem real en Pendientes " +
      "(etiquetado como “Idea”) y, si eliges marca, se le genera copy en segundo plano.",
    placeholder:
      "Ej. Hilo sobre los 5 momentazos de la jornada con datos curiosos de cada equipo…",
    etiquetaCampo: "Tu idea",
    multilinea: true,
    boton: "Enviar idea",
  },
  enlace: {
    icono: Link2,
    titulo: "Enlaces de redes / internet",
    descripcion:
      "Pega un enlace (nota, post, video). Se extrae su contenido y se crea un ítem real en " +
      "Pendientes (etiquetado como “Enlace”) con copy en segundo plano si eliges marca.",
    placeholder: "https://…",
    etiquetaCampo: "URL",
    multilinea: false,
    boton: "Procesar enlace",
  },
  interna: {
    icono: Building2,
    titulo: "Contenido interno de AMX",
    descripcion:
      "Registra a mano contenido interno de AMX (briefs, material de programa, avisos). Crea " +
      "un ítem real en Pendientes (etiquetado como “Interno AMX”) con copy en segundo plano.",
    placeholder: "Pega aquí el contenido interno (texto, brief, transcripción)…",
    etiquetaCampo: "Contenido interno",
    multilinea: true,
    boton: "Registrar contenido",
    nota: "El conector automático con los sistemas internos de AMX queda PENDIENTE; por ahora la ingestión es manual.",
  },
};

/**
 * Formulario de aportación MANUAL. Reusa `POST /api/fuentes/aportar`: el backend crea un
 * `contenido` `flujo='importante'` con su `origen` (idea/enlace/interna) y, best-effort,
 * lanza copy en segundo plano. No es UI decorativa: produce un ítem real en el pipeline.
 */
function AportarManual({
  tipo,
  marcas,
  redes,
}: {
  tipo: "idea" | "enlace" | "interna";
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const ui = APORTAR_UI[tipo];
  const Icono = ui.icono;

  // Por defecto la marca activa global (si la cubre el catálogo); si no hay marca
  // activa ("Todas"), queda sin preseleccionar. El usuario puede cambiarla.
  const { marcaActiva } = useMarcaActiva();
  const [texto, setTexto] = React.useState("");
  const [marca, setMarca] = React.useState(
    marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : "",
  );
  const [generar, setGenerar] = React.useState(true);
  const [redesDef, setRedesDef] = React.useState<Set<string>>(() => new Set());

  const opcionesRedes = React.useMemo(
    () => redes.map((r) => ({ id: r.id, nombre: r.nombre })),
    [redes],
  );

  function alternarRed(red: string, marcada: boolean) {
    setRedesDef((prev) => {
      const siguiente = new Set(prev);
      if (marcada) siguiente.add(red);
      else siguiente.delete(red);
      return siguiente;
    });
  }

  const aportar = useMutation({
    mutationFn: () =>
      api.aportarFuente({
        tipo,
        marca: marca || undefined,
        redes: redesDef.size > 0 ? [...redesDef] : undefined,
        generar,
        ...(tipo === "enlace" ? { url: texto.trim() } : { texto: texto.trim() }),
      }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["publicaciones"] });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      setTexto("");
      toast.success(
        data.copy_en_proceso
          ? "Copy en marcha — aparecerá en el Feed para imagen y aprobación."
          : "Aportación creada en Pendientes",
        {
          action: {
            label: "Ver feed",
            onClick: () => navigate("/operacion/feed/lista"),
          },
        },
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Si se quiere copy automático hace falta marca (sin voz no hay copy). Sin generar, la
  // marca es opcional (el ítem entra a Pendientes y la marca/copy se completan a mano).
  const puedeEnviar =
    texto.trim().length > 0 && !aportar.isPending && (!generar || marca !== "");

  return (
    <div className="mx-auto grid max-w-2xl gap-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Icono className="h-4 w-4" />
            {ui.titulo}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">{ui.descripcion}</p>

          <div className="space-y-1.5">
            <Label htmlFor="aportar-texto">{ui.etiquetaCampo}</Label>
            {ui.multilinea ? (
              <Textarea
                id="aportar-texto"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder={ui.placeholder}
                rows={6}
              />
            ) : (
              <Input
                id="aportar-texto"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder={ui.placeholder}
                type="url"
                inputMode="url"
              />
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="aportar-marca">
              Marca{" "}
              {!generar && (
                <span className="font-normal text-muted-foreground">(opcional)</span>
              )}
            </Label>
            <Select value={marca} onValueChange={setMarca}>
              <SelectTrigger id="aportar-marca">
                <SelectValue placeholder="Elige una marca" />
              </SelectTrigger>
              <SelectContent>
                {marcas.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-start gap-2">
            <Checkbox
              id="aportar-generar"
              checked={generar}
              onCheckedChange={(v) => setGenerar(!!v)}
              className="mt-0.5"
              aria-label="Generar copy en segundo plano"
            />
            <div className="space-y-0.5">
              <Label htmlFor="aportar-generar" className="cursor-pointer font-normal">
                Generar copy en segundo plano
              </Label>
              <p className="text-xs text-muted-foreground">
                Crea borradores por red en el tablero. Si lo desmarcas, el ítem entra a
                Pendientes y completas copy a mano.
              </p>
            </div>
          </div>

          {generar && (
            <SelectorRedMultiple
              opciones={opcionesRedes}
              seleccionadas={redesDef}
              onCambio={alternarRed}
            />
          )}

          {ui.nota && (
            <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
              {ui.nota}
            </p>
          )}

          <div className="flex justify-end">
            <Button onClick={() => aportar.mutate()} disabled={!puedeEnviar}>
              {aportar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              {ui.boton}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// --- Feeds (panel izquierdo) -----------------------------------------------

/** Panel izquierdo: alta + lista de feeds con salud, edición y activación. */
function GestionFuentes({
  marcas,
  redes,
}: {
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  // Por marca: cada equipo gestiona los feeds de SU marca + los compartidos (sin marca).
  // El radar/plan de la marca lee exactamente este conjunto. Admin (sin marca activa) ve todo.
  const { marcaActiva, nombreActiva } = useMarcaActiva();

  const query = useQuery({
    queryKey: [...CLAVE_FUENTES, marcaActiva ?? ""],
    queryFn: ({ signal }) => api.fuentesRss(signal),
  });

  // null = sin diálogo; "nuevo" = creando; objeto = editando ese feed.
  const [editando, setEditando] = React.useState<FuenteRss | "nuevo" | null>(null);
  const todas = React.useMemo(() => query.data?.fuentes ?? [], [query.data]);
  const fuentes = React.useMemo(
    () => (marcaActiva ? todas.filter((f) => !f.marca || f.marca === marcaActiva) : todas),
    [todas, marcaActiva],
  );
  const compartidas = React.useMemo(
    () => fuentes.filter((f) => !f.marca).length,
    [fuentes],
  );

  return (
    <Card className="h-fit">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Rss className="h-4 w-4" />
          Feeds{marcaActiva && nombreActiva ? ` de ${nombreActiva}` : ""}
        </CardTitle>
        <Button size="sm" variant="outline" onClick={() => setEditando("nuevo")}>
          <Plus className="h-4 w-4" />
          Añadir
        </Button>
      </CardHeader>
      {marcaActiva && (
        <div className="px-6 pb-1 text-xs text-muted-foreground">
          Las fuentes de {nombreActiva ?? "tu marca"} y las compartidas alimentan su radar y plan
          del día.{compartidas > 0 && ` ${compartidas} compartida(s).`}
        </div>
      )}
      <CardContent className="space-y-4">
        {query.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <p className="py-4 text-center text-sm text-muted-foreground">{mensajeError(query.error)}</p>
        ) : fuentes.length === 0 ? (
          <EstadoVacioTexto
            texto={
              marcaActiva
                ? `Aún no hay feeds de ${nombreActiva ?? "tu marca"} ni compartidos. Añade el primero: nutrirá su radar y plan del día.`
                : "Aún no hay feeds. Añade el primero con el botón de arriba."
            }
            className="py-4"
          />
        ) : (
          <div className="space-y-2">
            {fuentes.map((f) => (
              <FilaFuente key={f.id} fuente={f} onEditar={() => setEditando(f)} />
            ))}
          </div>
        )}
      </CardContent>

      <DialogoFuente
        abierto={editando !== null}
        fuente={editando === "nuevo" ? null : editando}
        marcas={marcas}
        redes={redes}
        onCerrar={() => setEditando(null)}
      />
    </Card>
  );
}

/** Una fila de feed con salud, toggle activo, editar y borrar. */
function FilaFuente({
  fuente,
  onEditar,
}: {
  fuente: FuenteRss;
  onEditar: () => void;
}) {
  const queryClient = useQueryClient();

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES });
    void queryClient.invalidateQueries({ queryKey: CLAVE_ITEMS });
  };

  const alternarActivo = useMutation({
    mutationFn: () => api.actualizarFuenteRss(fuente.id, { activo: !fuente.activo }),
    onSuccess: () => {
      invalidar();
      toast.success(fuente.activo ? "Feed desactivado" : "Feed activado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarFuenteRss(fuente.id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? "Feed borrado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Acción primaria = editar el feed. Activar/desactivar y borrar van al menú
  // contextual / kebab; el estado se comunica con la insignia "Inactivo" y la
  // opacidad de la fila, así que el icono de toggle persistente sobra.
  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: fuente.activo ? "Desactivar" : "Activar",
      icono: fuente.activo ? CircleSlash : CheckCircle2,
      onClick: () => alternarActivo.mutate(),
      activo: fuente.activo,
      deshabilitado: alternarActivo.isPending,
    },
    { separador: true },
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Borrar el feed "${fuente.nombre}"?`,
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        )
          borrar.mutate();
      },
      destructivo: true,
      deshabilitado: borrar.isPending,
    },
  ];

  return (
    <FilaConAcciones
      como="div"
      onPrimaria={onEditar}
      acciones={acciones}
      etiquetaAcciones={`Acciones de "${fuente.nombre}"`}
      kebab="hover"
      className={cn(
        "space-y-2 rounded-md border border-border p-3 pr-10",
        !fuente.activo && "opacity-60",
      )}
    >
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{fuente.nombre}</span>
          {fuente.marca && (
            <Badge variant="outline" className="font-normal">
              {fuente.marca_nombre || fuente.marca}
            </Badge>
          )}
          {!fuente.activo && (
            <Badge variant="secondary" className="font-normal">
              Inactivo
            </Badge>
          )}
        </div>
        <a
          href={fuente.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex max-w-full items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
          title={fuente.url}
        >
          <span className="truncate">{fuente.url}</span>
          <ExternalLink className="h-3 w-3 shrink-0" />
        </a>
      </div>
      <SaludFeed fuente={fuente} />
    </FilaConAcciones>
  );
}

/** Línea de salud de un feed: última actualización, conteo y error. */
function SaludFeed({ fuente }: { fuente: FuenteRss }) {
  const relativo = tiempoRelativo(fuente.ultima_actualizacion);
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      {fuente.ultimo_error ? (
        <span className="inline-flex items-center gap-1.5" title={fuente.ultimo_error}>
          <span className="h-2 w-2 shrink-0 rounded-full bg-red-500" aria-hidden />
          Error al refrescar
        </span>
      ) : (
        <span>
          {fuente.ultimo_conteo} {fuente.ultimo_conteo === 1 ? "item" : "items"}
        </span>
      )}
      <span className="text-muted-foreground/60">·</span>
      <span title={formatearFechaHora(fuente.ultima_actualizacion) || undefined}>
        {relativo ? `Actualizado ${relativo}` : "Sin actualizar aún"}
      </span>
    </div>
  );
}

/** Diálogo de alta / edición de un feed. */
function DialogoFuente({
  abierto,
  fuente,
  marcas,
  redes,
  onCerrar,
}: {
  abierto: boolean;
  fuente: FuenteRss | null;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
  onCerrar: () => void;
}) {
  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Rss className="h-5 w-5" />
            {fuente ? "Editar feed" : "Nuevo feed"}
          </DialogTitle>
          <DialogDescription>
            Configura el feed RSS: filtros por palabra clave, redes por defecto al generar y si
            está activo.
          </DialogDescription>
        </DialogHeader>
        {abierto && (
          <FormularioFuente
            fuente={fuente}
            marcas={marcas}
            redes={redes}
            onListo={onCerrar}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Formulario de alta/edición de un feed (dentro del diálogo). */
function FormularioFuente({
  fuente,
  marcas,
  redes,
  onListo,
}: {
  fuente: FuenteRss | null;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
  onListo: () => void;
}) {
  const queryClient = useQueryClient();
  // Feed NUEVO: por defecto la marca activa (así nace tagueado y alimenta su radar).
  // Editando: respeta la marca guardada del feed.
  const { marcaActiva } = useMarcaActiva();
  const [nombre, setNombre] = React.useState(fuente?.nombre ?? "");
  const [url, setUrl] = React.useState(fuente?.url ?? "");
  const [marca, setMarca] = React.useState(
    fuente
      ? desdeMarca(fuente.marca)
      : desdeMarca(
          marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : undefined,
        ),
  );
  const [incluir, setIncluir] = React.useState(fuente?.incluir ?? "");
  const [excluir, setExcluir] = React.useState(fuente?.excluir ?? "");
  const [activo, setActivo] = React.useState(fuente?.activo ?? true);
  const [propia, setPropia] = React.useState(fuente?.propia ?? false);
  const [redesDef, setRedesDef] = React.useState<Set<string>>(
    () => new Set(fuente?.redes_def ?? []),
  );

  const guardar = useMutation({
    mutationFn: () => {
      const marcaVal = marcaParam(marca) ?? "";
      const redesArr = [...redesDef];
      if (fuente) {
        return api.actualizarFuenteRss(fuente.id, {
          nombre: nombre.trim(),
          url: url.trim(),
          marca: marcaVal,
          activo,
          incluir: incluir.trim(),
          excluir: excluir.trim(),
          redes_def: redesArr,
          propia,
        });
      }
      return api.crearFuenteRss({
        nombre: nombre.trim(),
        url: url.trim(),
        marca: marcaVal || undefined,
        incluir: incluir.trim() || undefined,
        excluir: excluir.trim() || undefined,
        redes_def: redesArr.length > 0 ? redesArr : undefined,
        propia: propia || undefined,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES });
      void queryClient.invalidateQueries({ queryKey: CLAVE_ITEMS });
      toast.success(fuente ? "Feed actualizado" : "Feed añadido");
      onListo();
    },
    // El backend puede devolver 400 si la URL no es válida o por SSRF.
    onError: (e) => toast.error(mensajeError(e)),
  });

  function alternarRed(red: string, marcada: boolean) {
    setRedesDef((prev) => {
      const siguiente = new Set(prev);
      if (marcada) siguiente.add(red);
      else siguiente.delete(red);
      return siguiente;
    });
  }

  const opcionesRedes = React.useMemo(
    () => redes.map((r) => ({ id: r.id, nombre: r.nombre })),
    [redes],
  );

  const puedeGuardar =
    nombre.trim().length > 0 && url.trim().length > 0 && !guardar.isPending;

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="fuente-nombre">Nombre</Label>
        <Input
          id="fuente-nombre"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Ej. UnoTV Deportes"
          maxLength={120}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fuente-url">URL del feed</Label>
        <Input
          id="fuente-url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://ejemplo.com/rss.xml"
          type="url"
          inputMode="url"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fuente-marca">
          Marca <span className="font-normal text-muted-foreground">(opcional)</span>
        </Label>
        <SelectorMarca
          id="fuente-marca"
          marcas={marcas}
          valor={marca}
          onCambio={setMarca}
          ariaLabel="Marca"
          className="w-full"
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="fuente-incluir">
            Incluir <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Input
            id="fuente-incluir"
            value={incluir}
            onChange={(e) => setIncluir(e.target.value)}
            placeholder="fútbol, liga"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fuente-excluir">
            Excluir <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Input
            id="fuente-excluir"
            value={excluir}
            onChange={(e) => setExcluir(e.target.value)}
            placeholder="opinión, podcast"
          />
        </div>
      </div>
      <SelectorRedMultiple
        opciones={opcionesRedes}
        seleccionadas={redesDef}
        onCambio={alternarRed}
      />
      <p className="-mt-1 text-xs text-muted-foreground">
        Redes por defecto al generar copy desde una noticia de este feed.
      </p>
      <div className="flex items-center gap-2">
        <Checkbox
          id="fuente-activo"
          checked={activo}
          onCheckedChange={(v) => setActivo(v)}
          aria-label="Feed activo"
        />
        <Label htmlFor="fuente-activo" className="cursor-pointer font-normal">
          Feed activo
        </Label>
      </div>
      <div className="flex items-start gap-2">
        <Checkbox
          id="fuente-propia"
          checked={propia}
          onCheckedChange={(v) => setPropia(!!v)}
          aria-label="Fuente de marca propia"
          className="mt-0.5"
        />
        <div className="space-y-0.5">
          <Label htmlFor="fuente-propia" className="cursor-pointer font-normal">
            Fuente de marca propia
          </Label>
          <p className="text-xs text-muted-foreground">
            Sitio propio: su imagen original es reutilizable, así que las piezas generadas
            desde sus noticias nacen con la imagen del artículo lista para usarse.
          </p>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onListo} disabled={guardar.isPending}>
          Cancelar
        </Button>
        <Button size="sm" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
          {guardar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          {fuente ? "Guardar cambios" : "Añadir feed"}
        </Button>
      </div>
    </div>
  );
}
