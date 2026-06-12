import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, MoreHorizontal, Save, ShieldCheck, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { MenuContextual } from "@/components/comunes/MenuContextual";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { api } from "@/lib/api";
import { useSesion } from "@/hooks/sesion-contexto";
import { cn } from "@/lib/utils";

import { CLAVE_IMAGEN, PROVEEDORES, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

/** Envoltorio con AUTOGUARDADO por rol (#153): los secretos de conexión son de admin.
 * Montada en su página contextual, se oculta sola a un editor (sesión null = modo local
 * pleno). El guard vive en un wrapper para no llamar hooks condicionalmente. */
export function SeccionImagen() {
  const { usuario } = useSesion();
  if (usuario !== null && usuario.rol !== "admin") return null;
  return <SeccionImagenAdmin />;
}

function SeccionImagenAdmin() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_IMAGEN,
    queryFn: ({ signal }) => api.conexionImagen(signal),
  });

  const [apiKey, setApiKey] = React.useState("");
  const [proveedor, setProveedor] = React.useState(PROVEEDORES[0].id);
  const [confirmarQuitar, setConfirmarQuitar] = React.useState(false);
  // Resultado de la última prueba (color verde/rojo según `ok`).
  const [resultadoPrueba, setResultadoPrueba] = React.useState<{ ok: boolean; mensaje: string } | null>(
    null,
  );

  // Sincroniza el proveedor seleccionado con el que reporta el servidor.
  React.useEffect(() => {
    if (data?.proveedor) setProveedor(data.proveedor);
  }, [data?.proveedor]);

  const guardar = useMutation({
    mutationFn: () => api.guardarConexionImagen({ proveedor, api_key: apiKey }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "Clave guardada.");
      setApiKey(""); // El secreto nunca se conserva en cliente.
      setResultadoPrueba(null);
      void queryClient.invalidateQueries({ queryKey: CLAVE_IMAGEN });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const probar = useMutation({
    mutationFn: () => api.probarConexionImagen(),
    onSuccess: (res) => {
      setResultadoPrueba(res);
      if (res.ok) toast.success(res.mensaje || "Conexión correcta.");
      else toast.error(res.mensaje || "La prueba falló.");
    },
    onError: (e) => {
      setResultadoPrueba({ ok: false, mensaje: mensajeError(e) });
      toast.error(mensajeError(e));
    },
  });

  const quitar = useMutation({
    mutationFn: () => api.eliminarConexionImagen(),
    onSuccess: (res) => {
      toast.success(res?.mensaje ?? "Clave eliminada.");
      setApiKey("");
      setResultadoPrueba(null);
      setConfirmarQuitar(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_IMAGEN });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Selector de modelo: el cambio persiste de inmediato (PUT) y refresca el estado.
  const guardarModelo = useMutation({
    mutationFn: (modelo: string) => api.guardarModeloImagen({ modelo }),
    onSuccess: () => {
      toast.success("Modelo de imagen actualizado.");
      void queryClient.invalidateQueries({ queryKey: CLAVE_IMAGEN });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const ocupado =
    guardar.isPending || probar.isPending || quitar.isPending || guardarModelo.isPending;

  return (
    <SeccionColapsable
      titulo="Imagen con IA"
      contentClassName="space-y-4"
      descripcion="Configura tu proveedor de imágenes."
    >
        {isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-64" />
          </div>
        ) : isError ? (
          <BloqueError
            titulo="No se pudo cargar la configuración de imagen"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : (
          <>
            {/* Estado actual */}
            <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
              <span className="text-sm font-medium">Estado</span>
              {data.configurado ? (
                <span className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
                  <Check className="h-4 w-4" aria-hidden="true" />
                  Configurada
                  {data.pista && (
                    <span className="font-mono text-xs text-muted-foreground">({data.pista})</span>
                  )}
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <X className="h-4 w-4" aria-hidden="true" />
                  Sin configurar
                </span>
              )}
            </div>

            {/* Proveedor */}
            <div className="space-y-2">
              <Label htmlFor="imagen-proveedor">Proveedor</Label>
              <Select value={proveedor} onValueChange={setProveedor} disabled={ocupado}>
                <SelectTrigger id="imagen-proveedor">
                  <SelectValue placeholder="Elige un proveedor" />
                </SelectTrigger>
                <SelectContent>
                  {PROVEEDORES.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Modelo de imagen (lista curada; el cambio se guarda al instante) */}
            <div className="space-y-2">
              <Label htmlFor="imagen-modelo">Modelo de imagen</Label>
              <Select
                value={data.modelo}
                onValueChange={(modelo) => guardarModelo.mutate(modelo)}
                disabled={ocupado}
              >
                <SelectTrigger id="imagen-modelo">
                  <SelectValue placeholder="Elige un modelo" />
                </SelectTrigger>
                <SelectContent>
                  {data.modelos.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Los modelos económicos no generan personas.
              </p>
            </div>

            {/* Clave (write-only) */}
            <div className="space-y-2">
              <Label htmlFor="imagen-api-key">Clave de API</Label>
              <Input
                id="imagen-api-key"
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={data.configurado ? "•••••••••• (escribe para reemplazar)" : "sk-or-…"}
                disabled={ocupado}
              />
              <p className="text-xs text-muted-foreground">
                Pega una nueva para cambiarla.
              </p>
            </div>

            {/* Resultado de la prueba */}
            {resultadoPrueba && (
              <p
                className={cn(
                  "flex items-center gap-1.5 text-sm",
                  resultadoPrueba.ok
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-destructive",
                )}
              >
                {resultadoPrueba.ok ? (
                  <Check className="h-4 w-4 shrink-0" aria-hidden="true" />
                ) : (
                  <X className="h-4 w-4 shrink-0" aria-hidden="true" />
                )}
                {resultadoPrueba.mensaje}
              </p>
            )}

            {/* Acciones */}
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => guardar.mutate()} disabled={ocupado || apiKey.trim() === ""}>
                <Save className={cn("h-4 w-4", guardar.isPending && "animate-pulse")} />
                {guardar.isPending ? "Guardando…" : "Guardar"}
              </Button>
              {/* Acciones secundarias (Probar / Quitar) agrupadas en un desplegable.
                  Ambas requieren una clave ya guardada, así que el menú aparece solo
                  cuando hay configuración. */}
              {data.configurado && (
                <MenuContextual
                  disparador="click"
                  etiqueta="Más opciones"
                  items={[
                    {
                      etiqueta: probar.isPending ? "Probando…" : "Probar conexión",
                      icono: ShieldCheck,
                      onClick: () => probar.mutate(),
                      deshabilitado: ocupado,
                    },
                    {
                      etiqueta: "Quitar",
                      icono: Trash2,
                      destructivo: true,
                      onClick: () => setConfirmarQuitar(true),
                      deshabilitado: ocupado,
                    },
                  ]}
                >
                  <Button variant="outline" disabled={ocupado}>
                    <MoreHorizontal className="h-4 w-4" /> Más{" "}
                    <ChevronDown className="h-4 w-4 opacity-60" />
                  </Button>
                </MenuContextual>
              )}
            </div>
          </>
        )}

      <Dialog open={confirmarQuitar} onOpenChange={setConfirmarQuitar}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Quitar la clave de imagen</DialogTitle>
            <DialogDescription>
              «Generar con IA» no estará disponible hasta que configures una nueva.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmarQuitar(false)}
              disabled={quitar.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => quitar.mutate()}
              disabled={quitar.isPending}
            >
              {quitar.isPending ? "Quitando…" : "Quitar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SeccionColapsable>
  );
}
