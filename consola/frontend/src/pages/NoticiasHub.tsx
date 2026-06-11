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
 * El Termómetro (galería internacional) se arma desde el botón de receta.
 */
import { Images } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { AjustesPagina } from "@/components/layout/AjustesPagina";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { useSesion } from "@/hooks/sesion-contexto";
import { SeccionesAjustes } from "@/pages/configuracion/SeccionFuncionalidad";

import Cobertura from "./Cobertura";

// Grupos del catálogo que gobiernan el motor de noticias (espejan
// `ajustes_catalogo.GRUPOS_NOTICIAS` del backend), en lenguaje editorial:
// qué entra → orden → rendimiento → última hora → producción + bloque técnico.
const GRUPOS_NOTICIAS = new Set([
  "noticias_entrada",
  "noticias_orden",
  "noticias_rendimiento",
  "noticias_breaking",
  "noticias_produccion",
  "noticias_produccion_marca",
  "noticias_tecnico",
]);

export default function NoticiasHub() {
  const navigate = useNavigate();
  const { usuario } = useSesion();
  const esAdmin = usuario === null || usuario.rol === "admin";
  return (
    <div className="space-y-4">
      {/* Reparto canónico de cabecera: ACCIONES de hub al menú "⋮" (la receta de Noticias:
          galería internacional, el antiguo Termómetro) y, para admins, los AJUSTES del motor
          de noticias al panel lateral (antes una subpágina propia). */}
      <AccionesPagina>
        <div className="flex items-center gap-1">
          {esAdmin && (
            <AjustesPagina
              titulo="Ajustes del motor de noticias"
              descripcion="Controlan qué noticias entran al pool, en qué orden se muestran y cuáles disparan producción automática. Los cambios aplican al momento (hasta ~1 minuto)."
            >
              <SeccionesAjustes ids={GRUPOS_NOTICIAS} />
            </AjustesPagina>
          )}
          <MenuAcciones>
            <ItemMenu icono={Images} onClick={() => navigate("/datos/investigacion/termometro")}>
              Armar galería internacional
            </ItemMenu>
          </MenuAcciones>
        </div>
      </AccionesPagina>
      <Cobertura />
    </div>
  );
}
