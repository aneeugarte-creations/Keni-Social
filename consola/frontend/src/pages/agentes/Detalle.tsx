import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, FileCode, Play, RefreshCw, Send } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RespuestaAgentes } from "@/types";

import { CLAVE_AGENTES } from "../Agentes";
import { claveAgente, mensajeError } from "./claves";
import { PestanaContenido } from "./PestanaContenido";
import { PestanaContexto } from "./PestanaContexto";
import { PestanaRuns } from "./PestanaRuns";

/** Esqueleto de carga del detalle. */
function EsqueletoDetalle() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-9 w-64" />
      <Skeleton className="h-9 w-72" />
      <Skeleton className="h-[320px] w-full rounded-xl" />
    </div>
  );
}

const BOTON_VOLVER = (
  <Button asChild variant="outline">
    <Link to="/agentes">
      <ArrowLeft className="h-4 w-4" />
      Volver
    </Link>
  </Button>
);

/**
 * Detalle de un agente (= una marca): cabecera con nombre/ruta y pestañas de
 * Contexto (CLAUDE.md + sub-contextos), Runs (ejecuciones) y Contenido
 * (publicaciones de la marca).
 */
export default function DetalleAgente() {
  const { id = "" } = useParams<{ id: string }>();

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: claveAgente(id),
    queryFn: ({ signal }) => api.agente(id, signal),
    enabled: id !== "",
  });

  // El conteo de publicaciones vive en el listado; lo reutilizamos si está en
  // caché (sin pedir nada extra). Cae a la longitud conocida si no está.
  const listaQuery = useQuery<RespuestaAgentes>({
    queryKey: CLAVE_AGENTES,
    queryFn: ({ signal }) => api.agentes(signal),
  });
  const resumen = listaQuery.data?.agentes.find((a) => a.id === id);
  const nPublicaciones = resumen?.n_publicaciones ?? 0;
  // Una marca de serie no puede tener publicaciones genéricas vacías "por
  // diseño"; un genérico sí. Si el resumen no está en caché, asumimos marca
  // (comportamiento previo) para no mostrar avisos espurios.
  const esMarca = resumen?.es_marca ?? true;

  if (isPending) {
    return (
      <>
        <PageHeader titulo="Agente" acciones={BOTON_VOLVER} />
        <EsqueletoDetalle />
      </>
    );
  }

  if (isError) {
    return (
      <>
        <PageHeader titulo="Agente" acciones={BOTON_VOLVER} />
        <BloqueError
          titulo="No se pudo cargar el agente"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      </>
    );
  }

  if (!data) {
    return (
      <>
        <PageHeader titulo="Agente" acciones={BOTON_VOLVER} />
        <EstadoVacio
          icono={Bot}
          titulo="Agente no encontrado"
          texto="Puede que la marca ya no exista. Vuelve al listado de agentes."
          accion={BOTON_VOLVER}
        />
      </>
    );
  }

  const acciones = (
    <>
      <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
        <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
        Actualizar
      </Button>
      {BOTON_VOLVER}
    </>
  );

  return (
    <>
      <PageHeader
        titulo={data.nombre}
        descripcion={data.ruta}
        acciones={acciones}
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge variant={esMarca ? "secondary" : "outline"}>
          {esMarca ? "Marca" : "Genérico"}
        </Badge>
        <Badge variant={data.claude_md.trim() !== "" ? "ok" : "aviso"}>
          {data.claude_md.trim() !== "" ? "Con CLAUDE.md" : "Sin CLAUDE.md"}
        </Badge>
        <Badge variant="secondary">{data.sub_contextos.length} sub-contextos</Badge>
        <Badge variant="secondary">{data.runs.length} runs</Badge>
      </div>

      <Tabs defaultValue="contexto">
        <TabsList>
          <TabsTrigger value="contexto" className="gap-1.5">
            <FileCode className="h-4 w-4" />
            Contexto
          </TabsTrigger>
          <TabsTrigger value="runs" className="gap-1.5">
            <Play className="h-4 w-4" />
            Runs
          </TabsTrigger>
          <TabsTrigger value="contenido" className="gap-1.5">
            <Send className="h-4 w-4" />
            Contenido
          </TabsTrigger>
        </TabsList>

        <TabsContent value="contexto" className="mt-4">
          <PestanaContexto agente={data} />
        </TabsContent>
        <TabsContent value="runs" className="mt-4">
          <PestanaRuns agente={data} />
        </TabsContent>
        <TabsContent value="contenido" className="mt-4">
          <PestanaContenido agente={data} nPublicaciones={nPublicaciones} esMarca={esMarca} />
        </TabsContent>
      </Tabs>
    </>
  );
}
