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
const RevisionEditorial = lazy(() => import("@/pages/RevisionEditorial"));
const Skills = lazy(() => import("@/pages/Skills"));
const Publicaciones = lazy(() => import("@/pages/Publicaciones"));
const Fuentes = lazy(() => import("@/pages/Fuentes"));
const Metricas = lazy(() => import("@/pages/Metricas"));
const Termometro = lazy(() => import("@/pages/Termometro"));
const Radar = lazy(() => import("@/pages/Radar"));
const Comercial = lazy(() => import("@/pages/Comercial"));
const ReporteDeportes = lazy(() => import("@/pages/ReporteDeportes"));
const Agentes = lazy(() => import("@/pages/Agentes"));
const DetalleAgente = lazy(() => import("@/pages/agentes/Detalle"));
const Monitor = lazy(() => import("@/pages/Monitor"));
const Tareas = lazy(() => import("@/pages/Tareas"));
const Rota = lazy(() => import("@/pages/Rota"));
const Configuracion = lazy(() => import("@/pages/Configuracion"));
const Sugerencias = lazy(() => import("@/pages/Sugerencias"));
const Usuarios = lazy(() => import("@/pages/Usuarios"));

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
      { path: "revision-editorial", element: <RevisionEditorial /> },
      { path: "skills", element: <Skills /> },
      { path: "publicaciones", element: <Publicaciones /> },
      { path: "fuentes", element: <Fuentes /> },
      { path: "termometro", element: <Termometro /> },
      { path: "radar", element: <Radar /> },
      { path: "metricas", element: <Metricas /> },
      { path: "comercial", element: <Comercial /> },
      { path: "reporte-deportes", element: <ReporteDeportes /> },
      { path: "agentes", element: <Agentes /> },
      { path: "agentes/:id", element: <DetalleAgente /> },
      { path: "tareas", element: <Tareas /> },
      { path: "rota", element: <Rota /> },
      { path: "monitor", element: <Monitor /> },
      // Ajustes
      { path: "configuracion", element: <Configuracion /> },
      { path: "sugerencias", element: <Sugerencias /> },
      // Gestión de usuarios (solo admin; el backend devuelve 403 si no, y la
      // propia página muestra el aviso de permiso al entrar por URL directa).
      { path: "usuarios", element: <Usuarios /> },
      // Redirecciones de páginas fusionadas/retiradas (issues #87, #88):
      // Conexiones se fusionó en Configuración; Estado pasó a la topbar.
      { path: "conexiones", element: <Navigate to="/configuracion" replace /> },
      { path: "estado", element: <Navigate to="/configuracion" replace /> },
      // Proyectos y Nueva carpeta se unificaron en Agentes (#85). Tareas vuelve a
      // tener su propia vista de pendientes (#104), por encima.
      { path: "proyectos", element: <Navigate to="/agentes" replace /> },
      { path: "carpetas", element: <Navigate to="/agentes" replace /> },
      // Cualquier otra ruta: de vuelta al inicio.
      { path: "*", element: <Navigate to="/generar-copy" replace /> },
    ],
  },
]);
