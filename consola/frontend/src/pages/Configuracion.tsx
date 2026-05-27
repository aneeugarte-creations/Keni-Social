/**
 * Página de Ajustes (Configuración). Reúne en una sola pantalla:
 *   1. Fuente de datos (muestra / real).
 *   2. Alcance de marcas (qué marcas se incluyen).
 *   3. Redes sociales (tokens por plataforma; estado conectado/sin conectar).
 *   4. Imagen con IA (clave del proveedor para «Generar con IA»).
 *
 * Las secciones de Redes e Imagen vivían antes en la página "Conexiones", que se
 * fusionó aquí (issue #87). Los secretos son write-only: nunca se muestran; del
 * servidor solo llega el estado/pista.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Info,
  Loader2,
  Moon,
  Plug,
  RefreshCw,
  Save,
  ShieldCheck,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
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
import { useTema } from "@/hooks/tema-contexto";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RedConexion } from "@/types";

const CLAVE_CONFIG = ["config"];
const CLAVE_ESFUERZO = ["config", "esfuerzo"];
const CLAVE_IMAGEN = ["conexiones", "imagen"];
const CLAVE_REDES = ["conexiones", "redes"];

/** Proveedores de imagen IA disponibles (gateway único OpenRouter). */
const PROVEEDORES = [{ id: "openrouter", nombre: "OpenRouter (gateway de IA)" }];

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

/* ------------------------------------------------------------------ */
/* Sección: Fuente de datos + Alcance de marcas                       */
/* ------------------------------------------------------------------ */

/** Esqueleto de carga de la sección de datos/marcas. */
function EsqueletoConfig() {
  return (
    <div className="space-y-6">
      {Array.from({ length: 2 }).map((_, i) => (
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

/** Fuente de datos y alcance por marcas (con su botón de guardar). */
function SeccionDatos() {
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

  if (isPending) return <EsqueletoConfig />;

  if (isError) {
    return (
      <BloqueError
        titulo="No se pudo cargar la configuración"
        mensaje={mensajeError(error)}
        onReintentar={() => void refetch()}
        cargando={isFetching}
      />
    );
  }

  return (
    <>
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
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Sección: Esfuerzo de generación (claude --effort)                  */
/* ------------------------------------------------------------------ */

/**
 * Nivel de esfuerzo de razonamiento que la IA usa al generar (copy, RSS,
 * hashtags y agentes). Más esfuerzo = mejor calidad pero más lento; menos =
 * más rápido. El valor "" es el predeterminado del modelo. Se guarda local.
 */
function SeccionEsfuerzo() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_ESFUERZO,
    queryFn: ({ signal }) => api.esfuerzo(signal),
  });

  const [esfuerzo, setEsfuerzo] = React.useState("");

  // Sincroniza el estado local con el nivel cargado del servidor.
  React.useEffect(() => {
    if (data) setEsfuerzo(data.esfuerzo);
  }, [data]);

  const guardar = useMutation({
    mutationFn: () => api.guardarEsfuerzo({ esfuerzo }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "Esfuerzo guardado.");
      void queryClient.invalidateQueries({ queryKey: CLAVE_ESFUERZO });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const hayCambios = data !== undefined && esfuerzo !== data.esfuerzo;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Esfuerzo de generación</CardTitle>
        <CardDescription>
          Cuánto «piensa» la IA al generar copy, RSS, hashtags y agentes. Más esfuerzo mejora la
          calidad pero tarda más; menos responde antes. Se guarda{" "}
          <strong>solo en esta máquina</strong>.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        {isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <BloqueError
            titulo="No se pudo cargar el esfuerzo"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : (
          <>
            {data.opciones.map((opcion) => {
              const seleccionada = esfuerzo === opcion.id;
              return (
                <label
                  key={opcion.id || "predeterminado"}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                    seleccionada ? "border-primary bg-primary/5" : "border-border hover:bg-accent",
                  )}
                >
                  <input
                    type="radio"
                    name="esfuerzo"
                    value={opcion.id}
                    checked={seleccionada}
                    onChange={() => setEsfuerzo(opcion.id)}
                    disabled={guardar.isPending}
                    className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                  />
                  <span className="space-y-0.5">
                    <span className="block text-sm font-medium">{opcion.etiqueta}</span>
                    <span className="block text-xs text-muted-foreground">{opcion.descripcion}</span>
                  </span>
                </label>
              );
            })}
            <div className="flex items-center gap-3 pt-1">
              <Button onClick={() => guardar.mutate()} disabled={guardar.isPending || !hayCambios}>
                <Save className={cn("h-4 w-4", guardar.isPending && "animate-pulse")} />
                {guardar.isPending ? "Guardando…" : "Guardar cambios"}
              </Button>
              {!hayCambios && !guardar.isPending && (
                <span className="text-xs text-muted-foreground">No hay cambios sin guardar.</span>
              )}
            </div>
          </>
        )}
      </CardContent>
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
          <BloqueError
            titulo="No se pudieron cargar las redes"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
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
/* Sección: Apariencia (tema claro/oscuro)                            */
/* ------------------------------------------------------------------ */

/** Selector de tema claro/oscuro. El tema se guarda en este equipo. */
function SeccionApariencia() {
  const { esOscuro, fijar } = useTema();

  const opciones: { id: "claro" | "oscuro"; etiqueta: string; icono: typeof Sun }[] = [
    { id: "claro", etiqueta: "Claro", icono: Sun },
    { id: "oscuro", etiqueta: "Oscuro", icono: Moon },
  ];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Apariencia</CardTitle>
        <CardDescription>
          Elige el tema de la consola. La preferencia se guarda{" "}
          <strong>solo en este equipo</strong>.
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <div role="radiogroup" aria-label="Tema" className="flex flex-wrap gap-2">
          {opciones.map((opcion) => {
            const Icono = opcion.icono;
            const activa = opcion.id === "oscuro" ? esOscuro : !esOscuro;
            return (
              <Button
                key={opcion.id}
                type="button"
                role="radio"
                aria-checked={activa}
                variant={activa ? "default" : "outline"}
                onClick={() => fijar(opcion.id)}
              >
                <Icono className="h-4 w-4" />
                {opcion.etiqueta}
              </Button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Página                                                             */
/* ------------------------------------------------------------------ */

/**
 * Página de Ajustes: fuente de datos, alcance de marcas, redes (tokens) e
 * imagen IA. El botón "Actualizar" refresca las cachés de las tres queries.
 */
export default function Configuracion() {
  const queryClient = useQueryClient();
  // ¿Hay alguna query de esta página en vuelo? (para el spinner del botón).
  const refrescando = useQuery({
    queryKey: CLAVE_CONFIG,
    queryFn: ({ signal }) => api.config(signal),
  }).isFetching;

  const acciones = (
    <Button
      variant="outline"
      onClick={() => {
        void queryClient.invalidateQueries({ queryKey: CLAVE_CONFIG });
        void queryClient.invalidateQueries({ queryKey: CLAVE_ESFUERZO });
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
        titulo="Configuración"
        descripcion="Fuente de datos, marcas, redes y clave de imagen IA. Los secretos se guardan solo en esta máquina."
        acciones={acciones}
      />

      <div className="space-y-6">
        <SeccionDatos />
        <SeccionEsfuerzo />
        <SeccionRedes />
        <SeccionImagen />
        <SeccionApariencia />
      </div>
    </>
  );
}
