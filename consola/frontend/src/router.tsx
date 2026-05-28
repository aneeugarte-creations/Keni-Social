import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";

// Carga diferida por ruta (code-splitting): cada pagina viaja en su propio chunk
// y solo se descarga al entrar. Asi el arranque no carga, por ejemplo, las graficas
// de Metricas (Tremor/recharts, el grueso del bundle) hasta que se visitan. El
// <Suspense> que muestra el fallback mientras carga vive en el AppShell.
const Panel = lazy(() => import("@/pages/Panel"));
const Generacion = lazy(() => import("@/pages/Generacion"));
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
const MiCuenta = lazy(() => import("@/pages/MiCuenta"));
const Usuarios = lazy(() => import("@/pages/Usuarios"));

/**
 * Rutas del SPA. El AppShell es el layout raiz (sidebar + topbar); las paginas
 * cuelgan de el. La landing `/` redirige a `/generacion`, que es el uso diario.
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/generacion" replace /> },
      // Trabajo
      { path: "panel", element: <Panel /> },
      { path: "generacion", element: <Generacion /> },
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
      // Agentes: la actividad IA (antes /monitor) es ahora la pestaña hermana
      // dentro de la misma sección. El detalle queda en su propia ruta para
      // ocupar toda la pantalla sin la subnav.
      { path: "agentes", element: <Agentes /> },
      { path: "agentes/actividad", element: <Monitor /> },
      { path: "agentes/:id", element: <DetalleAgente /> },
      { path: "tareas", element: <Tareas /> },
      { path: "rota", element: <Rota /> },
      // Ajustes
      { path: "configuracion", element: <Configuracion /> },
      { path: "sugerencias", element: <Sugerencias /> },
      // Configuración de la propia cuenta (cualquier rol): datos + cambio de contraseña.
      { path: "mi-cuenta", element: <MiCuenta /> },
      // Gestión de usuarios (solo admin; el backend devuelve 403 si no, y la
      // propia página muestra el aviso de permiso al entrar por URL directa).
      { path: "usuarios", element: <Usuarios /> },
      // Redirecciones de páginas fusionadas/retiradas:
      // Conexiones se fusionó en Configuración; Estado pasó a la topbar (#87, #88).
      { path: "conexiones", element: <Navigate to="/configuracion" replace /> },
      { path: "estado", element: <Navigate to="/configuracion" replace /> },
      // Proyectos y Nueva carpeta se unificaron en Agentes (#85). Tareas vuelve a
      // tener su propia vista de pendientes (#104), por encima.
      { path: "proyectos", element: <Navigate to="/agentes" replace /> },
      { path: "carpetas", element: <Navigate to="/agentes" replace /> },
      // Generar copy + Imágenes se fusionaron en Generación. Monitor pasó a ser
      // la pestaña "Actividad IA" dentro de Agentes.
      { path: "generar-copy", element: <Navigate to="/generacion" replace /> },
      { path: "imagenes", element: <Navigate to="/generacion" replace /> },
      { path: "monitor", element: <Navigate to="/agentes/actividad" replace /> },
      // Cualquier otra ruta: de vuelta al inicio.
      { path: "*", element: <Navigate to="/generacion" replace /> },
    ],
  },
]);
