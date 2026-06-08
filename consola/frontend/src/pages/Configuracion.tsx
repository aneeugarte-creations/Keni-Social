/**
 * Página de Ajustes (Configuración). Reúne en una sola pantalla:
 *   1. Alcance de marcas (qué marcas se incluyen).
 *   2. Métricas (Metricool) por marca: token + userId → descubrir blogId → guardar.
 *   3. Imagen con IA (clave del proveedor para «Generar con IA»).
 *
 * Las métricas se consumen vía Metricool (ADR 0005 §B): la antigua sección "Redes
 * sociales" (tokens por plataforma para la ingesta propia) se retiró. La sección de
 * Imagen vivía antes en la página "Conexiones", fusionada aquí (issue #87). Los
 * secretos son write-only: nunca se muestran; del servidor solo llega el estado/pista.
 */
import { useIsFetching, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  Info,
  Loader2,
  Moon,
  MoreHorizontal,
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
import { MenuContextual } from "@/components/comunes/MenuContextual";
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
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { useTema } from "@/hooks/tema-contexto";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AjusteAdmin, MarcaMetricool, PerfilMetricool, RespuestaAjustes } from "@/types";

const CLAVE_ESFUERZO = ["config", "esfuerzo"];
const CLAVE_IMAGEN = ["conexiones", "imagen"];
const CLAVE_METRICOOL = ["conexiones", "metricool"];
const CLAVE_AJUSTES = ["ajustes"];

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

/** Tarjeta COLAPSABLE de configuración: cabecera clicable (título + descripción + chevron) que
 *  pliega/despliega el contenido. Reduce el ruido de una página muy llena; cada tarjeta recuerda
 *  su estado mientras la página está montada. `abiertaInicial` deja abierta la(s) más importante(s). */
function TarjetaColapsable({
  titulo,
  descripcion,
  abiertaInicial = false,
  contentClassName = "pt-0",
  children,
}: {
  titulo: string;
  descripcion?: React.ReactNode;
  abiertaInicial?: boolean;
  contentClassName?: string;
  children: React.ReactNode;
}) {
  const [abierta, setAbierta] = React.useState(abiertaInicial);
  const alternar = () => setAbierta((v) => !v);
  return (
    <Card>
      <CardHeader
        role="button"
        tabIndex={0}
        aria-expanded={abierta}
        onClick={alternar}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            alternar();
          }
        }}
        className="cursor-pointer select-none pb-3"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">{titulo}</CardTitle>
            {descripcion && <CardDescription className="mt-1">{descripcion}</CardDescription>}
          </div>
          <ChevronDown
            aria-hidden
            className={cn(
              "mt-0.5 h-5 w-5 shrink-0 text-muted-foreground transition-transform",
              abierta && "rotate-180",
            )}
          />
        </div>
      </CardHeader>
      {abierta && <CardContent className={contentClassName}>{children}</CardContent>}
    </Card>
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
    <TarjetaColapsable
      titulo="Esfuerzo de generación"
      contentClassName="space-y-2 pt-0"
      descripcion={
        <>
          Cuánto «piensa» la IA al generar copy, RSS, hashtags y agentes. Más esfuerzo mejora la
          calidad pero tarda más; menos responde antes. Se guarda{" "}
          <strong>solo en esta máquina</strong>.
        </>
      }
    >
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
    </TarjetaColapsable>
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
        {/* Acciones secundarias (Probar / Quitar) agrupadas en un desplegable.
            Solo aplican con la credencial ya guardada, así que el menú se muestra
            cuando la marca está conectada. */}
        {marca.conectado && (
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
            <Button size="sm" variant="outline" disabled={ocupado}>
              <MoreHorizontal className="h-4 w-4" /> Más{" "}
              <ChevronDown className="h-4 w-4 opacity-60" />
            </Button>
          </MenuContextual>
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
    <TarjetaColapsable
      titulo="Métricas (Metricool)"
      contentClassName="space-y-4 pt-0"
      descripcion={
        <>
          Conecta cada marca con su cuenta de Metricool. Pega el token y el user ID, pulsa «Buscar
          marcas» y elige la marca; el blog ID se rellena solo.
        </>
      }
    >
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
    </TarjetaColapsable>
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
    <TarjetaColapsable
      titulo="Imagen con IA"
      contentClassName="space-y-4 pt-0"
      descripcion={
        <>
          Configura la clave del proveedor para activar <strong>«Generar con IA»</strong> al crear
          imágenes en las publicaciones. La clave se guarda{" "}
          <strong>solo en esta máquina</strong> y nunca se muestra.
        </>
      }
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
    </TarjetaColapsable>
  );
}

/* ------------------------------------------------------------------ */
/* Sección: Apariencia (tema claro/oscuro)                            */
/* ------------------------------------------------------------------ */

/** Selector de tema claro/oscuro. Preferencia personal e instantánea: vive ARRIBA DEL TODO y
 *  SIEMPRE visible (tarjeta compacta no colapsable, fuera de las pestañas), no enterrada entre
 *  la configuración del producto. El tema se guarda en este equipo. */
function SeccionApariencia() {
  const { esOscuro, fijar } = useTema();

  const opciones: { id: "claro" | "oscuro"; etiqueta: string; icono: typeof Sun }[] = [
    { id: "claro", etiqueta: "Claro", icono: Sun },
    { id: "oscuro", etiqueta: "Oscuro", icono: Moon },
  ];

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
        <div className="min-w-0">
          <p className="text-sm font-medium">Apariencia</p>
          <p className="text-xs text-muted-foreground">
            Tema de la consola. Se guarda <strong>solo en este equipo</strong>.
          </p>
        </div>
        <div role="radiogroup" aria-label="Tema" className="flex shrink-0 flex-wrap gap-2">
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
/** Una fila de ajuste: toggle (bool), número (int/float) o selector (select).
 *
 * `bloqueado` (solo bool): la fila se muestra APAGADA y deshabilitada porque otro control la
 * gobierna (p. ej. una excepción por marca cuyo maestro de etapa está OFF). `notaBloqueo` es la
 * etiqueta corta que explica por qué. No cambia el valor guardado: solo refleja que no aplica. */
function FilaAjuste({
  ajuste,
  onGuardar,
  guardando,
  bloqueado = false,
  notaBloqueo,
}: {
  ajuste: AjusteAdmin;
  onGuardar: (cuerpo: { clave: string; valor?: boolean | number | string }) => void;
  guardando: boolean;
  bloqueado?: boolean;
  notaBloqueo?: string;
}) {
  const [confirmar, setConfirmar] = React.useState(false);
  const [num, setNum] = React.useState(String(ajuste.valor));
  React.useEffect(() => {
    setNum(String(ajuste.valor));
  }, [ajuste.valor]);

  const cabecera = (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{ajuste.etiqueta}</span>
        {ajuste.peligroso && (
          <Badge variant="destructive" className="text-[10px]">
            Publica de verdad
          </Badge>
        )}
        {bloqueado && notaBloqueo && (
          <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            · {notaBloqueo}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{ajuste.ayuda}</p>
    </div>
  );

  if (ajuste.tipo === "bool") {
    // Si está bloqueado por su maestro, se ve apagado pase lo que pase (el daemon no corre).
    const activo = bloqueado ? false : Boolean(ajuste.valor);
    const onToggle = (valor: boolean) => {
      // Encender un flag PELIGROSO (publicación real) pide confirmación explícita.
      if (valor && ajuste.peligroso) {
        setConfirmar(true);
        return;
      }
      onGuardar({ clave: ajuste.clave, valor });
    };
    return (
      <div
        className={cn(
          "flex items-center justify-between gap-4 border-b border-border/50 py-3 last:border-0",
          bloqueado && "opacity-50",
        )}
      >
        {cabecera}
        <Switch
          checked={activo}
          onCheckedChange={onToggle}
          disabled={guardando || bloqueado}
          aria-label={ajuste.etiqueta}
        />
        <Dialog open={confirmar} onOpenChange={setConfirmar}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Activar publicación real</DialogTitle>
              <DialogDescription>
                «{ajuste.etiqueta}» hará que las piezas aprobadas y programadas se publiquen DE
                VERDAD en las redes (vía Metricool). Asegúrate de que es lo que quieres.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmar(false)}>
                Cancelar
              </Button>
              <Button
                variant="destructive"
                onClick={() => {
                  onGuardar({ clave: ajuste.clave, valor: true });
                  setConfirmar(false);
                }}
              >
                Sí, publicar de verdad
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  if (ajuste.tipo === "select") {
    return (
      <div className="flex items-center justify-between gap-4 border-b border-border/50 py-3 last:border-0">
        {cabecera}
        <Select
          value={String(ajuste.valor) || "_vacio"}
          onValueChange={(valor) =>
            onGuardar({ clave: ajuste.clave, valor: valor === "_vacio" ? "" : valor })
          }
          disabled={guardando}
        >
          <SelectTrigger className="w-[160px]" aria-label={ajuste.etiqueta}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(ajuste.opciones ?? []).map((o) => (
              <SelectItem key={o.id || "_vacio"} value={o.id || "_vacio"}>
                {o.etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  // int / float: se guarda al salir del campo (blur) si cambió.
  const guardarNumero = () => {
    if (num !== String(ajuste.valor) && num.trim() !== "") {
      onGuardar({ clave: ajuste.clave, valor: Number(num) });
    }
  };
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border/50 py-3 last:border-0">
      {cabecera}
      <Input
        type="number"
        value={num}
        min={ajuste.min}
        max={ajuste.max}
        step={ajuste.tipo === "float" ? "0.1" : "1"}
        onChange={(e) => setNum(e.target.value)}
        onBlur={guardarNumero}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        disabled={guardando}
        className="w-[120px] tabular-nums"
        aria-label={ajuste.etiqueta}
      />
    </div>
  );
}

/** Toggles de generación por MARCA (copy + arte), en una pestaña por marca (en vez de lista plana).
 *
 * Cada ajuste del grupo "Automatización por marca" tiene clave `ENV::marca` y etiqueta
 * "Nombre · Etapa"; agrupamos por marca (orden de aparición) y, dentro de su pestaña, la fila
 * muestra solo la ETAPA (el nombre ya lo da la pestaña). Reutiliza `FilaAjuste`. */
function AjustesPorMarca({
  ajustes,
  onGuardar,
  guardando,
  maestros,
}: {
  ajustes: AjusteAdmin[];
  onGuardar: (cuerpo: { clave: string; valor?: boolean | number | string }) => void;
  guardando: boolean;
  /** Valor de cada maestro de etapa por su clave ENV (p. ej. `KENI_PIPELINE`). Si el maestro de
   *  la etapa está OFF, su excepción por marca se OCULTA (no se gestiona hasta encender la etapa). */
  maestros: Record<string, boolean>;
}) {
  const porMarca = React.useMemo(() => {
    const orden: string[] = [];
    const mapa = new Map<string, { nombre: string; ajustes: AjusteAdmin[] }>();
    for (const a of ajustes) {
      const marcaId = a.clave.split("::")[1] ?? a.clave;
      const [nombre, etapa] = a.etiqueta.split(" · ");
      if (!mapa.has(marcaId)) {
        mapa.set(marcaId, { nombre: nombre || marcaId, ajustes: [] });
        orden.push(marcaId);
      }
      // En la pestaña de la marca, la fila muestra solo la etapa (no repite el nombre).
      mapa.get(marcaId)!.ajustes.push({ ...a, etiqueta: etapa || a.etiqueta });
    }
    return orden.map((id) => ({ id, ...mapa.get(id)! }));
  }, [ajustes]);

  const { marcaActiva } = useMarcaActiva();
  const [activa, setActiva] = React.useState(
    (marcaActiva && porMarca.some((m) => m.id === marcaActiva) ? marcaActiva : porMarca[0]?.id) ?? "",
  );
  React.useEffect(() => {
    if (porMarca.length && !porMarca.some((m) => m.id === activa)) {
      setActiva(
        marcaActiva && porMarca.some((m) => m.id === marcaActiva) ? marcaActiva : porMarca[0].id,
      );
    }
  }, [porMarca, activa, marcaActiva]);

  if (!porMarca.length) return null;
  return (
    <Tabs value={activa} onValueChange={setActiva} className="mt-1">
      <TabsList className="flex-wrap">
        {porMarca.map((m) => (
          <TabsTrigger key={m.id} value={m.id}>
            {m.nombre}
          </TabsTrigger>
        ))}
      </TabsList>
      {porMarca.map((m) => {
        // Etapa = clave ENV antes de "::". Solo gestionamos excepciones de etapas ENCENDIDAS:
        // con el maestro OFF la excepción no aplica, así que ocultamos la fila (no la atenuamos).
        const visibles = m.ajustes.filter((a) => maestros[a.clave.split("::")[0]] !== false);
        return (
          <TabsContent key={m.id} value={m.id}>
            {visibles.length > 0 ? (
              visibles.map((a) => (
                <FilaAjuste key={a.clave} ajuste={a} onGuardar={onGuardar} guardando={guardando} />
              ))
            ) : (
              <p className="py-3 text-xs text-muted-foreground">
                Enciende el maestro de la etapa para gestionar excepciones por marca.
              </p>
            )}
          </TabsContent>
        );
      })}
    </Tabs>
  );
}


/** Grupos de ajustes que viven en la pestaña «Básica»: el master de la máquina, los tres maestros
 *  de etapa (Crear noticias / Generar copy / Generar arte) y sus excepciones por marca (las tres
 *  etapas). Son los controles clave del día a día. Todo grupo que NO esté aquí (publicación,
 *  publicación por marca, automatismos generales, ajustes finos) va a «Avanzada». Coincide con la
 *  `id` de grupo del backend; un grupo ausente en la respuesta simplemente no pinta nada. */
const GRUPOS_BASICOS = new Set(["maquina_global", "maestros_etapa", "automatizacion_marca"]);

/** Sección admin: toggles + ajustes finos de funcionalidad (aplican en caliente).
 *
 * `nivel` decide qué grupos pinta: «basica» muestra los grupos de `GRUPOS_BASICOS`; «avanzada»
 * muestra todo lo demás. Si tras filtrar no queda ningún grupo, la tarjeta no se renderiza (no
 * deja un hueco vacío en la pestaña). */
function SeccionFuncionalidad({ nivel }: { nivel: "basica" | "avanzada" }) {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_AJUSTES,
    queryFn: ({ signal }) => api.ajustes(signal),
  });

  const avanzada = nivel === "avanzada";
  // Grupos que tocan a esta pestaña (basica: los de GRUPOS_BASICOS; avanzada: el resto).
  const grupos = (data?.grupos ?? []).filter((g) =>
    avanzada ? !GRUPOS_BASICOS.has(g.id) : GRUPOS_BASICOS.has(g.id),
  );
  const guardar = useMutation({
    mutationFn: (cuerpo: { clave: string; valor?: boolean | number | string }) =>
      api.guardarAjuste(cuerpo),
    onSuccess: (res) => {
      // Sustituye el ajuste en la caché (sin refetch completo) y confirma.
      queryClient.setQueryData<RespuestaAjustes>(CLAVE_AJUSTES, (prev) =>
        prev
          ? {
              grupos: prev.grupos.map((g) => ({
                ...g,
                ajustes: g.ajustes.map((a) => (a.clave === res.ajuste.clave ? res.ajuste : a)),
              })),
            }
          : prev,
      );
      toast.success(`«${res.ajuste.etiqueta}» actualizado.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Maestros de etapa por su clave ENV (p. ej. `KENI_PIPELINE` -> bool). Se usa para atenuar las
  // excepciones por marca cuyo maestro está OFF.
  const ajustesMaestros = grupos.find((g) => g.id === "maestros_etapa")?.ajustes ?? [];
  const maestros: Record<string, boolean> = {};
  for (const m of ajustesMaestros) maestros[m.clave] = Boolean(m.valor);

  // Sin grupos para esta pestaña (p. ej. la API aún no trae el grupo): no pintamos la tarjeta.
  // Va DESPUÉS de los hooks (useQuery/useMutation) para no llamarlos condicionalmente.
  if (!isPending && !isError && grupos.length === 0) return null;

  return (
    <TarjetaColapsable
      titulo={avanzada ? "Ajustes finos" : "Funcionalidad"}
      abiertaInicial
      contentClassName="space-y-6 pt-0"
      descripcion={
        avanzada ? (
          <>
            Granularidad de la automatización (intervalos, máximos por barrido, umbrales, jobs…).
            Funcionan bien en sus <strong>valores por defecto</strong>; tócalos solo para afinar.
            Los cambios aplican <strong>en caliente</strong> (hasta ~1 minuto).
          </>
        ) : undefined
      }
    >
        {isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <BloqueError
            titulo="No se pudieron cargar los ajustes"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : (
          grupos.map((grupo) => {
            const onGuardar = (cuerpo: { clave: string; valor?: boolean | number | string }) =>
              guardar.mutate(cuerpo);
            const filas = grupo.ajustes.map((ajuste) => (
              <FilaAjuste
                key={ajuste.clave}
                ajuste={ajuste}
                onGuardar={onGuardar}
                guardando={guardar.isPending}
              />
            ));

            // Maestros de etapa (Crear noticias / Generar copy / Generar arte): título + filas.
            if (grupo.id === "maestros_etapa") {
              return (
                <div key={grupo.id} className="space-y-1">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {grupo.titulo}
                  </h4>
                  <div>{filas}</div>
                </div>
              );
            }

            // Excepciones por marca: una pestaña por marca; atenuadas si su maestro está OFF.
            if (grupo.id === "automatizacion_marca") {
              return (
                <div key={grupo.id} className="space-y-1">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {grupo.titulo}
                  </h4>
                  <AjustesPorMarca
                    ajustes={grupo.ajustes}
                    onGuardar={onGuardar}
                    guardando={guardar.isPending}
                    maestros={maestros}
                  />
                </div>
              );
            }

            // Publicación: el mega-maestro del paso final (postea de verdad), en su BLOQUE PROPIO
            // destacado (acento ámbar) por ser el más peligroso. Mismo patrón maestro+excepción:
            // el maestro autoriza el posteo real global; debajo, las excepciones por marca lo
            // restan (apagan una marca -> dry-run). El grupo `publicacion_marca` se pinta AQUÍ.
            if (grupo.id === "publicacion") {
              const maestroPub = grupo.ajustes[0];
              const maestroPubOn = Boolean(maestroPub?.valor);
              const exMarca = grupos.find((g) => g.id === "publicacion_marca")?.ajustes ?? [];
              return (
                <div
                  key={grupo.id}
                  className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3"
                >
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
                      {grupo.titulo} · publica de verdad
                    </h4>
                    <p className="text-xs text-muted-foreground">
                      Autoriza el posteo <strong>REAL</strong> a Metricool.
                    </p>
                  </div>
                  <div>{filas}</div>
                  {exMarca.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                        Excepciones por marca
                      </p>
                      <div>
                        {exMarca.map((a) => (
                          <FilaAjuste
                            key={a.clave}
                            ajuste={a}
                            onGuardar={onGuardar}
                            guardando={guardar.isPending}
                            bloqueado={!maestroPubOn}
                            notaBloqueo="maestro apagado"
                          />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            }
            // Las excepciones de publicación se pintan dentro del bloque «publicacion» de arriba.
            if (grupo.id === "publicacion_marca") return null;

            // Automatismos generales: barridos del sistema; van en un colapsible para no confundir
            // con los controles de las etapas de la máquina de arriba.
            if (grupo.id === "automatismos_generales") {
              return (
                <TarjetaColapsable
                  key={grupo.id}
                  titulo={grupo.titulo}
                  descripcion="Barridos del sistema sin dimensión por marca (radar, alertas, vencimientos, limpieza…)."
                >
                  <div>{filas}</div>
                </TarjetaColapsable>
              );
            }

            // Resto (Publicación, Ajustes finos): título + lista plana.
            return (
              <div key={grupo.id} className="space-y-1">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {grupo.titulo}
                </h4>
                <div>{filas}</div>
              </div>
            );
          })
        )}
    </TarjetaColapsable>
  );
}

export default function Configuracion() {
  const queryClient = useQueryClient();
  const { usuario } = useSesion();
  // Metricool e Imagen IA son SECRETOS GLOBALES: el backend solo deja a un admin verlos
  // o cambiarlos (#153, /api/conexiones exige rol admin). Ocultamos esas secciones a un
  // editor para no mostrarle un error 403. Sin usuario de sesión (acceso por token
  // interino / modo local mono-usuario) cuenta como plenos permisos, así que se muestran.
  const puedeVerConexiones = usuario === null || usuario.rol === "admin";
  // ¿Hay alguna query (de cualquier sección) en vuelo? (para el spinner del botón).
  const refrescando = useIsFetching() > 0;

  const acciones = (
    <Button
      variant="outline"
      onClick={() => {
        void queryClient.invalidateQueries({ queryKey: CLAVE_ESFUERZO });
        if (puedeVerConexiones) {
          void queryClient.invalidateQueries({ queryKey: CLAVE_AJUSTES });
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
        descripcion="Automatización, Metricool y clave de imagen IA. Los secretos se guardan solo en esta máquina."
        acciones={acciones}
      />

      {/* Orden por frecuencia/criticidad, no por tema. Arriba del todo y SIEMPRE visible: el
          tema (preferencia personal, instantánea). Debajo, dos pestañas que doman una página
          muy llena. */}
      <div className="space-y-4">
        <SeccionApariencia />

        <Tabs defaultValue="basica" className="space-y-4">
          <TabsList>
            <TabsTrigger value="basica">Básica</TabsTrigger>
            <TabsTrigger value="avanzada">Avanzada</TabsTrigger>
          </TabsList>

          {/* Básica: controles clave de arriba (lo que más se toca) a abajo (setup-once).
              Funcionalidad (toggles del día) arranca abierta; las Conexiones (Imagen IA +
              Metricool) van AL FINAL y colapsadas: se configuran una vez y casi nunca se
              vuelven a abrir. Metricool, lo último. Todas: solo admin (#153). */}
          <TabsContent value="basica" className="space-y-4">
            {puedeVerConexiones && <SeccionFuncionalidad nivel="basica" />}
            {puedeVerConexiones && <SeccionImagen />}
            {puedeVerConexiones && <SeccionMetricool />}
          </TabsContent>

          {/* Avanzada: la granularidad que funciona en sus valores por defecto (ajustes finos
              + esfuerzo de generación); rara vez se toca. */}
          <TabsContent value="avanzada" className="space-y-4">
            {puedeVerConexiones && <SeccionFuncionalidad nivel="avanzada" />}
            <SeccionEsfuerzo />
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
}
