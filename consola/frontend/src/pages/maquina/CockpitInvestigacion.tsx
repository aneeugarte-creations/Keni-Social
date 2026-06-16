import { ListChecks, Search } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Algoritmos from "@/pages/Algoritmos";
import Cobertura from "@/pages/Cobertura";
import ContenidosHub from "@/pages/ContenidosHub";
import Fuentes from "@/pages/Fuentes";
import { PanelInvestigacion } from "@/pages/configuracion/SeccionFuncionalidad";

/**
 * Cockpit OPERATIVO de INVESTIGACIÓN (`/maquina/investigacion`): el pool de noticias que el equipo
 * revisa a diario. Pestañas planas (`?seccion=`), cada una REUTILIZANDO una superficie existente:
 *   · NOTICIAS (`Cobertura`): el pool segmentado por líneas con usar/descartar — lo que el humano
 *     revisa. Es la pestaña por defecto. (La ruta vieja `/datos/investigacion` redirige aquí.)
 *   · FUENTES (`Fuentes`): los canales que alimentan el pool.
 *   · ALGORITMOS (`Algoritmos`): inteligencia de plataforma + trends.
 *   · CONTENIDOS (`ContenidosHub`): el banco EVERGREEN —piezas que no caducan—.
 *
 * El PIPELINE (recolectar → verificar) ya NO vive aquí: se enciende y se vigila en «Contexto»
 * (Máquina), donde cada fase trae su prompt, su contexto y sus logs. El menú «⋮» (oculto en
 * Algoritmos, que aporta el suyo) ofrece los ajustes del motor y un puente a Agentes prefiltrado.
 */

/** Pestañas del cockpit (clave `?seccion=`). Noticias (el pool) es la primera y la por defecto. */
type Seccion = "mesa" | "fuentes" | "algoritmos" | "contenidos";
const SECCIONES: readonly Seccion[] = ["mesa", "fuentes", "algoritmos", "contenidos"];

export default function CockpitInvestigacion() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const seccionParam = searchParams.get("seccion");
  const seccion: Seccion = SECCIONES.includes(seccionParam as Seccion)
    ? (seccionParam as Seccion)
    : "mesa";
  const cambiarSeccion = (valor: string) => {
    setSearchParams(
      (prev) => {
        prev.set("seccion", valor);
        return prev;
      },
      { replace: true },
    );
  };

  return (
    <>
      <TituloPagina titulo="Investigación" icono={Search} />
      {/* El menú propio del cockpit se oculta en la pestaña Algoritmos, que aporta el suyo
          (Refrescar…): así no se solapan dos «⋮» en la barra. */}
      {seccion !== "algoritmos" && (
        <AccionesPagina>
          <MenuAcciones ajustesTitulo="Ajustes de investigación" ajustes={<PanelInvestigacion />}>
            <ItemMenu icono={ListChecks} onClick={() => navigate("/maquina/computo?proceso=investigacion")}>
              Ver cómputo
            </ItemMenu>
          </MenuAcciones>
        </AccionesPagina>
      )}

      <Tabs value={seccion} onValueChange={cambiarSeccion}>
        <TabsList>
          <TabsTrigger value="mesa">Noticias</TabsTrigger>
          <TabsTrigger value="fuentes">Fuentes</TabsTrigger>
          <TabsTrigger value="algoritmos">Algoritmos</TabsTrigger>
          <TabsTrigger value="contenidos">Contenidos</TabsTrigger>
        </TabsList>

        {/* NOTICIAS: el pool con usar/descartar (Cobertura) — la pestaña por defecto. */}
        <TabsContent value="mesa">
          <Cobertura />
        </TabsContent>

        {/* FUENTES: los canales que alimentan el pool. */}
        <TabsContent value="fuentes">
          <Fuentes />
        </TabsContent>

        {/* ALGORITMOS: inteligencia de plataforma + trends. */}
        <TabsContent value="algoritmos">
          <Algoritmos />
        </TabsContent>

        {/* CONTENIDOS: el banco EVERGREEN (ContenidosHub). */}
        <TabsContent value="contenidos">
          <ContenidosHub />
        </TabsContent>
      </Tabs>
    </>
  );
}
