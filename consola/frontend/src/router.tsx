import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { FronteraError } from "@/components/comunes/FronteraError";
import { GuardTurnos } from "@/components/layout/GuardTurnos";
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
  import("@/pages/biblioteca/GestionLineas").then((m) => ({ default: m.GestionLineas })),
);

// Sub-paginas de cada hub. Los hubs no tienen componente wrapper propio: la
// ruta-padre se deja sin `element` y react-router renderiza `<Outlet/>` por defecto;
// la subnav entre sub-rutas vive in-page (SubnavHub, via HUB_TABS).
const Fuentes = lazy(() => import("@/pages/Fuentes"));
const Termometro = lazy(() => import("@/pages/Termometro"));
// Hub Investigación colapsado a 3 PIEZAS (Noticias · Contenidos · Fuentes).
// NoticiasHub es el índice del hub (compone el pool persistente de cobertura +
// el descubrimiento del Investigador); ContenidosHub es el banco evergreen (GREEN).
const NoticiasHub = lazy(() => import("@/pages/NoticiasHub"));
const ContenidosHub = lazy(() => import("@/pages/ContenidosHub"));
// Las antiguas hojas del hub (Investigador, Cajones, Eventos, Agentes, Cobertura) ya
// viven COMPUESTAS dentro de NoticiasHub (pool + descubrimiento) y de Fuentes
// (buzones/agentes/eventos); sus rutas directas redirigen a su nuevo hogar (abajo).
// Algoritmos: inteligencia de plataforma; ahora pestaña de la Biblioteca.
const Algoritmos = lazy(() => import("@/pages/Algoritmos"));

const RevisionEditorial = lazy(() => import("@/pages/RevisionEditorial"));
const Verificacion = lazy(() => import("@/pages/Verificacion"));
// Carril Rápido de Breaking: solo para Claro Sports (y vista "Todas").
const CarrilRapido = lazy(() => import("@/pages/CarrilRapido"));

const Metricas = lazy(() => import("@/pages/Metricas"));
const Comercial = lazy(() => import("@/pages/Comercial"));

const Rota = lazy(() => import("@/pages/Rota"));
// Feed de ideación (Flujo D, Fase 4): la "red social interna" dentro del AppShell.
const FeedIdeacion = lazy(() => import("@/pages/feed/FeedIdeacion"));
// Lista de contenido (pestaña "Lista" del hub Feed) y calendario de publicaciones
// (pestaña "Calendario" del hub Calendario): las dos mitades del antiguo tablero (#cal-feed).
const ListaContenido = lazy(() => import("@/pages/feed/ListaContenido"));
const CalendarioContenido = lazy(() => import("@/pages/calendario/CalendarioContenido"));

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
 * (herramientas de creación) y `/datos/*` (entradas y señales). La home es el
 * feed del equipo (`/operacion/feed`). Cada hub (Feed, Calendario,
 * Revisión, Investigación, Analíticas, Biblioteca) es una ruta-layout sin
 * componente: react-router renderiza `<Outlet/>` y la subnav entre sub-rutas vive
 * in-page (SubnavHub, via HUB_TABS).
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
          // Hub Calendario: Programación (calendario de publicaciones, para TODAS las marcas)
          // + Turnos de cobertura (rota). La 1ª pestaña es Programación, así que el índice del
          // hub aterriza ahí. TURNOS es solo de Claro Sports: su guard redirige a Programación
          // para otra marca (el resto del hub es válido para todas).
          {
            path: "calendario",
            children: [
              { index: true, element: <Navigate to="calendario" replace /> },
              { path: "calendario", element: <CalendarioContenido /> },
              {
                path: "turnos",
                element: (
                  <GuardTurnos>
                    <Rota />
                  </GuardTurnos>
                ),
              },
            ],
          },
          // Compat (#cal-feed): el antiguo hub `/operacion/parrilla/*` se separó en
          // `/operacion/feed/*` y `/operacion/calendario/*`. Redirigimos sus sub-rutas.
          {
            path: "parrilla",
            children: [
              { index: true, element: <Navigate to="/operacion/feed" replace /> },
              { path: "pendientes", element: <Navigate to="/operacion/feed/lista" replace /> },
              { path: "piezas", element: <Navigate to="/operacion/feed/lista" replace /> },
              { path: "feed", element: <Navigate to="/operacion/feed/feed" replace /> },
              { path: "turnos", element: <Navigate to="/operacion/calendario/turnos" replace /> },
              { path: "calendario", element: <Navigate to="/operacion/calendario/turnos" replace /> },
              { path: "*", element: <Navigate to="/operacion/feed" replace /> },
            ],
          },
          // Hub Revisión: cola de aprobación (editorial) + verificación de media
          // + Carril Rápido de Breaking (Claro Sports: temas con señal acelerando).
          {
            path: "revision",
            children: [
              { index: true, element: <Navigate to="editorial" replace /> },
              { path: "editorial", element: <RevisionEditorial /> },
              { path: "verificacion", element: <Verificacion /> },
              { path: "breaking", element: <CarrilRapido /> },
            ],
          },
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
          // Página TEXTO (antes "Biblioteca"): prompts + línea editorial con filtros.
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
          // Compatibilidad: los paths antiguos (estudio/editor/biblioteca) redirigen a los nuevos.
          { path: "estudio", element: <Navigate to="/contenido/imagen" replace /> },
          { path: "editor", element: <Navigate to="/contenido/imagen" replace /> },
          { path: "biblioteca", element: <RedirigirPrefijo a="/contenido/texto" /> },
          { path: "biblioteca/*", element: <RedirigirPrefijo a="/contenido/texto" /> },
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
              { path: "termometro", element: <Termometro /> },
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
              // se mudó a la Biblioteca.
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
          // Hub Actividad IA: el feed de actividad (índice) + Pipelines (vista CI/CD del
          // pipeline de contenido, etapa a etapa). Pipelines es una pestaña del hub, no una
          // entrada suelta del sidebar.
          {
            path: "actividad",
            children: [
              { index: true, element: <Actividad /> },
              { path: "pipelines", element: <Pipelines /> },
            ],
          },
          // Compat: la antigua ruta plana /datos/pipelines ahora es pestaña de Actividad IA.
          { path: "pipelines", element: <Navigate to="/datos/actividad/pipelines" replace /> },
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
      { path: "imagenes", element: <Navigate to="/contenido/imagen" replace /> },
      { path: "estudio", element: <Navigate to="/contenido/imagen" replace /> },
      { path: "biblioteca/*", element: <RedirigirPrefijo a="/contenido/texto" /> },
      { path: "investigacion/parrilla-dia", element: <Navigate to="/datos/investigacion" replace /> },
      { path: "investigacion/*", element: <RedirigirPrefijo a="/datos/investigacion" /> },
      { path: "revision/*", element: <RedirigirPrefijo a="/operacion/revision" /> },
      { path: "analiticas/*", element: <RedirigirPrefijo a="/datos/analiticas" /> },
      // El hub "Parrilla" se separó en "Feed" y "Calendario" (#cal-feed). Sus rutas
      // antiguas se redirigen a la pestaña equivalente del nuevo hub.
      { path: "parrilla/calendario", element: <Navigate to="/operacion/calendario/turnos" replace /> },
      { path: "parrilla/turnos", element: <Navigate to="/operacion/calendario/turnos" replace /> },
      { path: "parrilla/feed", element: <Navigate to="/operacion/feed/feed" replace /> },
      { path: "parrilla/pendientes", element: <Navigate to="/operacion/feed/lista" replace /> },
      { path: "parrilla/piezas", element: <Navigate to="/operacion/feed/lista" replace /> },
      { path: "parrilla/*", element: <Navigate to="/operacion/feed" replace /> },
      { path: "actividad", element: <Navigate to="/datos/actividad" replace /> },
      // "Activos"/"Plantillas" quedaron obsoletas; sus rutas redirigen a la Biblioteca.
      { path: "activos", element: <Navigate to="/contenido/texto/documentos" replace /> },
      { path: "activos/plantillas", element: <Navigate to="/contenido/texto/documentos" replace /> },
      // Hojas planas antiguas (pre-hub) y fusiones previas:
      { path: "fuentes", element: <Navigate to="/datos/investigacion/fuentes" replace /> },
      { path: "termometro", element: <Navigate to="/datos/investigacion/termometro" replace /> },
      { path: "radar", element: <Navigate to="/datos/investigacion" replace /> },
      { path: "revision-editorial", element: <Navigate to="/operacion/revision/editorial" replace /> },
      { path: "verificacion", element: <Navigate to="/operacion/revision/verificacion" replace /> },
      { path: "metricas", element: <Navigate to="/datos/analiticas/metricas" replace /> },
      { path: "comercial", element: <Navigate to="/datos/analiticas/comercial" replace /> },
      { path: "tareas", element: <Navigate to="/operacion/feed/lista" replace /> },
      { path: "rota", element: <Navigate to="/operacion/calendario/turnos" replace /> },
      // Publicaciones se FUSIONÓ en el contenido (#fase2); ahora vive en la Lista del Feed.
      { path: "publicaciones", element: <Navigate to="/operacion/feed/lista" replace /> },
      // El hub Agentes se retiró: su Actividad IA vive ahora en /datos/actividad.
      { path: "monitor", element: <Navigate to="/datos/actividad" replace /> },
      { path: "agentes", element: <Navigate to="/datos/actividad" replace /> },
      { path: "agentes/actividad", element: <Navigate to="/datos/actividad" replace /> },
      // El copy se generaba en /generacion (motor antiguo, retirado): ahora vive en
      // la Biblioteca; el catálogo de prompts también vive en la Biblioteca.
      { path: "generar-copy", element: <Navigate to="/contenido/texto" replace /> },
      { path: "generacion", element: <Navigate to="/contenido/texto" replace /> },
      { path: "conexiones", element: <Navigate to="/configuracion" replace /> },
      { path: "estado", element: <Navigate to="/configuracion" replace /> },
      { path: "proyectos", element: <Navigate to="/datos/actividad" replace /> },
      { path: "carpetas", element: <Navigate to="/datos/actividad" replace /> },

      // Cualquier otra ruta (URL desconocida, no cubierta por las redirecciones
      // legacy de arriba): página 404 dedicada en vez de rebotar en silencio al
      // feed, para dejar claro que la dirección no existe.
      { path: "*", element: <Error404 /> },
    ],
  },
]);
