/**
 * Diálogo «Descargar PDF» de una campaña: muestra una PREVISUALIZACIÓN del documento (el
 * panel real + el pie con el enlace público y su QR) y, al pulsar, lo captura a un PDF A4.
 * La previa se renderiza para que la gráfica tenga layout ANTES de capturar (evita que salga
 * en blanco). Asegura un enlace público (idempotente) para imprimirlo en el pie.
 */
import { useQuery } from "@tanstack/react-query";
import { Download, Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { generarPdfInforme } from "@/lib/informe-pdf";
import type { Campania } from "@/types";

import { CLAVE_CAMPANIAS } from "./claves";
import { ComposicionInforme } from "./ComposicionInforme";

function slug(texto: string): string {
  return texto.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "campania";
}

/** Fuerza el tema CLARO mientras el diálogo está abierto: el documento se ve y se descarga
 * en claro (como se aprobó), sin importar el tema del usuario. Restaura al cerrar. */
function useTemaClaroMientrasAbierto(abierto: boolean) {
  React.useEffect(() => {
    if (!abierto) return;
    const root = document.documentElement;
    const eraOscuro = root.classList.contains("dark");
    if (eraOscuro) root.classList.remove("dark");
    return () => {
      if (eraOscuro) root.classList.add("dark");
    };
  }, [abierto]);
}

export function DialogoInformePdf({
  abierto,
  campania,
  rango,
  ocultarAds,
  onCerrar,
}: {
  abierto: boolean;
  campania: Campania | null;
  rango: string;
  ocultarAds: boolean;
  onCerrar: () => void;
}) {
  useTemaClaroMientrasAbierto(abierto);
  const ref = React.useRef<HTMLDivElement>(null);
  const [generando, setGenerando] = React.useState(false);
  const campaniaId = campania?.id ?? "";

  // Analítica: misma queryKey que el panel → sirve de la caché (sin segunda llamada).
  const datosQuery = useQuery({
    queryKey: [...CLAVE_CAMPANIAS, "analitica", campaniaId, rango],
    queryFn: ({ signal }) => api.analiticaCampania(campaniaId, { rango }, signal),
    enabled: abierto && campaniaId !== "",
  });

  // Enlace público a imprimir en el pie: idempotente por (campaña, periodo, modo).
  const enlaceQuery = useQuery({
    queryKey: [...CLAVE_CAMPANIAS, "pdf-enlace", campaniaId, rango, ocultarAds],
    queryFn: () => api.crearEnlaceCampania(campaniaId, { rango, ocultar_ads: ocultarAds }),
    enabled: abierto && campaniaId !== "",
    staleTime: Infinity,
  });

  const enlaceUrl = enlaceQuery.data
    ? `${window.location.origin}/c/${enlaceQuery.data.enlace.token}`
    : null;

  const descargar = async () => {
    if (!ref.current) return;
    setGenerando(true);
    try {
      await generarPdfInforme(ref.current, `campania-${slug(campania?.nombre ?? "")}-${rango}.pdf`);
    } catch {
      toast.error("No se pudo generar el PDF.");
    } finally {
      setGenerando(false);
    }
  };

  const listo = datosQuery.isSuccess;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[92vh] gap-4 sm:max-w-[880px]">
        <DialogHeader>
          <DialogTitle>Descargar PDF de «{campania?.nombre}»</DialogTitle>
          <DialogDescription>
            Documento visual del periodo, idéntico al panel. Incluye al pie un enlace público
            (solo lectura) para ver este mismo informe en línea.
          </DialogDescription>
        </DialogHeader>

        <div className="overflow-auto rounded-lg border border-border bg-neutral-100 p-4 dark:bg-neutral-900">
          {datosQuery.isPending ? (
            <div className="flex h-64 items-center justify-center text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin" aria-label="Cargando" />
            </div>
          ) : datosQuery.isError ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No se pudo cargar la analítica.
            </p>
          ) : (
            <div className="mx-auto w-fit shadow-sm">
              <ComposicionInforme ref={ref} datos={datosQuery.data} enlaceUrl={enlaceUrl} ocultarAds={ocultarAds} />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cerrar
          </Button>
          <Button onClick={() => void descargar()} disabled={!listo || generando}>
            {generando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Descargar PDF
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
