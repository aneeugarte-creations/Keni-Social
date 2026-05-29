import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";

// Carga diferida por ruta (code-splitting): cada pagina viaja en su propio chunk
// y solo se descarga al entrar. Asi el arranque no carga, por ejemplo, las graficas
// de Metricas (Tremor/recharts, el grueso del bundle) hasta que se visitan. El
// <Suspense> que muestra el fallback mientras carga vive en el AppShell.
const Launcher = lazy(() => import("@/pages/Launcher"));
const Panel = lazy(() => import("@/pages/Panel"));
const Generacion = lazy(() => import("@/pages/Generacion"));
const Publicaciones = lazy(() => import("@/pages/Publicaciones"));
const Skills = lazy(() => import("@/pages/Skills"));

// Hubs (layouts con tabs internos) y sus subpaginas.
const Investigacion = lazy(() => import("@/pages/Investigacion"));
const Fuentes = lazy(() => import("@/pages/Fuentes"));
const Termometro = lazy(() => import("@/pages/Termometro"));
const Radar = lazy(() => import("@/pages/Radar"));
const ParrillaDia = lazy(() => import("@/pages/ParrillaDia"));

const Revision = lazy(() => import("@/pages/Revision"));
const RevisionEditorial = lazy(() => import("@/pages/RevisionEditorial"));
const Verificacion = lazy(() => import("@/pages/Verificacion"));

const Analiticas = lazy(() => import("@/pages/Analiticas"));
const Metricas = lazy(() => import("@/pages/Metricas"));
const Comercial = lazy(() => import("@/pages/Comercial"));
const ReporteDeportes = lazy(() => import("@/pages/ReporteDeportes"));

const Parrilla = lazy(() => import("@/pages/Parrilla"));
const Tareas = lazy(() => import("@/pages/Tareas"));
const Rota = lazy(() => import("@/pages/Rota"));

const AgentesHub = lazy(() => import("@/pages/AgentesHub"));
const Agentes = lazy(() => import("@/pages/Agentes"));
const Monitor = lazy(() => import("@/pages/Monitor"));
const DetalleAgente = lazy(() => import("@/pages/agentes/Detalle"));

// Ajustes (ahora solo accesibles via dropdown del avatar).
const Configuracion = lazy(() => import("@/pages/Configuracion"));
const Sugerencias = lazy(() => import("@/pages/Sugerencias"));
const MiCuenta = lazy(() => import("@/pages/MiCuenta"));
const Usuarios = lazy(() => import("@/pages/Usuarios"));

/**
 * Rutas del SPA. El AppShell es el layout raiz (sidebar + topbar); las paginas
 * cuelgan de el. Cada "hub" (Investigación, Revisión, Analíticas, Parrilla,
 * Agentes) es a su vez un layout con tabs internos que renderiza sub-rutas.
 *
 * La landing `/` es el LAUNCHER (cajón de apps): tarjetas de las apps activas.
 * Al entrar en una app, el sidebar se reduce a sus secciones (ver Sidebar).
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Launcher /> },

      // Diario
      { path: "panel", element: <Panel /> },
      { path: "generacion", element: <Generacion /> },
      { path: "publicaciones", element: <Publicaciones /> },
      { path: "skills", element: <Skills /> },

      // Hub Investigación
      {
        path: "investigacion",
        element: <Investigacion />,
        children: [
          { index: true, element: <Navigate to="fuentes" replace /> },
          { path: "fuentes", element: <Fuentes /> },
          { path: "termometro", element: <Termometro /> },
          { path: "radar", element: <Radar /> },
          { path: "parrilla-dia", element: <ParrillaDia /> },
        ],
      },

      // Hub Revisión
      {
        path: "revision",
        element: <Revision />,
        children: [
          { index: true, element: <Navigate to="editorial" replace /> },
          { path: "editorial", element: <RevisionEditorial /> },
          { path: "verificacion", element: <Verificacion /> },
        ],
      },

      // Hub Analíticas
      {
        path: "analiticas",
        element: <Analiticas />,
        children: [
          { index: true, element: <Navigate to="metricas" replace /> },
          { path: "metricas", element: <Metricas /> },
          { path: "comercial", element: <Comercial /> },
          { path: "reporte-deportes", element: <ReporteDeportes /> },
        ],
      },

      // Hub Parrilla (antes /tareas + /rota)
      {
        path: "parrilla",
        element: <Parrilla />,
        children: [
          { index: true, element: <Navigate to="pendientes" replace /> },
          { path: "pendientes", element: <Tareas /> },
          { path: "calendario", element: <Rota /> },
        ],
      },

      // Hub Agentes (catalogo + Actividad IA como pestañas). El detalle queda
      // fuera del hub para ocupar toda la pantalla sin la subnav.
      {
        path: "agentes",
        element: <AgentesHub />,
        children: [
          { index: true, element: <Agentes /> },
          { path: "actividad", element: <Monitor /> },
        ],
      },
      { path: "agentes/:id", element: <DetalleAgente /> },

      // Ajustes (sin entrada en el sidebar; se llega desde el dropdown del avatar).
      { path: "mi-cuenta", element: <MiCuenta /> },
      { path: "configuracion", element: <Configuracion /> },
      { path: "sugerencias", element: <Sugerencias /> },
      // Gestion de usuarios: solo admin (el backend devuelve 403 si no, y la
      // propia pagina muestra el aviso al entrar por URL directa).
      { path: "usuarios", element: <Usuarios /> },

      // ===== Redirecciones de rutas legacy =====
      // Fusiones de paginas individuales en hubs:
      { path: "fuentes", element: <Navigate to="/investigacion/fuentes" replace /> },
      { path: "termometro", element: <Navigate to="/investigacion/termometro" replace /> },
      { path: "radar", element: <Navigate to="/investigacion/radar" replace /> },
      { path: "revision-editorial", element: <Navigate to="/revision/editorial" replace /> },
      { path: "verificacion", element: <Navigate to="/revision/verificacion" replace /> },
      { path: "metricas", element: <Navigate to="/analiticas/metricas" replace /> },
      { path: "comercial", element: <Navigate to="/analiticas/comercial" replace /> },
      { path: "reporte-deportes", element: <Navigate to="/analiticas/reporte-deportes" replace /> },
      { path: "tareas", element: <Navigate to="/parrilla/pendientes" replace /> },
      { path: "rota", element: <Navigate to="/parrilla/calendario" replace /> },
      { path: "monitor", element: <Navigate to="/agentes/actividad" replace /> },
      // Fusiones anteriores (mantener compatibilidad):
      { path: "generar-copy", element: <Navigate to="/generacion" replace /> },
      { path: "imagenes", element: <Navigate to="/generacion" replace /> },
      { path: "conexiones", element: <Navigate to="/configuracion" replace /> },
      { path: "estado", element: <Navigate to="/configuracion" replace /> },
      { path: "proyectos", element: <Navigate to="/agentes" replace /> },
      { path: "carpetas", element: <Navigate to="/agentes" replace /> },

      // Cualquier otra ruta: de vuelta al launcher (cajón de apps).
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
