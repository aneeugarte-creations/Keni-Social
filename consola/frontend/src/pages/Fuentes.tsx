import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  CircleSlash,
  CircleX,
  ExternalLink,
  Layers,
  Lightbulb,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  Rss,
  Search,
  Send,
  Sparkles,
  Trash2,
  TrendingUp,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { MarcaIA } from "@/components/comunes/MarcaIA";
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
import { Tooltip } from "@/components/ui/tooltip";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  FuenteRss,
  ItemRss,
  MarcaDisponible,
  RedPublicacion,
} from "@/types";

import {
  formatearFechaHora,
  ORDEN_REDES,
  tiempoRelativo,
} from "./publicaciones/meta";
import { GestionLineas } from "./fuentes/GestionLineas";
import { TallerGreen } from "./fuentes/TallerGreen";

const CLAVE_FUENTES = ["rss", "fuentes"] as const;
const CLAVE_ITEMS = ["rss", "items"] as const;

/** Valor de "todas las fuentes" en el filtro de items. */
const FUENTE_TODAS = "__todas__";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/**
 * Limpia emojis de estado (❌ ✅ ⚠️) que el backend puede anteponer a los
 * mensajes y normaliza la puntuación inicial para una vista sobria.
 */
function limpiarMensaje(texto: string): string {
  return String(texto ?? "")
    .replace(/[✅❌⚠]/g, "")
    .replace(/️/g, "")
    .replace(/^[\s:;,.\-–—]+/, "")
    .trim();
}

const CABECERA = {
  titulo: "Fuentes",
  descripcion:
    "El hub de insumos: vigila TODAS tus fuentes en un sitio y aporta material por tipo " +
    "(RSS, Google Trends, ideas, enlaces y contenido interno). Lo que aportas llega al pipeline.",
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
  { valor: "trends", etiqueta: "Google Trends" },
  { valor: "idea", etiqueta: "Ideas" },
  { valor: "enlace", etiqueta: "Enlaces" },
  { valor: "interna", etiqueta: "Interno AMX" },
  { valor: "green", etiqueta: "Green" },
  { valor: "lineas", etiqueta: "Líneas" },
];

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

  return (
    <>
      <PageHeader {...CABECERA} />
      <Tabs defaultValue="todas" className="space-y-4">
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
        <TabsContent value="rss">
          <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
            <GestionFuentes marcas={marcas} redes={opcionesRedes} />
            <ItemsRecientes marcas={marcas} redes={opcionesRedes} />
          </div>
        </TabsContent>
        <TabsContent value="trends">
          <FuenteTrends />
        </TabsContent>
        <TabsContent value="idea">
          <AportarManual tipo="idea" marcas={marcas} redes={opcionesRedes} />
        </TabsContent>
        <TabsContent value="enlace">
          <AportarManual tipo="enlace" marcas={marcas} redes={opcionesRedes} />
        </TabsContent>
        <TabsContent value="interna">
          <AportarManual tipo="interna" marcas={marcas} redes={opcionesRedes} />
        </TabsContent>
        <TabsContent value="green">
          <TallerGreen marcas={marcas} redes={opcionesRedes} />
        </TabsContent>
        <TabsContent value="lineas">
          <GestionLineas />
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
  const query = useQuery({
    queryKey: ["fuentes", "hub"],
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
        </CardContent>
      </Card>
    </div>
  );
}

// --- Google Trends (fuente built-in del Radar) -----------------------------

/**
 * Pestaña Google Trends. Trends NO es multi-instancia: es una fuente BUILT-IN del Radar,
 * configurable GLOBALMENTE (geo + umbral de señal) vía las variables del daemon de
 * auto-promoción. Aquí se muestra esa config viva y su estado de forma honesta, sin inventar
 * multi-instancia que no aplica. La config se ajusta por entorno (no editable desde la UI).
 */
function FuenteTrends() {
  const query = useQuery({
    queryKey: ["radar", "auto", "bandeja"],
    queryFn: ({ signal }) => api.bandejaRadarAuto(signal),
  });

  if (query.isPending) {
    return <Skeleton className="h-56 w-full rounded-md" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo cargar la configuración de Google Trends"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const { config } = query.data;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <Card className="h-fit">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <TrendingUp className="h-4 w-4" />
            Google Trends
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            Tendencias de búsqueda de Google como señal del Radar. Es una fuente única
            (built-in), no se dan de alta varias: se configura globalmente y alimenta el{" "}
            <Link to="/datos/investigacion/radar" className="underline hover:text-foreground">
              Radar
            </Link>{" "}
            y la auto-promoción del día.
          </p>
          <dl className="grid grid-cols-2 gap-3">
            <div className="rounded-md border p-3">
              <dt className="text-xs text-muted-foreground">Región (geo)</dt>
              <dd className="mt-0.5 font-medium">{config.geo || "MX"}</dd>
            </div>
            <div className="rounded-md border p-3">
              <dt className="text-xs text-muted-foreground">Umbral de señal</dt>
              <dd className="mt-0.5 font-medium">{config.umbral.toLocaleString("es-MX")}</dd>
            </div>
            <div className="rounded-md border p-3">
              <dt className="text-xs text-muted-foreground">Auto-promoción</dt>
              <dd className="mt-0.5 font-medium">{config.activo ? "Activa" : "Inactiva"}</dd>
            </div>
            <div className="rounded-md border p-3">
              <dt className="text-xs text-muted-foreground">Máximo por barrido</dt>
              <dd className="mt-0.5 font-medium">{config.max_por_barrido}</dd>
            </div>
          </dl>
          <p className="text-xs text-muted-foreground">
            Estos valores se ajustan por entorno (variables del servidor); por eso aquí se
            muestran en claro pero no se editan. Para revisar lo que entraría hoy, mira la
            bandeja del Radar.
          </p>
        </CardContent>
      </Card>

      <Card className="h-fit">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Estado</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            <span>Disponible como señal del Radar.</span>
          </div>
          <p className="text-xs text-muted-foreground">
            La disponibilidad real (si Google responde) se ve por fuente en el panel del Radar,
            sin inventar nada.
          </p>
        </CardContent>
      </Card>
    </div>
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

  const [texto, setTexto] = React.useState("");
  const [marca, setMarca] = React.useState("");
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
          ? "Aportación creada; generando copy en segundo plano"
          : "Aportación creada en Pendientes",
        {
          action: {
            label: "Ver en el tablero",
            onClick: () => navigate("/operacion/parrilla/pendientes"),
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
  const query = useQuery({
    queryKey: CLAVE_FUENTES,
    queryFn: ({ signal }) => api.fuentesRss(signal),
  });

  // null = sin diálogo; "nuevo" = creando; objeto = editando ese feed.
  const [editando, setEditando] = React.useState<FuenteRss | "nuevo" | null>(null);

  const fuentes = query.data?.fuentes ?? [];

  return (
    <Card className="h-fit">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Rss className="h-4 w-4" />
          Feeds
        </CardTitle>
        <Button size="sm" variant="outline" onClick={() => setEditando("nuevo")}>
          <Plus className="h-4 w-4" />
          Añadir
        </Button>
      </CardHeader>
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
            texto="Aún no hay feeds. Añade el primero con el botón de arriba."
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
  const [nombre, setNombre] = React.useState(fuente?.nombre ?? "");
  const [url, setUrl] = React.useState(fuente?.url ?? "");
  const [marca, setMarca] = React.useState(desdeMarca(fuente?.marca));
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

// --- Items (panel derecho) -------------------------------------------------

/** Panel derecho: items recientes con filtros, refresco y acciones. */
function ItemsRecientes({
  marcas,
  redes,
}: {
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  const [fuenteSel, setFuenteSel] = React.useState(FUENTE_TODAS);
  const [ocultarUsados, setOcultarUsados] = React.useState(false);
  const [filtro, setFiltro] = React.useState("");

  const fuentesQuery = useQuery({
    queryKey: CLAVE_FUENTES,
    queryFn: ({ signal }) => api.fuentesRss(signal),
  });
  const fuentes = React.useMemo(
    () => fuentesQuery.data?.fuentes ?? [],
    [fuentesQuery.data],
  );

  const fuenteParam = fuenteSel === FUENTE_TODAS ? undefined : fuenteSel;
  const query = useQuery({
    queryKey: [...CLAVE_ITEMS, fuenteParam ?? "", ocultarUsados],
    queryFn: ({ signal }) => api.itemsRss(fuenteParam, ocultarUsados, signal),
  });

  const items = React.useMemo(() => query.data?.items ?? [], [query.data]);
  const errores = query.data?.errores ?? [];

  // Filtro por palabra clave (en cliente, sobre título + resumen).
  const itemsFiltrados = React.useMemo(() => {
    const t = filtro.trim().toLowerCase();
    if (!t) return items;
    return items.filter(
      (i) =>
        i.titulo.toLowerCase().includes(t) || i.resumen.toLowerCase().includes(t),
    );
  }, [items, filtro]);

  // Mapa de redes por feed para predefinir al generar copy.
  const redesPorFuente = React.useMemo(() => {
    const mapa = new Map<string, string[]>();
    for (const f of fuentes) mapa.set(f.id, f.redes_def ?? []);
    return mapa;
  }, [fuentes]);
  const marcaPorFuente = React.useMemo(() => {
    const mapa = new Map<string, string>();
    for (const f of fuentes) mapa.set(f.id, f.marca);
    return mapa;
  }, [fuentes]);

  const ultimaActualizacion = React.useMemo(() => {
    const fechas = fuentes
      .map((f) => f.ultima_actualizacion)
      .filter((x): x is string => Boolean(x))
      .sort();
    return fechas.length ? fechas[fechas.length - 1] : null;
  }, [fuentes]);

  return (
    <Card>
      <CardHeader className="space-y-3 pb-3">
        <div className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="text-base">Noticias recientes</CardTitle>
          <div className="flex items-center gap-2">
            <Select value={fuenteSel} onValueChange={setFuenteSel}>
              <SelectTrigger className="w-[180px]" aria-label="Filtrar por fuente">
                <SelectValue placeholder="Fuente" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={FUENTE_TODAS}>Todas las fuentes</SelectItem>
                {fuentes.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Tooltip label="Refrescar">
              <Button
                variant="outline"
                size="icon"
                aria-label="Refrescar noticias"
                onClick={() => void query.refetch()}
                disabled={query.isFetching}
              >
                <RefreshCw className={cn("h-4 w-4", query.isFetching && "animate-spin")} />
              </Button>
            </Tooltip>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[12rem] flex-1">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filtro}
              onChange={(e) => setFiltro(e.target.value)}
              placeholder="Filtrar por palabra clave…"
              className="pl-8"
              aria-label="Filtrar noticias por palabra clave"
            />
          </div>
          <div className="flex items-center gap-2">
            <Checkbox
              id="ocultar-usados"
              checked={ocultarUsados}
              onCheckedChange={(v) => setOcultarUsados(v)}
              aria-label="Ocultar usados"
            />
            <Label htmlFor="ocultar-usados" className="cursor-pointer font-normal">
              Ocultar usados
            </Label>
          </div>
          {ultimaActualizacion && (
            <span className="text-xs text-muted-foreground" title={formatearFechaHora(ultimaActualizacion)}>
              Actualizado {tiempoRelativo(ultimaActualizacion)}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {errores.length > 0 && (
          <div className="space-y-1.5 rounded-md border border-border p-3 text-sm text-muted-foreground">
            <p className="flex items-center gap-2 font-medium text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden />
              Algunos feeds dieron error al refrescar
            </p>
            <ul className="ml-4 list-disc text-xs">
              {errores.map((e) => (
                <li key={e.fuente_id}>
                  <span className="font-medium text-foreground">{e.fuente_nombre}</span>:{" "}
                  {limpiarMensaje(e.error)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {query.isPending ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <BloqueError
            titulo="No se pudieron cargar las noticias"
            mensaje={mensajeError(query.error)}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        ) : itemsFiltrados.length === 0 ? (
          <EstadoVacioTexto
            texto={
              items.length === 0
                ? "No hay noticias para mostrar. Añade un feed o cambia el filtro."
                : "Ninguna noticia coincide con el filtro."
            }
          />
        ) : (
          <div className="space-y-3">
            {itemsFiltrados.map((item, i) => (
              <ItemNoticia
                key={`${item.fuente_id}-${item.clave || item.enlace}-${i}`}
                item={item}
                marcas={marcas}
                redes={redes}
                redesDefecto={redesPorFuente.get(item.fuente_id) ?? []}
                marcaDefecto={marcaPorFuente.get(item.fuente_id) ?? ""}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Una noticia con acciones: marcar usado, generar copy, abrir. */
function ItemNoticia({
  item,
  marcas,
  redes,
  redesDefecto,
  marcaDefecto,
}: {
  item: ItemRss;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
  redesDefecto: string[];
  marcaDefecto: string;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [generarAbierto, setGenerarAbierto] = React.useState(false);

  const marcarUsado = useMutation({
    mutationFn: () =>
      api.marcarItemRssUsado({
        fuente_id: item.fuente_id,
        clave: item.clave,
        usado: !item.usado,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_ITEMS });
      toast.success(item.usado ? "Marcado como no usado" : "Marcado como usado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function usarEnGenerar() {
    const texto = [item.titulo, item.resumen, item.enlace].filter(Boolean).join("\n\n");
    navigate("/generacion", { state: { texto } });
  }

  return (
    <div
      className={cn(
        "space-y-2 rounded-md border border-border p-3 transition-opacity",
        item.usado && "opacity-55",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <Badge variant="secondary" className="font-normal">
          {item.fuente_nombre}
        </Badge>
        {item.fecha && <span>{formatearFechaHora(item.fecha)}</span>}
        {item.usado && (
          <Badge variant="secondary" className="font-normal">
            <CheckCircle2 className="mr-1 h-3 w-3" />
            Usado
          </Badge>
        )}
      </div>
      <p className="font-medium leading-snug">{item.titulo}</p>
      {item.resumen && (
        <p className="line-clamp-3 text-sm text-muted-foreground">{item.resumen}</p>
      )}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button size="sm" onClick={() => setGenerarAbierto(true)}>
          <MarcaIA />
          Generar copy
        </Button>
        <Button variant="outline" size="sm" onClick={usarEnGenerar}>
          <ExternalLink className="h-4 w-4" />
          Abrir en Generar copy
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => marcarUsado.mutate()}
          disabled={marcarUsado.isPending || !item.clave}
          title={!item.clave ? "Este item no admite marcado" : undefined}
        >
          {marcarUsado.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : item.usado ? (
            <CircleSlash className="h-4 w-4" />
          ) : (
            <CheckCircle2 className="h-4 w-4" />
          )}
          {item.usado ? "Marcar no usado" : "Marcar usado"}
        </Button>
        {item.enlace && (
          <Button variant="ghost" size="sm" asChild>
            <a href={item.enlace} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-4 w-4" />
              Abrir
            </a>
          </Button>
        )}
      </div>

      <DialogoGenerar
        abierto={generarAbierto}
        onCerrar={() => setGenerarAbierto(false)}
        item={item}
        marcas={marcas}
        redes={redes}
        redesDefecto={redesDefecto}
        marcaDefecto={marcaDefecto}
      />
    </div>
  );
}

/** Diálogo: elige marca + redes y genera copy desde el item (auto-guarda). */
function DialogoGenerar({
  abierto,
  onCerrar,
  item,
  marcas,
  redes,
  redesDefecto,
  marcaDefecto,
}: {
  abierto: boolean;
  onCerrar: () => void;
  item: ItemRss;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
  redesDefecto: string[];
  marcaDefecto: string;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // Predefine la marca del feed (si la hay y existe en el catálogo) y la
  // primera marca disponible como respaldo.
  const marcaInicial = React.useMemo(() => {
    if (marcaDefecto && marcas.some((m) => m.id === marcaDefecto)) return marcaDefecto;
    return marcas[0]?.id ?? "";
  }, [marcaDefecto, marcas]);

  const [marca, setMarca] = React.useState(marcaInicial);
  const [seleccionadas, setSeleccionadas] = React.useState<Set<string>>(
    () => new Set(redesDefecto),
  );

  // Al (re)abrir, restablece marca y redes a los valores por defecto del feed.
  React.useEffect(() => {
    if (abierto) {
      setMarca(marcaInicial);
      setSeleccionadas(
        new Set(redesDefecto.length > 0 ? redesDefecto : redes.map((r) => r.id)),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [abierto]);

  const opcionesRedes = React.useMemo(
    () => redes.map((r) => ({ id: r.id, nombre: r.nombre })),
    [redes],
  );

  function alternarRed(red: string, marcada: boolean) {
    setSeleccionadas((prev) => {
      const siguiente = new Set(prev);
      if (marcada) siguiente.add(red);
      else siguiente.delete(red);
      return siguiente;
    });
  }

  // La generación corre en background; seguimos el progreso en el propio diálogo.
  const { generacion, ejecutando, iniciar, cancelar, cancelando } = useGeneracion();

  const generar = useMutation({
    mutationFn: () =>
      api.generarDesdeItemRss({
        titulo: item.titulo,
        resumen: item.resumen || undefined,
        enlace: item.enlace || undefined,
        marca,
        redes: [...seleccionadas],
        fuente_id: item.fuente_id || undefined,
        clave: item.clave || undefined,
        imagen: item.imagen || undefined,
      }),
    onSuccess: (data) => iniciar(data.generacion),
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Al completar: avisamos, refrescamos items/publicaciones y cerramos. Error -> toast.
  const terminalRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!generacion || generacion.id === terminalRef.current) return;
    if (generacion.estado === "completado") {
      terminalRef.current = generacion.id;
      const n = generacion.resultado?.publicaciones?.length ?? 0;
      toast.success(
        n > 0
          ? `Generado y guardado en ${n} ${n === 1 ? "publicación" : "publicaciones"}`
          : "Copy generado",
        { action: { label: "Ver en el tablero", onClick: () => navigate("/operacion/parrilla/pendientes") } },
      );
      void queryClient.invalidateQueries({ queryKey: CLAVE_ITEMS });
      void queryClient.invalidateQueries({ queryKey: ["publicaciones"] });
      onCerrar();
    } else if (generacion.estado === "error") {
      terminalRef.current = generacion.id;
      toast.error(generacion.error || "No se pudo generar el copy.");
    }
  }, [generacion, navigate, queryClient, onCerrar]);

  const generando = generar.isPending || ejecutando;
  const puedeGenerar = marca !== "" && seleccionadas.size > 0 && !generando;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            Generar copy
          </DialogTitle>
          <DialogDescription className="line-clamp-2">{item.titulo}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="generar-marca">Marca</Label>
            <Select value={marca} onValueChange={setMarca}>
              <SelectTrigger id="generar-marca">
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

          <SelectorRedMultiple
            opciones={opcionesRedes}
            seleccionadas={seleccionadas}
            onCambio={alternarRed}
            disabled={generando}
          />

          <div className="flex items-center gap-3">
            <Button onClick={() => generar.mutate()} disabled={!puedeGenerar}>
              {generando ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <MarcaIA />
              )}
              {generando ? "Generando…" : "Generar y guardar"}
            </Button>
            {generando && (
              <span className="text-xs text-muted-foreground">
                Se genera en segundo plano; lo verás aquí.
              </span>
            )}
          </div>

          {/* Progreso en vivo (texto token a token + métricas) mientras corre. */}
          {generacion && (ejecutando || generacion.estado === "error") && (
            <ProgresoGeneracion generacion={generacion} onCancelar={cancelar} cancelando={cancelando} />
          )}
          <p className="text-xs text-muted-foreground">
            Se crea un borrador por red en el{" "}
            <Link to="/operacion/parrilla/pendientes" className="underline hover:text-foreground">
              tablero
            </Link>{" "}
            y la noticia queda marcada como usada.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
