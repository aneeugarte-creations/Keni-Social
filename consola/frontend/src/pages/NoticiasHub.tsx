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
import { Images, SlidersHorizontal } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { useSesion } from "@/hooks/sesion-contexto";

import Cobertura from "./Cobertura";

export default function NoticiasHub() {
  const navigate = useNavigate();
  const { usuario } = useSesion();
  const esAdmin = usuario === null || usuario.rol === "admin";
  return (
    <div className="space-y-4">
      {/* Acciones de hub → menú "⋮" de la barra: la receta de Noticias (galería internacional,
          el antiguo Termómetro) y, para admins, la subpágina de ajustes del motor de noticias. */}
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu icono={Images} onClick={() => navigate("/datos/investigacion/termometro")}>
            Armar galería internacional
          </ItemMenu>
          {esAdmin && (
            <ItemMenu
              icono={SlidersHorizontal}
              onClick={() => navigate("/datos/investigacion/ajustes")}
            >
              Ajustes del motor
            </ItemMenu>
          )}
        </MenuAcciones>
      </AccionesPagina>
      <Cobertura />
    </div>
  );
}
