import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { FronteraError } from "@/components/comunes/FronteraError";
import { RedirigirPrefijo } from "@/components/comunes/RedirigirPrefijo";
import { Loader2 } from "lucide-react";

// Carga diferida por ruta (code-splitting): cada pagina viaja en su propio chunk
// y solo se descarga al entrar. Asi el arranque no carga, por ejemplo, las graficas
// de Metricas (Tremor/recharts, el grueso del bundle) hasta que se visitan. El
// <Suspense> que muestra el fallback mientras carga vive en el AppShell.
const Panel = lazy(() => import("@/pages/Panel"));
const Estudio = lazy(() => import("@/pages/Estudio"));
const Biblioteca = lazy(() => import("@/pages/Biblioteca"));

// Sub-paginas de cada hub. Los hubs no tienen componente wrapper propio: la
// ruta-padre se deja sin `element` y react-router renderiza `<Outlet/>` por defecto;
// la subnav entre sub-rutas vive in-page (SubnavHub, via HUB_TABS).
const Fuentes = lazy(() => import("@/pages/Fuentes"));
const Termometro = lazy(() => import("@/pages/Termometro"));
const Radar = lazy(() => import("@/pages/Radar"));
const Algoritmos = lazy(() => import("@/pages/Algoritmos"));

const RevisionEditorial = lazy(() => import("@/pages/RevisionEditorial"));
const Verificacion = lazy(() => import("@/pages/Verificacion"));

const Metricas = lazy(() => import("@/pages/Metricas"));
const Comercial = lazy(() => import("@/pages/Comercial"));
const ReporteDeportes = lazy(() => import("@/pages/ReporteDeportes"));

const Tareas = lazy(() => import("@/pages/Tareas"));
const Rota = lazy(() => import("@/pages/Rota"));
// Feed de ideación (Flujo D, Fase 4): la "red social interna" dentro del AppShell.
const FeedIdeacion = lazy(() => import("@/pages/feed/FeedIdeacion"));

const PlantillasContenido = lazy(() => import("@/pages/activos/PlantillasContenido"));

const Actividad = lazy(() => import("@/pages/Actividad"));
const Pipelines = lazy(() => import("@/pages/Pipelines"));

// Feed móvil para revisores (#qa-movil-feed): superficie tipo red social, una
// columna, SIN sidebar. Vive FUERA del AppShell (layout propio) y se llega por
// enlace directo (no se registra en el catálogo de apps).
const MobileFeed = lazy(() => import("@/pages/MobileFeed"));

// Ajustes (ahora solo accesibles via dropdown del avatar).
const Configuracion = lazy(() => import("@/pages/Configuracion"));
const Sugerencias = lazy(() => import("@/pages/Sugerencias"));
const Webhooks = lazy(() => import("@/pages/Webhooks"));
const MiCuenta = lazy(() => import("@/pages/MiCuenta"));
const Usuarios = lazy(() => import("@/pages/Usuarios"));
const Sistema = lazy(() => import("@/pages/Sistema"));

/**
 * Rutas del SPA. El AppShell es el layout raiz (sidebar + topbar); las paginas
 * cuelgan de el. La navegación se agrupa por MOMENTO DEL FLUJO y ese bloque vive
 * TAMBIÉN en la URL: `/operacion/*` (checkpoints diarios), `/contenido/*`
 * (herramientas de creación) y `/datos/*` (entradas y señales). Panel es la home
 * transversal y se queda en `/panel`. Cada hub (Parrilla, Revisión, Investigación,
 * Analíticas, Biblioteca) es una ruta-layout sin componente: react-router renderiza
 * `<Outlet/>` y la subnav entre sub-rutas vive in-page (SubnavHub, via HUB_TABS).
 *
 * Las rutas planas anteriores (`/estudio`, `/investigacion/...`, `/parrilla/...`, etc.)
 * se mantienen como redirecciones a su nuevo path con prefijo de bloque.
 */
export const router = createBrowserRouter([
  // Feed móvil para revisores: ruta hermana del AppShell (layout propio, sin
  // sidebar). Su propia frontera de error + Suspense, ya que no cuelga del shell.
  {
    path: "/feed",
    element: (
      <FronteraError>
        <Suspense
          fallback={
            <div className="flex min-h-dvh items-center justify-center text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin" aria-label="Cargando" />
            </div>
          }
        >
          <MobileFeed />
        </Suspense>
      </FronteraError>
    ),
  },
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/panel" replace /> },

      // Home transversal (shell): el vistazo del día. Encabeza el bloque Operación
      // en el sidebar pero vive sin prefijo (es la landing, no una página de sección).
      { path: "panel", element: <Panel /> },

      // ===== Bloque OPERACIÓN (checkpoints diarios) =====
      {
        path: "operacion",
        children: [
          { index: true, element: <Navigate to="/operacion/parrilla" replace /> },
          // Hub Parrilla (tablero del equipo): pendientes · feed · turnos.
          {
            path: "parrilla",
            children: [
              { index: true, element: <Navigate to="pendientes" replace /> },
              { path: "pendientes", element: <Tareas /> },
              // Feed de ideación: la pieza vista como post (material → copy IA → arte) con
              // estado de la cadena IA en vivo y aprobación en línea (Flujo D, Fase 4).
              { path: "feed", element: <FeedIdeacion /> },
              { path: "turnos", element: <Rota /> },
            ],
          },
          // Hub Revisión: cola de aprobación (editorial) + verificación de media.
          {
            path: "revision",
            children: [
              { index: true, element: <Navigate to="editorial" replace /> },
              { path: "editorial", element: <RevisionEditorial /> },
              { path: "verificacion", element: <Verificacion /> },
            ],
          },
        ],
      },

      // ===== Bloque CONTENIDO (herramientas para crear/editar a mano) =====
      {
        path: "contenido",
        children: [
          { index: true, element: <Navigate to="/contenido/estudio" replace /> },
          { path: "estudio", element: <Estudio /> },
          // Hub Biblioteca: documentos (prompts + línea editorial) + plantillas de
          // contenido (antes su propia página "Activos", ahora una pestaña más).
          {
            path: "biblioteca",
            children: [
              { index: true, element: <Navigate to="documentos" replace /> },
              { path: "documentos", element: <Biblioteca /> },
              { path: "plantillas", element: <PlantillasContenido /> },
            ],
          },
        ],
      },

      // ===== Bloque DATOS (entradas y señales que alimentan/reflejan la automatización) =====
      {
        path: "datos",
        children: [
          { index: true, element: <Navigate to="/datos/investigacion" replace /> },
          // Hub Investigación: fuentes RSS, termómetro mundial, radar y algoritmos.
          {
            path: "investigacion",
            children: [
              { index: true, element: <Navigate to="fuentes" replace /> },
              { path: "fuentes", element: <Fuentes /> },
              { path: "termometro", element: <Termometro /> },
              { path: "radar", element: <Radar /> },
              { path: "algoritmos", element: <Algoritmos /> },
            ],
          },
          // Hub Analíticas: métricas, comercial y deck deportivo.
          {
            path: "analiticas",
            children: [
              { index: true, element: <Navigate to="metricas" replace /> },
              { path: "metricas", element: <Metricas /> },
              { path: "comercial", element: <Comercial /> },
              { path: "reporte-deportes", element: <ReporteDeportes /> },
            ],
          },
          // Actividad IA: feed unificado de generaciones + runs de agentes con métricas.
          { path: "actividad", element: <Actividad /> },
          // Pipelines: vista CI/CD del pipeline de contenido (etapas por pieza).
          { path: "pipelines", element: <Pipelines /> },
        ],
      },

      // Ajustes (sin entrada en el sidebar; se llega desde el dropdown del avatar).
      { path: "mi-cuenta", element: <MiCuenta /> },
      { path: "configuracion", element: <Configuracion /> },
      { path: "sugerencias", element: <Sugerencias /> },
      // Webhooks salientes: solo admin (el backend devuelve 403 si no; la pagina avisa
      // al entrar por URL directa). Gestionar webhooks = abrir la red de salida.
      { path: "webhooks", element: <Webhooks /> },
      // Gestion de usuarios: solo admin (el backend devuelve 403 si no, y la
      // propia pagina muestra el aviso al entrar por URL directa).
      { path: "usuarios", element: <Usuarios /> },
      // Panel de sistema: solo admin (el backend devuelve 403 si no, y la propia
      // página muestra el aviso al entrar por URL directa).
      { path: "sistema", element: <Sistema /> },

      // ===== Redirecciones de rutas legacy =====
      // Rutas planas anteriores → su nuevo path con prefijo de bloque (preservando
      // la pestaña con `RedirigirPrefijo` donde aplica).
      { path: "imagenes", element: <Navigate to="/contenido/estudio" replace /> },
      { path: "estudio", element: <Navigate to="/contenido/estudio" replace /> },
      { path: "biblioteca/*", element: <RedirigirPrefijo a="/contenido/biblioteca" /> },
      { path: "investigacion/parrilla-dia", element: <Navigate to="/datos/investigacion/radar" replace /> },
      { path: "investigacion/*", element: <RedirigirPrefijo a="/datos/investigacion" /> },
      { path: "revision/*", element: <RedirigirPrefijo a="/operacion/revision" /> },
      { path: "analiticas/*", element: <RedirigirPrefijo a="/datos/analiticas" /> },
      // Parrilla: la pestaña "calendario" se renombró a "turnos"; el resto preserva.
      { path: "parrilla/calendario", element: <Navigate to="/operacion/parrilla/turnos" replace /> },
      { path: "parrilla/piezas", element: <Navigate to="/operacion/parrilla/pendientes" replace /> },
      { path: "parrilla/*", element: <RedirigirPrefijo a="/operacion/parrilla" /> },
      { path: "actividad", element: <Navigate to="/datos/actividad" replace /> },
      // "Activos" se fusionó como pestaña "Plantillas" dentro de la Biblioteca.
      { path: "activos", element: <Navigate to="/contenido/biblioteca/plantillas" replace /> },
      { path: "activos/plantillas", element: <Navigate to="/contenido/biblioteca/plantillas" replace /> },
      // Hojas planas antiguas (pre-hub) y fusiones previas:
      { path: "fuentes", element: <Navigate to="/datos/investigacion/fuentes" replace /> },
      { path: "termometro", element: <Navigate to="/datos/investigacion/termometro" replace /> },
      { path: "radar", element: <Navigate to="/datos/investigacion/radar" replace /> },
      { path: "revision-editorial", element: <Navigate to="/operacion/revision/editorial" replace /> },
      { path: "verificacion", element: <Navigate to="/operacion/revision/verificacion" replace /> },
      { path: "metricas", element: <Navigate to="/datos/analiticas/metricas" replace /> },
      { path: "comercial", element: <Navigate to="/datos/analiticas/comercial" replace /> },
      { path: "reporte-deportes", element: <Navigate to="/datos/analiticas/reporte-deportes" replace /> },
      { path: "tareas", element: <Navigate to="/operacion/parrilla/pendientes" replace /> },
      { path: "rota", element: <Navigate to="/operacion/parrilla/turnos" replace /> },
      // Publicaciones se FUSIONÓ en el tablero (#fase2).
      { path: "publicaciones", element: <Navigate to="/operacion/parrilla/pendientes" replace /> },
      // El hub Agentes se retiró: su Actividad IA vive ahora en /datos/actividad.
      { path: "monitor", element: <Navigate to="/datos/actividad" replace /> },
      { path: "agentes", element: <Navigate to="/datos/actividad" replace /> },
      { path: "agentes/actividad", element: <Navigate to="/datos/actividad" replace /> },
      // El copy se generaba en /generacion (motor de skills, retirado): ahora vive en
      // la Biblioteca; el catálogo de skills (/skills) también pasa a la Biblioteca.
      { path: "generar-copy", element: <Navigate to="/contenido/biblioteca" replace /> },
      { path: "generacion", element: <Navigate to="/contenido/biblioteca" replace /> },
      { path: "skills", element: <Navigate to="/contenido/biblioteca" replace /> },
      { path: "conexiones", element: <Navigate to="/configuracion" replace /> },
      { path: "estado", element: <Navigate to="/configuracion" replace /> },
      { path: "proyectos", element: <Navigate to="/datos/actividad" replace /> },
      { path: "carpetas", element: <Navigate to="/datos/actividad" replace /> },

      // Cualquier otra ruta: de vuelta al Panel (ya no hay launcher).
      { path: "*", element: <Navigate to="/panel" replace /> },
    ],
  },
]);
