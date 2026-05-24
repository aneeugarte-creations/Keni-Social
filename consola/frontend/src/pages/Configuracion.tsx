import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, RefreshCw, Save, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { CredencialesPresentes } from "@/types";

const CLAVE_CONFIG = ["config"];

/** Texto legible del error de la API (o un fallback en español). */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/** Etiqueta legible por fuente de datos. */
function etiquetaFuente(fuente: string): string {
  if (fuente === "muestra") return "Datos de muestra";
  if (fuente === "real") return "Datos reales";
  return fuente;
}

/** Descripción de ayuda por fuente de datos. */
function descripcionFuente(fuente: string): string {
  if (fuente === "muestra") {
    return "Usa datos de ejemplo. Ideal para probar la consola sin conectar credenciales.";
  }
  if (fuente === "real") {
    return "Usa los datos reales de las plataformas conectadas.";
  }
  return "";
}

/** Nombres legibles de cada credencial de plataforma. */
const NOMBRE_CREDENCIAL: Record<keyof CredencialesPresentes, string> = {
  meta: "Meta (Facebook / Instagram)",
  youtube: "YouTube",
  x: "X (Twitter)",
  tiktok: "TikTok",
};

const ORDEN_CREDENCIALES: (keyof CredencialesPresentes)[] = ["meta", "youtube", "x", "tiktok"];

/** Esqueleto de carga de la página de configuración. */
function EsqueletoConfig() {
  return (
    <div className="space-y-6">
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i}>
          <CardHeader className="pb-3">
            <Skeleton className="h-5 w-44" />
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            <Skeleton className="h-5 w-64" />
            <Skeleton className="h-5 w-52" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/**
 * Página de configuración: fuente de datos, alcance por marcas y estado
 * (solo lectura) de las credenciales presentes.
 */
export default function Configuracion() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_CONFIG,
    queryFn: ({ signal }) => api.config(signal),
  });

  const [fuente, setFuente] = React.useState("");
  const [marcas, setMarcas] = React.useState<string[]>([]);

  // Sincroniza el estado local con la configuración cargada del servidor.
  React.useEffect(() => {
    if (data) {
      setFuente(data.fuente);
      setMarcas(data.marcas);
    }
  }, [data]);

  const guardar = useMutation({
    mutationFn: () => api.guardarConfig({ fuente, marcas }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "Configuración guardada.");
      void queryClient.invalidateQueries({ queryKey: CLAVE_CONFIG });
    },
    onError: (errorGuardar) => toast.error(mensajeError(errorGuardar)),
  });

  function alternarMarca(id: string) {
    setMarcas((prev) => (prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]));
  }

  // ¿Hay cambios respecto a lo guardado?
  const hayCambios =
    data !== undefined &&
    (fuente !== data.fuente ||
      marcas.length !== data.marcas.length ||
      marcas.some((m) => !data.marcas.includes(m)));

  const acciones = (
    <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
      <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
      Actualizar
    </Button>
  );

  return (
    <>
      <PageHeader
        titulo="Configuración"
        descripcion="Fuente de datos, marcas activas y estado de las credenciales."
        acciones={acciones}
      />

      {isPending ? (
        <EsqueletoConfig />
      ) : isError ? (
        <Card className="border-destructive/40">
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">No se pudo cargar la configuración</p>
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
          {/* Fuente de datos */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Fuente de datos</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              {data.fuentes_validas.map((f) => {
                const seleccionada = fuente === f;
                return (
                  <label
                    key={f}
                    className={cn(
                      "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                      seleccionada ? "border-primary bg-primary/5" : "border-border hover:bg-accent",
                    )}
                  >
                    <input
                      type="radio"
                      name="fuente"
                      value={f}
                      checked={seleccionada}
                      onChange={() => setFuente(f)}
                      disabled={guardar.isPending}
                      className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                    />
                    <span className="space-y-0.5">
                      <span className="block text-sm font-medium">{etiquetaFuente(f)}</span>
                      {descripcionFuente(f) && (
                        <span className="block text-xs text-muted-foreground">
                          {descripcionFuente(f)}
                        </span>
                      )}
                    </span>
                  </label>
                );
              })}
            </CardContent>
          </Card>

          {/* Alcance (marcas) */}
          <Card>
            <CardHeader className="pb-1">
              <CardTitle className="text-base">Alcance (marcas)</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <p className="mb-3 text-sm text-muted-foreground">
                Elige las marcas con las que trabajar. Sin selección, se incluyen todas.
              </p>
              {data.marcas_disponibles.length === 0 ? (
                <p className="text-sm text-muted-foreground">No hay marcas disponibles.</p>
              ) : (
                <div className="space-y-2">
                  {data.marcas_disponibles.map((marca) => {
                    const marcada = marcas.includes(marca.id);
                    return (
                      <label
                        key={marca.id}
                        className={cn(
                          "flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors",
                          marcada ? "border-primary bg-primary/5" : "border-border hover:bg-accent",
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={marcada}
                          onChange={() => alternarMarca(marca.id)}
                          disabled={guardar.isPending}
                          className="h-4 w-4 shrink-0 accent-primary"
                        />
                        <span className="text-sm font-medium">{marca.nombre}</span>
                      </label>
                    );
                  })}
                </div>
              )}
              {marcas.length === 0 && data.marcas_disponibles.length > 0 && (
                <p className="mt-3 text-xs text-muted-foreground">
                  Sin marcas seleccionadas: se incluirán todas.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Credenciales presentes (solo lectura) */}
          <Card>
            <CardHeader className="pb-1">
              <CardTitle className="text-base">Credenciales presentes</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <p className="mb-3 text-sm text-muted-foreground">
                Solo lectura. Indica si la credencial está configurada (nunca se muestra su
                valor). Se configuran por fuera de la consola.
              </p>
              <ul className="divide-y divide-border rounded-lg border">
                {ORDEN_CREDENCIALES.map((clave) => {
                  const presente = data.credenciales_presentes[clave];
                  return (
                    <li
                      key={clave}
                      className="flex items-center justify-between gap-3 px-3 py-2.5"
                    >
                      <span className="text-sm font-medium">{NOMBRE_CREDENCIAL[clave]}</span>
                      {presente ? (
                        <span className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
                          <Check className="h-4 w-4" aria-hidden="true" />
                          Configurada
                        </span>
                      ) : (
                        <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                          <X className="h-4 w-4" aria-hidden="true" />
                          Sin configurar
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>

          <div className="flex items-center gap-3">
            <Button
              onClick={() => guardar.mutate()}
              disabled={guardar.isPending || !hayCambios || fuente === ""}
            >
              <Save className={cn("h-4 w-4", guardar.isPending && "animate-pulse")} />
              {guardar.isPending ? "Guardando…" : "Guardar cambios"}
            </Button>
            {!hayCambios && !guardar.isPending && (
              <span className="text-xs text-muted-foreground">No hay cambios sin guardar.</span>
            )}
          </div>
        </div>
      )}
    </>
  );
}
