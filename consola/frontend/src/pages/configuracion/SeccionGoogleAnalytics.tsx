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
import { confirmar } from "@/components/comunes/confirmar";
import { MenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Spinner } from "@/components/ui/spinner";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { MarcaGoogleAnalytics, PropiedadGoogleAnalytics } from "@/types";

import { CLAVE_GA_PROPIEDADES, CLAVE_GOOGLE_ANALYTICS, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

// Ruta de la ventana de retorno del OAuth (la misma que usa el panel de Marcas).
const RUTA_OAUTH_RETORNO = "/oauth/conectado";
const MSG_OAUTH = "keni-oauth-conectado";

/**
 * Fila de UNA marca: mapea una propiedad GA4 a la marca. Si la app está conectada,
 * la propiedad se elige de un desplegable poblado con las propiedades de la cuenta;
 * si la lista no se pudo cargar, se cae a un campo de texto con el id numérico.
 * «Guardar» persiste el mapeo, «Probar» hace una lectura en vivo y «Quitar» lo borra.
 */
function FilaGoogleAnalytics({
  marca,
  propiedades,
  conectado,
  propiedadesError,
}: {
  marca: MarcaGoogleAnalytics;
  propiedades: PropiedadGoogleAnalytics[];
  conectado: boolean;
  propiedadesError: boolean;
}) {
  const queryClient = useQueryClient();
  const [propertyId, setPropertyId] = React.useState(marca.property_id ?? "");
  const [resultadoPrueba, setResultadoPrueba] = React.useState<{
    ok: boolean;
    mensaje: string;
  } | null>(null);

  // Sincroniza el id de propiedad con lo que reporta el servidor.
  React.useEffect(() => {
    setPropertyId(marca.property_id ?? "");
  }, [marca.property_id]);

  const guardar = useMutation({
    mutationFn: () =>
      api.guardarPropiedadGoogleAnalytics(marca.marca, { property_id: propertyId.trim() }),
    onSuccess: (res) => {
      toast.success(res.mensaje || `${marca.etiqueta} conectada.`);
      setResultadoPrueba(null);
      void queryClient.invalidateQueries({ queryKey: CLAVE_GOOGLE_ANALYTICS });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const probar = useMutation({
    mutationFn: () => api.probarGoogleAnalytics(marca.marca),
    onSuccess: (res) => {
      const mensaje = res.mensaje || `${res.filas} filas leídas.`;
      setResultadoPrueba({ ok: res.ok, mensaje });
      if (res.ok) toast.success(mensaje);
      else toast.error(mensaje);
    },
    onError: (e) => {
      setResultadoPrueba({ ok: false, mensaje: mensajeError(e) });
      toast.error(mensajeError(e));
    },
  });

  const quitar = useMutation({
    mutationFn: () => api.eliminarPropiedadGoogleAnalytics(marca.marca),
    onSuccess: (res) => {
      toast.success(res?.mensaje ?? `${marca.etiqueta} desconectada.`);
      setResultadoPrueba(null);
      void queryClient.invalidateQueries({ queryKey: CLAVE_GOOGLE_ANALYTICS });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const pedirQuitar = async () => {
    if (
      await confirmar({
        titulo: `Desconectar ${marca.etiqueta}`,
        mensaje:
          "Se quitará la propiedad de Google Analytics mapeada a esta marca. Podrás volver a asignarla cuando quieras. ¿Quieres continuar?",
        destructivo: true,
        textoConfirmar: "Quitar",
      })
    )
      quitar.mutate();
  };

  const ocupado = guardar.isPending || probar.isPending || quitar.isPending;
  const idProp = `ga-prop-${marca.marca}`;
  const puedeGuardar = propertyId.trim() !== "";
  // El desplegable solo se usa con la app conectada y la lista de propiedades cargada.
  const usarDesplegable = conectado && !propiedadesError && propiedades.length > 0;

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
        <Label htmlFor={idProp} className="text-xs text-muted-foreground">
          Propiedad de Google Analytics
        </Label>
        {usarDesplegable ? (
          <Select value={propertyId} onValueChange={setPropertyId} disabled={ocupado}>
            <SelectTrigger id={idProp}>
              <SelectValue placeholder="Elige una propiedad" />
            </SelectTrigger>
            <SelectContent>
              {propiedades.map((p) => (
                <SelectItem key={p.property_id} value={p.property_id}>
                  {p.nombre} ({p.property_id}) · {p.cuenta}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Input
            id={idProp}
            autoComplete="off"
            value={propertyId}
            onChange={(e) => setPropertyId(e.target.value)}
            placeholder="ID de la propiedad (numérico)"
            disabled={ocupado}
          />
        )}
      </div>

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
        <Button size="sm" onClick={() => guardar.mutate()} disabled={ocupado || !puedeGuardar}>
          {guardar.isPending ? <Spinner className="h-4 w-4" /> : <Save className="h-4 w-4" />}
          {guardar.isPending ? "Guardando…" : marca.conectado ? "Reemplazar" : "Guardar"}
        </Button>
        {/* Probar / Quitar solo aplican con la propiedad ya mapeada. */}
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

/** Envoltorio con guard de admin: los secretos de conexión son de admin. Montada en
 * su página contextual, se oculta sola a un editor (sesión null = modo local pleno). */
export function SeccionGoogleAnalytics() {
  const { usuario } = useSesion();
  if (usuario !== null && usuario.rol !== "admin") return null;
  return <SeccionGoogleAnalyticsAdmin />;
}

function SeccionGoogleAnalyticsAdmin() {
  const queryClient = useQueryClient();
  const [clientId, setClientId] = React.useState("");
  const [clientSecret, setClientSecret] = React.useState("");

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_GOOGLE_ANALYTICS,
    queryFn: ({ signal }) => api.conexionesGoogleAnalytics(signal),
  });

  const appConfigurada = data?.app_configurada ?? false;
  const conectado = data?.conectado ?? false;

  // Refleja el client_id que reporta el servidor (no es secreto).
  React.useEffect(() => {
    setClientId(data?.client_id ?? "");
  }, [data?.client_id]);

  // Las propiedades GA4 solo se piden con la app conectada (necesitan el OAuth hecho).
  const propiedadesQuery = useQuery({
    queryKey: CLAVE_GA_PROPIEDADES,
    queryFn: ({ signal }) => api.propiedadesGoogleAnalytics(signal),
    enabled: conectado,
  });
  const propiedades = propiedadesQuery.data?.propiedades ?? [];

  const guardarApp = useMutation({
    mutationFn: () =>
      api.guardarAppGoogleAnalytics({ client_id: clientId.trim(), client_secret: clientSecret }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "App de Google Analytics guardada.");
      setClientSecret(""); // El secret nunca se conserva en cliente.
      void queryClient.invalidateQueries({ queryKey: CLAVE_GOOGLE_ANALYTICS });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const desconectar = useMutation({
    mutationFn: () => api.eliminarGoogleAnalytics(),
    onSuccess: (res) => {
      toast.success(res?.mensaje ?? "Google Analytics desconectado.");
      void queryClient.invalidateQueries({ queryKey: CLAVE_GOOGLE_ANALYTICS });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const pedirDesconectar = async () => {
    if (
      await confirmar({
        titulo: "Desconectar Google Analytics",
        mensaje:
          "Se cerrará la sesión de Google Analytics. Las marcas mapeadas dejarán de leer métricas hasta que vuelvas a conectar. ¿Quieres continuar?",
        destructivo: true,
        textoConfirmar: "Desconectar",
      })
    )
      desconectar.mutate();
  };

  // La ventana de retorno del OAuth nos avisa al terminar: refrescamos al instante.
  React.useEffect(() => {
    function alMensaje(e: MessageEvent) {
      if (e.origin !== window.location.origin) return;
      if (e.data?.tipo !== MSG_OAUTH) return;
      void queryClient.invalidateQueries({ queryKey: CLAVE_GOOGLE_ANALYTICS });
      void queryClient.invalidateQueries({ queryKey: CLAVE_GA_PROPIEDADES });
      if (e.data.ok) toast.success("Google Analytics conectado.");
    }
    window.addEventListener("message", alMensaje);
    return () => window.removeEventListener("message", alMensaje);
  }, [queryClient]);

  const [conectando, setConectando] = React.useState(false);
  function conectar() {
    // Ventana abierta SINCRÓNICAMENTE en el clic (los bloqueadores de popups lo exigen).
    const popup = window.open("about:blank", "keni_conectar_ga", "width=620,height=760");
    setConectando(true);
    api
      .conectarGoogleAnalytics({ redirect_uri: window.location.origin + RUTA_OAUTH_RETORNO })
      .then((res) => {
        if (popup) popup.location.href = res.url;
        else window.open(res.url, "_blank", "noopener,noreferrer");
      })
      .catch((e) => {
        popup?.close();
        toast.error(mensajeError(e));
      })
      .finally(() => setConectando(false));
  }

  const ocupadoApp = guardarApp.isPending || desconectar.isPending;
  const puedeGuardarApp = clientId.trim() !== "" && clientSecret.trim() !== "";

  return (
    <SeccionColapsable
      titulo="Métricas · Google Analytics"
      contentClassName="space-y-4"
      descripcion="Conecta Google Analytics y mapea una propiedad por marca."
    >
      <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Configura la app una vez, conecta con Google y elige la propiedad de cada marca.
        </p>
      </div>

      {/* App OAuth: client_id (no secreto) + client_secret (write-only). */}
      <div className="space-y-3 rounded-lg border border-border p-3">
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="ga-client-id" className="text-sm font-medium">
            App de Google
          </Label>
          {appConfigurada ? (
            <Badge variant="ok">Configurada</Badge>
          ) : (
            <Badge variant="secondary">Sin configurar</Badge>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="ga-client-id" className="text-xs text-muted-foreground">
            Client ID
          </Label>
          <Input
            id="ga-client-id"
            autoComplete="off"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            placeholder="ID de cliente de la app de Google"
            disabled={ocupadoApp}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="ga-client-secret" className="text-xs text-muted-foreground">
            Client Secret
          </Label>
          <Input
            id="ga-client-secret"
            type="password"
            autoComplete="off"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={
              appConfigurada ? "•••••••••• (escribe para reemplazar)" : "Pega el secret aquí"
            }
            disabled={ocupadoApp}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={() => guardarApp.mutate()}
            disabled={ocupadoApp || !puedeGuardarApp}
          >
            {guardarApp.isPending ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {guardarApp.isPending ? "Guardando…" : appConfigurada ? "Reemplazar" : "Guardar"}
          </Button>

          {appConfigurada && (
            <>
              {conectado ? (
                <Badge variant="ok">Conectado con Google</Badge>
              ) : (
                <Badge variant="secondary">Sin conectar</Badge>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={conectar}
                disabled={ocupadoApp || conectando}
              >
                {conectando ? <Spinner className="h-4 w-4" /> : <Plug className="h-4 w-4" />}
                {conectando ? "Abriendo…" : conectado ? "Reconectar" : "Conectar con Google"}
              </Button>
              {conectado && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void pedirDesconectar()}
                  disabled={ocupadoApp}
                >
                  <Trash2 className="h-4 w-4" /> Desconectar
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Mapeo por marca: una propiedad GA4 por marca. */}
      {isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full rounded-lg" />
          ))}
        </div>
      ) : isError ? (
        <BloqueError
          titulo="No se pudo cargar el estado de Google Analytics"
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
            <FilaGoogleAnalytics
              key={marca.marca}
              marca={marca}
              propiedades={propiedades}
              conectado={conectado}
              propiedadesError={propiedadesQuery.isError}
            />
          ))}
        </div>
      )}
    </SeccionColapsable>
  );
}
