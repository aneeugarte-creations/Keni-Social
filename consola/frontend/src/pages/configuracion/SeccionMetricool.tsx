import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  Info,
  MoreHorizontal,
  Plug,
  Save,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Campo } from "@/components/comunes/Campo";
import { confirmar } from "@/components/comunes/confirmar";
import { MenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useSesion } from "@/hooks/sesion-contexto";
import { cn } from "@/lib/utils";
import type { MarcaMetricool, PerfilMetricool } from "@/types";

import { CLAVE_METRICOOL, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

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
  // Marcas descubiertas vía /perfiles (desplegable). Se limpian al cambiar el token.
  const [perfiles, setPerfiles] = React.useState<PerfilMetricool[]>([]);
  const [resultadoPrueba, setResultadoPrueba] = React.useState<{
    ok: boolean;
    mensaje: string;
  } | null>(null);
  // El error solo se muestra tras un intento de guardar (no mientras se escribe).
  const [intentado, setIntentado] = React.useState(false);

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
      setIntentado(false);
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
      setIntentado(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_METRICOOL });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const pedirQuitar = async () => {
    if (
      await confirmar({
        titulo: `Desconectar ${marca.etiqueta}`,
        mensaje: `Se eliminará la credencial de Metricool guardada para esta marca. Podrás volver a conectarla pegando un token nuevo. ¿Quieres continuar?`,
        destructivo: true,
        textoConfirmar: "Quitar",
      })
    )
      quitar.mutate();
  };

  const ocupado =
    guardar.isPending || probar.isPending || quitar.isPending || buscarMarcas.isPending;
  const idTok = `mc-token-${marca.marca}`;
  const idUid = `mc-userid-${marca.marca}`;
  const idMarca = `mc-marca-${marca.marca}`;
  // Para buscar marcas basta con token + userId.
  const puedeBuscar = userToken.trim() !== "" && userId.trim() !== "";
  // Para guardar hacen falta los tres campos (token + user_id + blog_id).
  const errToken = userToken.trim() === "" ? "Pega el token." : null;
  const errUserId = userId.trim() === "" ? "Indica el User ID." : null;
  const errBlogId = blogId.trim() === "" ? "Elige una marca." : null;
  const hayErrores = Boolean(errToken || errUserId || errBlogId);

  const onGuardar = () => {
    setIntentado(true);
    if (hayErrores) return;
    guardar.mutate();
  };

  return (
    <div className="space-y-4 rounded-xl border bg-card p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{marca.etiqueta}</span>
        {marca.conectado ? (
          <Badge variant="ok">Conectado</Badge>
        ) : (
          <Badge variant="secondary">Sin conectar</Badge>
        )}
      </div>

      <Campo
        etiqueta="Token de Metricool"
        htmlFor={idTok}
        error={intentado ? errToken : null}
      >
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
          aria-invalid={(intentado && Boolean(errToken)) || undefined}
        />
      </Campo>

      <Campo etiqueta="User ID" htmlFor={idUid} error={intentado ? errUserId : null}>
        <div className="flex gap-2">
          <Input
            id={idUid}
            autoComplete="off"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="userId (de Metricool)"
            disabled={ocupado}
            aria-invalid={(intentado && Boolean(errUserId)) || undefined}
          />
          <Tooltip label={!puedeBuscar ? "Pega el token y el userId para buscar." : ""}>
            <Button
              size="sm"
              variant="outline"
              className="shrink-0"
              onClick={() => buscarMarcas.mutate()}
              disabled={ocupado || !puedeBuscar}
            >
              {buscarMarcas.isPending ? (
                <Spinner className="h-4 w-4" />
              ) : (
                <Plug className="h-4 w-4" />
              )}
              {buscarMarcas.isPending ? "Buscando…" : "Buscar marcas"}
            </Button>
          </Tooltip>
        </div>
      </Campo>

      {/* Marca de Metricool: se elige del desplegable que devuelve «Buscar marcas»;
          el blogId se rellena solo. Antes de buscar, muestra el blogId ya guardado. */}
      <Campo etiqueta="Marca de Metricool" htmlFor={idMarca} error={intentado ? errBlogId : null}>
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
              ? `Marca actual. Usa «Buscar marcas» para cambiarla.`
              : "Pulsa «Buscar marcas» para elegir la marca de Metricool."}
          </p>
        )}
      </Campo>

      {resultadoPrueba && (
        <p
          className={cn(
            "flex items-center gap-1.5 text-sm",
            resultadoPrueba.ok ? "text-emerald-700 dark:text-emerald-300" : "text-destructive",
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
        <Button size="sm" onClick={onGuardar} disabled={ocupado}>
          {guardar.isPending ? (
            <Spinner className="h-4 w-4" />
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
                onClick: () => void pedirQuitar(),
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

    </div>
  );
}

/** Envoltorio con AUTOGUARDADO por rol: los secretos de conexión son de admin.
 * Montada en su página contextual, se oculta sola a un editor (sesión null = modo local
 * pleno). El guard vive en un wrapper para no llamar hooks condicionalmente. */
export function SeccionMetricool() {
  const { usuario } = useSesion();
  if (usuario !== null && usuario.rol !== "admin") return null;
  return <SeccionMetricoolAdmin />;
}

function SeccionMetricoolAdmin() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_METRICOOL,
    queryFn: ({ signal }) => api.conexionesMetricool(signal),
  });

  return (
    <SeccionColapsable
      titulo="Conexiones · Métricas (Metricool)"
      contentClassName="space-y-4"
      descripcion="Conecta cada marca con Metricool."
    >
        <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">
            Token local · Usa «Probar» para validar.
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
    </SeccionColapsable>
  );
}
