#!/usr/bin/env node
// Renderizador determinista de la plantilla de marca (canvas-2D, @napi-rs/canvas).
//
// Lo invoca el back/worker por subproceso desde Python (dominio/estudio_imagen.py), igual que
// el motor Pillow. Protocolo:
//   - argv: `--salida <out.png>`
//   - stdin: un objeto JSON `{spec, formato, placeholder, foto|null, assets:{logo,fondo}, bindings}`
//   - salida: escribe el PNG en `out.png` (rc 0). En error: stderr + rc≠0.
//   - imprime `DATOS {json}` por stdout (diagnóstico; Python usa rc0 + archivo).
//
// El render real lo hace `dibujar.mjs` (compartido como única fuente de verdad). Aquí solo se
// registran fuentes, se cargan las imágenes y se vuelca el PNG.

import { createCanvas, loadImage } from "@napi-rs/canvas";
import { writeFileSync } from "node:fs";
import process from "node:process";

import { dibujarSpec } from "./dibujar.mjs";
import { registrarFuentes, familiaReal } from "./fuentes.mjs";

function arg(nombre) {
  const i = process.argv.indexOf(nombre);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : null;
}

async function leerStdin() {
  const trozos = [];
  for await (const t of process.stdin) trozos.push(t);
  return Buffer.concat(trozos).toString("utf-8");
}

async function cargar(ruta) {
  if (!ruta) return null;
  try { return await loadImage(ruta); } catch { return null; }
}

async function main() {
  const salida = arg("--salida");
  if (!salida) { process.stderr.write("Falta --salida\n"); return 2; }

  let payload;
  try {
    payload = JSON.parse(await leerStdin());
  } catch (e) {
    process.stderr.write("Payload JSON inválido: " + e.message + "\n");
    return 2;
  }

  const spec = payload.spec || {};
  const nombreFmt = payload.formato || "feed";
  const formato = (spec.formatos || {})[nombreFmt];
  if (!formato) { process.stderr.write(`Formato '${nombreFmt}' ausente en el spec\n`); return 2; }

  registrarFuentes();

  const imgs = {
    foto: payload.placeholder ? null : await cargar(payload.foto),
    logo: await cargar(payload.assets?.logo),
    fondo: await cargar(payload.assets?.fondo),
  };

  const { w, h } = formato.lienzo;
  const canvas = createCanvas(w, h);
  const ctx = canvas.getContext("2d");

  dibujarSpec(ctx, {
    formato,
    fuentes: spec.fuentes,
    bindings: payload.bindings || {},
    placeholder: !!payload.placeholder,
    imgs,
    familiaReal: (logica) => familiaReal(spec.fuentes, logica),
  });

  writeFileSync(salida, canvas.toBuffer("image/png"));
  process.stdout.write(
    "DATOS " + JSON.stringify({
      salida, formato: nombreFmt, tamano: `${w}x${h}`,
      placeholder: !!payload.placeholder,
    }) + "\n",
  );
  return 0;
}

main().then((c) => process.exit(c)).catch((e) => {
  process.stderr.write("Error de render: " + (e?.stack || e) + "\n");
  process.exit(1);
});
