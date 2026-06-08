import {
  ArrowDown,
  ArrowUp,
  ChevronsUpDown,
  Download,
  File,
  FileImage,
  Folder,
  Loader2,
  Trash2,
} from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { urlS3Objeto } from "@/lib/api";
import { formatearFecha } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { ObjetoS3 } from "@/types";

import { dirPorDefecto, esImagen, formatoBytes } from "./lib";
import type { ClaveOrden, OrdenS3 } from "./tipos";

/** Miniatura de una imagen del bucket (lazy). Si falla la carga, cae a un icono. */
function ThumbnailObjeto({ objeto }: { objeto: ObjetoS3 }) {
  const [error, setError] = React.useState(false);
  if (!esImagen(objeto.key) || error) {
    const Icono = esImagen(objeto.key) ? FileImage : File;
    return (
      <div className="flex h-12 w-12 items-center justify-center rounded-md border bg-muted/40">
        <Icono className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
      </div>
    );
  }
  return (
    <img
      src={urlS3Objeto(objeto.key)}
      alt={objeto.nombre}
      loading="lazy"
      onError={() => setError(true)}
      className="h-12 w-12 rounded-md border object-cover"
    />
  );
}

/** Cabecera de columna clicable que alterna el orden de la tabla. */
function CabeceraOrden({
  clave,
  etiqueta,
  orden,
  onOrden,
  alinearDerecha,
}: {
  clave: ClaveOrden;
  etiqueta: string;
  orden: OrdenS3 | null;
  onOrden: (o: OrdenS3) => void;
  alinearDerecha?: boolean;
}) {
  const activa = orden?.clave === clave;
  const Icono = !activa ? ChevronsUpDown : orden.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={() =>
        onOrden({
          clave,
          // Mismo campo: alterna dirección. Campo nuevo: dirección por defecto.
          dir: activa ? (orden.dir === "asc" ? "desc" : "asc") : dirPorDefecto(clave),
        })
      }
      className={cn(
        "inline-flex items-center gap-1 hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        activa ? "text-foreground" : "text-muted-foreground",
        alinearDerecha && "flex-row-reverse",
      )}
      aria-label={`Ordenar por ${etiqueta.toLowerCase()}`}
    >
      {etiqueta}
      <Icono className="h-3.5 w-3.5" aria-hidden="true" />
    </button>
  );
}

/** Tabla de carpetas y objetos del nivel actual del explorador S3. */
export function TablaObjetos({
  prefijo,
  carpetas,
  objetosOrdenados,
  hayObjetos,
  orden,
  onOrden,
  onNavegar,
  seleccion,
  todosSeleccionados,
  onAlternarUno,
  onAlternarTodos,
  onPreview,
  onBorrar,
  borrando,
  keyBorrando,
}: {
  prefijo: string;
  carpetas: string[];
  objetosOrdenados: ObjetoS3[];
  hayObjetos: boolean;
  orden: OrdenS3 | null;
  onOrden: (o: OrdenS3) => void;
  onNavegar: (prefijo: string) => void;
  seleccion: Set<string>;
  todosSeleccionados: boolean;
  onAlternarUno: (key: string) => void;
  onAlternarTodos: () => void;
  onPreview: (objeto: ObjetoS3) => void;
  onBorrar: (objeto: ObjetoS3) => void;
  borrando: boolean;
  keyBorrando: string | null;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-10">
            {hayObjetos && (
              <Checkbox
                checked={todosSeleccionados}
                onCheckedChange={onAlternarTodos}
                aria-label="Seleccionar todos los objetos"
              />
            )}
          </TableHead>
          <TableHead className="w-16" />
          <TableHead>
            <CabeceraOrden
              clave="nombre"
              etiqueta="Nombre"
              orden={orden}
              onOrden={onOrden}
            />
          </TableHead>
          <TableHead className="text-right">
            <CabeceraOrden
              clave="tamano"
              etiqueta="Tamaño"
              orden={orden}
              onOrden={onOrden}
              alinearDerecha
            />
          </TableHead>
          <TableHead className="hidden text-right sm:table-cell">
            <CabeceraOrden
              clave="modificado"
              etiqueta="Modificado"
              orden={orden}
              onOrden={onOrden}
              alinearDerecha
            />
          </TableHead>
          <TableHead className="w-20" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {/* Enlace ".." para subir un nivel */}
        {prefijo && (
          <TableRow
            className="cursor-pointer hover:bg-muted/50"
            onClick={() => {
              // Sube al nivel anterior: quita el último segmento del prefijo.
              const partes = prefijo.replace(/\/$/, "").split("/");
              partes.pop();
              onNavegar(partes.length > 0 ? `${partes.join("/")}/` : "");
            }}
          >
            <TableCell />
            <TableCell>
              <div className="flex h-12 w-12 items-center justify-center">
                <Folder className="h-5 w-5 text-blue-500" aria-hidden="true" />
              </div>
            </TableCell>
            <TableCell className="font-medium text-muted-foreground">..</TableCell>
            <TableCell />
            <TableCell className="hidden sm:table-cell" />
            <TableCell />
          </TableRow>
        )}

        {/* Subcarpetas */}
        {carpetas.map((carpeta) => {
          // Nombre legible: el ultimo segmento del prefijo (sin barra final).
          const nombre = carpeta.replace(/\/$/, "").split("/").pop() ?? carpeta;
          return (
            <TableRow
              key={carpeta}
              className="cursor-pointer hover:bg-muted/50"
              onClick={() => onNavegar(carpeta)}
            >
              <TableCell />
              <TableCell>
                <div className="flex h-12 w-12 items-center justify-center">
                  <Folder className="h-5 w-5 text-blue-500" aria-hidden="true" />
                </div>
              </TableCell>
              <TableCell className="font-medium">{nombre}/</TableCell>
              <TableCell className="text-right text-muted-foreground">—</TableCell>
              <TableCell className="hidden text-right text-muted-foreground sm:table-cell">
                —
              </TableCell>
              <TableCell />
            </TableRow>
          );
        })}

        {/* Objetos del nivel actual */}
        {objetosOrdenados.map((obj) => {
          const fechaCorta = obj.modificado ? formatearFecha(obj.modificado) : "—";
          const seleccionado = seleccion.has(obj.key);
          return (
            <TableRow
              key={obj.key}
              data-state={seleccionado ? "selected" : undefined}
              className="cursor-pointer hover:bg-muted/50 data-[state=selected]:bg-muted"
              onClick={() => onPreview(obj)}
            >
              <TableCell onClick={(e) => e.stopPropagation()}>
                <Checkbox
                  checked={seleccionado}
                  onCheckedChange={() => onAlternarUno(obj.key)}
                  aria-label={`Seleccionar ${obj.nombre}`}
                />
              </TableCell>
              <TableCell>
                <ThumbnailObjeto objeto={obj} />
              </TableCell>
              <TableCell className="font-medium">{obj.nombre}</TableCell>
              <TableCell className="text-right tabular-nums text-muted-foreground">
                {formatoBytes(obj.tamano)}
              </TableCell>
              <TableCell className="hidden text-right text-muted-foreground sm:table-cell">
                {fechaCorta}
              </TableCell>
              <TableCell>
                <div className="flex items-center justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Descargar ${obj.nombre}`}
                    onClick={(e) => {
                      // No abrir el preview al pulsar descargar.
                      e.stopPropagation();
                      window.open(
                        urlS3Objeto(obj.key, true),
                        "_blank",
                        "noopener,noreferrer",
                      );
                    }}
                  >
                    <Download className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Borrar ${obj.nombre}`}
                    disabled={borrando}
                    onClick={(e) => {
                      // No abrir el preview al pulsar borrar. Sin confirmación: borra directo.
                      e.stopPropagation();
                      onBorrar(obj);
                    }}
                  >
                    {keyBorrando === obj.key ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    ) : (
                      <Trash2
                        className="h-4 w-4 text-destructive"
                        aria-hidden="true"
                      />
                    )}
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
