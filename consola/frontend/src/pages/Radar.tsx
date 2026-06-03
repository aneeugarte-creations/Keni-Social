import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CircleCheck,
  CircleX,
  ExternalLink,
  Flame,
  Play,
  Radar as RadarIcon,
  RefreshCw,
  Star,
  TrendingUp,
  Zap,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { BotonExportarLista } from "@/components/comunes/BotonExportarLista";
import type { ItemExportable } from "@/components/comunes/exportarLista";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import type { FuenteRadar, RespuestaRadar, TemaRadar } from "@/types";

const CABECERA = {
  titulo: "Descubrimiento",
  descripcion:
    "Tendencias virales y señales del momento, a partir de fuentes reales. SOLO propone: marca lo relevante y aliméntalo al Plan del día; publicar lo decides tú.",
};

/** Texto introductorio del panel "Tendencias" (antes la descripción de la página Radar). */
const INTRO_TENDENCIAS =
  "Lo más viral del momento, multi-red, agrupado por tema con su “por qué sube” y enlaces. El radar SOLO propone: marca lo relevante; publicar lo decides tú. No inventa nada: solo muestra lo que devuelven las fuentes reales.";

/**
 * Página Descubrimiento: dos vistas que derivan de las mismas fuentes reales en
 * pestañas internas — "Tendencias" (lo viral del momento) y "Auto" (la bandeja de
 * auto-promoción del Radar). El Plan del día es ahora su propia pestaña de
 * Investigación (consume estas señales). Cada panel monta su propio fetch; la
 * pestaña vive en estado local (no en la URL).
 */
export default function Radar() {
  return (
    <>
      <PageHeader {...CABECERA} />
      <Tabs defaultValue="tendencias" className="space-y-4">
        <TabsList>
          <TabsTrigger value="tendencias">Tendencias</TabsTrigger>
          <TabsTrigger value="auto">Auto</TabsTrigger>
        </TabsList>
        <TabsContent value="tendencias">
          <PanelTendencias />
        </TabsContent>
        <TabsContent value="auto">
          <PanelRadarAuto />
        </TabsContent>
      </Tabs>
    </>
  );
}

/** Clave de localStorage para recordar qué temas marcó el equipo como relevantes. */
const CLAVE_RELEVANTES = "keni:radar-relevantes";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Mapea los temas del radar a ítems exportables (Markdown copiar-pegar). */
function temasExportables(temas: TemaRadar[]): ItemExportable[] {
  return temas.map((t) => ({
    titulo: t.titulo,
    senal: t.senal_texto,
    fuentes: t.fuentes,
    porQue: t.por_que,
    enlaces: t.enlaces,
  }));
}

/** Etiqueta humana de una red/superficie del radar (a partir de su id). */
function etiquetaRed(red: string): string {
  if (red.startsWith("busquedas-")) return "Búsquedas";
  if (red === "rss") return "RSS del equipo";
  return red;
}

/**
 * Panel "Tendencias": el contenido original de la página Radar (lo viral del
 * momento). Sin PageHeader (lo pinta el contenedor); muestra su propia barra de
 * acciones (país + actualizar) e intro.
 */
function PanelTendencias() {
  const [geo, setGeo] = React.useState("MX");
  // Marca activa: las tendencias se filtran a su foco (deriva del perfil / switch).
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const query = useQuery({
    queryKey: ["radar", geo, marcaActiva],
    queryFn: ({ signal }) => api.radar(geo, true, marcaActiva ?? undefined, signal),
  });

  // Selección del equipo (qué temas son relevantes). SOLO marca; no publica nada.
  const [relevantes, setRelevantes] = React.useState<Set<string>>(() => {
    try {
      const crudo = localStorage.getItem(CLAVE_RELEVANTES);
      return new Set(crudo ? (JSON.parse(crudo) as string[]) : []);
    } catch {
      return new Set();
    }
  });

  function alternarRelevante(titulo: string) {
    setRelevantes((prev) => {
      const siguiente = new Set(prev);
      if (siguiente.has(titulo)) siguiente.delete(titulo);
      else siguiente.add(titulo);
      try {
        localStorage.setItem(CLAVE_RELEVANTES, JSON.stringify([...siguiente]));
      } catch {
        // localStorage lleno o no disponible: la marca vive solo en memoria.
      }
      return siguiente;
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-3xl text-sm text-muted-foreground">{INTRO_TENDENCIAS}</p>
        {query.isSuccess && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <BotonExportarLista titulo="Tendencias del Radar" items={temasExportables(query.data.temas)} />
            <Select value={geo} onValueChange={setGeo}>
              <SelectTrigger className="w-44" aria-label="País del radar">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {query.data.geos_disponibles.map((g) => (
                  <SelectItem key={g.id} value={g.id}>
                    {g.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
            >
              <RefreshCw className={query.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
              Actualizar
            </Button>
          </div>
        )}
      </div>

      {query.isPending ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <Skeleton className="h-96 w-full rounded-md" />
          <Skeleton className="h-72 w-full rounded-md" />
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar el radar"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <ListaTemas
            datos={query.data}
            relevantes={relevantes}
            onAlternar={alternarRelevante}
            nombreMarca={nombreActiva}
          />
          <PanelFuentes datos={query.data} />
        </div>
      )}
    </div>
  );
}

// --- Lista de temas (panel principal) -------------------------------------

function ListaTemas({
  datos,
  relevantes,
  onAlternar,
  nombreMarca,
}: {
  datos: RespuestaRadar;
  relevantes: Set<string>;
  onAlternar: (titulo: string) => void;
  nombreMarca: string | null;
}) {
  const sinDatos = datos.temas.length === 0;
  const algunaFuenteCaida = datos.fuentes.some((f) => !f.disponible);
  const fueraFoco = datos.total_fuera_foco ?? 0;
  // Hay marca activa y se descartaron tendencias por no ser suyas (filtro real).
  const filtradoPorMarca = Boolean(datos.marca) && (sinDatos ? fueraFoco > 0 : true);

  return (
    <div className="space-y-4">
      {sinDatos ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <RadarIcon className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
            {filtradoPorMarca ? (
              <>
                <p className="text-sm font-medium">
                  No hay tendencias de {nombreMarca ?? "tu marca"} ahora mismo.
                </p>
                <p className="max-w-md text-sm text-muted-foreground">
                  Había {fueraFoco} tendencia(s) generales, pero ninguna del foco de la marca. El
                  radar mira tendencias generales (Google Trends); da de alta fuentes de la marca
                  en Fuentes para nutrir su descubrimiento.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium">No hay tendencias que mostrar ahora mismo.</p>
                <p className="max-w-md text-sm text-muted-foreground">
                  {algunaFuenteCaida
                    ? "Alguna fuente no está disponible (mira el panel de la derecha). No se inventa nada: cuando haya datos reales, aparecerán aquí."
                    : "Las fuentes respondieron sin tendencias. Da de alta feeds en Fuentes o cambia el país."}
                </p>
              </>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {datos.total} {datos.total === 1 ? "tema" : "temas"}
            {filtradoPorMarca && nombreMarca ? ` de ${nombreMarca}` : ""} · ordenados por señal (lo
            más viral arriba).{" "}
            {filtradoPorMarca && fueraFoco > 0 && `${fueraFoco} fuera del foco de la marca. `}
            {relevantes.size > 0 && `${relevantes.size} marcado(s) como relevante.`}
          </p>
          <ul className="space-y-3">
            {datos.temas.map((tema) => (
              <li key={tema.titulo}>
                <TarjetaTema
                  tema={tema}
                  relevante={relevantes.has(tema.titulo)}
                  onAlternar={() => onAlternar(tema.titulo)}
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function TarjetaTema({
  tema,
  relevante,
  onAlternar,
}: {
  tema: TemaRadar;
  relevante: boolean;
  onAlternar: () => void;
}) {
  return (
    <Card className={relevante ? "border-primary/60" : undefined}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1.5">
            <CardTitle className="text-base leading-snug">{tema.titulo}</CardTitle>
            <div className="flex flex-wrap items-center gap-1.5">
              {tema.senal_texto && (
                <Badge variant="aviso" className="gap-1">
                  <TrendingUp className="h-3 w-3" />
                  {tema.senal_texto}
                </Badge>
              )}
              {[...new Set(tema.redes.map(etiquetaRed))].map((r) => (
                <Badge key={r} variant="secondary">
                  {r}
                </Badge>
              ))}
              {tema.fuentes.length > 1 && (
                <Badge variant="outline" className="gap-1">
                  <Flame className="h-3 w-3" />
                  {tema.fuentes.length} fuentes
                </Badge>
              )}
            </div>
            {tema.fuentes.length > 0 && (
              <p className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Fuente: </span>
                {tema.fuentes.join(" · ")}
              </p>
            )}
          </div>
          <Button
            variant={relevante ? "default" : "outline"}
            size="sm"
            className="shrink-0"
            onClick={onAlternar}
            aria-pressed={relevante}
          >
            <Star className={relevante ? "h-4 w-4 fill-current" : "h-4 w-4"} />
            {relevante ? "Relevante" : "Marcar"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {tema.por_que && (
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Por qué sube: </span>
            {tema.por_que}
          </p>
        )}
        {tema.enlaces.length > 0 && (
          <ul className="space-y-1">
            {tema.enlaces.map((e, i) => (
              <li key={`${e.url}-${i}`} className="flex items-start gap-1.5 text-sm">
                <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                {e.url ? (
                  <a
                    href={e.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    {e.titulo || e.url}
                    {e.fuente && <span className="text-muted-foreground"> · {e.fuente}</span>}
                  </a>
                ) : (
                  <span>
                    {e.titulo}
                    {e.fuente && <span className="text-muted-foreground"> · {e.fuente}</span>}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// --- Panel de fuentes (estado honesto, derecha) ---------------------------

function FilaFuente({ fuente }: { fuente: FuenteRadar }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      {fuente.disponible ? (
        <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
      ) : (
        <CircleX className="mt-0.5 h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
      )}
      <div className="min-w-0">
        <p className="font-medium">
          {fuente.nombre}
          {fuente.disponible && (
            <span className="font-normal text-muted-foreground">
              {" "}
              · {fuente.conteo} {fuente.conteo === 1 ? "tema" : "temas"}
            </span>
          )}
        </p>
        {!fuente.disponible && fuente.motivo && (
          <p className="text-xs text-muted-foreground">{fuente.motivo}</p>
        )}
      </div>
    </li>
  );
}

function PanelFuentes({ datos }: { datos: RespuestaRadar }) {
  return (
    <div className="space-y-4">
      <Card className="h-fit">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <RadarIcon className="h-4 w-4" />
            Fuentes consultadas
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2.5">
            {datos.fuentes.map((f) => (
              <FilaFuente key={f.id} fuente={f} />
            ))}
          </ul>
        </CardContent>
      </Card>

      {datos.fuentes_pendientes.length > 0 && (
        <Card className="h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Redes aún no cubiertas</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-3 text-xs text-muted-foreground">
              Estas redes necesitan una API/credencial que aún no está conectada. El radar lo dice
              en claro en vez de inventar tendencias.
            </p>
            <ul className="space-y-2.5">
              {datos.fuentes_pendientes.map((f) => (
                <li key={f.red} className="flex items-start gap-2 text-sm">
                  <CircleX className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <p className="font-medium">{f.nombre}</p>
                    <p className="text-xs text-muted-foreground">{f.motivo}</p>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// --- Panel Auto (bandeja de auto-promoción del Radar) ---------------------

/**
 * Panel "Auto": muestra la bandeja de la auto-promoción del Radar (los temas que
 * ENTRARÍAN ahora a "importante del día", sin escribir nada) más su config viva
 * (umbral, geo, daemon activo). El botón "Ejecutar ahora" promueve el batch
 * (POST /radar/auto/ejecutar, SOLO ADMIN) y refresca la bandeja. Lectura segura:
 * la bandeja se calcula aunque el daemon esté apagado.
 */
function PanelRadarAuto() {
  const queryClient = useQueryClient();
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";

  const bandejaQuery = useQuery({
    queryKey: ["radar", "auto", "bandeja"],
    queryFn: ({ signal }) => api.bandejaRadarAuto(signal),
  });

  const ejecutar = useMutation({
    mutationFn: () => api.ejecutarRadarAuto(),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: ["radar", "auto"] });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      toast.success(
        res.total === 0
          ? "No había temas por encima del umbral; no se promovió nada."
          : `${res.total} ${res.total === 1 ? "tema promovido" : "temas promovidos"} a “importante del día”.`,
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (bandejaQuery.isPending) {
    return <Skeleton className="h-72 w-full rounded-md" />;
  }
  if (bandejaQuery.isError) {
    return (
      <BloqueError
        titulo="No se pudo cargar la bandeja"
        mensaje={mensajeError(bandejaQuery.error)}
        onReintentar={() => void bandejaQuery.refetch()}
        cargando={bandejaQuery.isFetching}
      />
    );
  }

  const { config, temas, total } = bandejaQuery.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-3xl space-y-2">
          <p className="text-sm text-muted-foreground">
            Auto-promoción del Radar: estos temas superarían el umbral de señal y entrarían a
            “importante del día”. Es revisable y no escribe nada hasta que se ejecuta.
          </p>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant={config.activo ? "ok" : "secondary"} className="gap-1">
              <Zap className="h-3 w-3" />
              {config.activo ? "Daemon activo" : "Daemon apagado"}
            </Badge>
            <Badge variant="outline">Umbral {config.umbral}</Badge>
            <Badge variant="outline">Geo {config.geo}</Badge>
            <Badge variant="outline">Máx {config.max_por_barrido}/barrido</Badge>
            {config.marca && <Badge variant="outline">Marca {config.marca}</Badge>}
          </div>
        </div>
        {esAdmin && (
          <Button
            size="sm"
            className="shrink-0"
            onClick={() => ejecutar.mutate()}
            disabled={ejecutar.isPending}
            title="Promueve ahora los temas de la bandeja a “importante del día”"
          >
            {ejecutar.isPending ? (
              <Loader2Spin />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Ejecutar ahora
          </Button>
        )}
      </div>

      {!esAdmin && (
        <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          Solo un administrador puede ejecutar la auto-promoción. Aquí puedes revisar qué entraría.
        </p>
      )}

      {total === 0 ? (
        <EstadoVacio
          icono={Zap}
          titulo="Nada por encima del umbral"
          texto="Ahora mismo ningún tema del Radar supera el umbral de auto-promoción. Cuando lo haga, aparecerá aquí."
        />
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {total} {total === 1 ? "tema entraría" : "temas entrarían"} (ordenados por señal).
          </p>
          <ul className="space-y-3">
            {temas.map((tema) => (
              <li key={tema.titulo}>
                <TarjetaTemaAuto tema={tema} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/** Spinner reutilizado (evita importar el icono dos veces con otro nombre). */
function Loader2Spin() {
  return <RefreshCw className="h-4 w-4 animate-spin" />;
}

/** Tarjeta de un tema de la bandeja auto (solo lectura; sin acciones por tema). */
function TarjetaTemaAuto({ tema }: { tema: TemaRadar }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="min-w-0 text-base leading-snug">{tema.titulo}</CardTitle>
          {tema.senal_texto && (
            <Badge variant="aviso" className="shrink-0 gap-1">
              <TrendingUp className="h-3 w-3" />
              {tema.senal_texto}
            </Badge>
          )}
        </div>
      </CardHeader>
      {tema.por_que && (
        <CardContent>
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Por qué sube: </span>
            {tema.por_que}
          </p>
        </CardContent>
      )}
    </Card>
  );
}
