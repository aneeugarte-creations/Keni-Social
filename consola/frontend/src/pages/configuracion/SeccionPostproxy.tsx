import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Info, Save, ShieldCheck, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Campo } from "@/components/comunes/Campo";
import { confirmar } from "@/components/comunes/confirmar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

import { CLAVE_POSTPROXY, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

/**
 * Proveedor de PUBLICACIÓN (Postproxy): una sola API key GLOBAL de cuenta. Es
 * infraestructura de admin —como la cuenta de Claude o el token de Metricool—, así
 * que vive en Sistema → Proveedores. La key se pega UNA vez; el equipo nunca la ve.
 *
 * La conexión de las redes de cada marca NO se gestiona aquí, sino en el panel de
 * «Marcas» (un par de clics por red, OAuth nativo dentro de Keni).
 *
 * Regla de oro: el secreto NUNCA vuelve al navegador. Del servidor solo llega el
 * estado (`configurado`) y, como mucho, una pista (`····last4`).
 */
export function SeccionPostproxy() {
  const { usuario } = useSesion();
  if (usuario !== null && usuario.rol !== "admin") return null;
  return <SeccionPostproxyAdmin />;
}

function SeccionPostproxyAdmin() {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = React.useState("");
  const [resultadoPrueba, setResultadoPrueba] = React.useState<{ ok: boolean; mensaje: string } | null>(
    null,
  );
  // El error solo se muestra tras un intento de guardar (no mientras se escribe).
  const [intentado, setIntentado] = React.useState(false);

  const { data } = useQuery({
    queryKey: CLAVE_POSTPROXY,
    queryFn: ({ signal }) => api.conexionesPostproxy(signal),
  });

  const guardar = useMutation({
    mutationFn: () => api.guardarPostproxy({ api_key: apiKey }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "API key de Postproxy guardada.");
      setApiKey(""); // La clave nunca se conserva en cliente.
      setResultadoPrueba(null);
      setIntentado(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_POSTPROXY });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const probar = useMutation({
    mutationFn: () => api.probarPostproxy(),
    onSuccess: (res) => {
      setResultadoPrueba({ ok: res.ok, mensaje: res.mensaje });
      if (res.ok) toast.success(res.mensaje || "Conexión correcta.");
      else toast.error(res.mensaje || "La prueba falló.");
    },
    onError: (e) => {
      setResultadoPrueba({ ok: false, mensaje: mensajeError(e) });
      toast.error(mensajeError(e));
    },
  });

  const quitar = useMutation({
    mutationFn: () => api.eliminarPostproxy(),
    onSuccess: (res) => {
      toast.success(res?.mensaje ?? "Conexión de Postproxy eliminada.");
      setApiKey("");
      setResultadoPrueba(null);
      setIntentado(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_POSTPROXY });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const pedirQuitar = async () => {
    if (
      await confirmar({
        titulo: "Quitar conexión de Postproxy",
        mensaje:
          "Se eliminará la API key global de Postproxy. Las redes ya conectadas dejarán de poder publicar hasta que vuelvas a configurarla. ¿Quieres continuar?",
        destructivo: true,
        textoConfirmar: "Quitar",
      })
    )
      quitar.mutate();
  };

  const configurado = data?.configurado ?? false;
  const ocupado = guardar.isPending || probar.isPending || quitar.isPending;
  const errKey = apiKey.trim() === "" ? "Pega la API key." : null;
  const hayErrores = Boolean(errKey);

  const onGuardar = () => {
    setIntentado(true);
    if (hayErrores) return;
    guardar.mutate();
  };

  return (
    <SeccionColapsable
      titulo="Publicación · Postproxy"
      contentClassName="space-y-4"
      descripcion="API key de cuenta para publicar en redes. Se configura una vez; las redes de cada marca se conectan desde el panel de Marcas."
    >
      <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Una sola API key global. Después, cada red se conecta por OAuth desde{" "}
          <span className="font-medium text-foreground">Marcas</span>, sin salir de Keni.
        </p>
      </div>

      {/* API key GLOBAL (write-only): solo se envía; del servidor llega el estado + una pista. */}
      <div className="space-y-2 rounded-xl border bg-card p-3">
        <Campo
          etiqueta={
            <span className="flex w-full items-center justify-between gap-3">
              API key de Postproxy
              {configurado ? (
                <Badge variant="ok">Configurada</Badge>
              ) : (
                <Badge variant="secondary">Sin configurar</Badge>
              )}
            </span>
          }
          htmlFor="pp-apikey"
          error={intentado ? errKey : null}
        >
          <Input
            id="pp-apikey"
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              configurado
                ? `•••••••••• ${data?.pista ? `(${data.pista})` : ""} — escribe para reemplazar`
                : "Pega la API key aquí"
            }
            disabled={ocupado}
            aria-invalid={(intentado && Boolean(errKey)) || undefined}
          />
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
            {guardar.isPending ? "Guardando…" : configurado ? "Reemplazar" : "Guardar"}
          </Button>
          {configurado && (
            <>
              <Button size="sm" variant="outline" onClick={() => probar.mutate()} disabled={ocupado}>
                {probar.isPending ? (
                  <Spinner className="h-4 w-4" />
                ) : (
                  <ShieldCheck className="h-4 w-4" />
                )}
                {probar.isPending ? "Probando…" : "Probar"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => void pedirQuitar()}
                disabled={ocupado}
              >
                <Trash2 className="h-4 w-4" /> Quitar
              </Button>
            </>
          )}
        </div>
      </div>
    </SeccionColapsable>
  );
}
