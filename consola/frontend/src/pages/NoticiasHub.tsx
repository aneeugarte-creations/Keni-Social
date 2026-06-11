/**
 * NoticiasHub — pieza «Noticias» del hub Investigación e ÍNDICE del hub.
 *
 * Noticias = items informativos/temporales a publicar (agencias, RSS ajenos,
 * reporteros, corresponsales). Caducan. Su única superficie es el POOL persistente
 * del motor de ingesta (`Cobertura`): el flujo continuo de noticias, donde las
 * Historias ya vienen ordenadas por señal/breaking — eso ES el descubrimiento. El
 * antiguo "Descubrimiento" en vivo (Radar v1: Google Trends + plan del día) se
 * retiró; el pool persistente es la única fuente de verdad de la ingesta.
 *
 * El armado MANUAL del Termómetro (galería internacional) también se retiró: la
 * galería se genera sola por el pipeline. Las acciones de página que queden las
 * portaliza `Cobertura` a su menú "⋮"; aquí solo viven los AJUSTES del motor (admin).
 */
import { AjustesPagina } from "@/components/layout/AjustesPagina";
import { AccionesPagina } from "@/components/layout/encabezado";
import { useSesion } from "@/hooks/sesion-contexto";
import { PanelAjustes } from "@/pages/configuracion/SeccionFuncionalidad";

import Cobertura from "./Cobertura";

// Los grupos del catálogo del motor de noticias (`ajustes_catalogo.GRUPOS_NOTICIAS`) REAGRUPADOS
// en cuatro ÁREAS colapsables de capa base, por afinidad editorial: entrada → orden/prioridad del
// pool → producción automática → técnico. Cada área lista sus grupos en este orden; la primera
// abre desplegada. El grupo `noticias_produccion_marca` (PLAN diario por marca) NO se pinta aquí:
// su editor único es el diálogo «Plan y horarios» de Programación (mismas claves `KENI_PLAN_DIA::
// marca`, pero con cupo + horarios en un formulario, en vez del texto crudo «mx:4,intl:4,…»).
const AREAS_NOTICIAS = [
  {
    titulo: "Entrada al pool",
    descripcion: "Qué noticias entran (filtro por temas, fuentes caídas) y su traducción.",
    grupos: ["noticias_entrada"],
    abiertaInicial: true,
  },
  {
    titulo: "Orden y prioridad del pool",
    descripcion:
      "Cómo se ordenan las historias: pesos del score, qué cuenta como última hora y el empujón a lo que mejor funciona en redes.",
    grupos: ["noticias_orden", "noticias_breaking", "noticias_rendimiento"],
    abiertaInicial: false,
  },
  {
    titulo: "Producción automática",
    descripcion:
      "Cuándo una historia dispara copy con IA: listón, maduración y cupos globales. El plan diario POR MARCA se edita en Programación → «Plan y horarios» (cupo y horarios, con buen formulario).",
    grupos: ["noticias_produccion"],
    abiertaInicial: false,
  },
  {
    titulo: "Técnico · capacidad y ritmo del motor",
    descripcion:
      "Cuánto trabajo hace el motor en cada ronda. Los valores por defecto van bien; tócalos solo si se queda corto o gasta de más.",
    grupos: ["noticias_tecnico"],
    abiertaInicial: false,
  },
] as const;

export default function NoticiasHub() {
  const { usuario } = useSesion();
  const esAdmin = usuario === null || usuario.rol === "admin";
  return (
    <div className="space-y-4">
      {/* Reparto canónico de cabecera: los AJUSTES del motor de noticias al panel lateral
          (solo admin). Las ACCIONES de página (p. ej. «Borrar todo») las aporta `Cobertura`
          al mismo hueco, en su menú "⋮". */}
      {esAdmin && (
        <AccionesPagina>
          <AjustesPagina
            titulo="Ajustes del motor de noticias"
            descripcion="Controlan qué noticias entran al pool, en qué orden se muestran y cuáles disparan producción automática. Los cambios aplican al momento (hasta ~1 minuto)."
          >
            {AREAS_NOTICIAS.map((area) => (
              <PanelAjustes
                key={area.titulo}
                titulo={area.titulo}
                descripcion={area.descripcion}
                grupos={area.grupos}
                abiertaInicial={area.abiertaInicial}
              />
            ))}
          </AjustesPagina>
        </AccionesPagina>
      )}
      <Cobertura />
    </div>
  );
}
