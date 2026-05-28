import { useQuery } from "@tanstack/react-query";
import { Bot, FileText, FolderInput, Pencil, Play, Plus, RefreshCw, Send, Trash2 } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AgenteResumen } from "@/types";

import {
  DialogoBorrarAgente,
  DialogoConectarAgente,
  DialogoCrearAgente,
  DialogoRenombrarAgente,
} from "./agentes/GestionAgentes";

/** Clave de React Query para el listado de agentes. */
export const CLAVE_AGENTES = ["agentes"] as const;

/** Texto legible del error de la API (o un fallback en español). */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/** Esqueleto de carga que imita la rejilla de agentes. */
function EsqueletoAgentes() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i}>
          <CardHeader className="pb-3">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-3 w-56" />
          </CardHeader>
          <CardContent className="flex gap-2 pt-0">
            <Skeleton className="h-5 w-28" />
            <Skeleton className="h-5 w-20" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/**
 * Tarjeta de un agente (= su carpeta). Clic en el cuerpo → detalle. Las marcas
 * de serie muestran un badge "Marca" y no se pueden gestionar; los genéricos
 * exponen acciones de renombrar y borrar.
 */
function TarjetaAgente({
  agente,
  onRenombrar,
  onBorrar,
}: {
  agente: AgenteResumen;
  onRenombrar: (a: AgenteResumen) => void;
  onBorrar: (a: AgenteResumen) => void;
}) {
  return (
    <Card className="flex flex-col transition-colors hover:border-primary/50">
      <Link to={`/agentes/${encodeURIComponent(agente.id)}`} className="block">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <CardTitle className="flex items-center gap-2 text-base">
                <Bot className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="truncate">{agente.nombre}</span>
              </CardTitle>
              <p
                className="truncate font-mono text-xs text-muted-foreground"
                title={agente.ruta}
              >
                {agente.ruta}
              </p>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              {agente.es_marca && <Badge variant="secondary">Marca</Badge>}
              <Badge variant={agente.tiene_claude_md ? "ok" : "aviso"}>
                {agente.tiene_claude_md ? "Con CLAUDE.md" : "Sin CLAUDE.md"}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-0 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Send className="h-4 w-4" aria-hidden="true" />
            {agente.n_publicaciones}{" "}
            {agente.n_publicaciones === 1 ? "publicación" : "publicaciones"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Play className="h-4 w-4" aria-hidden="true" />
            {agente.n_runs} {agente.n_runs === 1 ? "ejecución" : "ejecuciones"}
          </span>
        </CardContent>
      </Link>

      {/* Acciones de gestión: solo para agentes genéricos (no marcas). */}
      {!agente.es_marca && (
        <div className="mt-auto flex items-center justify-end gap-1 border-t border-border px-4 py-2">
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => onRenombrar(agente)}
          >
            <Pencil className="h-4 w-4" />
            Renombrar
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-destructive"
            onClick={() => onBorrar(agente)}
          >
            <Trash2 className="h-4 w-4" />
            Borrar
          </Button>
        </div>
      )}
    </Card>
  );
}

/**
 * Página de Agentes: lista un conjunto abierto de agentes (cada uno con su
 * carpeta, CLAUDE.md, sub-contextos y runs). Hay 5 marcas de serie (no
 * gestionables) y agentes genéricos que se pueden crear, conectar, renombrar y
 * borrar. Al pulsar una tarjeta se abre su detalle.
 */
export default function Agentes() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_AGENTES,
    queryFn: ({ signal }) => api.agentes(signal),
  });

  const [crear, setCrear] = React.useState(false);
  const [conectar, setConectar] = React.useState(false);
  const [renombrando, setRenombrando] = React.useState<AgenteResumen | null>(null);
  const [borrando, setBorrando] = React.useState<AgenteResumen | null>(null);

  const acciones = (
    <>
      <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
        <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
        Actualizar
      </Button>
      <Button variant="outline" onClick={() => setConectar(true)}>
        <FolderInput className="h-4 w-4" />
        Conectar carpeta
      </Button>
      <Button onClick={() => setCrear(true)}>
        <Plus className="h-4 w-4" />
        Crear agente
      </Button>
    </>
  );

  return (
    <>
      <PageHeader
        titulo="Agentes"
        descripcion="Cada agente es una carpeta con su contexto (CLAUDE.md), sub-contextos y ejecuciones. Las marcas de serie son fijas; los genéricos se gestionan aquí."
        acciones={acciones}
      />

      {isPending ? (
        <EsqueletoAgentes />
      ) : isError ? (
        <BloqueError
          titulo="No se pudieron cargar los agentes"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      ) : data.agentes.length === 0 ? (
        <EstadoVacio
          icono={Bot}
          titulo="Aún no hay agentes"
          texto="Crea un agente genérico o conecta una carpeta existente para empezar. Las marcas configuradas también aparecerán aquí."
          accion={
            <div className="flex flex-wrap items-center justify-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setConectar(true)}>
                <FolderInput className="h-4 w-4" />
                Conectar carpeta
              </Button>
              <Button size="sm" onClick={() => setCrear(true)}>
                <Plus className="h-4 w-4" />
                Crear agente
              </Button>
              <Button asChild variant="ghost" size="sm">
                <Link to="/configuracion">
                  <FileText className="h-4 w-4" />
                  Configurar marcas
                </Link>
              </Button>
            </div>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.agentes.map((a) => (
            <TarjetaAgente
              key={a.id}
              agente={a}
              onRenombrar={setRenombrando}
              onBorrar={setBorrando}
            />
          ))}
        </div>
      )}

      <DialogoCrearAgente abierto={crear} onCerrar={() => setCrear(false)} />
      <DialogoConectarAgente abierto={conectar} onCerrar={() => setConectar(false)} />
      <DialogoRenombrarAgente agente={renombrando} onCerrar={() => setRenombrando(null)} />
      <DialogoBorrarAgente agente={borrando} onCerrar={() => setBorrando(null)} />
    </>
  );
}
