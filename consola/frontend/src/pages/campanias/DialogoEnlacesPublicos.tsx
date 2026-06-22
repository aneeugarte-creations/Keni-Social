/**
 * Diálogo de ENLACES PÚBLICOS de una campaña: crear, copiar y revocar capability-URLs de
 * solo lectura. Cada enlace congela el periodo y el modo (Ads ocultos o no) con los que se
 * comparte, caduca a los 90 días y se puede revocar en cualquier momento (corta el acceso
 * a todos al instante). Quien tenga el enlace ve SOLO esa campaña, sin login.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Link2, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, mensajeError } from "@/lib/api";
import type { Campania, EnlacePublicoCampania } from "@/types";

import { CLAVE_CAMPANIAS } from "./claves";

function urlEnlace(token: string): string {
  return `${window.location.origin}/c/${token}`;
}

function fechaCaducidad(expira: string): string {
  if (!expira) return "no caduca";
  // `expira` es ISO UTC naive (sin zona): se interpreta como UTC para mostrar la fecha local.
  const d = new Date(`${expira}Z`);
  return `caduca el ${d.toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" })}`;
}

function FilaEnlace({
  enlace,
  onRevocar,
  revocando,
}: {
  enlace: EnlacePublicoCampania;
  onRevocar: () => void;
  revocando: boolean;
}) {
  const url = urlEnlace(enlace.token);
  const copiar = () => {
    void navigator.clipboard.writeText(url).then(
      () => toast.success("Enlace copiado"),
      () => toast.error("No se pudo copiar"),
    );
  };
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border p-3">
      <Link2 className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="truncate font-mono text-xs text-foreground" title={url}>
          {url}
        </p>
        <p className="text-xs text-muted-foreground">
          {enlace.ocultar_ads ? "Sin Ads · " : ""}
          {enlace.vigente ? fechaCaducidad(enlace.expira) : enlace.desactivado ? "revocado" : "caducado"}
        </p>
      </div>
      {!enlace.vigente && (
        <Badge variant="secondary" className="shrink-0">
          {enlace.desactivado ? "Revocado" : "Caducado"}
        </Badge>
      )}
      {enlace.vigente && (
        <Button variant="ghost" size="sm" onClick={copiar} className="shrink-0">
          <Copy className="h-3.5 w-3.5" />
          Copiar
        </Button>
      )}
      <Button
        variant="ghost"
        size="sm"
        onClick={onRevocar}
        disabled={revocando || !enlace.vigente}
        className="shrink-0 text-rose-600 dark:text-rose-400"
        aria-label="Revocar enlace"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

export function DialogoEnlacesPublicos({
  abierto,
  campania,
  rango,
  ocultarAds,
  onCerrar,
}: {
  abierto: boolean;
  campania: Campania | null;
  /** Periodo activo: se CONGELA en el enlace que se cree. */
  rango: string;
  /** Modo cliente activo: el enlace nuevo se crea con (o sin) pauta según esto. */
  ocultarAds: boolean;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const campaniaId = campania?.id ?? "";
  const claveLista = [...CLAVE_CAMPANIAS, "enlaces", campaniaId];

  const consulta = useQuery({
    queryKey: claveLista,
    queryFn: ({ signal }) => api.enlacesCampania(campaniaId, signal),
    enabled: abierto && campaniaId !== "",
  });

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: claveLista });

  const crear = useMutation({
    mutationFn: () => api.crearEnlaceCampania(campaniaId, { rango, ocultar_ads: ocultarAds }),
    onSuccess: (r) => {
      invalidar();
      void navigator.clipboard.writeText(urlEnlace(r.enlace.token)).then(
        () => toast.success("Enlace creado y copiado"),
        () => toast.success("Enlace creado"),
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const revocar = useMutation({
    mutationFn: (enlaceId: string) => api.revocarEnlaceCampania(campaniaId, enlaceId),
    onSuccess: () => {
      invalidar();
      toast.success("Enlace revocado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const enlaces = consulta.data?.enlaces ?? [];

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Enlace público de «{campania?.nombre}»</DialogTitle>
          <DialogDescription>
            Cualquiera con el enlace puede VER este informe (solo lectura), sin cuenta y sin
            acceso a nada más. Congela el periodo y el modo actuales; caduca a los 90 días y se
            puede revocar.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <Button onClick={() => crear.mutate()} disabled={crear.isPending || !campaniaId}>
            {crear.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Crear enlace {ocultarAds ? "(sin Ads)" : ""}
          </Button>

          <div className="max-h-[40vh] space-y-2 overflow-y-auto">
            {consulta.isPending ? (
              <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
            ) : enlaces.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Aún no hay enlaces. Crea uno para compartir este informe.
              </p>
            ) : (
              enlaces.map((e) => (
                <FilaEnlace
                  key={e.id}
                  enlace={e}
                  revocando={revocar.isPending}
                  onRevocar={() => revocar.mutate(e.id)}
                />
              ))
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
