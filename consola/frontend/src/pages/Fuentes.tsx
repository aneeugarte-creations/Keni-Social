import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";

import { CatalogoPresets } from "./fuentes/CatalogoPresets";
// Descubrimiento: el canal AUTOMÁTICO (Google Trends), paralelo a las fuentes manuales (RSS).
import { Descubrimiento } from "./fuentes/Descubrimiento";
import { GestionFuentes } from "./fuentes/GestionFuentes";
// Salud del motor de ingesta de feeds: estado de los canales externos (feeds activos/
// con error, huecos, reactivar). Vive bajo "Externas".
import { RendimientoFuentes } from "./fuentes/RendimientoFuentes";
import { SaludFeeds } from "./fuentes/SaludFeeds";
// Buzones del equipo (listas tipo portal/WhatsApp/corresponsales y Excel): la fuente
// INTERNA. Compone la página de Cajones del día.
import CajonesDia from "./CajonesDia";
// Cajón PRESIDENCIA: la nota de WhatsApp de presidencia (texto + media) que genera sola
// una pieza CARRUSEL en el feed. Es un buzón aparte de los Cajones del día (no se parsea
// con IA: la nota va tal cual y el media adjunto ES el carrusel).
import CajonPresidencia from "./fuentes/CajonPresidencia";
// Cajón CLIPS (Claro Sports): el video/foto de WhatsApp que genera sola una pieza en el feed
// (video o carrusel). Hermano de Presidencia, pero para el material visual de Claro Sports.
import CajonClips from "./fuentes/CajonClips";

/** Una clase de fuente (pestaña). */
type PestanaTipo = {
  valor: string;
  etiqueta: string;
};

// Clases de fuente, y la barra lo refleja:
//   • Externas — feeds RSS manuales (+ catálogo) y el estado del motor.
//   • Descubrimiento — el canal AUTOMÁTICO (Google Trends), paralelo a las fuentes manuales.
//   • Internas — lo que pone el equipo: buzones del día (Cajones). (Las aportaciones manuales
//     "Idea" e "Interno AMX" se mudaron a Publicaciones, al banco de ideas evergreen.)
const PESTANAS_TIPO: PestanaTipo[] = [
  { valor: "externas", etiqueta: "Externas" },
  { valor: "descubrimiento", etiqueta: "Descubrimiento" },
  { valor: "internas", etiqueta: "Internas" },
  // Rendimiento: evaluación editorial de las fuentes (quién abre, quién corrobora, % uso).
  { valor: "rendimiento", etiqueta: "Rendimiento" },
];

/**
 * Página de Fuentes: ajustes de los canales de los que se alimentan Noticias y Publicaciones.
 * Dos clases, dos pestañas:
 *   • Externas — feeds RSS (alta/edición con salud inline), catálogo y estado del motor.
 *   • Internas — buzones del equipo (Cajones) y aportes a mano (idea/interno).
 */
export default function Fuentes() {
  // Las marcas y redes viven en el catálogo de opciones de piezas.
  const opcionesQuery = useQuery({
    queryKey: ["piezas", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  // Deep-link de pestaña: las rutas viejas del hub (cajones/agentes/eventos)
  // redirigen aquí con `?tab=` para abrir directamente su canal.
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  // Por defecto INTERNAS: el flujo DIARIO del equipo (volcar cajones y clips) vive ahí;
  // "Externas" son ajustes de RSS que se tocan de pascuas a ramos (deep-link ?tab=externas).
  const tabInicial = PESTANAS_TIPO.some((p) => p.valor === tabParam)
    ? (tabParam as string)
    : "internas";

  return (
    <>
      <Tabs defaultValue={tabInicial} className="space-y-4">
        <TabsList>
          {PESTANAS_TIPO.map((p) => (
            <TabsTrigger key={p.valor} value={p.valor}>
              {p.etiqueta}
            </TabsTrigger>
          ))}
        </TabsList>
        {/* EXTERNAS: feeds RSS manuales (alta/edición con su salud inline) + catálogo para
            añadir de un clic + estado del motor de ingesta. El canal automático (Google
            Trends) vive en su propia pestaña, Descubrimiento. */}
        <TabsContent value="externas" className="space-y-8">
          <GestionFuentes marcas={marcas} />
          <CatalogoPresets marcas={marcas} />
          <SaludFeeds />
        </TabsContent>
        {/* DESCUBRIMIENTO: el canal AUTOMÁTICO (Google Trends), paralelo a las fuentes
            manuales. Descubre temas calientes y vuelca una muestra al pool; el equipo los cura. */}
        <TabsContent value="descubrimiento" className="space-y-8">
          <Descubrimiento />
        </TabsContent>
        {/* INTERNAS: lo que pone el equipo. Buzones del día (listas tipo portal/WhatsApp/
            corresponsales y Excel), filtrados por la marca activa. Las aportaciones a mano
            ("Idea" e "Interno AMX") se mudaron a Publicaciones, fusionadas con el generador de ideas. */}
        <TabsContent value="internas" className="space-y-8">
          <CajonPresidencia />
          <CajonClips />
          <CajonesDia />
        </TabsContent>
        {/* RENDIMIENTO: qué fuentes aportan de verdad (abren historias, se usan). Alimenta
            la decisión de relevancia de cada fuente (pestaña Externas). */}
        <TabsContent value="rendimiento" className="space-y-8">
          <RendimientoFuentes />
        </TabsContent>
      </Tabs>
    </>
  );
}
