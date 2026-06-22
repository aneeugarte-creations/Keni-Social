import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { FronteraError } from "@/components/comunes/FronteraError";
import { RedirigirCola } from "@/components/comunes/RedirigirCola";
import { RedirigirMonitor } from "@/components/comunes/RedirigirMonitor";
import { RedirigirPrefijo } from "@/components/comunes/RedirigirPrefijo";
import Error404 from "@/pages/Error404";
import { Loader2 } from "lucide-react";

// Carga diferida por ruta (code-splitting): cada pagina viaja en su propio chunk
// y solo se descarga al entrar. Asi el arranque no carga, por ejemplo, las graficas
// de Metricas (Tremor/recharts, el grueso del bundle) hasta que se visitan. El
// <Suspense> que muestra el fallback mientras carga vive en el AppShell.
const Imagen = lazy(() => import("@/pages/Imagen"));
const Video = lazy(() => import("@/pages/Video"));
const Audio = lazy(() => import("@/pages/Audio"));

// Sub-paginas de cada hub. Los hubs no tienen componente wrapper propio: la
// ruta-padre se deja sin `element` y react-router renderiza `<Outlet/>` por defecto;
// la subnav entre sub-rutas vive in-page (SubnavHub, via HUB_TABS).
const Fuentes = lazy(() => import("@/pages/Fuentes"));
const PublicacionesHub = lazy(() => import("@/pages/PublicacionesHub"));

const Metricas = lazy(() => import("@/pages/Metricas"));
const Campanias = lazy(() => import("@/pages/Campanias"));
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

// Sección «Máquina» (fase 2A): la máquina de generación como UNA sección con dos cockpits
// (Investigación · Producción, esqueletos por ahora) y la Cola compartida (la vista global
// del worker/cola).
const CockpitInvestigacion = lazy(() => import("@/pages/maquina/CockpitInvestigacion"));
// Detalle de UNA historia de la Mesa como SUBPÁGINA (URL propia, deep-link).
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
// tablas de daemons (Sistema + cockpits). La LISTA «Agentes» se retiró: los dos agentes IA son
// los dos cockpits (su on/off y prompts viven ahí; su salud, en el doctor).
const AgenteDetalle = lazy(() => import("@/pages/maquina/AgenteDetalle"));
// «Cómputo y cola» (`/maquina/computo`): la cola por dentro (en curso + esperando) con su control
// admin (priorizar/cancelar/reintentar/purgar) + estado de slots. Pestaña de aterrizaje del hub.
const Computo = lazy(() => import("@/pages/maquina/Computo"));
// «Economía» (`/maquina/economia`): la contabilidad de la máquina (presupuesto + parada de
// emergencia + economía de tokens desglosada por motor). Pestaña del hub de la máquina.
const Economia = lazy(() => import("@/pages/maquina/Economia"));
// «Actividad» (`/maquina/actividad`): la TRAZA unificada de la máquina (runs del pipeline +
// trabajos sueltos), antes embebida en Agentes. Es el feed de Producción como página propia.
const Actividad = lazy(() => import("@/pages/Produccion"));

// Feed móvil para revisores (#verificación-movil-feed): superficie tipo red social, una
// columna, SIN sidebar. Vive FUERA del AppShell (layout propio) y se llega por
// enlace directo (no se registra en el catálogo de apps).
const MobileFeed = lazy(() => import("@/pages/MobileFeed"));

// Ventana de retorno del OAuth de redes (popup de «Marcas»). Layout propio, fuera del
// AppShell: se abre, avisa al panel y se cierra. No se registra en el catálogo de apps.
const OauthConectado = lazy(() => import("@/pages/OauthConectado"));

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
 * TAMBIÉN en la URL: `/operacion/*` (checkpoints diarios), `/publicaciones/*`
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
  // Retorno del OAuth de redes: ventana emergente efímera de «Marcas». Hermana del
  // AppShell (layout propio, sin sidebar): su propia frontera de error + Suspense.
  {
    path: "/oauth/conectado",
    element: (
      <FronteraError>
        <Suspense
          fallback={
            <div className="flex min-h-dvh items-center justify-center text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin" aria-label="Cargando" />
            </div>
          }
        >
          <OauthConectado />
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
              <Loader2 className="h-6 w-6 animate-spin" aria-label="Cargando" />
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
      // Home: el feed del equipo (primer checkpoint del día). Ya no hay Panel.
      { index: true, element: <Navigate to="/operacion/feed" replace /> },
      // Compatibilidad: enlaces/markers antiguos a /panel caen en el feed.
      { path: "panel", element: <Navigate to="/operacion/feed" replace /> },

      // ===== Bloque OPERACIÓN (checkpoints diarios) =====
      {
        path: "operacion",
        children: [
          { index: true, element: <Navigate to="/operacion/feed" replace /> },
          // El tablero de cobertura (eventos/tareas) es ahora el destino «Trabajo»; la ruta vieja
          // `/operacion/tareas` redirige allí (compat con enlaces/marcadores).
          { path: "tareas", element: <Navigate to="/operacion/trabajo" replace /> },
          // «Trabajo»: eventos/tareas y su cobertura (Panorama · Mis tareas · Por cubrir), por marca.
          { path: "trabajo", element: <Trabajo /> },
          // El antiguo hub "Parrilla" se separó en DOS (#cal-feed):
          // Hub Feed: feed de ideación (formato red social) + Portal + Lista de contenido.
          {
            path: "feed",
            children: [
              { index: true, element: <Navigate to="feed" replace /> },
              // Feed de ideación: la pieza vista como post (material → copy IA → arte) con
              // estado de la cadena IA en vivo y aprobación en línea (Flujo D, Fase 4).
              { path: "feed", element: <FeedIdeacion /> },
              // Portal: el MISMO feed acotado al canal `origen="portal"` (los auto-producidos de
              // fuente propia, cross-marca) con sus 3 pestañas de estado. Un clon de Feed, no una
              // pestaña-vista más, porque el portal produce mucho y merece su propia superficie.
              { path: "portal", element: <FeedIdeacion origen="portal" /> },
              // Lista de contenido (header de acciones: aportar/crear/gestionar).
              { path: "lista", element: <ListaPublicacion /> },
            ],
          },
          // El hub "Calendario" se separó en DOS páginas planas del sidebar (sin pestañas):
          // Programación (calendario de piezas, por marca activa) y Turnos (rota de
          // cobertura del equipo, por marca activa). Ambas respetan el switch global de marca;
          // "Todas" agrega. Las rutas legacy /operacion/calendario/* redirigen abajo.
          // «Programa»: hub con dos pestañas — Programación (la rejilla mensual) y Plan (las líneas
          // de la marca: su hashtag derivado y los keywords del clasificador). El índice aterriza en
          // Programación (la vista de trabajo).
          {
            path: "programa",
            children: [
              { index: true, element: <Navigate to="/operacion/programa/programacion" replace /> },
              { path: "programacion", element: <CalendarioPublicacion /> },
              { path: "plan", element: <ProgramaPlan /> },
            ],
          },
          // Compat: la página plana «Programación» pasó a ser el hub «Programa».
          { path: "programacion", element: <Navigate to="/operacion/programa/programacion" replace /> },
          { path: "turnos", element: <Rota /> },
          // Compat: el antiguo hub `/operacion/calendario/*` (Programación/Turnos como pestañas)
          // se separó. Redirigimos sus sub-rutas al hub Programa / a Turnos.
          {
            path: "calendario",
            children: [
              { index: true, element: <Navigate to="/operacion/programa/programacion" replace /> },
              { path: "calendario", element: <Navigate to="/operacion/programa/programacion" replace /> },
              { path: "turnos", element: <Navigate to="/operacion/turnos" replace /> },
              { path: "*", element: <Navigate to="/operacion/programa/programacion" replace /> },
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
          // La página "Revisión" (revisión editorial + verificación + Carril Rápido) se retiró por
          // obsoleta: la aprobación vive ahora en línea en el Feed. Sus rutas redirigen al Feed.
          { path: "revision", element: <Navigate to="/operacion/feed" replace /> },
          { path: "revision/*", element: <Navigate to="/operacion/feed" replace /> },
        ],
      },

      // ===== Bloque CONTENIDO (herramientas para crear/editar a mano) =====
      {
        path: "contenido",
        children: [
          { index: true, element: <Navigate to="/publicaciones/imagen" replace /> },
          // CONTENIDO = TRES páginas planas por tipo: Imagen · Video · Texto. El nombre de la
          // página coincide con su ruta y con su API (`/api/imagen`, `/api/video`, `/api/prompts`).
          // Página IMAGEN: editor profesional por capas (Konva); diseña/edita el Documento.
          { path: "imagen", element: <Imagen /> },
          // Página VIDEO: subida + preview (motor de edición próximamente).
          { path: "video", element: <Video /> },
          // Página AUDIO: gestor audio→texto (transcripción whisper + agentes de Claude).
          { path: "audio", element: <Audio /> },
          // Página TEXTO/Prompts: RETIRADA. Los prompts viven en cada fase del pipeline en
          // «Contexto» (Máquina) y el contexto editorial se inyecta desde ahí. Todo
          // `/publicaciones/texto*` (incl. la vieja pestaña de algoritmos) redirige a Contexto.
          { path: "texto", element: <Navigate to="/maquina/contexto" replace /> },
          { path: "texto/*", element: <Navigate to="/maquina/contexto" replace /> },
          // Compatibilidad: los paths antiguos (estudio/editor) redirigen a Imagen.
          { path: "estudio", element: <Navigate to="/publicaciones/imagen" replace /> },
          { path: "editor", element: <Navigate to="/publicaciones/imagen" replace /> },
        ],
      },

      // ===== Bloque DATOS (entradas y señales que alimentan/reflejan la automatización) =====
      {
        path: "datos",
        children: [
          { index: true, element: <Navigate to="/datos/investigacion" replace /> },
          // Hub Investigación: la pieza «Noticias» (la MESA DE REDACCIÓN: el pool persistente de
          // cobertura) se RELOCALIZÓ al cockpit de Investigación (`/maquina/investigacion`,
          // pestaña «Mesa de redacción»). El índice y las hojas que la componían redirigen allí.
          // Quedan vivas Publicaciones (banco evergreen) y Fuentes como sub-rutas del hub.
          {
            path: "investigacion",
            children: [
              {
                index: true,
                element: <Navigate to="/maquina/investigacion?seccion=mesa" replace />,
              },
              { path: "contenidos", element: <PublicacionesHub /> },
              { path: "fuentes", element: <Fuentes /> },
              // El armado MANUAL del Termómetro (galería internacional) se retiró: la galería se
              // genera sola. El deep-link cae en la mesa del cockpit.
              {
                path: "termometro",
                element: <Navigate to="/maquina/investigacion?seccion=mesa" replace />,
              },
              // Los ajustes del motor viven en el drawer del cockpit de Investigación.
              {
                path: "ajustes",
                element: <Navigate to="/maquina/investigacion?seccion=mesa" replace />,
              },
              // Investigador y Cobertura ERAN la mesa de redacción → cockpit (pestaña «Mesa»).
              {
                path: "investigador",
                element: <Navigate to="/maquina/investigacion?seccion=mesa" replace />,
              },
              {
                path: "cobertura",
                element: <Navigate to="/maquina/investigacion?seccion=mesa" replace />,
              },
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
              // Compatibilidad con enlaces previos: "plan", "descubrimiento" y "radar" eran el
              // descubrimiento → mesa del cockpit; "algoritmos" es su pestaña de inputs.
              {
                path: "plan",
                element: <Navigate to="/maquina/investigacion?seccion=mesa" replace />,
              },
              {
                path: "descubrimiento",
                element: <Navigate to="/maquina/investigacion?seccion=mesa" replace />,
              },
              {
                path: "radar",
                element: <Navigate to="/maquina/investigacion?seccion=mesa" replace />,
              },
              {
                path: "algoritmos",
                element: <Navigate to="/maquina/investigacion?seccion=algoritmos" replace />,
              },
            ],
          },
          // Hub Analíticas: métricas, campañas y deck deportivo.
          {
            path: "analiticas",
            children: [
              { index: true, element: <Navigate to="metricas" replace /> },
              { path: "metricas", element: <Metricas /> },
              { path: "campanias", element: <Campanias /> },
              // Bookmark viejo: el apartado se llamaba "comercial".
              { path: "comercial", element: <Navigate to="/datos/analiticas/campanias" replace /> },
            ],
          },
          // Producción (antes «Actividad IA»): el FEED unificado (runs del pipeline + actividad
          // suelta) se PLEGÓ como la sección «Actividad» del dashboard de Workers (`/maquina/cola`);
          // su índice redirige allí. Cada run y cada trabajo suelto conservan su página de detalle
          // entrada/salida (las tarjetas del feed enlazan a ellas).
          {
            path: "produccion",
            children: [
              { index: true, element: <Navigate to="/maquina/actividad" replace /> },
              // Los detalles (run del pipeline / trabajo suelto) se RELOCALIZARON bajo la pestaña
              // Actividad del hub de la máquina (`/maquina/actividad/...`); estas rutas viejas
              // redirigen preservando el id (compat con enlaces/marcadores).
              { path: "pipelines/*", element: <RedirigirPrefijo a="/maquina/actividad/pipelines" /> },
              { path: "actividad/*", element: <RedirigirPrefijo a="/maquina/actividad/generacion" /> },
              // Monitor: RELOCALIZADO a la sección «Máquina» (fase 2A). La vista global del
              // worker/cola es `/maquina/cola`; la tira de etapas + el drawer de ajustes,
              // el cockpit de Producción. Redirige preservando `?tab=`/`?proceso=`.
              { path: "monitor", element: <RedirigirMonitor /> },
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

      // ===== Sección MÁQUINA (la máquina de generación, fase 2A) =====
      // Una sección con DOS motores/cockpits de igual peso —Investigación (descubre/verifica)
      // y Producción (genera copy/arte)— y una COLA compartida (la vista global del worker/
      // cola que ambos motores comparten). Los cockpits son esqueletos en 2A; los rellenan
      // 2B/2C. La Cola se relocalizó del antiguo Monitor (/datos/produccion/monitor).
      {
        path: "maquina",
        children: [
          { index: true, element: <Navigate to="/maquina/computo" replace /> },
          { path: "contexto", element: <Contexto /> },
          { path: "contexto/doc/*", element: <DocumentoContexto /> },
          { path: "contexto/:proceso/:fase", element: <FaseDetalle /> },
          { path: "investigacion", element: <CockpitInvestigacion /> },
          // Detalle de una historia de la Mesa (deep-link directo por URL).
          { path: "investigacion/historia/:id", element: <DetalleHistoriaPagina /> },
          // El cockpit de Producción se fusionó en «Contexto» (su pipeline + ajustes); redirige allí.
          { path: "produccion", element: <Navigate to="/maquina/contexto?proceso=produccion" replace /> },
          // La LISTA «Agentes» se retiró (redundante con los dos cockpits): redirige al hub.
          { path: "agentes", element: <Navigate to="/maquina/computo" replace /> },
          // Detalle de UN daemon (`:agente` = nombre): lo abren las tablas de daemons.
          { path: "agentes/:agente", element: <AgenteDetalle /> },
          // Cómputo y cola (estática; no choca con la dinámica `agentes/:agente`).
          { path: "computo", element: <Computo /> },
          // Economía (contabilidad) y Actividad (traza): pestañas hermanas del hub de la máquina.
          { path: "economia", element: <Economia /> },
          { path: "actividad", element: <Actividad /> },
          // Detalle desde la traza: una run del pipeline y un trabajo suelto (generación). Viven
          // bajo Actividad (la traza), no en «datos»; las tarjetas del feed enlazan aquí.
          { path: "actividad/pipelines/:id", element: <PipelineDetalle /> },
          { path: "actividad/generacion/:id", element: <GeneracionDetalle /> },
          // Compat: la página se llamaba «Workers» (`/maquina/cola`); redirige preservando
          // `?proceso=` (los cockpits enlazan aquí prefiltrado).
          { path: "cola", element: <RedirigirCola /> },
        ],
      },

      // Ajustes (sin entrada en el sidebar; se llega desde el dropdown del avatar).
      { path: "mi-cuenta", element: <MiCuenta /> },
      // La página Configuración se DISTRIBUYÓ y la máquina se CONSOLIDÓ: máquina,
      // investigación/motor de noticias, conexiones (Metricool + imagen IA), sistema y
      // esfuerzo viven en el drawer de ajustes de la máquina; publicación → Programación;
      // apariencia → Mi cuenta. La ruta vieja redirige al drawer (cockpit de Producción).
      { path: "configuracion", element: <Navigate to="/maquina/contexto?proceso=produccion&tab=ajustes" replace /> },
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
      // Sistema: solo admin (el backend devuelve 403 si no; la página avisa al entrar por
      // URL directa). Estuvo consolidada como pestaña «Salud» del Monitor; el Monitor
      // redirige aquí los deep-links viejos (?tab=salud).
      { path: "sistema", element: <Sistema /> },
      // Marcas: dashboard en vivo de marcas × redes × cuentas. La entrada de nav del
      // sidebar la sirve el catálogo del backend (GET /api/catalogo, ADR 0005); aquí
      // solo se registra la ruta del SPA.
      { path: "marcas", element: <Marcas /> },

      // ===== Redirecciones de rutas legacy =====
      // Rutas planas anteriores → su nuevo path con prefijo de bloque (preservando
      // la pestaña con `RedirigirPrefijo` donde aplica).
      { path: "imagenes", element: <Navigate to="/publicaciones/imagen" replace /> },
      { path: "estudio", element: <Navigate to="/publicaciones/imagen" replace /> },
      { path: "texto/*", element: <RedirigirPrefijo a="/publicaciones/texto" /> },
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
      { path: "activos", element: <Navigate to="/publicaciones/texto/documentos" replace /> },
      { path: "activos/plantillas", element: <Navigate to="/publicaciones/texto/documentos" replace /> },
      // Hojas planas antiguas (pre-hub) y fusiones previas:
      { path: "fuentes", element: <Navigate to="/datos/investigacion/fuentes" replace /> },
      { path: "termometro", element: <Navigate to="/datos/investigacion" replace /> },
      { path: "radar", element: <Navigate to="/datos/investigacion" replace /> },
      // "Revisión" se retiró (obsoleta); estas hojas planas legacy caen en el Feed.
      { path: "revision-editorial", element: <Navigate to="/operacion/feed" replace /> },
      { path: "verificacion", element: <Navigate to="/operacion/feed" replace /> },
      { path: "metricas", element: <Navigate to="/datos/analiticas/metricas" replace /> },
      { path: "comercial", element: <Navigate to="/datos/analiticas/campanias" replace /> },
      { path: "tareas", element: <Navigate to="/operacion/turnos" replace /> },
      { path: "rota", element: <Navigate to="/operacion/turnos" replace /> },
      // Piezas se FUSIONÓ en el contenido (#fase2); ahora vive en la Lista del Feed.
      { path: "piezas", element: <Navigate to="/operacion/feed/lista" replace /> },
      // El antiguo Monitor se relocalizó a «Máquina»; el deep-link plano `/monitor` cae en la
      // Cola (preservando `?tab=`/`?proceso=` vía el mismo redirector que la ruta anidada).
      { path: "monitor", element: <RedirigirMonitor /> },
      { path: "agentes", element: <Navigate to="/datos/produccion" replace /> },
      { path: "agentes/actividad", element: <Navigate to="/datos/produccion" replace /> },
      // El copy se generaba en /generacion (motor antiguo, retirado): ahora vive en
      // la Texto; el catálogo de prompts también vive en la Texto.
      { path: "generar-copy", element: <Navigate to="/publicaciones/texto" replace /> },
      { path: "generacion", element: <Navigate to="/publicaciones/texto" replace /> },
      { path: "conexiones", element: <Navigate to="/configuracion" replace /> },
      { path: "estado", element: <Navigate to="/configuracion" replace /> },

      // Cualquier otra ruta (URL desconocida, no cubierta por las redirecciones
      // legacy de arriba): página 404 dedicada en vez de rebotar en silencio al
      // feed, para dejar claro que la dirección no existe.
      { path: "*", element: <Error404 /> },
    ],
  },
]);
