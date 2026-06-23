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
import type { ProveedorStock } from "@/types";

import { CLAVE_FUENTES_STOCK, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

/**
 * Proveedores de FOTOS DE STOCK de pago (Pexels/Pixabay). Son agencias GENÉRICAS: una
 * sola clave GLOBAL por agencia sirve a todas las marcas. La API key es un secreto
 * compartido del despliegue (como el token de Metricool), así que se pega aquí, en
 * Sistema → Proveedores. Las fuentes gratuitas (Wikimedia/NASA/Openverse) no necesitan
 * clave y se habilitan/deshabilitan por marca en la subpágina de la etapa Stock.
 *
 * Regla de oro: la clave NUNCA vuelve al navegador. Del servidor solo llega el estado
 * (`configurado`) y, como mucho, una pista (`····last4`).
 */
export function SeccionFuentesStock() {
  const { usuario } = useSesion();
  if (usuario !== null && usuario.rol !== "admin") return null;
  return <SeccionFuentesStockAdmin />;
}

/** Una fila de clave: input write-only + estado + Guardar / Probar / Quitar para un proveedor. */
function FilaClaveStock({ proveedor }: { proveedor: ProveedorStock }) {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = React.useState("");
  const [resultadoPrueba, setResultadoPrueba] = React.useState<{
    ok: boolean;
    mensaje: string;
  } | null>(null);

  const configurado = proveedor.configurado ?? false;
  const id = `stock-${proveedor.proveedor}`;

  const invalidar = () => queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES_STOCK });

  const guardar = useMutation({
    mutationFn: () => api.guardarClaveStock(proveedor.proveedor, apiKey),
    onSuccess: (res) => {
      toast.success(res.mensaje || `Clave de ${proveedor.nombre} guardada.`);
      setApiKey(""); // La clave nunca se conserva en cliente.
      setResultadoPrueba(null);
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const probar = useMutation({
    mutationFn: () => api.probarClaveStock(proveedor.proveedor),
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
    mutationFn: () => api.eliminarClaveStock(proveedor.proveedor),
    onSuccess: (res) => {
      toast.success(res.mensaje || `Clave de ${proveedor.nombre} borrada.`);
      setApiKey("");
      setResultadoPrueba(null);
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const pedirQuitar = async () => {
    if (
      await confirmar({
        titulo: `Quitar clave de ${proveedor.nombre}`,
        mensaje: `Se eliminará la API key global de ${proveedor.nombre}. Dejará de poder usarse como fuente en todas las marcas hasta que vuelvas a configurarla. ¿Quieres continuar?`,
        destructivo: true,
        textoConfirmar: "Quitar",
      })
    )
      quitar.mutate();
  };

  const ocupado = guardar.isPending || probar.isPending || quitar.isPending;
  const puedeGuardar = apiKey.trim() !== "";

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id} className="text-xs font-medium">
          {proveedor.nombre}
        </Label>
        {configurado ? (
          <Badge variant="ok">Configurada{proveedor.pista ? ` ${proveedor.pista}` : ""}</Badge>
        ) : (
          <Badge variant="secondary">Sin configurar</Badge>
        )}
      </div>
      <Input
        id={id}
        type="password"
        autoComplete="off"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder={configurado ? "•••••••••• (escribe para reemplazar)" : "Pega la API key aquí"}
        disabled={ocupado}
      />

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
            <Button size="sm" variant="outline" onClick={() => void pedirQuitar()} disabled={ocupado}>
              <Trash2 className="h-4 w-4" /> Quitar
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function SeccionFuentesStockAdmin() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_FUENTES_STOCK,
    queryFn: ({ signal }) => api.estadoProveedoresStock(signal),
  });

  const conClave = data?.proveedores.filter((p) => p.requiere_clave) ?? [];

  return (
    <SeccionColapsable
      titulo="Fotos de stock · Claves globales"
      contentClassName="space-y-4"
      descripcion="API keys de Pexels y Pixabay (una por agencia, vale para todas las marcas). Las fuentes gratuitas no necesitan clave."
    >
      <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Pexels y Pixabay son agencias genéricas: su clave es{" "}
          <span className="font-medium text-foreground">global</span> y sirve a todas las marcas.
          Wikimedia, NASA y Openverse son gratuitas, no llevan clave y se habilitan por marca en la
          etapa <span className="font-medium text-foreground">Stock</span> de Contexto.
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
          titulo="No se pudieron cargar las fuentes de stock"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      ) : conClave.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No hay proveedores de pago disponibles.
        </p>
      ) : (
        <div className="space-y-4 rounded-lg border border-border p-3">
          {conClave.map((proveedor) => (
            <FilaClaveStock key={proveedor.proveedor} proveedor={proveedor} />
          ))}
        </div>
      )}
    </SeccionColapsable>
  );
}
