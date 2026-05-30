import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { PuertaSesion } from "@/components/auth/PuertaSesion";
import { FronteraError } from "@/components/comunes/FronteraError";
import { Toaster } from "@/components/ui/sonner";
import { SesionProvider } from "@/hooks/use-sesion";
import { TemaProvider } from "@/hooks/use-tema";
import { ApiError } from "@/lib/api";
import { router } from "@/router";

import "./index.css";

// Cliente de React Query. No reintentamos errores 4xx (un 404/400 no mejora al
// reintentar); el resto reintenta una vez. Datos frescos por 30s.
const queryClient = new QueryClient({
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
              <RouterProvider router={router} />
            </PuertaSesion>
          </SesionProvider>
        </FronteraError>
        <Toaster />
      </QueryClientProvider>
    </TemaProvider>
  </React.StrictMode>,
);
