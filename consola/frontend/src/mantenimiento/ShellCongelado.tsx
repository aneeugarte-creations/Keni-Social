import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Bell, Building2 } from "lucide-react";
import { MemoryRouter } from "react-router-dom";

import { PanelActualizando } from "@/components/comunes/PanelActualizando";
import { Sidebar } from "@/components/layout/Sidebar";
import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { UsuarioSesion } from "@/types";

import { CATALOGO } from "./catalogo";

/**
 * Cascarón de la Consola CONGELADO para la página de mantenimiento. Reutiliza los componentes
 * REALES del shell (el `Sidebar` data-driven, las primitivas `Card`/iconos, `index.css` con los
 * tokens del sistema de diseño) para que sea PÍXEL-IDÉNTICO a la app, no una réplica. El back no
 * está, así que en vez de los providers de red (`SesionProvider`/`MarcaActivaProvider`, que piden
 * `/api/auth/me` y `/api/catalogo`) inyectamos sus CONTEXTOS con datos estáticos y sembramos la
 * caché de react-query con el snapshot del catálogo: el árbol se pinta sin tocar la red.
 */

const noop = () => {};
const noopAsync = async () => {};

const USUARIO: UsuarioSesion = {
  id: "frozen",
  usuario: "equipo",
  nombre: "Equipo Keni",
  rol: "admin",
  debe_cambiar_password: false,
};

const SESION: ValorSesion = {
  usuario: USUARIO,
  cargando: false,
  errorConexion: false,
  iniciarSesion: async () => ({ mfaRequerido: false }),
  verificarConPasskey: noopAsync,
  entrarConPasskey: noopAsync,
  cerrarSesion: noopAsync,
  refrescar: noopAsync,
};

// Vista de admin sobre "Todas" las marcas: el gating del Sidebar muestra entonces TODA la nav.
const MARCA: ValorMarcaActiva = {
  marcaActiva: null,
  marcaPrimaria: null,
  enMarcaPrimaria: true,
  esMultiMarca: false,
  puedeTodas: true,
  marcaActivaEsNoticias: true,
  etiquetaInvestigacion: "Noticias",
  marcasParaSwitch: [],
  nombreActiva: null,
  cambiarMarca: noop,
  volverAPrimaria: noop,
};

// Caché sembrada con el snapshot del catálogo: la `useQuery(["catalogo"])` del Sidebar lo
// encuentra (staleTime Infinity en el propio Sidebar) y NO refetcha -> cero red.
const queryClient = new QueryClient();
queryClient.setQueryData(["catalogo"], CATALOGO);

export function ShellCongelado() {
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/operacion/feed"]}>
        <SesionContexto.Provider value={SESION}>
          <MarcaActivaContexto.Provider value={MARCA}>
            <div className="flex h-dvh w-full overflow-hidden bg-background">
              {/* Sidebar REAL (oculto bajo md, como el AppShell). Congelado: sin interacción. */}
              <aside className="hidden md:block" aria-hidden="true">
                <div className="pointer-events-none h-full">
                  <Sidebar />
                </div>
              </aside>

              <div className="flex min-w-0 flex-1 flex-col">
                {/* Topbar: mismas clases que el header del AppShell. Congelado. */}
                <header
                  aria-hidden="true"
                  className="relative z-30 flex h-12 shrink-0 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:px-6"
                >
                  <div className="flex h-full min-w-0 flex-1 items-center">
                    <span className="text-sm font-medium text-foreground">Feed</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {/* Chip de marca (rama de marca única sin filtros de ControlContexto). */}
                    <span className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2.5 text-sm font-medium text-foreground">
                      <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                      <span className="max-w-[140px] truncate">UnoTV</span>
                    </span>
                    {/* Campana (estilo del botón ghost icon de la barra). */}
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground">
                      <Bell className="h-4 w-4" aria-hidden="true" />
                    </span>
                  </div>
                </header>

                {/* Lienzo con la tarjeta viva (mensaje), sobre la app atenuada. La tarjeta y su
                    barra son el componente compartido `PanelActualizando` (el mismo de la puerta de
                    sesión y el velo in-app del back). Aquí sondea `/version.json`: mientras el front
                    está caído lo sirve este contenedor (503, no-ok); cuando vuelve, responde 200 ->
                    barra al 100% y recarga (el SPA ya se sirve). */}
                <main className="relative min-w-0 flex-1 overflow-hidden">
                  <div className="absolute inset-0 bg-background/40 backdrop-blur-[1px]" aria-hidden="true" />
                  <div className="relative grid h-full place-items-center p-6">
                    <PanelActualizando
                      sondearListo={async () =>
                        (await fetch("/version.json", { cache: "no-store" })).ok
                      }
                      onListo={() => window.location.reload()}
                    />
                  </div>
                </main>
              </div>
            </div>
          </MarcaActivaContexto.Provider>
        </SesionContexto.Provider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}
