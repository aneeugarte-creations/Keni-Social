import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { toast } from "sonner";

import { PuertaSesion } from "@/components/auth/PuertaSesion";
import { BurbujaRalph } from "@/components/ralph";
import { ContenedorConfirmacion } from "@/components/comunes/ContenedorConfirmacion";
import { FronteraError } from "@/components/comunes/FronteraError";
import { Toaster } from "@/components/ui/sonner";
import { FiltrosPublicacionProvider } from "@/hooks/use-filtros-contenido";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import { marcarSesionExpirada, SesionProvider } from "@/hooks/use-sesion";
import { TemaProvider } from "@/hooks/use-tema";
import { ApiError } from "@/lib/api";
import { registrarExitoRed, registrarFalloRed } from "@/lib/estado-red";
import { router } from "@/router";

import "./index.css";

/**
 * Manejador GLOBAL de sesión expirada (#): cualquier query/mutación que falle con un 401
 * (la cookie de sesión venció a mitad de uso) limpia la sesión y devuelve la app al login,
 * en vez de dejar cada página lanzando `ApiError(401)` sin salida. El `me`/`login` del
 * provider NO pasan por react-query, así que no hay bucle de redirección. Deduplicamos el
 * toast: muchas queries pueden fallar a la vez (todas las de la página), pero una sola
 * expiración debe avisar una sola vez.
 */
let avisoSesionExpiradaEnVuelo = false;
function manejarErrorGlobal(error: unknown): void {
  // Conexión degradada DURANTE el uso: un fallo de red (sin respuesta = status 0) o un
  // 502/503/504 del proxy (back desplegando/caído) alimenta el detector que monta el banner
  // sticky del AppShell. Un 401 (sesión expirada) NO es esto: se trata abajo, va al login.
  if (error instanceof ApiError && (error.status === 0 || error.status >= 502)) {
    registrarFalloRed();
  }
  if (!(error instanceof ApiError) || error.status !== 401) return;
  if (avisoSesionExpiradaEnVuelo) return;
  avisoSesionExpiradaEnVuelo = true;
  toast.error("Tu sesión expiró, vuelve a entrar.");
  marcarSesionExpirada();
  // Permite avisar de nuevo en la siguiente expiración (tras un nuevo login).
  setTimeout(() => {
    avisoSesionExpiradaEnVuelo = false;
  }, 5_000);
}

// Cliente de React Query. No reintentamos errores 4xx (un 404/400 no mejora al
// reintentar); el resto reintenta una vez. Datos frescos por 30s.
const queryClient = new QueryClient({
  // `onSuccess`: el primer fetch que vuelve a responder limpia el banner de conexión degradada.
  queryCache: new QueryCache({ onError: manejarErrorGlobal, onSuccess: () => registrarExitoRed() }),
  mutationCache: new MutationCache({ onError: manejarErrorGlobal }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (fallos, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return fallos < 1;
      },
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <TemaProvider>
      <QueryClientProvider client={queryClient}>
        <FronteraError>
          <SesionProvider>
            <PuertaSesion>
              <MarcaActivaProvider>
                <FiltrosPublicacionProvider>
                  <RouterProvider router={router} />
                </FiltrosPublicacionProvider>
              </MarcaActivaProvider>
              <BurbujaRalph />
            </PuertaSesion>
          </SesionProvider>
        </FronteraError>
        <Toaster />
        <ContenedorConfirmacion />
      </QueryClientProvider>
    </TemaProvider>
  </React.StrictMode>,
);
