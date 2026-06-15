import { Newspaper, Trophy } from "lucide-react";

/**
 * ¿El título parece un PARTIDO (deporte)? Los partidos se nombran «Equipo vs Equipo»
 * (p. ej. «España vs Cabo Verde»); las noticias y demás coberturas, no. No hay un campo
 * de disciplina en el evento, así que distinguimos por el patrón « vs » del título
 * (admite «vs», «VS» y «vs.»).
 */
export function esPartido(titulo: string): boolean {
  return /\svs\.?\s/i.test(titulo ?? "");
}

/**
 * Icono de una cobertura: la COPA solo para partidos de fútbol/deporte; para el resto
 * (noticias en UnoTV, y cualquier cobertura no-partido en Claro Sports) un PERIÓDICO.
 */
export function IconoEvento({ titulo, className }: { titulo: string; className?: string }) {
  const partido = esPartido(titulo);
  const Icono = partido ? Trophy : Newspaper;
  return <Icono className={className} aria-label={partido ? "Partido" : "Noticia"} />;
}
