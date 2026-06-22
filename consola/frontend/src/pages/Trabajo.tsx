/**
 * Trabajo — el destino del equipo para «qué hay que hacer y quién lo coge»: eventos editoriales,
 * tareas y su cobertura (Panorama · Mis tareas · Por cubrir). Es el plano de COBERTURA, hermano
 * del calendario de turnos (CAPACIDAD): éste mira el trabajo; «Calendario» (`/operacion/turnos`)
 * mira el horario. Reúne el mismo tablero (`TareasBoard`) que antes vivía como pestaña dentro de
 * Turnos, ahora con entrada propia en el sidebar.
 */
import { ClipboardList } from "lucide-react";

import { TituloPagina } from "@/components/layout/encabezado";
import { TareasBoard } from "@/pages/tareas/Tareas";

export default function Trabajo() {
  return (
    <>
      <TituloPagina titulo="Trabajo" icono={ClipboardList} />
      <TareasBoard />
    </>
  );
}
