import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";

// Carga diferida por ruta (code-splitting): cada pagina viaja en su propio chunk
// y solo se descarga al entrar. Asi el arranque no carga, por ejemplo, las graficas
// de Metricas (Tremor/recharts, el grueso del bundle) hasta que se visitan. El
// <Suspense> que muestra el fallback mientras carga vive en el AppShell.
const GenerarCopy = lazy(() => import("@/pages/GenerarCopy"));
const Metricas = lazy(() => import("@/pages/Metricas"));
const Tareas = lazy(() => import("@/pages/Tareas"));
const Proyectos = lazy(() => import("@/pages/Proyectos"));
const Carpetas = lazy(() => import("@/pages/Carpetas"));
const Estado = lazy(() => import("@/pages/Estado"));
const Configuracion = lazy(() => import("@/pages/Configuracion"));

/**
 * Rutas del SPA. El AppShell es el layout raiz (sidebar + topbar); las 7 paginas
 * cuelgan de el. La landing `/` redirige a `/generar-copy`, que es el uso diario.
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/generar-copy" replace /> },
      // Trabajo
      { path: "generar-copy", element: <GenerarCopy /> },
      { path: "metricas", element: <Metricas /> },
      { path: "tareas", element: <Tareas /> },
      // Ajustes
      { path: "proyectos", element: <Proyectos /> },
      { path: "carpetas", element: <Carpetas /> },
      { path: "estado", element: <Estado /> },
      { path: "configuracion", element: <Configuracion /> },
      // Cualquier otra ruta: de vuelta al inicio.
      { path: "*", element: <Navigate to="/generar-copy" replace /> },
    ],
  },
]);
