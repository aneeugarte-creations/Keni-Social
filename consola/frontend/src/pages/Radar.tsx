import { useQuery } from "@tanstack/react-query";
import {
  CircleCheck,
  CircleX,
  ExternalLink,
  Flame,
  Radar as RadarIcon,
  RefreshCw,
  Star,
  TrendingUp,
} from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
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
import { api, ApiError } from "@/lib/api";
import type { FuenteRadar, RespuestaRadar, TemaRadar } from "@/types";

const CABECERA = {
  titulo: "Radar de tendencias",
  descripcion:
    "Lo más viral del momento, multi-red, agrupado por tema con su “por qué sube” y enlaces. El radar SOLO propone: marca lo relevante; publicar lo decides tú. No inventa nada: solo muestra lo que devuelven las fuentes reales.",
};

/** Clave de localStorage para recordar qué temas marcó el equipo como relevantes. */
const CLAVE_RELEVANTES = "keni:radar-relevantes";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Etiqueta humana de una red/superficie del radar (a partir de su id). */
function etiquetaRed(red: string): string {
  if (red.startsWith("busquedas-")) return "Búsquedas";
  if (red === "rss") return "RSS del equipo";
  return red;
}

export default function Radar() {
  const [geo, setGeo] = React.useState("MX");
  const query = useQuery({
    queryKey: ["radar", geo],
    queryFn: ({ signal }) => api.radar(geo, true, signal),
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

  const acciones = query.isSuccess ? (
    <div className="flex items-center gap-2">
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
      <Button variant="outline" size="sm" onClick={() => void query.refetch()} disabled={query.isFetching}>
        <RefreshCw className={query.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
        Actualizar
      </Button>
    </div>
  ) : undefined;

  return (
    <>
      <PageHeader {...CABECERA} acciones={acciones} />
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
          />
          <PanelFuentes datos={query.data} />
        </div>
      )}
    </>
  );
}

// --- Lista de temas (panel principal) -------------------------------------

function ListaTemas({
  datos,
  relevantes,
  onAlternar,
}: {
  datos: RespuestaRadar;
  relevantes: Set<string>;
  onAlternar: (titulo: string) => void;
}) {
  const sinDatos = datos.temas.length === 0;
  const algunaFuenteCaida = datos.fuentes.some((f) => !f.disponible);

  return (
    <div className="space-y-4">
      {sinDatos ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <RadarIcon className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
            <p className="text-sm font-medium">No hay tendencias que mostrar ahora mismo.</p>
            <p className="max-w-md text-sm text-muted-foreground">
              {algunaFuenteCaida
                ? "Alguna fuente no está disponible (mira el panel de la derecha). No se inventa nada: cuando haya datos reales, aparecerán aquí."
                : "Las fuentes respondieron sin tendencias. Da de alta feeds en Fuentes o cambia el país."}
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {datos.total} {datos.total === 1 ? "tema" : "temas"} · ordenados por señal (lo más viral
            arriba). {relevantes.size > 0 && `${relevantes.size} marcado(s) como relevante.`}
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
