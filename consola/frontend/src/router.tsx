import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { FronteraError } from "@/components/comunes/FronteraError";
import { RedirigirPrefijo } from "@/components/comunes/RedirigirPrefijo";
import Error404 from "@/pages/Error404";
import { Loader2 } from "lucide-react";

// Carga diferida por ruta (code-splitting): cada pagina viaja en su propio chunk
// y solo se descarga al entrar. Asi el arranque no carga, por ejemplo, las graficas
// de Metricas (Tremor/recharts, el grueso del bundle) hasta que se visitan. El
// <Suspense> que muestra el fallback mientras carga vive en el AppShell.
const Imagen = lazy(() => import("@/pages/Imagen"));
const Video = lazy(() => import("@/pages/Video"));
const Texto = lazy(() => import("@/pages/Texto"));
const EstrategiaMarcas = lazy(() =>
  import("@/pages/texto/GestionLineas").then((m) => ({ default: m.GestionLineas })),
);

// Sub-paginas de cada hub. Los hubs no tienen componente wrapper propio: la
// ruta-padre se deja sin `element` y react-router renderiza `<Outlet/>` por defecto;
// la subnav entre sub-rutas vive in-page (SubnavHub, via HUB_TABS).
const Fuentes = lazy(() => import("@/pages/Fuentes"));
// Hub Investigación colapsado a 3 PIEZAS (Noticias · Contenidos · Fuentes).
// NoticiasHub es el índice del hub (compone el pool persistente de cobertura +
// el descubrimiento del Investigador); ContenidosHub es el banco evergreen (EVERGREEN).
const NoticiasHub = lazy(() => import("@/pages/NoticiasHub"));
const ContenidosHub = lazy(() => import("@/pages/ContenidosHub"));
// Los ajustes del motor de noticias viven en el drawer del Monitor (sección «Investigación», Fase 3).
// Las antiguas hojas del hub (Investigador, Cajones, Eventos, Agentes, Cobertura) ya
// viven COMPUESTAS dentro de NoticiasHub (pool + descubrimiento) y de Fuentes
// (buzones/agentes/eventos); sus rutas directas redirigen a su nuevo hogar (abajo).
// Algoritmos: inteligencia de plataforma; ahora pestaña de la Texto.
const Algoritmos = lazy(() => import("@/pages/Algoritmos"));

const Metricas = lazy(() => import("@/pages/Metricas"));
const Comercial = lazy(() => import("@/pages/Comercial"));

const Rota = lazy(() => import("@/pages/rota"));
// Feed de ideación (Flujo D, Fase 4): la "red social interna" dentro del AppShell.
const FeedIdeacion = lazy(() => import("@/pages/feed/FeedIdeacion"));
// Lista de contenido (pestaña "Lista" del hub Feed) y calendario de publicaciones
// (página plana "Programación", `/operacion/programacion`): las dos mitades del antiguo tablero.
const ListaContenido = lazy(() => import("@/pages/feed/ListaContenido"));
const CalendarioContenido = lazy(() => import("@/pages/calendario/CalendarioContenido"));

const Produccion = lazy(() => import("@/pages/Produccion"));
const PipelineDetalle = lazy(() => import("@/pages/PipelineDetalle"));
const GeneracionDetalle = lazy(() => import("@/pages/GeneracionDetalle"));
const Monitor = lazy(() => import("@/pages/Monitor"));

// Feed móvil para revisores (#qa-movil-feed): superficie tipo red social, una
// columna, SIN sidebar. Vive FUERA del AppShell (layout propio) y se llega por
// enlace directo (no se registra en el catálogo de apps).
const MobileFeed = lazy(() => import("@/pages/MobileFeed"));

// Ajustes (ahora solo accesibles via dropdown del avatar).
const Sugerencias = lazy(() => import("@/pages/Sugerencias"));
const Webhooks = lazy(() => import("@/pages/Webhooks"));
const MiCuenta = lazy(() => import("@/pages/MiCuenta"));
const Usuarios = lazy(() => import("@/pages/Usuarios"));
// Sistema (admin): la infraestructura que sostiene la consola (recursos, daemons,
// backups, latencias, S3). Antes pestaña «Salud» del Monitor; página propia de nuevo.
const Sistema = lazy(() => import("@/pages/sistema/Sistema"));

/**
 * Rutas del SPA. El AppShell es el layout raiz (sidebar + topbar); las paginas
 * cuelgan de el. La navegación se agrupa por MOMENTO DEL FLUJO y ese bloque vive
 * TAMBIÉN en la URL: `/operacion/*` (checkpoints diarios), `/contenido/*`
 * (herramientas de creación) y `/datos/*` (entradas y señales). La home es el
 * feed del equipo (`/operacion/feed`). Los hubs que quedan (Feed, Investigación,
 * Analíticas, Texto, Producción) son una ruta-layout sin componente:
 * react-router renderiza `<Outlet/>` y la subnav entre sub-rutas vive in-page
 * (SubnavHub, via HUB_TABS). Programación y Turnos (antes pestañas del hub
 * Calendario) son ya páginas planas; Revisión se retiró por obsoleta.
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
      // Home: el feed del equipo (primer checkpoint del día). Ya no hay Panel.
      { index: true, element: <Navigate to="/operacion/feed" replace /> },
      // Compatibilidad: enlaces/markers antiguos a /panel caen en el feed.
      { path: "panel", element: <Navigate to="/operacion/feed" replace /> },

      // ===== Bloque OPERACIÓN (checkpoints diarios) =====
      {
        path: "operacion",
        children: [
          { index: true, element: <Navigate to="/operacion/feed" replace /> },
          // El tablero de Tareas se integró como pestaña «Cobertura» dentro de Turnos; la ruta
          // vieja redirige allí (compat con enlaces/marcadores).
          { path: "tareas", element: <Navigate to="/operacion/turnos" replace /> },
          // El antiguo hub "Parrilla" se separó en DOS (#cal-feed):
          // Hub Feed: feed de ideación (formato red social) + Lista de contenido.
          {
            path: "feed",
            children: [
              { index: true, element: <Navigate to="feed" replace /> },
              // Feed de ideación: la pieza vista como post (material → copy IA → arte) con
              // estado de la cadena IA en vivo y aprobación en línea (Flujo D, Fase 4).
              { path: "feed", element: <FeedIdeacion /> },
              // Lista de contenido (header de acciones: aportar/crear/gestionar).
              { path: "lista", element: <ListaContenido /> },
            ],
          },
          // El hub "Calendario" se separó en DOS páginas planas del sidebar (sin pestañas):
          // Programación (calendario de publicaciones, por marca activa) y Turnos (rota de
          // cobertura del equipo, por marca activa). Ambas respetan el switch global de marca;
          // "Todas" agrega. Las rutas legacy /operacion/calendario/* redirigen abajo.
          { path: "programacion", element: <CalendarioContenido /> },
          { path: "turnos", element: <Rota /> },
          // Compat: el antiguo hub `/operacion/calendario/*` (Programación/Turnos como pestañas)
          // se separó en las dos páginas planas de arriba. Redirigimos sus sub-rutas.
          {
            path: "calendario",
            children: [
              { index: true, element: <Navigate to="/operacion/programacion" replace /> },
              { path: "calendario", element: <Navigate to="/operacion/programacion" replace /> },
              { path: "turnos", element: <Navigate to="/operacion/turnos" replace /> },
              { path: "*", element: <Navigate to="/operacion/programacion" replace /> },
            ],
          },
          // Compat (#cal-feed): el antiguo hub `/operacion/parrilla/*` se separó en
          // `/operacion/feed/*`, `/operacion/programacion` y `/operacion/turnos`.
          {
            path: "parrilla",
            children: [
              { index: true, element: <Navigate to="/operacion/feed" replace /> },
              { path: "pendientes", element: <Navigate to="/operacion/feed/lista" replace /> },
              { path: "piezas", element: <Navigate to="/operacion/feed/lista" replace /> },
              { path: "feed", element: <Navigate to="/operacion/feed/feed" replace /> },
              { path: "turnos", element: <Navigate to="/operacion/turnos" replace /> },
              { path: "calendario", element: <Navigate to="/operacion/turnos" replace /> },
              { path: "*", element: <Navigate to="/operacion/feed" replace /> },
            ],
          },
          // La página "Revisión" (QA editorial + verificación + Carril Rápido) se retiró por
          // obsoleta: la aprobación vive ahora en línea en el Feed. Sus rutas redirigen al Feed.
          { path: "revision", element: <Navigate to="/operacion/feed" replace /> },
          { path: "revision/*", element: <Navigate to="/operacion/feed" replace /> },
        ],
      },

      // ===== Bloque CONTENIDO (herramientas para crear/editar a mano) =====
      {
        path: "contenido",
        children: [
          { index: true, element: <Navigate to="/contenido/imagen" replace /> },
          // CONTENIDO = TRES páginas planas por tipo: Imagen · Video · Texto. El nombre de la
          // página coincide con su ruta y con su API (`/api/imagen`, `/api/video`, `/api/texto`).
          // Página IMAGEN: editor profesional por capas (Konva); diseña/edita el Documento.
          { path: "imagen", element: <Imagen /> },
          // Página VIDEO: subida + preview (motor de edición próximamente).
          { path: "video", element: <Video /> },
          // Página TEXTO (antes "Texto"): prompts + línea editorial con filtros.
          {
            path: "texto",
            children: [
              { index: true, element: <Navigate to="documentos" replace /> },
              { path: "documentos", element: <Texto /> },
              { path: "estrategia", element: <EstrategiaMarcas /> },
              // Algoritmos: inteligencia de plataforma (alimenta las fichas editoriales).
              { path: "algoritmos", element: <Algoritmos /> },
            ],
          },
          // Compatibilidad: los paths antiguos (estudio/editor/texto) redirigen a los nuevos.
          { path: "estudio", element: <Navigate to="/contenido/imagen" replace /> },
          { path: "editor", element: <Navigate to="/contenido/imagen" replace /> },
          { path: "texto", element: <RedirigirPrefijo a="/contenido/texto" /> },
          { path: "texto/*", element: <RedirigirPrefijo a="/contenido/texto" /> },
        ],
      },

      // ===== Bloque DATOS (entradas y señales que alimentan/reflejan la automatización) =====
      {
        path: "datos",
        children: [
          { index: true, element: <Navigate to="/datos/investigacion" replace /> },
          // Hub Investigación, colapsado a 3 PIEZAS: Noticias (índice), Contenidos y
          // Fuentes. El índice (NoticiasHub) compone el pool persistente de cobertura +
          // el descubrimiento del Investigador. Termómetro, Cajones, Eventos, Agentes,
          // Cobertura e Investigador siguen vivos como rutas (sin pestaña en la subnav)
          // para no romper deep-links durante la transición; se fusionarán y redirigirán
          // en fases posteriores.
          {
            path: "investigacion",
            children: [
              { index: true, element: <NoticiasHub /> },
              { path: "contenidos", element: <ContenidosHub /> },
              { path: "fuentes", element: <Fuentes /> },
              // El armado MANUAL del Termómetro (galería internacional) se retiró: la
              // galería se genera sola (pipeline estructurado). El deep-link cae al hub.
              { path: "termometro", element: <Navigate to="/datos/investigacion" replace /> },
              // Los ajustes del motor ya no son subpágina: viven en el panel lateral de
              // ajustes de Noticias. El deep-link viejo cae al índice del hub.
              { path: "ajustes", element: <Navigate to="/datos/investigacion" replace /> },
              // Las hojas del antiguo hub ya viven dentro de Noticias/Fuentes; sus rutas
              // directas redirigen a su nuevo hogar. Fuentes tiene 2 clases (Externas/
              // Internas), deep-linkadas vía ?tab=. Cobertura/Investigador → Noticias.
              { path: "investigador", element: <Navigate to="/datos/investigacion" replace /> },
              { path: "cobertura", element: <Navigate to="/datos/investigacion" replace /> },
              // Cajones y eventos son fuentes INTERNAS (buzones/Excel del equipo).
              {
                path: "cajones",
                element: <Navigate to="/datos/investigacion/fuentes?tab=internas" replace />,
              },
              {
                path: "eventos",
                element: <Navigate to="/datos/investigacion/fuentes?tab=internas" replace />,
              },
              // Agentes de investigación se retiró (no aportaba): cae en Fuentes.
              {
                path: "agentes",
                element: <Navigate to="/datos/investigacion/fuentes" replace />,
              },
              // Compatibilidad con enlaces previos: "plan", "descubrimiento" y "radar"
              // se fusionaron en el Investigador (ahora dentro de NoticiasHub); "algoritmos"
              // se mudó a la Texto.
              { path: "plan", element: <Navigate to="/datos/investigacion" replace /> },
              { path: "descubrimiento", element: <Navigate to="/datos/investigacion" replace /> },
              { path: "radar", element: <Navigate to="/datos/investigacion" replace /> },
              {
                path: "algoritmos",
                element: <Navigate to="/contenido/texto/algoritmos" replace />,
              },
            ],
          },
          // Hub Analíticas: métricas, comercial y deck deportivo.
          {
            path: "analiticas",
            children: [
              { index: true, element: <Navigate to="metricas" replace /> },
              { path: "metricas", element: <Metricas /> },
              { path: "comercial", element: <Comercial /> },
            ],
          },
          // Hub Producción (antes «Actividad IA» con pestañas Feed/Pipelines, hoy FUSIONADAS):
          // el feed unificado (runs del pipeline + actividad suelta) es el índice; cada run
          // y cada trabajo suelto tienen su página de detalle entrada/salida.
          {
            path: "produccion",
            children: [
              { index: true, element: <Produccion /> },
              { path: "pipelines/:id", element: <PipelineDetalle /> },
              // Detalle de un trabajo SUELTO (generación fuera del pipeline): mismo in/out.
              { path: "actividad/:id", element: <GeneracionDetalle /> },
              // Monitor: cola en vivo (todo el equipo) + pestaña Salud (infra, admin).
              { path: "monitor", element: <Monitor /> },
            ],
          },
          // Compat: el hub se llamaba «Actividad IA» (/datos/actividad, con Pipelines como
          // pestaña/vista). Redirige preservando el resto del path (p. ej. pipelines/:id,
          // monitor) y la query (?tab=...).
          { path: "actividad/pipelines", element: <Navigate to="/datos/produccion" replace /> },
          { path: "actividad/*", element: <RedirigirPrefijo a="/datos/produccion" /> },
          { path: "actividad", element: <Navigate to="/datos/produccion" replace /> },
          // Compat: la antigua ruta plana /datos/pipelines.
          { path: "pipelines", element: <Navigate to="/datos/produccion" replace /> },
        ],
      },

      // Ajustes (sin entrada en el sidebar; se llega desde el dropdown del avatar).
      { path: "mi-cuenta", element: <MiCuenta /> },
      // La página Configuración se DISTRIBUYÓ y la Fase 3 CONSOLIDÓ la máquina: máquina,
      // investigación/motor de noticias, conexiones (Metricool + imagen IA), sistema y
      // esfuerzo viven en el drawer Monitor·Ajustes; publicación → Programación;
      // apariencia → Mi cuenta. La ruta vieja redirige al Monitor·Ajustes.
      { path: "configuracion", element: <Navigate to="/datos/produccion/monitor?tab=ajustes" replace /> },
      { path: "sugerencias", element: <Sugerencias /> },
      // Webhooks salientes: solo admin (el backend devuelve 403 si no; la pagina avisa
      // al entrar por URL directa). Gestionar webhooks = abrir la red de salida.
      { path: "webhooks", element: <Webhooks /> },
      // Gestion de usuarios: solo admin (el backend devuelve 403 si no, y la
      // propia pagina muestra el aviso al entrar por URL directa).
      { path: "usuarios", element: <Usuarios /> },
      // Sistema: solo admin (el backend devuelve 403 si no; la página avisa al entrar por
      // URL directa). Estuvo consolidada como pestaña «Salud» del Monitor; el Monitor
      // redirige aquí los deep-links viejos (?tab=salud).
      { path: "sistema", element: <Sistema /> },

      // ===== Redirecciones de rutas legacy =====
      // Rutas planas anteriores → su nuevo path con prefijo de bloque (preservando
      // la pestaña con `RedirigirPrefijo` donde aplica).
      { path: "imagenes", element: <Navigate to="/contenido/imagen" replace /> },
      { path: "estudio", element: <Navigate to="/contenido/imagen" replace /> },
      { path: "texto/*", element: <RedirigirPrefijo a="/contenido/texto" /> },
      { path: "investigacion/parrilla-dia", element: <Navigate to="/datos/investigacion" replace /> },
      { path: "investigacion/*", element: <RedirigirPrefijo a="/datos/investigacion" /> },
      // La página "Revisión" se retiró (obsoleta): sus rutas planas legacy caen en el Feed.
      { path: "revision/*", element: <Navigate to="/operacion/feed" replace /> },
      { path: "analiticas/*", element: <RedirigirPrefijo a="/datos/analiticas" /> },
      // El hub "Parrilla" se separó en "Feed" y "Calendario"; "Calendario" a su vez en
      // "Programación" y "Turnos" (páginas planas). Sus rutas antiguas redirigen a la nueva.
      { path: "parrilla/calendario", element: <Navigate to="/operacion/turnos" replace /> },
      { path: "parrilla/turnos", element: <Navigate to="/operacion/turnos" replace /> },
      { path: "parrilla/feed", element: <Navigate to="/operacion/feed/feed" replace /> },
      { path: "parrilla/pendientes", element: <Navigate to="/operacion/feed/lista" replace /> },
      { path: "parrilla/piezas", element: <Navigate to="/operacion/feed/lista" replace /> },
      { path: "parrilla/*", element: <Navigate to="/operacion/feed" replace /> },
      { path: "actividad", element: <Navigate to="/datos/produccion" replace /> },
      // "Activos"/"Plantillas" quedaron obsoletas; sus rutas redirigen a la Texto.
      { path: "activos", element: <Navigate to="/contenido/texto/documentos" replace /> },
      { path: "activos/plantillas", element: <Navigate to="/contenido/texto/documentos" replace /> },
      // Hojas planas antiguas (pre-hub) y fusiones previas:
      { path: "fuentes", element: <Navigate to="/datos/investigacion/fuentes" replace /> },
      { path: "termometro", element: <Navigate to="/datos/investigacion" replace /> },
      { path: "radar", element: <Navigate to="/datos/investigacion" replace /> },
      // "Revisión" se retiró (obsoleta); estas hojas planas legacy caen en el Feed.
      { path: "revision-editorial", element: <Navigate to="/operacion/feed" replace /> },
      { path: "verificacion", element: <Navigate to="/operacion/feed" replace /> },
      { path: "metricas", element: <Navigate to="/datos/analiticas/metricas" replace /> },
      { path: "comercial", element: <Navigate to="/datos/analiticas/comercial" replace /> },
      { path: "tareas", element: <Navigate to="/operacion/turnos" replace /> },
      { path: "rota", element: <Navigate to="/operacion/turnos" replace /> },
      // Publicaciones se FUSIONÓ en el contenido (#fase2); ahora vive en la Lista del Feed.
      { path: "publicaciones", element: <Navigate to="/operacion/feed/lista" replace /> },
      // El hub Agentes se retiró: su actividad vive ahora en Producción (/datos/produccion).
      { path: "monitor", element: <Navigate to="/datos/produccion/monitor" replace /> },
      { path: "agentes", element: <Navigate to="/datos/produccion" replace /> },
      { path: "agentes/actividad", element: <Navigate to="/datos/produccion" replace /> },
      // El copy se generaba en /generacion (motor antiguo, retirado): ahora vive en
      // la Texto; el catálogo de prompts también vive en la Texto.
      { path: "generar-copy", element: <Navigate to="/contenido/texto" replace /> },
      { path: "generacion", element: <Navigate to="/contenido/texto" replace /> },
      { path: "conexiones", element: <Navigate to="/configuracion" replace /> },
      { path: "estado", element: <Navigate to="/configuracion" replace /> },
      { path: "proyectos", element: <Navigate to="/datos/produccion" replace /> },
      { path: "carpetas", element: <Navigate to="/datos/produccion" replace /> },

      // Cualquier otra ruta (URL desconocida, no cubierta por las redirecciones
      // legacy de arriba): página 404 dedicada en vez de rebotar en silencio al
      // feed, para dejar claro que la dirección no existe.
      { path: "*", element: <Error404 /> },
    ],
  },
]);
