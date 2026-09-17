/**
 * Vista previa (solo localhost) de la PÁGINA PÚBLICA `/c/:token`: lo que ve quien abre el
 * enlace del PDF. Solo lectura, sin sidebar ni login, acotada a UNA campaña. Datos de
 * ejemplo (ver `_mock.ts`). Directorio desechable: borrar antes de promover.
 */
import { Lock } from "lucide-react";
import * as React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { PanelCampania } from "@/pages/campanias/PanelCampania";

import { MOCK, queryClient } from "./_mock";
import "../index.css";

function InformePublico() {
  const c = MOCK.campania;
  return (
    <div className="h-full overflow-y-auto bg-background">
      {/* Barra pública: marca + aviso de solo lectura. Sin navegación de la consola. */}
      <header className="sticky top-0 z-10 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1040px] items-center justify-between px-6 py-3">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold tracking-[0.3em] text-neutral-900 dark:text-neutral-100">
              KENI
            </span>
            <span className="text-sm text-muted-foreground">· Informe de campaña</span>
          </div>
          <Badge variant="secondary" className="gap-1.5">
            <Lock className="h-3 w-3" />
            Solo lectura
          </Badge>
        </div>
      </header>

      <main className="mx-auto max-w-[1040px] px-6 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-semibold tracking-tight">{c.nombre}</h1>
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
            Periodo: {MOCK.periodo.desde} – {MOCK.periodo.hasta} · Fuente: Metricool
          </p>
        </div>

        <PanelCampania campaniaId="preview" rango="mes" ocultarAds />

        <footer className="mt-12 border-t border-border py-6 text-center text-xs text-muted-foreground">
          Vista compartida por el equipo de Claro Sports · KENI · Solo lectura
        </footer>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <InformePublico />
    </QueryClientProvider>
  </React.StrictMode>,
);
