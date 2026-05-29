/**
 * Página de Ajustes (Configuración). Reúne en una sola pantalla:
 *   1. Fuente de datos (muestra / real).
 *   2. Alcance de marcas (qué marcas se incluyen).
 *   3. Métricas (Metricool) por marca: token + userId → descubrir blogId → guardar.
 *   4. Imagen con IA (clave del proveedor para «Generar con IA»).
 *
 * Las métricas se consumen vía Metricool (ADR 0005 §B): la antigua sección "Redes
 * sociales" (tokens por plataforma para la ingesta propia) se retiró. La sección de
 * Imagen vivía antes en la página "Conexiones", fusionada aquí (issue #87). Los
 * secretos son write-only: nunca se muestran; del servidor solo llega el estado/pista.
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
import { useSesion } from "@/hooks/sesion-contexto";
import { useTema } from "@/hooks/tema-contexto";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { MarcaMetricool, PerfilMetricool } from "@/types";

const CLAVE_CONFIG = ["config"];
const CLAVE_ESFUERZO = ["config", "esfuerzo"];
const CLAVE_IMAGEN = ["conexiones", "imagen"];
const CLAVE_METRICOOL = ["conexiones", "metricool"];

/** Proveedores de imagen IA disponibles (gateway único OpenRouter). */
const PROVEEDORES = [{ id: "openrouter", nombre: "OpenRouter (gateway de IA)" }];

/**
 * Limpia emojis de estado (❌ ✅ ⚠️ …) que pueda traer el backend y normaliza
 * espacios y puntuación, para mostrar un texto sobrio en la consola.
 */
function limpiarMensaje(texto: string): string {
  return texto
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]/gu, "")
    .replace(/️/g, "")
    .replace(/\s+/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

/** Texto legible del error de la API (o un fallback en español). */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return limpiarMensaje(error.message);
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
      toast.success(res.mensaje ? limpiarMensaje(res.mensaje) : "Configuración guardada.");
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
/* Sección: Métricas (Metricool) por marca                            */
/* ------------------------------------------------------------------ */

/**
 * Tarjeta de UNA marca de Metricool. Cada marca es una cuenta Metricool distinta:
 * tiene su PROPIO token (write-only, nunca se muestra) + user_id. El blogId NO se
 * teclea a mano: el usuario mete token + userId, pulsa «Buscar marcas» (llama a
 * `/perfiles`, que descubre los blogId del token vía Metricool sin persistir nada) y
 * elige la marca en un desplegable; al elegir se rellena el blogId. Luego «Guardar»
 * persiste la credencial por-marca. El token solo se envía; del servidor llega el
 * estado (conectado, pista de user_id y blog_id), nunca el token.
 */
function TarjetaMetricool({ marca }: { marca: MarcaMetricool }) {
  const queryClient = useQueryClient();
  const [userToken, setUserToken] = React.useState("");
  const [userId, setUserId] = React.useState(marca.user_id_pista ?? "");
  const [blogId, setBlogId] = React.useState(marca.blog_id ?? "");
  const [confirmarQuitar, setConfirmarQuitar] = React.useState(false);
  // Marcas descubiertas vía /perfiles (desplegable). Se limpian al cambiar el token.
  const [perfiles, setPerfiles] = React.useState<PerfilMetricool[]>([]);
  const [resultadoPrueba, setResultadoPrueba] = React.useState<{
    ok: boolean;
    mensaje: string;
  } | null>(null);

  // Sincroniza user_id/blog_id no secretos con lo que reporta el servidor.
  React.useEffect(() => {
    setUserId(marca.user_id_pista ?? "");
    setBlogId(marca.blog_id ?? "");
  }, [marca.user_id_pista, marca.blog_id]);

  // Descubre las marcas (blogId) del token. NO persiste nada; el token no vuelve.
  const buscarMarcas = useMutation({
    mutationFn: () =>
      api.descubrirPerfilesMetricool({ user_token: userToken, user_id: userId }),
    onSuccess: (res) => {
      setPerfiles(res.marcas);
      // Si la marca ya tenía un blogId guardado y sigue en la lista, lo conserva;
      // si no, preselecciona la primera para que «Guardar» quede a un clic.
      const sigueDisponible = res.marcas.some((m) => m.blog_id === blogId);
      if (!sigueDisponible) setBlogId(res.marcas[0]?.blog_id ?? "");
      toast.success(
        res.marcas.length === 1
          ? "1 marca encontrada en Metricool."
          : `${res.marcas.length} marcas encontradas en Metricool.`,
      );
    },
    onError: (e) => {
      setPerfiles([]);
      toast.error(mensajeError(e));
    },
  });

  const guardar = useMutation({
    mutationFn: () =>
      api.guardarMetricool(marca.marca, {
        user_token: userToken,
        user_id: userId,
        blog_id: blogId,
      }),
    onSuccess: (res) => {
      toast.success(res.mensaje || `${marca.etiqueta} conectada.`);
      setUserToken(""); // El token nunca se conserva en cliente.
      setPerfiles([]); // Las marcas descubiertas dependían del token recién borrado.
      setResultadoPrueba(null);
      void queryClient.invalidateQueries({ queryKey: CLAVE_METRICOOL });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const probar = useMutation({
    mutationFn: () => api.probarMetricool(marca.marca),
    onSuccess: (res) => {
      setResultadoPrueba({ ok: res.ok, mensaje: res.detalle });
      if (res.ok) toast.success(res.detalle || "Conexión correcta.");
      else toast.error(res.detalle || "La prueba falló.");
    },
    onError: (e) => {
      setResultadoPrueba({ ok: false, mensaje: mensajeError(e) });
      toast.error(mensajeError(e));
    },
  });

  const quitar = useMutation({
    mutationFn: () => api.eliminarMetricool(marca.marca),
    onSuccess: (res) => {
      toast.success(res?.mensaje ?? `${marca.etiqueta} desconectada.`);
      setUserToken("");
      setPerfiles([]);
      setResultadoPrueba(null);
      setConfirmarQuitar(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_METRICOOL });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const ocupado =
    guardar.isPending || probar.isPending || quitar.isPending || buscarMarcas.isPending;
  const idTok = `mc-token-${marca.marca}`;
  const idUid = `mc-userid-${marca.marca}`;
  const idMarca = `mc-marca-${marca.marca}`;
  // Para buscar marcas basta con token + userId.
  const puedeBuscar = userToken.trim() !== "" && userId.trim() !== "";
  // Para guardar hacen falta los tres campos (token + user_id + blog_id).
  const puedeGuardar = puedeBuscar && blogId.trim() !== "";

  return (
    <div className="space-y-3 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{marca.etiqueta}</span>
        {marca.conectado ? (
          <Badge variant="ok">Conectado</Badge>
        ) : (
          <Badge variant="secondary">Sin conectar</Badge>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor={idTok} className="text-xs text-muted-foreground">
          Token de Metricool (user_token)
        </Label>
        <Input
          id={idTok}
          type="password"
          autoComplete="off"
          value={userToken}
          onChange={(e) => {
            setUserToken(e.target.value);
            setPerfiles([]); // El token cambió: las marcas descubiertas ya no aplican.
          }}
          placeholder={
            marca.conectado ? "•••••••••• (escribe para reemplazar)" : "Pega el token aquí"
          }
          disabled={ocupado}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor={idUid} className="text-xs text-muted-foreground">
          User ID
        </Label>
        <div className="flex gap-2">
          <Input
            id={idUid}
            autoComplete="off"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="userId (en la misma pantalla de Metricool)"
            disabled={ocupado}
          />
          <Button
            size="sm"
            variant="outline"
            className="shrink-0"
            onClick={() => buscarMarcas.mutate()}
            disabled={ocupado || !puedeBuscar}
            title={!puedeBuscar ? "Pega el token y el userId para buscar." : undefined}
          >
            {buscarMarcas.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plug className="h-4 w-4" />
            )}
            {buscarMarcas.isPending ? "Buscando…" : "Buscar marcas"}
          </Button>
        </div>
      </div>

      {/* Marca de Metricool: se elige del desplegable que devuelve «Buscar marcas»;
          el blogId se rellena solo. Antes de buscar, muestra el blogId ya guardado. */}
      <div className="space-y-2">
        <Label htmlFor={idMarca} className="text-xs text-muted-foreground">
          Marca de Metricool
        </Label>
        {perfiles.length > 0 ? (
          <Select value={blogId} onValueChange={setBlogId} disabled={ocupado}>
            <SelectTrigger id={idMarca}>
              <SelectValue placeholder="Elige una marca" />
            </SelectTrigger>
            <SelectContent>
              {perfiles.map((p) => (
                <SelectItem key={p.blog_id} value={p.blog_id}>
                  {p.label} ({p.blog_id})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <p className="text-xs text-muted-foreground">
            {blogId
              ? `Marca actual (blogId ${blogId}). Usa «Buscar marcas» para cambiarla.`
              : "Pulsa «Buscar marcas» para elegir la marca de Metricool."}
          </p>
        )}
      </div>

      {resultadoPrueba && (
        <p
          className={cn(
            "flex items-center gap-1.5 text-sm",
            resultadoPrueba.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive",
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

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => guardar.mutate()} disabled={ocupado || !puedeGuardar}>
          {guardar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {guardar.isPending ? "Guardando…" : marca.conectado ? "Reemplazar" : "Guardar"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => probar.mutate()}
          disabled={ocupado || !marca.conectado}
          title={!marca.conectado ? "Guarda la credencial antes de probar." : undefined}
        >
          {probar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ShieldCheck className="h-4 w-4" />
          )}
          {probar.isPending ? "Probando…" : "Probar"}
        </Button>
        {marca.conectado && (
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
            <DialogTitle>Desconectar {marca.etiqueta}</DialogTitle>
            <DialogDescription>
              Se eliminará la credencial de Metricool guardada para esta marca. Podrás volver a
              conectarla pegando un token nuevo. ¿Quieres continuar?
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

function SeccionMetricool() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_METRICOOL,
    queryFn: ({ signal }) => api.conexionesMetricool(signal),
  });

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-base">Métricas (Metricool)</CardTitle>
        <CardDescription>
          Conecta cada marca con su cuenta de Metricool. Pega el token y el user ID, pulsa «Buscar
          marcas» y elige la marca; el blog ID se rellena solo.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">
            En AMX cada marca es una <strong>cuenta de Metricool distinta</strong>. El token se
            guarda <strong>solo en esta máquina</strong>, es <strong>revocable</strong> y nunca se
            muestra; al buscar marcas <strong>no se guarda nada</strong>. Usa «Probar» para validar
            la conexión en vivo.
          </p>
        </div>

        {isPending ? (
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-44 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <BloqueError
            titulo="No se pudieron cargar las marcas de Metricool"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : data.marcas.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No hay marcas disponibles para conectar.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {data.marcas.map((marca) => (
              <TarjetaMetricool key={marca.marca} marca={marca} />
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
                Elige modelos económicos para posts sin foto de persona; los GPT-5 generan
                personas.
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
 * Página de Ajustes: fuente de datos, alcance de marcas, métricas (Metricool) e
 * imagen IA. El botón "Actualizar" refresca las cachés de las queries.
 */
export default function Configuracion() {
  const queryClient = useQueryClient();
  const { usuario } = useSesion();
  // Metricool e Imagen IA son SECRETOS GLOBALES: el backend solo deja a un admin verlos
  // o cambiarlos (#153, /api/conexiones exige rol admin). Ocultamos esas secciones a un
  // editor para no mostrarle un error 403. Sin usuario de sesión (acceso por token
  // interino / modo local mono-usuario) cuenta como plenos permisos, así que se muestran.
  const puedeVerConexiones = usuario === null || usuario.rol === "admin";
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
        if (puedeVerConexiones) {
          void queryClient.invalidateQueries({ queryKey: CLAVE_IMAGEN });
          void queryClient.invalidateQueries({ queryKey: CLAVE_METRICOOL });
        }
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
        descripcion="Fuente de datos, marcas, Metricool y clave de imagen IA. Los secretos se guardan solo en esta máquina."
        acciones={acciones}
      />

      <div className="space-y-6">
        <SeccionDatos />
        <SeccionEsfuerzo />
        {/* Metricool e Imagen IA: solo admin (secretos globales, #153). */}
        {puedeVerConexiones && <SeccionMetricool />}
        {puedeVerConexiones && <SeccionImagen />}
        <SeccionApariencia />
      </div>
    </>
  );
}
