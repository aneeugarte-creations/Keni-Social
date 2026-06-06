/**
 * NoticiasHub — pieza «Noticias» del hub Investigación e ÍNDICE del hub (Fase 1).
 *
 * Noticias = items informativos/temporales a publicar (agencias, RSS ajenos,
 * reporteros, corresponsales). Caducan. Su núcleo operativo es el POOL persistente
 * del motor de ingesta (lo que hoy es `Cobertura`): el flujo continuo de noticias
 * a publicar. La parte de descubrimiento/plan del día (`Investigador`) se conserva
 * como segunda vista para no perder esa superficie durante la transición.
 *
 * Decisión de diseño (Fase 1 = esqueleto): este hub COMPONE los componentes
 * existentes sin reescribir su lógica. Cada vista trae su propia cabecera y sus
 * propios filtros; aquí solo se conmuta entre ellas. Fases posteriores fusionarán
 * ambas superficies en una sola.
 */
import { Images } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import Cobertura from "./Cobertura";
import Investigador from "./Investigador";

export default function NoticiasHub() {
  const [vista, setVista] = React.useState("pool");

  return (
    <div className="space-y-4">
      {/* Receta de Noticias: armar la galería internacional (el antiguo Termómetro,
          que dejó de ser pestaña al colapsar el hub a 3 piezas). */}
      <div className="flex items-center justify-end">
        <Button asChild variant="outline" size="sm">
          <Link to="/datos/investigacion/termometro">
            <Images className="mr-2 h-4 w-4" aria-hidden="true" />
            Armar galería internacional
          </Link>
        </Button>
      </div>
      <Tabs value={vista} onValueChange={setVista} className="space-y-4">
        <TabsList>
          {/* Núcleo: el pool persistente de noticias a publicar. */}
          <TabsTrigger value="pool">Pool de noticias</TabsTrigger>
          {/* Descubrimiento + plan del día (el antiguo Investigador). */}
          <TabsTrigger value="descubrimiento">Descubrimiento</TabsTrigger>
        </TabsList>
        <TabsContent value="pool">
          <Cobertura />
        </TabsContent>
        <TabsContent value="descubrimiento">
          <Investigador />
        </TabsContent>
      </Tabs>
    </div>
  );
}
