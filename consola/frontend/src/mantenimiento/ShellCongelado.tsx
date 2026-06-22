import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Bell, Building2 } from "lucide-react";
import { useEffect, useState } from "react";
import { MemoryRouter } from "react-router-dom";

import { Sidebar } from "@/components/layout/Sidebar";
import { Card } from "@/components/ui/card";
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

// Tiempo medio aproximado que tarda el front en volver a estar sano tras un deploy. La barra se
// arrastra hacia ~94% con esta escala (curva que frena al final, nunca llega a 100% sola): da
// sensación de avance honesta sin prometer un final que no controla. El 100% lo pone SOLO la
// señal real de que el front volvió.
const DURACION_ESTIMADA_MS = 22000;
// Sondeo de disponibilidad real: mientras el front está caído, `/version.json` lo sirve el
// contenedor de mantenimiento (503, no-ok); cuando el front vuelve, Traefik enruta a él y responde
// 200. En cuanto es 200 -> barra al 100% y recarga (el SPA ya está sirviéndose). Backstop: si el
// sondeo fallara siempre, una recarga a los 90s reintenta con una página fresca.
const INTERVALO_SONDEO_MS = 2000;
const BACKSTOP_RECARGA_MS = 90000;

/**
 * Barra de progreso de la actualización. Avance estimado por curva (frena cerca del 94%) +
 * detección REAL de la vuelta del front por sondeo de `/version.json`: al recibir 200, completa
 * y recarga. Sustituye al spinner; va DEBAJO del texto.
 */
function ProgresoActualizacion() {
  const [pct, setPct] = useState(0);
  const [completo, setCompleto] = useState(false);

  // Arranca la animación al siguiente frame: la transición CSS larga lleva la barra de 0 -> 94%.
  useEffect(() => {
    const id = requestAnimationFrame(() => setPct(94));
    return () => cancelAnimationFrame(id);
  }, []);

  // Sondeo de disponibilidad real del front + backstop de recarga.
  useEffect(() => {
    let vivo = true;
    let pendiente: number | undefined;
    const sondear = async () => {
      try {
        const r = await fetch("/version.json", { cache: "no-store" });
        if (vivo && r.ok) {
          setCompleto(true);
          setPct(100);
          window.setTimeout(() => window.location.reload(), 500);
          return;
        }
      } catch {
        // Sin respuesta (front aún cayendo / red): se reintenta abajo.
      }
      if (vivo) pendiente = window.setTimeout(sondear, INTERVALO_SONDEO_MS);
    };
    pendiente = window.setTimeout(sondear, INTERVALO_SONDEO_MS);
    const backstop = window.setTimeout(() => window.location.reload(), BACKSTOP_RECARGA_MS);
    return () => {
      vivo = false;
      window.clearTimeout(pendiente);
      window.clearTimeout(backstop);
    };
  }, []);

  return (
    <div
      className="mt-6 h-1.5 w-full overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-label="Progreso de la actualización"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
    >
      <div
        className="h-full rounded-full bg-foreground ease-out"
        style={{
          width: `${pct}%`,
          // Avance lento por curva; el salto al 100% (señal real) es rápido.
          transition: `width ${completo ? 500 : DURACION_ESTIMADA_MS}ms ${completo ? "ease-out" : "cubic-bezier(0,0.6,0.2,1)"}`,
        }}
      />
    </div>
  );
}

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

                {/* Lienzo con la tarjeta viva (mensaje), sobre la app atenuada. */}
                <main className="relative min-w-0 flex-1 overflow-hidden">
                  <div className="absolute inset-0 bg-background/40 backdrop-blur-[1px]" aria-hidden="true" />
                  <div className="relative grid h-full place-items-center p-6">
                    <Card
                      role="status"
                      aria-live="polite"
                      className="w-full max-w-sm p-8 text-center shadow-[0_1px_2px_rgba(0,0,0,0.04),0_8px_30px_rgba(0,0,0,0.06)]"
                    >
                      <h2 className="mb-6 text-base font-light uppercase tracking-[0.3em] text-foreground">
                        <span className="inline-block [margin-right:-0.3em]">KENI</span>
                      </h2>
                      <h1 className="text-lg font-semibold text-foreground">
                        Estamos actualizando la consola
                      </h1>
                      <ProgresoActualizacion />
                    </Card>
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
