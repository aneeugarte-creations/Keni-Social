import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";

// Carga diferida por ruta (code-splitting): cada pagina viaja en su propio chunk
// y solo se descarga al entrar. Asi el arranque no carga, por ejemplo, las graficas
// de Metricas (Tremor/recharts, el grueso del bundle) hasta que se visitan. El
// <Suspense> que muestra el fallback mientras carga vive en el AppShell.
const GenerarCopy = lazy(() => import("@/pages/GenerarCopy"));
const Imagenes = lazy(() => import("@/pages/Imagenes"));
const Verificacion = lazy(() => import("@/pages/Verificacion"));
const Skills = lazy(() => import("@/pages/Skills"));
const Publicaciones = lazy(() => import("@/pages/Publicaciones"));
const Fuentes = lazy(() => import("@/pages/Fuentes"));
const Metricas = lazy(() => import("@/pages/Metricas"));
const ReporteDeportes = lazy(() => import("@/pages/ReporteDeportes"));
const Agentes = lazy(() => import("@/pages/Agentes"));
const DetalleAgente = lazy(() => import("@/pages/agentes/Detalle"));
const Monitor = lazy(() => import("@/pages/Monitor"));
const Configuracion = lazy(() => import("@/pages/Configuracion"));
const Sugerencias = lazy(() => import("@/pages/Sugerencias"));

/**
 * Rutas del SPA. El AppShell es el layout raiz (sidebar + topbar); las paginas
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
      { path: "imagenes", element: <Imagenes /> },
      { path: "verificacion", element: <Verificacion /> },
      { path: "skills", element: <Skills /> },
      { path: "publicaciones", element: <Publicaciones /> },
      { path: "fuentes", element: <Fuentes /> },
      { path: "metricas", element: <Metricas /> },
      { path: "reporte-deportes", element: <ReporteDeportes /> },
      { path: "agentes", element: <Agentes /> },
      { path: "agentes/:id", element: <DetalleAgente /> },
      { path: "monitor", element: <Monitor /> },
      // Ajustes
      { path: "configuracion", element: <Configuracion /> },
      { path: "sugerencias", element: <Sugerencias /> },
      // Redirecciones de páginas fusionadas/retiradas (issues #87, #88):
      // Conexiones se fusionó en Configuración; Estado pasó a la topbar.
      { path: "conexiones", element: <Navigate to="/configuracion" replace /> },
      { path: "estado", element: <Navigate to="/configuracion" replace /> },
      // Proyectos, Tareas y Nueva carpeta se unificaron en Agentes (#85).
      { path: "proyectos", element: <Navigate to="/agentes" replace /> },
      { path: "tareas", element: <Navigate to="/agentes" replace /> },
      { path: "carpetas", element: <Navigate to="/agentes" replace /> },
      // Cualquier otra ruta: de vuelta al inicio.
      { path: "*", element: <Navigate to="/generar-copy" replace /> },
    ],
  },
]);
