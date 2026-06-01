import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ExternalLink,
  Film,
  Images,
  LayoutList,
  ListOrdered,
  ListPlus,
  Loader2,
  RefreshCw,
  ScrollText,
  Sparkles,
  Video,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
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
import { api, ApiError } from "@/lib/api";
import type { ItemParrilla, RespuestaParrilla, SubtipoParrilla } from "@/types";

/** Texto introductorio del panel "Plan del día" (antes la descripción de la página). */
const INTRO =
  "A partir del Radar, propone la parrilla editorial del día: 13 posteos (clip, galería, infografía o normal) y 6 video-editoriales, jerarquizados por importancia para México. SOLO propone el orden; qué y cuándo publicar lo decides tú. No inventa nada: deriva de las fuentes reales del Radar.";

/** Etiqueta + icono por subtipo de posteo (vacío => posteo normal). */
const SUBTIPO: Record<SubtipoParrilla, { etiqueta: string; Icono: typeof Film }> = {
  clip: { etiqueta: "Clip", Icono: Film },
  galeria: { etiqueta: "Galería", Icono: Images },
  infografia: { etiqueta: "Infografía", Icono: ScrollText },
  normal: { etiqueta: "Posteo", Icono: LayoutList },
  "": { etiqueta: "Posteo", Icono: LayoutList },
};

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

function etiquetaRed(red: string): string {
  if (red.startsWith("busquedas-")) return "Búsquedas";
  if (red === "rss") return "RSS del equipo";
  return red;
}

/**
 * Panel "Plan del día": pestaña de Investigación (dentro de Radar). Antes era la
 * página `/investigacion/parrilla-dia`; conserva su fetch y lógica intactos. No
 * pinta PageHeader (lo hace el contenedor Radar); muestra su propia barra de
 * acciones (país + actualizar) y una intro corta.
 */
export function PanelPlanDelDia() {
  const [geo, setGeo] = React.useState("MX");
  const query = useQuery({
    queryKey: ["parrilla-dia", geo],
    queryFn: ({ signal }) => api.parrillaDia(geo, signal),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-3xl text-sm text-muted-foreground">{INTRO}</p>
        {query.isSuccess && (
          <div className="flex shrink-0 items-center gap-2">
            <Select value={geo} onValueChange={setGeo}>
              <SelectTrigger className="w-44" aria-label="País del contexto">
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
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-96 w-full rounded-md" />
          <Skeleton className="h-96 w-full rounded-md" />
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo armar la parrilla"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : (
        <Contenido datos={query.data} />
      )}
    </div>
  );
}

function Contenido({ datos }: { datos: RespuestaParrilla }) {
  if (datos.total_entrada === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <ListOrdered className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm font-medium">No hay temas para armar la parrilla ahora mismo.</p>
          <p className="max-w-md text-sm text-muted-foreground">
            El Radar respondió sin tendencias (o sus fuentes no están disponibles). No se inventan
            temas: cuando haya datos reales, la parrilla aparecerá aquí.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-xs text-muted-foreground">
        {datos.total_entrada} {datos.total_entrada === 1 ? "tema" : "temas"} del Radar →{" "}
        <strong className="text-foreground">{datos.total_posteos}</strong> posteos +{" "}
        <strong className="text-foreground">{datos.total_editorial}</strong> editoriales
        {datos.total_sobrantes > 0 && ` · ${datos.total_sobrantes} sobrante(s)`}. Ordenados por
        importancia (1 = se publica primero).
      </p>

      <div className="grid gap-6 lg:grid-cols-2">
        <Columna
          titulo="Posteos"
          icono={LayoutList}
          objetivo={datos.cuota_posteos}
          items={datos.posteos}
          vacio="No clasificó ningún tema como posteo rápido."
        />
        <Columna
          titulo="Video editorial"
          icono={Video}
          objetivo={datos.cuota_editorial}
          items={datos.editorial}
          vacio="No clasificó ningún tema con “carnita” para editorial."
        />
      </div>

      {datos.sobrantes.length > 0 && (
        <Columna
          titulo="Sobrantes (sobre la cuota)"
          icono={ListOrdered}
          items={datos.sobrantes}
          vacio=""
        />
      )}
    </div>
  );
}

function Columna({
  titulo,
  icono: Icono,
  objetivo,
  items,
  vacio,
}: {
  titulo: string;
  icono: typeof Film;
  objetivo?: number;
  items: ItemParrilla[];
  vacio: string;
}) {
  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icono className="h-4 w-4" />
          {titulo}
          <Badge variant="secondary" className="ml-1">
            {objetivo != null ? `${items.length}/${objetivo}` : items.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">{vacio}</p>
        ) : (
          <ol className="space-y-3">
            {items.map((item) => (
              <li key={`${item.tipo}-${item.orden}-${item.titulo}`}>
                <TarjetaItem item={item} />
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function TarjetaItem({ item }: { item: ItemParrilla }) {
  const navigate = useNavigate();
  const sub = SUBTIPO[item.subtipo] ?? SUBTIPO[""];
  const SubIcono = sub.Icono;

  // Siembra la generación con el tema (título + por qué + enlaces); FlujoGeneracion
  // lee `location.state.texto`. Solo PROPONE el texto base; el copy lo decide el humano.
  function generarCopy() {
    const texto = [item.titulo, item.por_que, ...item.enlaces.map((e) => e.url)]
      .filter(Boolean)
      .join("\n\n");
    navigate("/generacion", { state: { texto, modo: "copy" } });
  }

  // Promueve el tema al tablero del CM como "importante del día" (origen Radar). El CM
  // luego elige plataformas y responsable allí. Prioridad alta para los 3 primeros.
  const llevarAlTablero = useMutation({
    mutationFn: () =>
      api.contenidoDesdeRadar({
        titulo: item.titulo,
        descripcion: [item.por_que, ...item.enlaces.map((e) => e.url)]
          .filter(Boolean)
          .join("\n"),
        prioridad: item.orden <= 3 ? "alta" : "media",
      }),
    onSuccess: () => toast.success("Llevado al tablero (Importante del día)."),
    onError: (e) => toast.error(mensajeError(e)),
  });
  return (
    <div className="flex gap-3 rounded-md border p-3">
      <div
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary"
        aria-label={`Orden ${item.orden}`}
      >
        {item.orden}
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-medium leading-snug">{item.titulo}</p>
          <Badge variant="outline" className="shrink-0 gap-1" title={`Score ${item.score}`}>
            {item.score.toFixed(2)}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {item.tipo === "posteo" && (
            <Badge variant="secondary" className="gap-1">
              <SubIcono className="h-3 w-3" />
              {sub.etiqueta}
            </Badge>
          )}
          {item.senal_texto && <Badge variant="aviso">{item.senal_texto}</Badge>}
          {[...new Set(item.redes.map(etiquetaRed))].map((r) => (
            <Badge key={r} variant="outline">
              {r}
            </Badge>
          ))}
        </div>

        {item.razon && (
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Por qué este orden: </span>
            {item.razon}
          </p>
        )}

        {item.enlaces.length > 0 && (
          <ul className="space-y-1">
            {item.enlaces.slice(0, 3).map((e, i) => (
              <li key={`${e.url}-${i}`} className="flex items-start gap-1.5 text-xs">
                <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
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

        <div className="flex flex-wrap gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={generarCopy}>
            <Sparkles className="h-3.5 w-3.5" />
            Generar copy
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => llevarAlTablero.mutate()}
            disabled={llevarAlTablero.isPending}
          >
            {llevarAlTablero.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ListPlus className="h-3.5 w-3.5" />
            )}
            Llevar al tablero
          </Button>
        </div>
      </div>
    </div>
  );
}
