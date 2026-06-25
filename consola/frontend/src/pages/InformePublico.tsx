/**
 * Vista PÚBLICA de un informe de campaña (`/c/:token`). Capability-URL de solo lectura: el
 * token resuelve a UNA campaña con su periodo+modo congelados; sin login, sin sidebar y sin
 * acceso a nada más. Reúsa el mismo panel que la app (`PanelCampania`) con los datos ya
 * servidos por el backend. Se marca `noindex` para que el enlace no acabe en buscadores.
 */
import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import * as React from "react";
import { useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { PanelCampania } from "@/pages/campanias/PanelCampania";

/** Inserta `<meta name="robots" content="noindex">` mientras la vista pública está montada. */
function useNoIndex() {
  React.useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex, nofollow";
    document.head.appendChild(meta);
    return () => {
      document.head.removeChild(meta);
    };
  }, []);
}

function Centrado({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh items-center justify-center px-6 text-center text-muted-foreground">
      {children}
    </div>
  );
}

export default function InformePublico() {
  const { token = "" } = useParams();
  useNoIndex();

  const consulta = useQuery({
    queryKey: ["informe-publico", token],
    queryFn: ({ signal }) => api.analiticaPublica(token, signal),
    retry: false,
  });

  if (consulta.isPending) {
    return (
      <Centrado>
        <Spinner className="h-6 w-6" aria-label="Cargando informe" />
      </Centrado>
    );
  }
  if (consulta.isError) {
    return (
      <Centrado>
        <div className="max-w-sm space-y-2">
          <p className="text-base font-medium text-foreground">Este enlace ya no es válido</p>
          <p className="text-sm">
            Puede haber caducado o haber sido revocado. Pide uno nuevo a quien te lo compartió.
          </p>
        </div>
      </Centrado>
    );
  }

  const datos = consulta.data;
  const c = datos.campania;

  return (
    <div className="h-dvh overflow-y-auto bg-background">
      <header className="sticky top-0 z-10 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1040px] items-center justify-between px-6 py-3">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold tracking-[0.3em] text-foreground">KENI</span>
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
            {c.marcas_nombres.length > 0 && c.hashtags.length > 0 && (
              <span className="mx-1 text-muted-foreground">·</span>
            )}
            {c.hashtags.map((h) => (
              <Badge key={h} variant="secondary">
                #{h}
              </Badge>
            ))}
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            Periodo: {datos.periodo.desde} – {datos.periodo.hasta}
          </p>
        </div>

        <PanelCampania datos={datos} ocultarAds={datos.ocultar_ads} />

        <footer className="mt-12 border-t border-border py-6 text-center text-xs text-muted-foreground">
          Informe compartido · KENI · Solo lectura
        </footer>
      </main>
    </div>
  );
}
