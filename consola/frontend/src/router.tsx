import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import Carpetas from "@/pages/Carpetas";
import Configuracion from "@/pages/Configuracion";
import Estado from "@/pages/Estado";
import GenerarCopy from "@/pages/GenerarCopy";
import Metricas from "@/pages/Metricas";
import Proyectos from "@/pages/Proyectos";
import Tareas from "@/pages/Tareas";

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
