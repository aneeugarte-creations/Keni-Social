import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Info, Save, ShieldCheck, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Agencia } from "@/types";

import { CLAVE_AGENCIAS, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

/**
 * Credenciales de las AGENCIAS de noticias / foto licenciada (AFP, Reuters). A diferencia de
 * los bancos de stock, cada agencia declara SUS PROPIOS campos (client_id + client_secret en
 * AFP, api_key en Reuters…), así que esta sección está dirigida por METADATOS: el backend
 * publica la forma de cada agencia y aquí se pinta genéricamente. Una credencial sirve a la
 * agencia entera (noticias + foto licenciada).
 *
 * Regla de oro: los secretos NUNCA vuelven al navegador. De cada campo `secreto` solo llega
 * `configurado` + una pista (`····last4`); los campos públicos (base_url) sí traen su valor.
 */
export function SeccionAgencias() {
  const { usuario } = useSesion();
  if (usuario !== null && usuario.rol !== "admin") return null;
  return <SeccionAgenciasAdmin />;
}

/** Una agencia: sus campos (write-only los secretos, editable base_url) + Guardar / Probar / Quitar. */
function TarjetaAgencia({ agencia }: { agencia: Agencia }) {
  const queryClient = useQueryClient();
  // Estado de EDICIÓN, separado del de presentación (que viene del prop):
  // - secretos: write-only, arrancan vacíos; un vacío no se manda (no reescribe el guardado).
  // - publicos: base_url y demás, inicializados con su valor efectivo y editables.
  const [secretos, setSecretos] = React.useState<Record<string, string>>({});
  const [publicos, setPublicos] = React.useState<Record<string, string>>(() => {
    const inicial: Record<string, string> = {};
    for (const campo of agencia.campos) if (!campo.secreto) inicial[campo.clave] = campo.valor;
    return inicial;
  });
  const [resultadoPrueba, setResultadoPrueba] = React.useState<{
    ok: boolean;
    mensaje: string;
  } | null>(null);

  const invalidar = () => queryClient.invalidateQueries({ queryKey: CLAVE_AGENCIAS });

  const reunirValores = (): Record<string, string> => {
    const valores: Record<string, string> = {};
    for (const campo of agencia.campos) {
      if (campo.secreto) {
        const valor = secretos[campo.clave] ?? "";
        if (valor.trim() !== "") valores[campo.clave] = valor;
      } else {
        valores[campo.clave] = publicos[campo.clave] ?? campo.valor;
      }
    }
    return valores;
  };

  const guardar = useMutation({
    mutationFn: () => api.guardarAgencia(agencia.agencia, reunirValores()),
    onSuccess: () => {
      toast.success(`Credenciales de ${agencia.nombre} guardadas.`);
      setSecretos({}); // Los secretos nunca se conservan en cliente.
      setResultadoPrueba(null);
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const probar = useMutation({
    mutationFn: () => api.probarAgencia(agencia.agencia),
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
    mutationFn: () => api.eliminarAgencia(agencia.agencia),
    onSuccess: () => {
      toast.success(`Credenciales de ${agencia.nombre} borradas.`);
      setSecretos({});
      setResultadoPrueba(null);
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const pedirQuitar = async () => {
    if (
      await confirmar({
        titulo: `Quitar credenciales de ${agencia.nombre}`,
        mensaje: `Se eliminarán las credenciales de ${agencia.nombre}. Dejará de poder usarse (noticias y foto licenciada) hasta que vuelvas a configurarla, salvo que haya un valor de respaldo en el entorno. ¿Quieres continuar?`,
        destructivo: true,
        textoConfirmar: "Quitar",
      })
    )
      quitar.mutate();
  };

  const ocupado = guardar.isPending || probar.isPending || quitar.isPending;

  return (
    <div className="space-y-4 rounded-xl border bg-card p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium">{agencia.nombre}</p>
        {agencia.configurado ? (
          <Badge variant="ok">Conectada</Badge>
        ) : (
          <Badge variant="secondary">Sin configurar</Badge>
        )}
      </div>

      {!agencia.disponible && agencia.motivo && (
        <p className="text-xs text-muted-foreground">{agencia.motivo}</p>
      )}

      {agencia.campos.map((campo) => {
        const id = `agencia-${agencia.agencia}-${campo.clave}`;
        return (
          <div key={campo.clave} className="space-y-1.5">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor={id} className="text-xs font-medium">
                {campo.etiqueta}
                {campo.opcional && (
                  <span className="ml-1 font-normal text-muted-foreground">(opcional)</span>
                )}
              </Label>
              {campo.secreto &&
                (campo.configurado ? (
                  <Badge variant="ok">Configurada{campo.pista ? ` ${campo.pista}` : ""}</Badge>
                ) : (
                  <Badge variant="secondary">Sin configurar</Badge>
                ))}
            </div>
            {campo.secreto ? (
              <Input
                id={id}
                type="password"
                autoComplete="off"
                value={secretos[campo.clave] ?? ""}
                onChange={(e) =>
                  setSecretos((prev) => ({ ...prev, [campo.clave]: e.target.value }))
                }
                placeholder={
                  campo.configurado
                    ? "•••••••••• (escribe para reemplazar)"
                    : "Pega el valor aquí"
                }
                disabled={ocupado}
              />
            ) : (
              <Input
                id={id}
                type="text"
                autoComplete="off"
                value={publicos[campo.clave] ?? campo.valor}
                onChange={(e) =>
                  setPublicos((prev) => ({ ...prev, [campo.clave]: e.target.value }))
                }
                disabled={ocupado}
              />
            )}
          </div>
        );
      })}

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
        <Button size="sm" onClick={() => guardar.mutate()} disabled={ocupado}>
          {guardar.isPending ? <Spinner className="h-4 w-4" /> : <Save className="h-4 w-4" />}
          {guardar.isPending ? "Guardando…" : "Guardar"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => probar.mutate()} disabled={ocupado}>
          {probar.isPending ? <Spinner className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
          {probar.isPending ? "Probando…" : "Probar"}
        </Button>
        {agencia.configurado && (
          <Button size="sm" variant="outline" onClick={() => void pedirQuitar()} disabled={ocupado}>
            <Trash2 className="h-4 w-4" /> Quitar
          </Button>
        )}
      </div>
    </div>
  );
}

function SeccionAgenciasAdmin() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_AGENCIAS,
    queryFn: ({ signal }) => api.estadoAgencias(signal),
  });

  const agencias = data?.agencias ?? [];

  return (
    <SeccionColapsable
      titulo="Agencias · Credenciales"
      contentClassName="space-y-4"
      descripcion="Credenciales de AFP y Reuters (noticias + foto licenciada). Una por agencia, válida para todas las marcas."
    >
      <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Estas credenciales sirven a la agencia{" "}
          <span className="font-medium text-foreground">entera</span> (noticias y foto licenciada).
          La variable de entorno sigue de respaldo si dejas un secreto sin configurar.
        </p>
      </div>

      {isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-52 w-full rounded-lg" />
          ))}
        </div>
      ) : isError ? (
        <BloqueError
          titulo="No se pudieron cargar las agencias"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      ) : agencias.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No hay agencias disponibles.
        </p>
      ) : (
        <div className="space-y-4">
          {agencias.map((agencia) => (
            <TarjetaAgencia key={agencia.agencia} agencia={agencia} />
          ))}
        </div>
      )}
    </SeccionColapsable>
  );
}
