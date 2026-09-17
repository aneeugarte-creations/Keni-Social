/**
 * Vista previa (solo localhost) del "documento visual" descargable de una campaña: el panel
 * REAL dentro de un marco tipo página, con el PIE que llevaría el enlace público de acceso.
 * Datos de ejemplo (ver `_mock.ts`). Directorio desechable: borrar antes de promover.
 */
import { Link2, QrCode } from "lucide-react";
import * as React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { PanelCampania } from "@/pages/campanias/PanelCampania";

import { MOCK, URL_PUBLICA, queryClient } from "./_mock";
import "../index.css";

function InformeCampania() {
  const c = MOCK.campania;
  return (
    <div className="h-full overflow-y-auto bg-neutral-100 px-4 py-8">
      <p className="mx-auto mb-4 max-w-[1080px] text-xs text-neutral-500">
        Vista previa del documento de campaña (datos de ejemplo). El export real saldría como
        este "papel": tema claro, sin el cromo de navegación. En PDF se pagina a A4.
      </p>
      <div className="mx-auto max-w-[1080px] rounded-xl border border-neutral-200 bg-background p-10 shadow-sm">
        <header className="mb-8 border-b border-border pb-6">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
            Informe de campaña
          </div>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">{c.nombre}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {c.marcas_nombres.map((n) => (
              <Badge key={n} variant="outline">
                {n}
              </Badge>
            ))}
            <span className="mx-1 text-muted-foreground">·</span>
            {c.hashtags.map((h) => (
              <Badge key={h} variant="secondary">
                #{h}
              </Badge>
            ))}
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            Periodo: {MOCK.periodo.desde} – {MOCK.periodo.hasta} · Últimos 30 días · Fuente:
            Metricool
          </p>
        </header>

        <PanelCampania campaniaId="preview" rango="mes" />

        {/* Pie con el enlace público: así aparecería impreso en el PDF. */}
        <footer className="mt-10 flex items-center justify-between gap-6 rounded-lg border border-border bg-muted/30 p-5">
          <div className="flex items-start gap-3">
            <Link2 className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
            <div className="space-y-1">
              <p className="text-sm font-medium">Ver este informe en línea (solo lectura)</p>
              <p className="break-all font-mono text-sm text-blue-700">{URL_PUBLICA}</p>
              <p className="text-xs text-muted-foreground">
                Acceso exclusivo a «{c.nombre}». No expone ninguna otra campaña ni marca · caduca
                en 90 días.
              </p>
            </div>
          </div>
          <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-md border border-dashed border-border text-muted-foreground">
            <QrCode className="h-10 w-10" />
          </div>
        </footer>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <InformeCampania />
    </QueryClientProvider>
  </React.StrictMode>,
);
