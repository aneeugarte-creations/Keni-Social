import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { rutaPrimaria } from "@/components/layout/apps-scope";
import { iconoDe } from "@/components/layout/navegacion";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AppCatalogo } from "@/types";

/**
 * Tarjeta del cajón de apps: icono, etiqueta y descripción corta. Toda la tarjeta
 * es un enlace a la ruta primaria de la app (su primer item de nav). Estilo
 * shadcn (Card + hover de acento), consistente con el resto de la consola.
 */
function TarjetaApp({
  to,
  icono: Icono,
  etiqueta,
  descripcion,
}: {
  to: string;
  icono: ReturnType<typeof iconoDe>;
  etiqueta: string;
  descripcion: string;
}) {
  return (
    <Link to={to} className="group block focus-visible:outline-none">
      <Card
        className={cn(
          "flex h-full flex-col gap-3 p-5 transition-colors",
          "hover:border-primary/40 hover:bg-accent",
          "group-focus-visible:ring-1 group-focus-visible:ring-ring",
        )}
      >
        <span className="flex h-10 w-10 items-center justify-center rounded-md border border-border bg-muted text-foreground">
          <Icono className="h-5 w-5" aria-hidden="true" />
        </span>
        <span className="block text-base font-semibold tracking-tight text-foreground">
          {etiqueta}
        </span>
        {descripcion && (
          <span className="block text-sm text-muted-foreground">{descripcion}</span>
        )}
      </Card>
    </Link>
  );
}

/** Esqueleto mientras carga el catálogo (mismo grid que las tarjetas). */
function TarjetasCargando() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-36 rounded-lg" />
      ))}
    </>
  );
}

/**
 * Launcher / cajón de apps (pantalla de inicio, `/`). Consume `GET /api/catalogo`
 * y pinta UNA tarjeta por app ACTIVA (data-driven: activar/desactivar una app en
 * el backend la añade/quita aquí sola). Cada tarjeta lleva a la ruta primaria de
 * su app; al entrar, el sidebar se reduce a las secciones de esa app.
 *
 * En esta ruta NO se renderiza el sidebar (lo decide el AppShell): solo el
 * avatar/topbar + las tarjetas. El acceso a Panel ya no vive aquí como tarjeta;
 * Panel es una entrada GLOBAL fija del sidebar (visible al entrar en una app).
 */
export default function Launcher() {
  const catalogoQuery = useQuery({
    queryKey: ["catalogo"],
    queryFn: ({ signal }) => api.catalogo(signal),
    staleTime: Infinity,
  });

  const apps: AppCatalogo[] = catalogoQuery.data?.apps ?? [];

  return (
    <div>
      <PageHeader
        titulo="Tus apps"
        descripcion="Elige con qué quieres trabajar. Al entrar verás solo las secciones de esa app."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {catalogoQuery.isLoading && <TarjetasCargando />}

        {apps.map((app) => (
          <TarjetaApp
            key={app.id}
            to={rutaPrimaria(app)}
            icono={iconoDe(app.icono)}
            etiqueta={app.etiqueta}
            descripcion={app.descripcion}
          />
        ))}
      </div>
    </div>
  );
}
