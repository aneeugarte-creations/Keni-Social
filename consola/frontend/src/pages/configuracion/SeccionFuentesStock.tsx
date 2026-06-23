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
import type { FuenteStock, MarcaFuentesStock } from "@/types";

import { CLAVE_FUENTES_STOCK, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

/**
 * Proveedores de FOTOS DE STOCK por marca. Pexels y Pixabay exigen una API key (un
 * secreto compartido del despliegue, como el token de Metricool), así que se pegan
 * aquí, en Sistema → Proveedores. Las fuentes gratuitas (Wikimedia/NASA/Openverse)
 * no necesitan clave y se habilitan/deshabilitan en la subpágina de la etapa Stock.
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
function FilaClaveStock({ marca, fuente }: { marca: string; fuente: FuenteStock }) {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = React.useState("");
  const [resultadoPrueba, setResultadoPrueba] = React.useState<{
    ok: boolean;
    mensaje: string;
  } | null>(null);

  const configurado = fuente.configurado ?? false;
  const id = `stock-${marca}-${fuente.proveedor}`;

  const invalidar = () => queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES_STOCK });

  const guardar = useMutation({
    mutationFn: () => api.guardarClaveStock(marca, fuente.proveedor, apiKey),
    onSuccess: (res) => {
      toast.success(res.mensaje || `Clave de ${fuente.nombre} guardada.`);
      setApiKey(""); // La clave nunca se conserva en cliente.
      setResultadoPrueba(null);
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const probar = useMutation({
    mutationFn: () => api.probarClaveStock(marca, fuente.proveedor),
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
    mutationFn: () => api.eliminarClaveStock(marca, fuente.proveedor),
    onSuccess: (res) => {
      toast.success(res.mensaje || `Clave de ${fuente.nombre} borrada.`);
      setApiKey("");
      setResultadoPrueba(null);
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const pedirQuitar = async () => {
    if (
      await confirmar({
        titulo: `Quitar clave de ${fuente.nombre}`,
        mensaje: `Se eliminará la API key de ${fuente.nombre} de esta marca. Dejará de poder usarse como fuente hasta que vuelvas a configurarla. ¿Quieres continuar?`,
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
          {fuente.nombre}
        </Label>
        {configurado ? (
          <Badge variant="ok">Configurada{fuente.pista ? ` ${fuente.pista}` : ""}</Badge>
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

/** Tarjeta de UNA marca: sus proveedores de pago (Pexels/Pixabay) con clave write-only. */
function TarjetaMarcaStock({ marca }: { marca: MarcaFuentesStock }) {
  const conClave = marca.fuentes.filter((f) => f.requiere_clave);
  return (
    <div className="space-y-3 rounded-lg border border-border p-3">
      <span className="text-sm font-medium">{marca.etiqueta}</span>
      {conClave.length === 0 ? (
        <p className="text-xs text-muted-foreground">Sin proveedores de pago para esta marca.</p>
      ) : (
        <div className="space-y-4">
          {conClave.map((fuente) => (
            <FilaClaveStock key={fuente.proveedor} marca={marca.marca} fuente={fuente} />
          ))}
        </div>
      )}
    </div>
  );
}

function SeccionFuentesStockAdmin() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_FUENTES_STOCK,
    queryFn: ({ signal }) => api.estadoFuentesStock(signal),
  });

  return (
    <SeccionColapsable
      titulo="Fotos de stock · Claves por marca"
      contentClassName="space-y-4"
      descripcion="API keys de Pexels y Pixabay por marca. Las fuentes gratuitas no necesitan clave."
    >
      <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Solo Pexels y Pixabay llevan clave. Wikimedia, NASA y Openverse son gratuitas y se
          habilitan sin clave en la etapa <span className="font-medium text-foreground">Stock</span>{" "}
          de Contexto.
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
      ) : data.marcas.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No hay marcas disponibles.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {data.marcas.map((marca) => (
            <TarjetaMarcaStock key={marca.marca} marca={marca} />
          ))}
        </div>
      )}
    </SeccionColapsable>
  );
}
