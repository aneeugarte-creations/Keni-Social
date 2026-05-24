import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { Toaster } from "@/components/ui/sonner";
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
        <RouterProvider router={router} />
        <Toaster />
      </QueryClientProvider>
    </TemaProvider>
  </React.StrictMode>,
);
