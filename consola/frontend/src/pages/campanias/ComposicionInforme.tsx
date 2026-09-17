/**
 * Composición del INFORME imprimible de una campaña: la cabecera + el panel real
 * (`PanelCampania`) + el pie con el enlace público y su QR. Es el nodo que se captura para
 * el PDF, así que se renderiza a ancho fijo (A4-friendly) y en claro. El QR se genera con
 * `qrcode` (import dinámico) cuando hay enlace.
 */
import { Link2 } from "lucide-react";
import * as React from "react";

import { PanelCampania } from "@/pages/campanias/PanelCampania";
import type { AnaliticaCampania } from "@/types";

export const ComposicionInforme = React.forwardRef<
  HTMLDivElement,
  { datos: AnaliticaCampania; enlaceUrl: string | null; ocultarAds: boolean }
>(function ComposicionInforme({ datos, enlaceUrl, ocultarAds }, ref) {
  const c = datos.campania;
  const [qr, setQr] = React.useState("");

  React.useEffect(() => {
    if (!enlaceUrl) {
      setQr("");
      return;
    }
    let activo = true;
    void import("qrcode")
      .then(({ default: QRCode }) =>
        QRCode.toDataURL(enlaceUrl, { margin: 0, width: 200, errorCorrectionLevel: "M" }),
      )
      .then((url) => {
        if (activo) setQr(url);
      })
      .catch(() => {
        /* sin QR: el enlace en texto basta */
      });
    return () => {
      activo = false;
    };
  }, [enlaceUrl]);

  return (
    <div ref={ref} className="w-[800px] bg-background p-10 text-foreground">
      <header className="mb-8 border-b border-border pb-6">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Informe de campaña</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">{c.nombre}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-sm">
          {c.marcas_nombres.join(" · ")}
          {c.marcas_nombres.length > 0 && c.hashtags.length > 0 && (
            <span className="text-muted-foreground">·</span>
          )}
          {c.hashtags.map((h) => (
            <span key={h} className="text-muted-foreground">
              #{h}
            </span>
          ))}
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          Periodo: {datos.periodo.desde} – {datos.periodo.hasta} · Fuente: Metricool
        </p>
      </header>

      <PanelCampania datos={datos} ocultarAds={ocultarAds} />

      {enlaceUrl && (
        <footer className="mt-10 flex items-center justify-between gap-6 rounded-lg border border-border bg-muted/30 p-5">
          <div className="flex items-start gap-3">
            <Link2 className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
            <div className="space-y-1">
              <p className="text-sm font-medium">Ver este informe en línea (solo lectura)</p>
              <p className="break-all font-mono text-sm text-blue-700 dark:text-blue-400">
                {enlaceUrl}
              </p>
              <p className="text-xs text-muted-foreground">
                Acceso exclusivo a «{c.nombre}». No expone ninguna otra campaña ni marca · caduca
                en 90 días.
              </p>
            </div>
          </div>
          {qr && (
            <img
              src={qr}
              alt="Código QR del enlace"
              className="h-24 w-24 shrink-0 rounded-md border border-border bg-white p-1"
            />
          )}
        </footer>
      )}
    </div>
  );
});
