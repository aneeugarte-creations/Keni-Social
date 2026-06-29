import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { FronteraError } from "@/components/comunes/FronteraError";
import { Spinner } from "@/components/ui/spinner";
import Error404 from "@/pages/Error404";

// Carga diferida por ruta (code-splitting): cada pagina viaja en su propio chunk
// y solo se descarga al entrar. Asi el arranque no carga, por ejemplo, las graficas
// de Metricas (Tremor/recharts, el grueso del bundle) hasta que se visitan. El
// <Suspense> que muestra el fallback mientras carga vive en el AppShell.
const Imagen = lazy(() => import("@/pages/Imagen"));
const Video = lazy(() => import("@/pages/Video"));
const Audio = lazy(() => import("@/pages/Audio"));
// Galería: descarga la app local keni-fotos + busca en las galerías conectadas. Página plana.
const Galeria = lazy(() => import("@/pages/Fotos"));

// Sub-paginas de cada hub. Los hubs no tienen componente wrapper propio: la
// ruta-padre se deja sin `element` y react-router renderiza `<Outlet/>` por defecto;
// la subnav entre sub-rutas vive in-page (SubnavHub, via HUB_TABS).
const Fuentes = lazy(() => import("@/pages/Fuentes"));
const PublicacionesHub = lazy(() => import("@/pages/PublicacionesHub"));
// Pestañas del hub Investigación que comparten superficie con otras secciones.
const Cobertura = lazy(() => import("@/pages/Cobertura"));
const Algoritmos = lazy(() => import("@/pages/Algoritmos"));

const Metricas = lazy(() => import("@/pages/Metricas"));
const Campanias = lazy(() => import("@/pages/Campanias"));
// Inbox: buzón de SOLO lectura (DMs + comentarios de FB/IG), pestaña del hub Analíticas.
const Inbox = lazy(() => import("@/pages/Inbox"));
// Marcas: dashboard en vivo de todas las marcas × redes × cuentas.
const Marcas = lazy(() => import("@/pages/Marcas"));

const Rota = lazy(() => import("@/pages/rota"));
// Trabajo: el tablero de cobertura (eventos/tareas) como destino propio, hermano del calendario.
const Trabajo = lazy(() => import("@/pages/Trabajo"));
// Feed de ideación (Flujo D, Fase 4): la "red social interna" dentro del AppShell.
const FeedIdeacion = lazy(() => import("@/pages/feed/FeedIdeacion"));
const ListaPublicacion = lazy(() => import("@/pages/feed/ListaPublicacion"));
const CalendarioPublicacion = lazy(() => import("@/pages/calendario/CalendarioPublicacion"));
const ProgramaPlan = lazy(() => import("@/pages/programa/ProgramaPlan"));

const PipelineDetalle = lazy(() => import("@/pages/PipelineDetalle"));
const GeneracionDetalle = lazy(() => import("@/pages/GeneracionDetalle"));

// Detalle de UNA historia de la Mesa como SUBPÁGINA del hub Investigación (URL propia, deep-link).
const DetalleHistoriaPagina = lazy(() => import("@/pages/noticias/DetalleHistoriaPagina"));
// «Contexto» (`/maquina/contexto`): la página única de la máquina — el pipeline de cada motor como
// estructura, con cada fase desplegable a Prompt · Contexto · Logs y su on/off.
const Contexto = lazy(() => import("@/pages/maquina/Contexto"));
// Subpágina de UNA fase (`/maquina/contexto/:proceso/:fase`): su Prompt · Acompaña · Logs.
const FaseDetalle = lazy(() => import("@/pages/maquina/FaseDetalle"));
// Subpágina de UN documento que acompaña a un prompt (`/maquina/contexto/doc/*`): editorial o
// sub-prompt, con el mismo editor completo que una fase (no overlay). El `*` captura el id con barras.
const DocumentoContexto = lazy(() => import("@/pages/maquina/DocumentoContexto"));
// Detalle de UN daemon (`/maquina/agentes/:agente`): su estado y log por barrido; lo abren las
// tablas de daemons (Sistema + cockpits).
const AgenteDetalle = lazy(() => import("@/pages/maquina/AgenteDetalle"));
// «Cómputo y cola» (`/maquina/agentes`): la cola por dentro (en curso + esperando) con su control
// admin (priorizar/cancelar/reintentar/purgar) + estado de slots. Pestaña de aterrizaje del hub Agentes.
const Computo = lazy(() => import("@/pages/maquina/Computo"));
// «Economía» (`/maquina/economia`): la contabilidad de la máquina (presupuesto + parada de
// emergencia + economía de tokens desglosada por motor). Pestaña del hub Agentes.
const Economia = lazy(() => import("@/pages/maquina/Economia"));
// «Actividad» (`/maquina/actividad`): la TRAZA unificada de la máquina (runs del pipeline +
// trabajos sueltos). Es el feed de Producción como pestaña del hub Agentes.
const Actividad = lazy(() => import("@/pages/Produccion"));
// «Controles» (`/maquina/controles`): mando único de la máquina — maestro, pausa, cuentas
// y todos los switches del pipeline en un solo lugar (solo admin).
const Controles = lazy(() => import("@/pages/maquina/Controles"));

// Feed móvil para revisores (#verificación-movil-feed): superficie tipo red social, una
// columna, SIN sidebar. Vive FUERA del AppShell (layout propio) y se llega por
// enlace directo (no se registra en el catálogo de apps).
const MobileFeed = lazy(() => import("@/pages/MobileFeed"));

// Ventana de retorno del OAuth de redes (popup de «Marcas»). Layout propio, fuera del
// AppShell: se abre, avisa al panel y se cierra. No se registra en el catálogo de apps.
const OauthConectado = lazy(() => import("@/pages/OauthConectado"));

// Autorización del escritorio keni-fotos (login OPCIONAL del Tauri, flujo loopback): página mínima
// hermana del AppShell (sin sidebar) pero DETRÁS de la puerta de sesión. Emite el token y redirige
// al loopback de la app. No se registra en el catálogo de apps.
const FotosAutorizar = lazy(() => import("@/pages/FotosAutorizar"));

// Informe PÚBLICO de campaña (`/c/:token`): capability-URL de solo lectura, sin login ni
// sidebar. Vive FUERA del AppShell (layout propio); el token es la única llave.
const InformePublico = lazy(() => import("@/pages/InformePublico"));

// Ajustes (ahora solo accesibles via dropdown del avatar).
const Sugerencias = lazy(() => import("@/pages/Sugerencias"));
const DetalleSugerenciaPagina = lazy(
  () => import("@/pages/sugerencias/DetalleSugerenciaPagina"),
);
const Webhooks = lazy(() => import("@/pages/Webhooks"));
const MiCuenta = lazy(() => import("@/pages/MiCuenta"));
// Panel de usuarios: lista (tabla) + subpáginas a tamaño completo (alta, detalle, config global).
const PanelUsuarios = lazy(() => import("@/pages/usuarios/PanelUsuarios"));
const UsuarioNuevo = lazy(() => import("@/pages/usuarios/UsuarioNuevo"));
const ConfiguracionGlobal = lazy(() => import("@/pages/usuarios/ConfiguracionGlobal"));
const UsuarioDetalle = lazy(() => import("@/pages/usuarios/UsuarioDetalle"));
// Sistema (admin): la infraestructura que sostiene la consola (recursos, daemons,
// backups, latencias, S3).
const Sistema = lazy(() => import("@/pages/sistema/Sistema"));

/**
 * Rutas del SPA. El AppShell es el layout raiz (sidebar + topbar); las paginas
 * cuelgan de el. La navegación se agrupa por MOMENTO DEL FLUJO y ese bloque vive
 * TAMBIÉN en la URL, una correspondencia 1:1 con los bloques del sidebar:
 *   · `/operacion/*` — el trabajo cotidiano del equipo (Investigación, Feed, Programa).
 *   · `/equipo/*`    — quién trabaja y cuándo (Trabajo, Calendario).
 *   · `/contenido/*` — herramientas para crear/editar a mano (Imagen, Video, Audio, Galería).
 *   · `/maquina/*`   — la máquina de generación (Contexto, Agentes).
 *   · `/datos/*`     — entradas y señales (Analíticas).
 * La home es el feed del equipo (`/operacion/feed`). Los hubs (Feed, Programa,
 * Investigación, Agentes, Analíticas) son una ruta-layout sin componente: react-router
 * renderiza `<Outlet/>` y la subnav entre sub-rutas vive in-page (SubnavHub, via
 * HUB_TABS). Cada hub aterriza en su primera pestaña (la ruta-padre redirige a ella),
 * para que la URL refleje siempre la pestaña activa.
 */
// Basename del router = `base` del bundle. En la app normal `BASE_URL` es "/" (sin cambio); un
// bundle de PREVIEW se compila con `base=/api/preview/<id>/`, así el router lo recorta y enruta
// bien bajo ese prefijo (sin él, toda ruta caería en el 404 del catch-all). Sin barra final.
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "") || "/";

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
              <Spinner className="h-6 w-6" aria-label="Cargando" />
            </div>
          }
        >
          <MobileFeed />
        </Suspense>
      </FronteraError>
    ),
  },
  // Retorno del OAuth de redes: ventana emergente efímera de «Marcas». Hermana del
  // AppShell (layout propio, sin sidebar): su propia frontera de error + Suspense.
  {
    path: "/oauth/conectado",
    element: (
      <FronteraError>
        <Suspense
          fallback={
            <div className="flex min-h-dvh items-center justify-center text-muted-foreground">
              <Spinner className="h-6 w-6" aria-label="Cargando" />
            </div>
          }
        >
          <OauthConectado />
        </Suspense>
      </FronteraError>
    ),
  },
  // Autorización del escritorio keni-fotos: ruta hermana del AppShell (sin sidebar) pero detrás de
  // la puerta de sesión (PuertaSesion envuelve al router): si no hay sesión se ve el login y al
  // entrar se vuelve aquí con `cb`/`state` intactos. Su propia frontera de error + Suspense.
  {
    path: "/fotos/autorizar",
    element: (
      <FronteraError>
        <Suspense
          fallback={
            <div className="flex min-h-dvh items-center justify-center text-muted-foreground">
              <Spinner className="h-6 w-6" aria-label="Cargando" />
            </div>
          }
        >
          <FotosAutorizar />
        </Suspense>
      </FronteraError>
    ),
  },
  // Informe público de campaña: ruta hermana del AppShell (sin sesión ni sidebar). El token
  // (capability-URL) es la única llave; la página marca `noindex`.
  {
    path: "/c/:token",
    element: (
      <FronteraError>
        <Suspense
          fallback={
            <div className="flex min-h-dvh items-center justify-center text-muted-foreground">
              <Spinner className="h-6 w-6" aria-label="Cargando" />
            </div>
          }
        >
          <InformePublico />
        </Suspense>
      </FronteraError>
    ),
  },
  {
    path: "/",
    element: <AppShell />,
    children: [
      // Home: el feed del equipo (primer checkpoint del día).
      { index: true, element: <Navigate to="/operacion/feed" replace /> },

      // ===== Bloque OPERACIÓN (trabajo cotidiano del equipo) =====
      {
        path: "operacion",
        children: [
          { index: true, element: <Navigate to="/operacion/feed" replace /> },
          // Hub Feed: feed de ideación (formato red social) + Portal + Lista de contenido.
          {
            path: "feed",
            children: [
              { index: true, element: <Navigate to="/operacion/feed/feed" replace /> },
              // Feed de ideación: la pieza vista como post (material → copy IA → arte) con
              // estado de la cadena IA en vivo y aprobación en línea (Flujo D, Fase 4).
              { path: "feed", element: <FeedIdeacion /> },
              // Portal: el MISMO feed acotado al canal `origen="portal"` (los auto-producidos de
              // fuente propia, cross-marca) con sus 3 pestañas de estado.
              { path: "portal", element: <FeedIdeacion origen="portal" /> },
              // Lista de contenido (header de acciones: aportar/crear/gestionar).
              { path: "lista", element: <ListaPublicacion /> },
            ],
          },
          // Hub Programa: «Programación» (la rejilla mensual de publicaciones) y «Plan» (las líneas
          // de la marca: su hashtag derivado y los keywords del clasificador). Aterriza en Programación.
          {
            path: "programa",
            children: [
              { index: true, element: <Navigate to="/operacion/programa/programacion" replace /> },
              { path: "programacion", element: <CalendarioPublicacion /> },
              { path: "plan", element: <ProgramaPlan /> },
            ],
          },
          // Hub Investigación: el pool de noticias que el equipo revisa a diario. Pestañas Noticias
          // (el pool, aterrizaje), Fuentes (los canales), Algoritmos (inteligencia de plataforma) y
          // Publicaciones (el banco evergreen). El pipeline (descubrir/verificar) se controla en
          // «Contexto» (Máquina), no aquí.
          {
            path: "investigacion",
            children: [
              { index: true, element: <Navigate to="/operacion/investigacion/noticias" replace /> },
              { path: "noticias", element: <Cobertura /> },
              { path: "fuentes", element: <Fuentes /> },
              { path: "algoritmos", element: <Algoritmos /> },
              { path: "publicaciones", element: <PublicacionesHub /> },
              // Detalle de una historia de la Mesa (deep-link directo por URL).
              { path: "historia/:id", element: <DetalleHistoriaPagina /> },
            ],
          },
        ],
      },

      // ===== Bloque EQUIPO (quién trabaja y cuándo) =====
      {
        path: "equipo",
        children: [
          { index: true, element: <Navigate to="/equipo/trabajo" replace /> },
          // «Trabajo»: eventos/tareas y su cobertura (Panorama · Mis tareas · Por cubrir), por marca.
          { path: "trabajo", element: <Trabajo /> },
          // «Calendario»: el horario de turnos del equipo (Yo/Equipo · Semana/Mes), por marca.
          { path: "calendario", element: <Rota /> },
        ],
      },

      // ===== Bloque CONTENIDO (herramientas para crear/editar a mano) =====
      {
        path: "contenido",
        children: [
          { index: true, element: <Navigate to="/contenido/imagen" replace /> },
          // Página IMAGEN: editor profesional por capas (Konva); diseña/edita el Documento.
          { path: "imagen", element: <Imagen /> },
          // Página VIDEO: subida + preview (motor de edición próximamente).
          { path: "video", element: <Video /> },
          // Página AUDIO: gestor audio→texto (transcripción whisper + agentes de Claude).
          { path: "audio", element: <Audio /> },
          // Página GALERÍA: lanzador de la herramienta local keni-fotos + galerías conectadas.
          { path: "galeria", element: <Galeria /> },
        ],
      },

      // ===== Sección MÁQUINA (la máquina de generación) =====
      // «Contexto» (el pipeline de cada motor como estructura: fases con prompt, contexto y logs +
      // on/off) y «Agentes» (la sala de máquinas: Cómputo —aterrizaje—, Economía y Actividad).
      {
        path: "maquina",
        children: [
          { index: true, element: <Navigate to="/maquina/agentes" replace /> },
          { path: "contexto", element: <Contexto /> },
          { path: "contexto/doc/*", element: <DocumentoContexto /> },
          { path: "contexto/:proceso/:fase", element: <FaseDetalle /> },
          // Hub Agentes: Cómputo (la cola) es la pestaña de aterrizaje en la propia ruta-padre;
          // Economía y Actividad son sus hermanas. El detalle de un daemon (`:agente`) cuelga del hub.
          { path: "agentes", element: <Computo /> },
          { path: "agentes/:agente", element: <AgenteDetalle /> },
          { path: "economia", element: <Economia /> },
          { path: "actividad", element: <Actividad /> },
          // Controles: mando único de la máquina (solo admin).
          { path: "controles", element: <Controles /> },
          // Detalle desde la traza: una run del pipeline y un trabajo suelto (generación). Las
          // tarjetas del feed de Actividad enlazan aquí.
          { path: "actividad/pipelines/:id", element: <PipelineDetalle /> },
          { path: "actividad/generacion/:id", element: <GeneracionDetalle /> },
        ],
      },

      // ===== Bloque DATOS (entradas y señales) =====
      {
        path: "datos",
        children: [
          { index: true, element: <Navigate to="/datos/analiticas" replace /> },
          // Hub Analíticas: métricas, campañas y buzón.
          {
            path: "analiticas",
            children: [
              { index: true, element: <Navigate to="/datos/analiticas/metricas" replace /> },
              { path: "metricas", element: <Metricas /> },
              { path: "campanias", element: <Campanias /> },
              { path: "inbox", element: <Inbox /> },
            ],
          },
        ],
      },

      // ===== Páginas del avatar (sin entrada en el sidebar) =====
      { path: "mi-cuenta", element: <MiCuenta /> },
      { path: "sugerencias", element: <Sugerencias /> },
      // Detalle/spec de una sugerencia como SUBPÁGINA (no popup): URL propia, deep-link.
      { path: "sugerencias/:id", element: <DetalleSugerenciaPagina /> },
      // Webhooks salientes: solo admin (el backend devuelve 403 si no; la pagina avisa
      // al entrar por URL directa). Gestionar webhooks = abrir la red de salida.
      { path: "webhooks", element: <Webhooks /> },
      // Gestión de usuarios: solo superadmin (el backend devuelve 403 si no, y cada
      // página muestra el aviso al entrar por URL directa). El panel es la TABLA (índice);
      // alta, configuración global y detalle de persona son subpáginas a tamaño completo.
      // Las rutas literales (`nuevo`, `configuracion`) van antes que la paramétrica `:id`.
      {
        path: "usuarios",
        children: [
          { index: true, element: <PanelUsuarios /> },
          { path: "nuevo", element: <UsuarioNuevo /> },
          { path: "configuracion", element: <ConfiguracionGlobal /> },
          { path: ":id", element: <UsuarioDetalle /> },
        ],
      },
      // Sistema: solo admin (el backend devuelve 403 si no; la página avisa al entrar por URL directa).
      { path: "sistema", element: <Sistema /> },
      // Marcas: dashboard en vivo de marcas × redes × cuentas. La entrada de nav del
      // sidebar la sirve el catálogo del backend (GET /api/catalogo, ADR 0005); aquí
      // solo se registra la ruta del SPA.
      { path: "marcas", element: <Marcas /> },

      // Cualquier otra ruta (URL desconocida): página 404 dedicada en vez de rebotar
      // en silencio al feed, para dejar claro que la dirección no existe.
      { path: "*", element: <Error404 /> },
    ],
  },
], { basename: BASENAME });
