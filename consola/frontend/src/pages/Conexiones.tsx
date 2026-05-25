/**
 * Página "Conexiones" (grupo Ajustes).
 *
 * Permite al equipo, sin tocar archivos:
 *  1. Configurar la clave del proveedor de imagen IA (activa "Generar con IA").
 *  2. Conectar redes sociales (pegar/quitar token por plataforma, ver estado).
 *
 * Los secretos son write-only: NUNCA se muestran. Los inputs son `type=password`
 * y se vacían tras guardar; del servidor solo llega el estado/pista. React Query
 * + mutations con invalidación, toasts (sonner), estados cargando/error, modo
 * claro/oscuro y texto es-MX.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Check,
  Info,
  Loader2,
  Plug,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RedConexion } from "@/types";

const CLAVE_IMAGEN = ["conexiones", "imagen"];
const CLAVE_REDES = ["conexiones", "redes"];

/** Proveedores de imagen IA disponibles (por ahora solo OpenAI). */
const PROVEEDORES = [{ id: "openai", nombre: "OpenAI (gpt-image-1)" }];

/** Texto legible del error de la API (o un fallback en español). */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/** Tarjeta de error reutilizable con botón de reintento. */
function TarjetaError({
  titulo,
  mensaje,
  onReintentar,
  reintentando,
}: {
  titulo: string;
  mensaje: string;
  onReintentar: () => void;
  reintentando: boolean;
}) {
  return (
    <Card className="border-destructive/40">
      <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertCircle className="h-6 w-6" />
        </div>
        <div className="space-y-1">
          <p className="font-medium">{titulo}</p>
          <p className="max-w-md text-sm text-muted-foreground">{mensaje}</p>
        </div>
        <Button onClick={onReintentar} disabled={reintentando}>
          <RefreshCw className={cn("h-4 w-4", reintentando && "animate-spin")} />
          Reintentar
        </Button>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Sección: Imagen con IA                                             */
/* ------------------------------------------------------------------ */

function SeccionImagen() {
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

  const ocupado = guardar.isPending || probar.isPending || quitar.isPending;

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-base">Imagen con IA</CardTitle>
        <CardDescription>
          Configura la clave del proveedor para activar <strong>«Generar con IA»</strong> al crear
          imágenes en las publicaciones. La clave se guarda{" "}
          <strong>solo en esta máquina</strong> y nunca se muestra.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-64" />
          </div>
        ) : isError ? (
          <TarjetaError
            titulo="No se pudo cargar la configuración de imagen"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            reintentando={isFetching}
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

            {/* Clave (write-only) */}
            <div className="space-y-2">
              <Label htmlFor="imagen-api-key">Clave de API</Label>
              <Input
                id="imagen-api-key"
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={data.configurado ? "•••••••••• (escribe para reemplazar)" : "sk-…"}
                disabled={ocupado}
              />
              <p className="text-xs text-muted-foreground">
                Por seguridad nunca mostramos la clave guardada. Para cambiarla, pega una nueva y
                guarda.
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
              <Button
                variant="outline"
                onClick={() => probar.mutate()}
                disabled={ocupado || !data.configurado}
                title={!data.configurado ? "Guarda una clave antes de probar." : undefined}
              >
                {probar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ShieldCheck className="h-4 w-4" />
                )}
                {probar.isPending ? "Probando…" : "Probar"}
              </Button>
              <Button
                variant="ghost"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => setConfirmarQuitar(true)}
                disabled={ocupado || !data.configurado}
              >
                <Trash2 className="h-4 w-4" />
                Quitar
              </Button>
            </div>
          </>
        )}
      </CardContent>

      <Dialog open={confirmarQuitar} onOpenChange={setConfirmarQuitar}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Quitar la clave de imagen IA</DialogTitle>
            <DialogDescription>
              Se eliminará la clave guardada en esta máquina y «Generar con IA» dejará de estar
              disponible hasta que configures una nueva. ¿Quieres continuar?
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
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Sección: Redes sociales                                            */
/* ------------------------------------------------------------------ */

/** Tarjeta de una plataforma: estado + input de token + conectar/quitar. */
function TarjetaRed({ red }: { red: RedConexion }) {
  const queryClient = useQueryClient();
  const [token, setToken] = React.useState("");
  const [confirmarQuitar, setConfirmarQuitar] = React.useState(false);

  const conectar = useMutation({
    mutationFn: () => api.conectarRed(red.plataforma, { token }),
    onSuccess: (res) => {
      toast.success(res.mensaje || `${red.nombre} conectada.`);
      setToken(""); // El token nunca se conserva en cliente.
      void queryClient.invalidateQueries({ queryKey: CLAVE_REDES });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const quitar = useMutation({
    mutationFn: () => api.desconectarRed(red.plataforma),
    onSuccess: (res) => {
      toast.success(res?.mensaje ?? `${red.nombre} desconectada.`);
      setToken("");
      setConfirmarQuitar(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_REDES });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const ocupado = conectar.isPending || quitar.isPending;
  const inputId = `red-token-${red.plataforma}`;

  return (
    <div className="space-y-3 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{red.nombre}</span>
        {red.conectado ? (
          <Badge variant="ok">Conectado</Badge>
        ) : (
          <Badge variant="secondary">Sin conectar</Badge>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor={inputId} className="text-xs text-muted-foreground">
          Token de acceso
        </Label>
        <Input
          id={inputId}
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder={red.conectado ? "•••••••••• (escribe para reemplazar)" : "Pega el token aquí"}
          disabled={ocupado}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          onClick={() => conectar.mutate()}
          disabled={ocupado || token.trim() === ""}
        >
          {conectar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plug className="h-4 w-4" />
          )}
          {conectar.isPending ? "Conectando…" : red.conectado ? "Reemplazar" : "Conectar"}
        </Button>
        {red.conectado && (
          <Button
            size="sm"
            variant="ghost"
            className="text-muted-foreground hover:text-destructive"
            onClick={() => setConfirmarQuitar(true)}
            disabled={ocupado}
          >
            <Trash2 className="h-4 w-4" />
            Quitar
          </Button>
        )}
      </div>

      <Dialog open={confirmarQuitar} onOpenChange={setConfirmarQuitar}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desconectar {red.nombre}</DialogTitle>
            <DialogDescription>
              Se eliminará el token guardado en esta máquina. Podrás volver a conectar pegando un
              token nuevo. ¿Quieres continuar?
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
    </div>
  );
}

function SeccionRedes() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_REDES,
    queryFn: ({ signal }) => api.conexionesRedes(signal),
  });

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-base">Redes sociales</CardTitle>
        <CardDescription>
          Conecta cada plataforma pegando su token de acceso para alimentar métricas y publicación.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {/* Aviso honesto */}
        <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">
            El token se guarda <strong>solo en esta máquina</strong> y es <strong>revocable</strong>
            ; alimenta las métricas (y la publicación cuando se habilite). La conexión de un clic
            (OAuth) llegará cuando las apps estén aprobadas.
          </p>
        </div>

        {isPending ? (
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <TarjetaError
            titulo="No se pudieron cargar las redes"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            reintentando={isFetching}
          />
        ) : data.redes.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No hay redes disponibles para conectar.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {data.redes.map((red) => (
              <TarjetaRed key={red.plataforma} red={red} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Página                                                             */
/* ------------------------------------------------------------------ */

/**
 * Página de conexiones: clave del proveedor de imagen IA y tokens de redes.
 * Cada sección gestiona su propia query/mutations; el botón "Actualizar"
 * refresca ambas cachés.
 */
export default function Conexiones() {
  const queryClient = useQueryClient();
  // ¿Hay alguna query de conexiones en vuelo? (para el spinner del botón).
  const refrescando = useQuery({
    queryKey: CLAVE_IMAGEN,
    queryFn: ({ signal }) => api.conexionImagen(signal),
  }).isFetching;

  const acciones = (
    <Button
      variant="outline"
      onClick={() => {
        void queryClient.invalidateQueries({ queryKey: CLAVE_IMAGEN });
        void queryClient.invalidateQueries({ queryKey: CLAVE_REDES });
      }}
      disabled={refrescando}
    >
      <RefreshCw className={cn("h-4 w-4", refrescando && "animate-spin")} />
      Actualizar
    </Button>
  );

  return (
    <>
      <PageHeader
        titulo="Conexiones"
        descripcion="Clave del proveedor de imagen IA y tokens de redes sociales. Los secretos se guardan solo en esta máquina."
        acciones={acciones}
      />

      <div className="space-y-6">
        <SeccionImagen />
        <SeccionRedes />
      </div>
    </>
  );
}
