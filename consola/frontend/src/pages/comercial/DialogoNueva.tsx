/**
 * Diálogo para empezar a monitorear una publicación comercial por su enlace.
 *
 * Pega el link, opcionalmente cliente/campaña/marca/red y un objetivo; al guardar,
 * el backend siembra el histórico y arranca el seguimiento. Es el "pongo el link y
 * que la monitoree" del flujo comercial.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import { NINGUNA, ningunaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import type { CuerpoCrearComercial, MetricaComercial, OpcionesComercial } from "@/types";

import { CLAVE_COMERCIAL } from "./claves";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

function hoyIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function DialogoNueva({
  abierto,
  opciones,
  onCerrar,
}: {
  abierto: boolean;
  opciones: OpcionesComercial;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [url, setUrl] = React.useState("");
  const [titulo, setTitulo] = React.useState("");
  const [cliente, setCliente] = React.useState("");
  const [campania, setCampania] = React.useState("");
  const [marca, setMarca] = React.useState(NINGUNA);
  const [red, setRed] = React.useState(NINGUNA);
  const [publicado, setPublicado] = React.useState(hoyIso());
  const [metrica, setMetrica] = React.useState<MetricaComercial>("interacciones");
  const [objetivo, setObjetivo] = React.useState("");
  const [notas, setNotas] = React.useState("");

  // Reseteamos el formulario cada vez que se abre.
  React.useEffect(() => {
    if (!abierto) return;
    setUrl("");
    setTitulo("");
    setCliente("");
    setCampania("");
    setMarca(NINGUNA);
    setRed(NINGUNA);
    setPublicado(hoyIso());
    setMetrica("interacciones");
    setObjetivo("");
    setNotas("");
  }, [abierto]);

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearComercial = {
        url: url.trim(),
        titulo: titulo.trim(),
        cliente: cliente.trim(),
        campania: campania.trim(),
        marca: ningunaParam(marca),
        red: ningunaParam(red),
        publicado,
        metrica_objetivo: metrica,
        objetivo: objetivo ? Number(objetivo) : 0,
        notas: notas.trim(),
      };
      return api.crearComercial(cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_COMERCIAL });
      toast.success("Publicación en seguimiento");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const urlValida = /^https?:\/\//i.test(url.trim());
  const puedeGuardar = urlValida && !crear.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Monitorear publicación</DialogTitle>
          <DialogDescription>
            Pega el enlace de la pieza. Le daremos seguimiento a interacciones y alcance, y
            podrás pedir su reporte cuando llegue el KPI.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="nueva-url">Enlace *</Label>
            <Input
              id="nueva-url"
              placeholder="https://www.instagram.com/p/…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            {url && !urlValida && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                El enlace debe empezar por http:// o https://.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="nueva-titulo">Título o referencia</Label>
            <Input
              id="nueva-titulo"
              placeholder="Spot lanzamiento, sorteo…"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="nueva-cliente">Cliente</Label>
              <Input
                id="nueva-cliente"
                placeholder="Anunciante"
                value={cliente}
                onChange={(e) => setCliente(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nueva-campania">Campaña</Label>
              <Input
                id="nueva-campania"
                placeholder="Agrupa una serie de piezas"
                value={campania}
                onChange={(e) => setCampania(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="nueva-marca">Marca</Label>
              <SelectorMarca
                id="nueva-marca"
                className="w-full"
                marcas={opciones.marcas}
                valor={marca}
                onCambio={setMarca}
                incluirTodas={false}
                incluirNinguna
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nueva-red">Red</Label>
              <SelectorRed
                id="nueva-red"
                className="w-full"
                redes={opciones.redes}
                valor={red}
                onCambio={setRed}
                incluirTodas={false}
                incluirNinguna
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="nueva-publicado">Fecha de publicación</Label>
            <Input
              id="nueva-publicado"
              type="date"
              value={publicado}
              onChange={(e) => setPublicado(e.target.value)}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="nueva-metrica">Métrica del objetivo</Label>
              <Select value={metrica} onValueChange={(v) => setMetrica(v as MetricaComercial)}>
                <SelectTrigger id="nueva-metrica">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {opciones.metricas.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nueva-objetivo">Objetivo (KPI)</Label>
              <Input
                id="nueva-objetivo"
                type="number"
                min={0}
                placeholder="Ej. 100000"
                value={objetivo}
                onChange={(e) => setObjetivo(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="nueva-notas">Notas</Label>
            <Textarea
              id="nueva-notas"
              rows={2}
              placeholder="Contexto del reporte, condiciones de la pauta…"
              value={notas}
              onChange={(e) => setNotas(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => crear.mutate()} disabled={!puedeGuardar}>
            {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Empezar seguimiento
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
