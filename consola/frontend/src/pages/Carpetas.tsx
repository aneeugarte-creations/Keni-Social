import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, FolderPlus, RefreshCw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Texto legible del error de la API (o un fallback en español). */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/**
 * Valida en cliente que el nombre sea una sola carpeta, no una ruta.
 * El backend sigue siendo la autoridad; esto solo evita errores obvios.
 */
function errorNombreLocal(nombre: string): string | null {
  const limpio = nombre.trim();
  if (limpio === "") return null; // vacío: aún no validamos, solo deshabilitamos
  if (limpio.includes("/") || limpio.includes("\\")) {
    return "Escribe solo el nombre de la carpeta, sin barras (/).";
  }
  if (limpio.includes("..")) {
    return "El nombre no puede contener «..».";
  }
  return null;
}

/** Esqueleto de carga del formulario. */
function EsqueletoCarpetas() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-3 w-64" />
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-36" />
      </CardContent>
    </Card>
  );
}

/**
 * Página para crear una carpeta de trabajo a partir de una plantilla.
 * La carpeta queda registrada como proyecto al crearse.
 */
export default function Carpetas() {
  const queryClient = useQueryClient();
  const [nombre, setNombre] = React.useState("");
  const [plantilla, setPlantilla] = React.useState("");

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["carpetas"],
    queryFn: ({ signal }) => api.carpetas(signal),
  });

  // Preselecciona la primera plantilla disponible cuando llegan los datos.
  React.useEffect(() => {
    if (data && plantilla === "" && data.plantillas.length > 0) {
      setPlantilla(data.plantillas[0].id);
    }
  }, [data, plantilla]);

  const crear = useMutation({
    mutationFn: () => api.crearCarpeta({ nombre: nombre.trim(), plantilla }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "Carpeta creada.", {
        description: `Quedó registrada en Proyectos. Ruta: ${res.ruta}`,
      });
      setNombre("");
      // Una carpeta nueva aparece en Proyectos: invalidamos esa caché.
      void queryClient.invalidateQueries({ queryKey: ["proyectos"] });
    },
    onError: (errorCrear) => toast.error(mensajeError(errorCrear)),
  });

  const errorNombre = errorNombreLocal(nombre);
  const valido = nombre.trim() !== "" && plantilla !== "" && errorNombre === null;

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (valido) crear.mutate();
  }

  const acciones = (
    <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
      <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
      Actualizar
    </Button>
  );

  return (
    <>
      <PageHeader
        titulo="Nueva carpeta"
        descripcion="Crea una carpeta de trabajo a partir de una plantilla. Quedará registrada como proyecto."
        acciones={acciones}
      />

      {isPending ? (
        <EsqueletoCarpetas />
      ) : isError ? (
        <Card className="border-destructive/40">
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">No se pudieron cargar las plantillas</p>
              <p className="max-w-md text-sm text-muted-foreground">{mensajeError(error)}</p>
            </div>
            <Button onClick={() => void refetch()} disabled={isFetching}>
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Reintentar
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Crear carpeta</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <p className="mb-4 text-sm text-muted-foreground">
                Se creará dentro de{" "}
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
                  {data.raiz}
                </code>
                .
              </p>
              <form onSubmit={enviar} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="carpeta-nombre">Nombre de la carpeta</Label>
                  <Input
                    id="carpeta-nombre"
                    value={nombre}
                    onChange={(e) => setNombre(e.target.value)}
                    placeholder="mi-carpeta"
                    disabled={crear.isPending}
                    aria-invalid={errorNombre !== null}
                  />
                  {errorNombre ? (
                    <p className="text-xs text-destructive">{errorNombre}</p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Solo el nombre, sin barras ni rutas.
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="carpeta-plantilla">Plantilla</Label>
                  {data.plantillas.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No hay plantillas disponibles.
                    </p>
                  ) : (
                    <Select
                      value={plantilla}
                      onValueChange={setPlantilla}
                      disabled={crear.isPending}
                    >
                      <SelectTrigger id="carpeta-plantilla">
                        <SelectValue placeholder="Elige una plantilla" />
                      </SelectTrigger>
                      <SelectContent>
                        {data.plantillas.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.nombre}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>

                <Button type="submit" disabled={!valido || crear.isPending}>
                  <FolderPlus className={cn("h-4 w-4", crear.isPending && "animate-pulse")} />
                  {crear.isPending ? "Creando…" : "Crear carpeta"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
