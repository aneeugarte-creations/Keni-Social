import { useQuery } from "@tanstack/react-query";
import { Inbox, Rss, BookOpen, Activity, TrendingUp } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";

import { CatalogoPresets } from "./fuentes/CatalogoPresets";
import { GestionFuentes } from "./fuentes/GestionFuentes";
// Salud del motor de ingesta de feeds: estado de los canales externos (feeds activos/
// con error, huecos, reactivar). Es un ÁREA propia.
import { RendimientoFuentes } from "./fuentes/RendimientoFuentes";
import { SaludFeeds } from "./fuentes/SaludFeeds";
// Buzones del equipo (listas tipo portal/WhatsApp/corresponsales y Excel): la fuente
// INTERNA. Compone la página de Cajones del día.
import CajonesDia from "./CajonesDia";
// Cajón PRESIDENCIA: la nota de WhatsApp de presidencia (texto + media) que genera sola
// una pieza CARRUSEL en el feed. Es un buzón aparte de los Cajones del día (no se parsea
// con IA: la nota va tal cual y el media adjunto ES el carrusel).
import CajonPresidencia from "./fuentes/CajonPresidencia";

/** Un ÁREA de Fuentes (pestaña de primer nivel): etiqueta + icono. */
type Area = {
  valor: string;
  etiqueta: string;
  icono: typeof Rss;
};

// ANTES Fuentes tenía 3 pestañas (Externas/Internas/Rendimiento) que APILABAN secciones
// grandes y obligaban a deslizar para llegar a la que querías. Ahora cada sección grande es
// un ÁREA alcanzable de un clic; solo el área activa se renderiza → sin scroll largo:
//   • Feeds RSS — alta/edición de los feeds (con su salud inline).
//   • Catálogo  — feeds curados listos para activar de un clic.
//   • Salud     — monitor del motor de ingesta (activos/error/stale/huecos, reactivar).
//   • Buzones   — lo que pone el equipo: Presidencia + Cajones del día.
//   • Rendimiento — evaluación editorial por fuente (quién abre, % de uso).
const AREAS: Area[] = [
  { valor: "feeds", etiqueta: "Feeds RSS", icono: Rss },
  { valor: "catalogo", etiqueta: "Catálogo", icono: BookOpen },
  { valor: "salud", etiqueta: "Salud", icono: Activity },
  { valor: "buzones", etiqueta: "Buzones", icono: Inbox },
  { valor: "rendimiento", etiqueta: "Rendimiento", icono: TrendingUp },
];

// Deep-link de compatibilidad: las rutas viejas del hub (cajones/eventos) y los enlaces
// anteriores llegan con `?tab=externas|internas|rendimiento`. Mapeamos esos valores a las
// nuevas áreas para que NINGÚN enlace viejo caiga en blanco. ("externas" abría la primera
// sección externa = los feeds RSS; "internas" = los buzones del equipo).
const ALIAS_TAB: Record<string, string> = {
  externas: "feeds",
  internas: "buzones",
  rendimiento: "rendimiento",
};

/**
 * Página de Fuentes: ajustes de los canales de los que se alimentan Noticias y Contenidos,
 * ORGANIZADA POR ÁREAS. Una barra de áreas pegajosa arriba (siempre a mano); solo el área
 * activa se renderiza, así que no hay que deslizar para alcanzar la sección que buscas.
 */
export default function Fuentes() {
  // Las marcas y redes viven en el catálogo de opciones de publicaciones.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  // Área inicial: acepta tanto el valor nuevo (?tab=feeds…) como los alias viejos
  // (?tab=externas|internas). Cualquier otra cosa cae en "feeds".
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get("tab") ?? "";
  const areaInicial = AREAS.some((a) => a.valor === tabParam)
    ? tabParam
    : (ALIAS_TAB[tabParam] ?? "feeds");

  return (
    <Tabs defaultValue={areaInicial} className="space-y-4">
      {/* Barra de áreas PEGAJOSA arriba: siempre a mano. En pantallas estrechas hace scroll
          horizontal (overflow-x-auto) en vez de salirse o apretar los triggers. */}
      <TabsList className="sticky top-0 z-10 flex h-auto w-full justify-start gap-1 overflow-x-auto bg-background p-1">
        {AREAS.map((a) => {
          const Icono = a.icono;
          return (
            <TabsTrigger key={a.valor} value={a.valor} className="shrink-0 gap-1.5">
              <Icono className="h-4 w-4" />
              {a.etiqueta}
            </TabsTrigger>
          );
        })}
      </TabsList>

      {/* FEEDS RSS: alta/edición de los feeds (con su salud inline). */}
      <TabsContent value="feeds">
        <GestionFuentes marcas={marcas} />
      </TabsContent>

      {/* CATÁLOGO: feeds curados listos para activar de un clic. */}
      <TabsContent value="catalogo">
        <CatalogoPresets marcas={marcas} />
      </TabsContent>

      {/* SALUD: monitor del motor de ingesta (activos/error/stale, huecos, reactivar). */}
      <TabsContent value="salud">
        <SaludFeeds />
      </TabsContent>

      {/* BUZONES: lo que pone el equipo. La nota de Presidencia (carrusel automático) y los
          Cajones del día (Portal/Corresponsales/Reporteros/Eventos), filtrados por marca. */}
      <TabsContent value="buzones" className="space-y-8">
        <CajonPresidencia />
        <CajonesDia />
      </TabsContent>

      {/* RENDIMIENTO: qué fuentes aportan de verdad (abren historias, se usan). */}
      <TabsContent value="rendimiento">
        <RendimientoFuentes />
      </TabsContent>
    </Tabs>
  );
}
