// Dibujo determinista de un FORMATO del spec sobre un contexto canvas-2D.
//
// Es la ÚNICA fuente de verdad del render: el servidor (@napi-rs/canvas) lo usa para producir
// el PNG final, y el editor muestra una "vista real" pidiendo ese mismo render al servidor. No
// depende de napi ni del DOM: recibe el `ctx`, las imágenes ya cargadas y un resolutor de
// familia de fuente. Coordenadas en px sobre el lienzo del formato.

const GRIS_PLACEHOLDER = "#3f4246"; // == (63,66,70) de lienzo_placeholder (Pillow)
const BORDE_PLACEHOLDER = "#969a9e"; // == (150,154,158)

// Modo de fusión por capa (etiqueta interna en español -> `globalCompositeOperation` del canvas).
// "normal" / ausente => "source-over" (idéntico al render legado, retrocompatible). Compartido por
// el editor (Konva) y este render para que la previa y el export coincidan.
export const MAPA_MEZCLA = {
  normal: "source-over",
  multiplicar: "multiply",
  trama: "screen",
  superponer: "overlay",
  aclarar: "lighten",
  oscurecer: "darken",
};

// Familias del catálogo CON cara ITÁLICA real registrada en AMBOS lados (TTF *Italic* en el
// servidor/`fuentes.mjs` y webfont itálica en el editor). Única fuente de verdad cliente/servidor:
// el editor deshabilita el botón de cursiva fuera de esta lista y ambos renders IGNORAN el flag
// para el resto (Skia no sintetiza oblicuas, y una oblicua sintética del navegador rompería la
// regla previa==export). Anton/Archivo Black/Oswald y las tipografías propias de marca (un solo
// TTF, sin cara itálica) quedan fuera.
export const FAMILIAS_CON_CURSIVA = ["Barlow", "Barlow Condensed", "Montserrat", "Lora", "Exo 2", "Lato"];

// ¿La familia REAL (ya resuelta por `familiaReal`) tiene itálica registrada?
export function tieneCursiva(familia) {
  return FAMILIAS_CON_CURSIVA.includes(familia);
}

function hexRGBA(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  // Hex de 8 dígitos (#RRGGBBAA): el par alfa multiplica el `alpha` recibido.
  if (hex.length >= 9) alpha *= parseInt(hex.slice(7, 9), 16) / 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

// Crea un degradado LINEAL `desde -> hasta` que abarca la caja (x,y,w,h) según `angulo` (grados).
// CONVENCIÓN (igual que CSS linear-gradient): ángulo medido en sentido horario desde ARRIBA.
//   0° = ↑ (de abajo hacia arriba)   90° = → (izquierda a derecha)
//   180° = ↓ (arriba hacia abajo, VERTICAL — el default histórico del fondo)   270° = ← (derecha a izquierda)
// El eje del degradado pasa por el centro de la caja; los extremos se proyectan sobre ese eje de
// modo que el degradado cubra toda la caja. La misma convención la usan el fondo, el texto y el marco.
function gradienteLineal(ctx, x, y, w, h, desde, hasta, angulo) {
  const a = ((angulo ?? 180) * Math.PI) / 180;
  // Vector unitario de la dirección del degradado (0°=arriba, horario).
  const ux = Math.sin(a), uy = -Math.cos(a);
  const cx = x + w / 2, cy = y + h / 2;
  // Mitad de la proyección de la caja sobre el eje (cubre las 4 esquinas).
  const semi = (Math.abs(w * ux) + Math.abs(h * uy)) / 2;
  const g = ctx.createLinearGradient(cx - ux * semi, cy - uy * semi, cx + ux * semi, cy + uy * semi);
  g.addColorStop(0, desde);
  g.addColorStop(1, hasta);
  return g;
}

// Lista de paradas [pos,color] de un degradado `deg`: usa `stops` (multi-parada) si viene válido,
// si no cae a `desde`/`hasta` (2 paradas 0/1). Retrocompat: sin `stops` == comportamiento legado.
function paradasDegradado(deg) {
  const stops = Array.isArray(deg.stops) ? deg.stops.filter((s) => s && typeof s.color === "string") : null;
  if (stops && stops.length >= 2) {
    return stops
      .map((s) => [Math.max(0, Math.min(1, Number(s.pos) || 0)), s.color])
      .sort((a, b) => a[0] - b[0]);
  }
  return [[0, deg.desde], [1, deg.hasta]];
}

// Construye un gradiente canvas (lineal o radial) que abarca la caja (x,y,w,h) a partir de un
// objeto degradado `deg` = {tipo?, desde, hasta, angulo?, stops?}. ÚNICA fuente de verdad de los
// degradados de texto/marco/fondo. Lineal: misma convención/eje que `gradienteLineal`. Radial:
// centrado en la caja, radio = mitad de la diagonal (cubre las esquinas). Las paradas salen de
// `paradasDegradado` (multi-stop si viene, si no desde/hasta). Retrocompat: tipo ausente => lineal.
function construirDegradado(ctx, x, y, w, h, deg) {
  const paradas = paradasDegradado(deg);
  let g;
  if (deg.tipo === "radial") {
    const cx = x + w / 2, cy = y + h / 2;
    const r = Math.sqrt(w * w + h * h) / 2;
    g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
  } else {
    const a = ((deg.angulo ?? 180) * Math.PI) / 180;
    const ux = Math.sin(a), uy = -Math.cos(a);
    const cx = x + w / 2, cy = y + h / 2;
    const semi = (Math.abs(w * ux) + Math.abs(h * uy)) / 2;
    g = ctx.createLinearGradient(cx - ux * semi, cy - uy * semi, cx + ux * semi, cy + uy * semi);
  }
  for (const [pos, color] of paradas) g.addColorStop(pos, color);
  return g;
}

// Reparte un texto en líneas que caben en `maxAncho` (greedy por palabras).
function envolver(ctx, texto, maxAncho) {
  const out = [];
  for (const parrafo of String(texto).split("\n")) {
    const palabras = parrafo.split(/\s+/).filter(Boolean);
    if (palabras.length === 0) { out.push(""); continue; }
    let linea = palabras[0];
    for (let i = 1; i < palabras.length; i++) {
      const cand = linea + " " + palabras[i];
      if (ctx.measureText(cand).width <= maxAncho) linea = cand;
      else { out.push(linea); linea = palabras[i]; }
    }
    out.push(linea);
  }
  return out;
}

// Baja el tamaño hasta que el texto cabe en ancho×alto y ≤ max_lineas (espejo de ajustar_titular).
function ajustar(ctx, texto, maxAncho, maxAlto, fontFor, tamMax, tamMin, maxLineas, interlineado) {
  for (let tam = tamMax; tam >= tamMin; tam -= 2) {
    ctx.font = fontFor(tam);
    const lineas = envolver(ctx, texto, maxAncho);
    const altoLinea = Math.round(tam * interlineado);
    if (lineas.length <= maxLineas && (!maxAlto || lineas.length * altoLinea <= maxAlto)) {
      return { tam, lineas, altoLinea };
    }
  }
  ctx.font = fontFor(tamMin);
  let lineas = envolver(ctx, texto, maxAncho).slice(0, maxLineas);
  if (lineas.length) lineas[lineas.length - 1] = lineas[lineas.length - 1].replace(/\s+$/, "") + "…";
  return { tam: tamMin, lineas, altoLinea: Math.round(tamMin * interlineado) };
}

// Catálogo de FORMAS compartido (marcos e imágenes). Traza en el path ACTUAL de `ctx` la silueta
// de `forma` inscrita en la caja (x,y,w,h). Es la ÚNICA fuente de verdad de las formas: lo usan el
// clip de la imagen (`dibujarImagenEnCaja`) y el relleno/borde del marco (`dibujarMarco`), y el
// editor (Konva) replica el mismo trazado en coords locales. `radio`/`radios` solo afectan a "rect"
// (radio uniforme o cuádruple [tl,tr,br,bl] por esquina; `radios` manda sobre `radio`).
// Retrocompat: "rect" sin radio == ctx.rect; "elipse" == ctx.ellipse de siempre.
function pathForma(ctx, forma, x, y, w, h, radio, radios) {
  const cx = x + w / 2, cy = y + h / 2;
  // Polígono regular de `n` lados inscrito en la caja (radio = w/2,h/2), con el primer vértice
  // ARRIBA (ángulo -90°). Cierra el path.
  const poligono = (n, rot = -Math.PI / 2) => {
    for (let i = 0; i < n; i++) {
      const a = rot + (i * 2 * Math.PI) / n;
      const px = cx + (w / 2) * Math.cos(a);
      const py = cy + (h / 2) * Math.sin(a);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
  };
  switch (forma) {
    case "elipse":
      ctx.ellipse(cx, cy, w / 2, h / 2, 0, 0, Math.PI * 2);
      return;
    case "triangulo":
      ctx.moveTo(cx, y);
      ctx.lineTo(x + w, y + h);
      ctx.lineTo(x, y + h);
      ctx.closePath();
      return;
    case "rombo":
      ctx.moveTo(cx, y);
      ctx.lineTo(x + w, cy);
      ctx.lineTo(cx, y + h);
      ctx.lineTo(x, cy);
      ctx.closePath();
      return;
    case "pentagono":
      poligono(5);
      return;
    case "hexagono":
      poligono(6);
      return;
    case "estrella": {
      // Estrella de 5 puntas: alterna radio externo (1) e interno (0.5) sobre la caja.
      const puntas = 5;
      for (let i = 0; i < puntas * 2; i++) {
        const a = -Math.PI / 2 + (i * Math.PI) / puntas;
        const rf = i % 2 === 0 ? 1 : 0.5;
        const px = cx + (w / 2) * rf * Math.cos(a);
        const py = cy + (h / 2) * rf * Math.sin(a);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      return;
    }
    case "flecha": {
      // Flecha hacia la derecha: cuerpo (40% del alto) + cabeza triangular (último 40% del ancho).
      const yTop = y + h * 0.3, yBot = y + h * 0.7;
      const xCabeza = x + w * 0.6;
      ctx.moveTo(x, yTop);
      ctx.lineTo(xCabeza, yTop);
      ctx.lineTo(xCabeza, y);
      ctx.lineTo(x + w, cy);
      ctx.lineTo(xCabeza, y + h);
      ctx.lineTo(xCabeza, yBot);
      ctx.lineTo(x, yBot);
      ctx.closePath();
      return;
    }
    default: {
      // "rect" (y cualquier desconocida): rectángulo, redondeado si `radio>0` o si hay `radios`.
      const hayRadios = Array.isArray(radios) && radios.some((r) => r > 0);
      if (radio > 0 || hayRadios) rutaRect(ctx, x, y, w, h, radio, radios);
      else ctx.rect(x, y, w, h);
    }
  }
}

// Normaliza un recorte (crop) no destructivo a píxeles de la imagen FUENTE. `crop` = {cx,cy,cw,ch}
// en fracciones 0..1 del rectángulo fuente. Sin crop (o inválido) => toda la imagen (retrocompat).
function rectFuente(img, crop) {
  const iw = img.width, ih = img.height;
  if (!crop) return { sx: 0, sy: 0, sw: iw, sh: ih };
  const cx = Math.max(0, Math.min(1, Number(crop.cx) || 0));
  const cy = Math.max(0, Math.min(1, Number(crop.cy) || 0));
  const cw = Math.max(0, Math.min(1 - cx, crop.cw == null ? 1 : Number(crop.cw)));
  const ch = Math.max(0, Math.min(1 - cy, crop.ch == null ? 1 : Number(crop.ch)));
  if (cw <= 0 || ch <= 0) return { sx: 0, sy: 0, sw: iw, sh: ih };
  return { sx: cx * iw, sy: cy * ih, sw: cw * iw, sh: ch * ih };
}

// `forma`/`radio`/`radios` (opcionales) definen el RECORTE-FORMA de la imagen: el catálogo de formas
// (rect con esquinas, elipse, triángulo, rombo, polígonos, estrella, flecha). `crop` recorta la
// FUENTE (sub-rect, no destructivo). `duotono` mapea la luminancia entre dos colores tras pintar.
// Sin forma/crop/duotono => rectángulo de siempre (llamadores existentes => idéntico).
function dibujarImagenEnCaja(ctx, img, x, y, w, h, ajuste, foco, zoom, forma, radio, radios, crop, duotono) {
  if (!img) return;
  // Imagen EFECTIVA = sub-rect fuente recortado (crop). El cover/contain se calcula sobre sus dims.
  const { sx, sy, sw, sh } = rectFuente(img, crop);
  const iw = sw, ih = sh;
  const z = zoom && zoom > 0 ? zoom : 1; // reencuadre: factor de acercamiento dentro del marco
  const base = ajuste === "contain" ? Math.min(w / iw, h / ih) : Math.max(w / iw, h / ih);
  const escala = base * z;
  const dw = iw * escala, dh = ih * escala;
  const fx = foco ? foco[0] : 0.5, fy = foco ? foco[1] : 0.45;
  const dx = x + (w - dw) * fx;
  const dy = y + (h - dh) * fy;
  const duo = duotono && duotono.luz && duotono.sombra ? duotono : null;
  ctx.save();
  ctx.beginPath();
  pathForma(ctx, forma, x, y, w, h, radio, radios);
  ctx.clip();
  // DUOTONO: la foto se pinta en GRIS (grayscale) para mapear su LUMINANCIA; luego dos capas de
  // color la tiñen entre `sombra` (luminancia baja) y `luz` (alta). Anteponemos grayscale(1) al
  // filtro CSS ya activo (brillo/contraste…). Sin duotono el filtro queda como lo dejó el llamador.
  const filtroPrevio = duo ? ctx.filter : null;
  if (duo) ctx.filter = `grayscale(1)${ctx.filter && ctx.filter !== "none" ? " " + ctx.filter : ""}`;
  // 9 args: recorta la fuente [sx,sy,sw,sh] y la pinta en el destino [dx,dy,dw,dh].
  ctx.drawImage(img, sx, sy, sw, sh, dx, dy, dw, dh);
  if (duo) ctx.filter = filtroPrevio;
  // Tinte de marca sobre la foto en gris, RECORTADO a la forma (seguimos dentro del clip):
  //   1) "multiply" con `luz`  -> oscurece hacia el color de luz manteniendo la estructura,
  //   2) "lighten" con `sombra`-> levanta las sombras al color de sombra.
  // Aproxima un duotono real (suficiente para un tinte de marca sobre foto).
  if (duo) {
    const duotono = duo;
    const prev = ctx.globalCompositeOperation;
    ctx.globalCompositeOperation = "multiply";
    ctx.fillStyle = duotono.luz;
    ctx.beginPath();
    pathForma(ctx, forma, x, y, w, h, radio, radios);
    ctx.fill();
    ctx.globalCompositeOperation = "lighten";
    ctx.fillStyle = duotono.sombra;
    ctx.beginPath();
    pathForma(ctx, forma, x, y, w, h, radio, radios);
    ctx.fill();
    ctx.globalCompositeOperation = prev;
  }
  ctx.restore();
}

function dibujarPlaceholder(ctx, w, h) {
  ctx.fillStyle = GRIS_PLACEHOLDER;
  ctx.fillRect(0, 0, w, h);
  const cx = Math.floor(w / 2), cy = Math.floor(h / 2);
  const lado = Math.floor(Math.min(w, h) * 0.3);
  ctx.strokeStyle = BORDE_PLACEHOLDER;
  ctx.lineWidth = 4;
  ctx.setLineDash([14, 14]);
  ctx.strokeRect(cx - lado, cy - lado, lado * 2, lado * 2);
  ctx.setLineDash([]);
  ctx.fillStyle = BORDE_PLACEHOLDER;
  ctx.font = `700 ${Math.max(28, Math.floor(Math.min(w, h) * 0.05))}px "Barlow"`;
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.fillText("Sube una foto", cx, cy - lado - 40);
  ctx.textAlign = "left";
}

function dibujarFondo(ctx, fondo, w, h, fondoImg) {
  if (!fondo) return;
  if (fondo.tipo === "color") {
    ctx.fillStyle = fondo.color;
    ctx.fillRect(0, 0, w, h);
  } else if (fondo.tipo === "degradado") {
    // Default vertical (ángulo 180 = ↓): equivalente al render legado top->bottom. Soporta tipo
    // lineal/radial y multi-stop vía `construirDegradado`.
    ctx.fillStyle = construirDegradado(ctx, 0, 0, w, h, fondo.degradado);
    ctx.fillRect(0, 0, w, h);
  } else if (fondo.tipo === "imagen" && fondoImg) {
    dibujarImagenEnCaja(ctx, fondoImg, 0, 0, w, h, fondo.imagen.ajuste || "cover", [0.5, 0.5]);
  }
}

// Banda de degradado de legibilidad pegada al borde INFERIOR de la caja (x,y,w,h). La caja es el
// LIENZO completo en el render legado (`dibujarSpec`, x=y=0) o la caja de la propia capa overlay en
// el documento (`dibujarCapa`), que la posiciona DENTRO de su caja (espejo de `CapaNodo`: la banda
// va a `y + h - band`, no a coords de lienzo). Retrocompat: un overlay a (0,0,W,H) => banda idéntica
// a la histórica (0, H-band, W, band).
function dibujarOverlayInferior(ctx, ov, x, y, w, h) {
  if (!ov) return;
  const band = Math.max(1, Math.floor(h * (ov.alto_frac ?? 0.58)));
  const g = ctx.createLinearGradient(0, y + h - band, 0, y + h);
  // rampa t**1.5 sobre alpha máx (paridad con degradado_inferior de Pillow).
  const aMax = (ov.alpha ?? 238) / 255;
  for (let i = 0; i <= 10; i++) {
    const t = i / 10;
    g.addColorStop(t, hexRGBA(ov.color || "#111315", aMax * Math.pow(t, 1.5)));
  }
  ctx.fillStyle = g;
  ctx.fillRect(x, y + h - band, w, band);
}

// Dibuja UNA línea de texto a lo largo de un ARCO (texto curvo). El texto se trata como una sola
// línea (se ignoran wrap/justificado en este modo). `radio` en px: positivo = arco hacia arriba
// (sonrisa, centro del círculo DEBAJO del ancla), negativo = hacia abajo (ceño, centro ENCIMA).
// Cada glyph se mide con `ctx.measureText` para avanzar el ángulo (longitud de arco = ancho del
// glyph) y se rota tangente al arco. Respeta alineación horizontal (centrado del texto en el arco),
// color/relleno (sólido o degradado), contorno y sombra (real si blur/opacidad). Mantiene la
// interletra ya fijada por el llamador. El punto de anclaje es el `tx` del camino normal.
function dibujarTextoCurvo(ctx, t, texto, radio, fontFor, relleno, sombra, contorno) {
  ctx.font = fontFor(t.tamano);
  const ax = t.alineacion === "centro" ? t.x + t.w / 2 : t.alineacion === "derecha" ? t.x + t.w : t.x;
  // Ancla vertical: en el camino normal el texto crece desde `t.y` (baseline "top"). Mantenemos el
  // arco tangente a esa línea en el punto de anclaje.
  const ay = t.y;
  // Glyphs y sus anchos (incluida la interletra ya activa en el ctx vía measureText).
  const glyphs = Array.from(texto);
  const anchos = glyphs.map((g) => ctx.measureText(g).width);
  const total = anchos.reduce((s, w) => s + w, 0);
  const r = Math.abs(radio);
  const arriba = radio > 0; // arco "sonrisa" (centro debajo) vs "ceño" (centro encima)
  // Centro del círculo, perpendicular al ancla. Arriba: centro debajo del ancla; abajo: encima.
  const cx = ax;
  const cy = arriba ? ay + r : ay - r;
  // Ángulo total que ocupa el texto (long. de arco / radio). Lo centramos en la vertical del ancla.
  const angTotal = total / r;
  // Punto medio del texto sobre el arco, según alineación horizontal: centro = vertical del ancla;
  // izquierda = el texto empieza en la vertical; derecha = termina en ella.
  const angMedio = -Math.PI / 2; // arriba del centro = vertical del ancla (en coords del círculo)
  let ang;
  if (t.alineacion === "centro") ang = angMedio - (arriba ? angTotal / 2 : -angTotal / 2);
  else if (t.alineacion === "derecha") ang = angMedio - (arriba ? angTotal : -angTotal);
  else ang = angMedio;
  const sombraReal = sombra && ((sombra.desenfoque ?? 0) > 0 || (sombra.opacidad ?? 1) < 1);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  // Dirección de avance del ángulo: arco arriba avanza en sentido horario (+), abajo antihorario (-).
  const dir = arriba ? 1 : -1;
  for (let i = 0; i < glyphs.length; i++) {
    const wg = anchos[i];
    // Centro del glyph: medio paso de su propio ancho desde el cursor.
    const aMid = ang + dir * (wg / 2) / r;
    const gx = cx + r * Math.cos(aMid);
    const gy = cy + r * Math.sin(aMid);
    // Tangente al arco: arriba el texto mira "hacia afuera" (rotación = aMid + 90°); abajo se
    // invierte para que el texto no quede boca abajo.
    const rot = arriba ? aMid + Math.PI / 2 : aMid - Math.PI / 2;
    ctx.save();
    ctx.translate(gx, gy);
    ctx.rotate(rot);
    if (sombraReal) {
      ctx.shadowColor = hexRGBA(sombra.color || "#000000", sombra.opacidad ?? 1);
      ctx.shadowBlur = sombra.desenfoque ?? 0;
      ctx.shadowOffsetX = sombra.dx ?? 0;
      ctx.shadowOffsetY = sombra.dy ?? 0;
      if (contorno) {
        ctx.lineJoin = "round";
        ctx.lineWidth = contorno.grosor;
        ctx.strokeStyle = contorno.color || "#000000";
        ctx.strokeText(glyphs[i], 0, 0);
        resetSombraCanvas(ctx);
      }
      ctx.fillStyle = relleno;
      ctx.fillText(glyphs[i], 0, 0);
      resetSombraCanvas(ctx);
    } else {
      if (sombra) {
        ctx.fillStyle = sombra.color || "#000000";
        ctx.fillText(glyphs[i], (sombra.dx ?? 2), (sombra.dy ?? 2));
      }
      if (contorno) {
        ctx.lineJoin = "round";
        ctx.lineWidth = contorno.grosor;
        ctx.strokeStyle = contorno.color || "#000000";
        ctx.strokeText(glyphs[i], 0, 0);
      }
      ctx.fillStyle = relleno;
      ctx.fillText(glyphs[i], 0, 0);
    }
    ctx.restore();
    ang += dir * wg / r;
  }
}

function dibujarTexto(ctx, t, valor, fuentes, familiaReal) {
  const texto = (t.mayusculas ? String(valor).toUpperCase() : String(valor)).trim();
  if (!texto) return; // binding vacío (p. ej. pleca "" ) => se omite la capa
  const familia = familiaReal(t.familia);
  // CURSIVA: el prefijo `italic` solo si la familia REAL tiene itálica registrada (espejo del
  // botón del editor). Para el resto el flag se ignora: nunca se sintetizan oblicuas.
  const cursiva = t.cursiva && tieneCursiva(familia) ? "italic " : "";
  const fontFor = (tam) => `${cursiva}${t.peso || 700} ${Math.round(tam)}px "${familia}"`;
  const aj = t.auto_ajuste || { max_lineas: 4, tam_min: 40 };
  // Interletra (letter-spacing): la fija ANTES de medir para que el wrap/chip cuadre. La soportan
  // tanto el canvas del navegador como @napi-rs/canvas (Skia). Se restablece al final.
  const interletra = t.interletra || 0;
  if (interletra) ctx.letterSpacing = `${interletra}px`;
  // TEXTO CURVO (texto en arco): si la capa trae `curva.radio != 0`, dibujamos una sola línea sobre
  // un arco (sin wrap ni justificado) y salimos. El relleno (sólido o degradado), contorno y sombra
  // se calculan igual que el camino normal, sobre el bbox de la caja. Sin `curva` => camino legado.
  if (t.curva && t.curva.radio) {
    const rdC = t.relleno_degradado || null;
    const rellenoC = rdC ? construirDegradado(ctx, t.x, t.y, t.w, t.tamano, rdC) : t.color;
    const contornoC = t.contorno && t.contorno.grosor > 0 ? t.contorno : null;
    dibujarTextoCurvo(ctx, t, texto, t.curva.radio, fontFor, rellenoC, t.sombra || null, contornoC);
    if (interletra) ctx.letterSpacing = "0px";
    return;
  }
  // CAJA de alto fijo (modo nuevo): si la capa trae `h>0`, el texto se auto-encoge para caber en
  // ancho Y alto (pasamos `maxAlto = boxH`). Si `h<=0` (plantillas legadas), seguimos como antes:
  // el texto solo se limita por ancho y nº de líneas, y el bloque se ancla por `ancla`.
  const boxH = t.h > 0 ? t.h : null;
  const { tam, lineas, altoLinea } = ajustar(
    ctx, texto, t.w, boxH || 0, fontFor, t.tamano, aj.tam_min, aj.max_lineas, t.interlineado || 1.14,
  );
  // Contorno del texto (legibilidad sobre fotos): se traza DEBAJO del relleno.
  const contorno = t.contorno && t.contorno.grosor > 0 ? t.contorno : null;
  ctx.textBaseline = "top";
  ctx.textAlign = t.alineacion === "centro" ? "center" : t.alineacion === "derecha" ? "right" : "left";
  const tx = t.alineacion === "centro" ? t.x + t.w / 2 : t.alineacion === "derecha" ? t.x + t.w : t.x;

  // Alto total del bloque (con el padding del chip arriba y abajo si hay chip).
  const py = t.chip ? (t.chip.pad_y ?? 14) : 0;
  const blockH = lineas.length * altoLinea + (t.chip ? py * 2 : 0);
  let top;
  if (boxH) {
    // CAJA inamovible [t.y, t.y+boxH]: posicionamos el bloque dentro según `valign` (con respaldo
    // a `ancla` si falta: "abajo"->"abajo", si no "arriba"). El texto ya cabe (se encogió).
    const valign = (t.valign === "arriba" || t.valign === "centro" || t.valign === "abajo")
      ? t.valign
      : (t.ancla === "abajo" ? "abajo" : "arriba");
    top = valign === "centro" ? t.y + (boxH - blockH) / 2
      : valign === "abajo" ? t.y + boxH - blockH
      : t.y;
  } else {
    // LEGADO (h<=0, sin caja): por defecto el bloque crece hacia ABAJO desde `t.y` (su borde
    // superior). Con `ancla: "abajo"`, `t.y` es el borde INFERIOR y el bloque crece hacia ARRIBA:
    // así un titular de 1 o de 4 líneas queda siempre pegado al borde inferior seguro.
    top = t.ancla === "abajo" ? t.y - blockH : t.y;
  }

  // Relleno del texto: color sólido o degradado lineal (abarcando el bbox del bloque). El degradado
  // sustituye al color sólido cuando `relleno_degradado` está presente (aditivo y retrocompatible).
  const rd = t.relleno_degradado || null;
  const relleno = rd
    ? construirDegradado(ctx, t.x, top, t.w, blockH, rd)
    : t.color;
  // SOMBRA REAL del canvas (blur/opacidad): solo cuando hay desenfoque>0 u opacidad<1. Si no, se
  // mantiene el camino legado (fillText manual desplazado) para que las placas existentes queden
  // pixel-idénticas. Un "glow" = sombra con dx=dy=0 y desenfoque alto (no necesita tipo aparte).
  const sombra = t.sombra || null;
  const sombraReal = sombra && ((sombra.desenfoque ?? 0) > 0 || (sombra.opacidad ?? 1) < 1);

  let y = top + py;
  const justif = t.alineacion === "justificado";
  for (let i = 0; i < lineas.length; i++) {
    const ln = lineas[i];
    const ultima = i === lineas.length - 1;
    // Chip POR LÍNEA: el fondo se ajusta al ancho de ESA línea, así CRECE con el texto y
    // cubre TODAS las líneas (antes solo la primera).
    if (t.chip && ln.trim()) {
      dibujarChipLinea(ctx, t, ctx.measureText(ln).width, y, altoLinea, tx);
    }
    // SUBRAYADO y TACHADO: líneas decorativas por CADA línea de texto, ANTES de los glifos (mismo
    // orden que el `textDecoration` de Konva, cuya geometría espeja `dibujarDecoracionLinea`:
    // subrayado a `altoLinea/2 + round(tam/2)` del tope de la línea; tachado a MEDIA altura,
    // `altoLinea/2`). El texto curvo no se decora en ninguno de los dos lados (el camino curvo
    // retorna antes de llegar aquí).
    if (t.subrayado && ln.trim()) {
      dibujarDecoracionLinea(ctx, t, ln, y + altoLinea / 2 + Math.round(tam / 2), tam, tx, relleno, sombra, sombraReal, justif && !ultima);
    }
    if (t.tachado && ln.trim()) {
      dibujarDecoracionLinea(ctx, t, ln, y + altoLinea / 2, tam, tx, relleno, sombra, sombraReal, justif && !ultima);
    }
    if (justif && !ultima) {
      dibujarLineaJustificada(ctx, ln, t.x, y, t.w, relleno, sombra, contorno);
    } else {
      const lx = justif ? t.x : tx;
      if (sombraReal) {
        // Sombra real: blur, offset y opacidad nativos del canvas. Orden = contorno DEBAJO del
        // relleno (como el camino legado y el `fillAfterStrokeEnabled` de Konva). La sombra la
        // proyecta el PRIMER trazo pintado y se resetea antes del relleno para no duplicarla.
        ctx.shadowColor = hexRGBA(sombra.color || "#000000", sombra.opacidad ?? 1);
        ctx.shadowBlur = sombra.desenfoque ?? 0;
        ctx.shadowOffsetX = sombra.dx ?? 0;
        ctx.shadowOffsetY = sombra.dy ?? 0;
        if (contorno) {
          ctx.lineJoin = "round";
          ctx.lineWidth = contorno.grosor;
          ctx.strokeStyle = contorno.color || "#000000";
          ctx.strokeText(ln, lx, y);
          // Reset SOLO si ya hubo sombra (la pintó el contorno); el relleno va limpio encima.
          ctx.shadowColor = "transparent";
          ctx.shadowBlur = 0;
          ctx.shadowOffsetX = 0;
          ctx.shadowOffsetY = 0;
        }
        // Sin contorno la sombra sigue activa y la proyecta el relleno (glow sobre el texto).
        ctx.fillStyle = relleno;
        ctx.fillText(ln, lx, y);
        ctx.shadowColor = "transparent";
        ctx.shadowBlur = 0;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 0;
      } else {
        if (sombra) {
          ctx.fillStyle = sombra.color || "#000000";
          ctx.fillText(ln, lx + (sombra.dx ?? 2), y + (sombra.dy ?? 2));
        }
        if (contorno) {
          ctx.lineJoin = "round";
          ctx.lineWidth = contorno.grosor;
          ctx.strokeStyle = contorno.color || "#000000";
          ctx.strokeText(ln, lx, y);
        }
        // Camino legado: el relleno se pinta encima del contorno.
        ctx.fillStyle = relleno;
        ctx.fillText(ln, lx, y);
      }
    }
    y += altoLinea;
  }
  if (interletra) ctx.letterSpacing = "0px";
}

// Subraya o tacha UNA línea de texto: traza una línea horizontal a la altura `uy` (px de lienzo,
// la calcula el llamador). ESPEJO de la geometría del `textDecoration` de Konva Text ("underline"
// a `altoLinea/2 + round(tam/2)` del tope de la línea; "line-through" a media altura,
// `altoLinea/2`): grosor `tam/15`, color del relleno (sólido o degradado), con el ancho MEDIDO de
// la línea según la alineación — salvo en justificado, donde las líneas no-últimas se decoran a
// todo el ancho de la caja (`anchoCompleto`). La sombra sigue el mismo doble camino que el texto:
// LEGADA = copia desplazada en el color de la sombra; REAL = la proyecta el propio trazo
// (blur/opacidad nativos).
function dibujarDecoracionLinea(ctx, t, ln, uy, tam, tx, relleno, sombra, sombraReal, anchoCompleto) {
  const ancho = anchoCompleto ? t.w : ctx.measureText(ln).width;
  const x = t.alineacion === "centro" ? tx - ancho / 2
    : t.alineacion === "derecha" ? tx - ancho
    : t.x;
  const traza = (dx, dy, color) => {
    ctx.beginPath();
    ctx.moveTo(x + dx, uy + dy);
    ctx.lineTo(x + Math.round(ancho) + dx, uy + dy);
    ctx.lineWidth = tam / 15;
    ctx.strokeStyle = color;
    ctx.stroke();
  };
  if (sombraReal) {
    ctx.shadowColor = hexRGBA(sombra.color || "#000000", sombra.opacidad ?? 1);
    ctx.shadowBlur = sombra.desenfoque ?? 0;
    ctx.shadowOffsetX = sombra.dx ?? 0;
    ctx.shadowOffsetY = sombra.dy ?? 0;
    traza(0, 0, relleno);
    resetSombraCanvas(ctx);
    return;
  }
  if (sombra) traza(sombra.dx ?? 2, sombra.dy ?? 2, sombra.color || "#000000");
  traza(0, 0, relleno);
}

// Dibuja el chip (fondo/pleca) de UNA línea de texto, ajustado a su ancho. `lineTop` es la
// y (baseline "top") de la línea; el chip se centra verticalmente alrededor de ella.
function dibujarChipLinea(ctx, t, lineWidth, lineTop, altoLinea, tx) {
  const px = t.chip.pad_x ?? 24, py = t.chip.pad_y ?? 14;
  const chipW = lineWidth + px * 2;
  const chipH = altoLinea + py;
  const topY = lineTop - py / 2;
  const chipX = t.alineacion === "derecha" ? tx - chipW
    : t.alineacion === "centro" ? tx - chipW / 2 : t.x;
  ctx.fillStyle = t.chip.color;
  const r = t.chip.radio || 0;
  if (r) {
    ctx.beginPath();
    ctx.moveTo(chipX + r, topY);
    ctx.arcTo(chipX + chipW, topY, chipX + chipW, topY + chipH, r);
    ctx.arcTo(chipX + chipW, topY + chipH, chipX, topY + chipH, r);
    ctx.arcTo(chipX, topY + chipH, chipX, topY, r);
    ctx.arcTo(chipX, topY, chipX + chipW, topY, r);
    ctx.closePath();
    ctx.fill();
  } else {
    ctx.fillRect(chipX, topY, chipW, chipH);
  }
}

// Dibuja una línea con las palabras repartidas para llenar `ancho` (justificado). Una palabra
// suelta cae a la izquierda. textAlign se fuerza a "left" (posicionamos cada palabra a mano).
function dibujarLineaJustificada(ctx, linea, x, y, ancho, relleno, sombra, contorno) {
  const palabras = linea.split(/\s+/).filter(Boolean);
  ctx.textAlign = "left";
  const sombraReal = sombra && ((sombra.desenfoque ?? 0) > 0 || (sombra.opacidad ?? 1) < 1);
  const pinta = (txt, px) => {
    if (sombraReal) {
      // Sombra real: contorno DEBAJO del relleno; la sombra la proyecta el primer trazo y se
      // resetea antes del relleno (paridad con `dibujarTexto` y `fillAfterStrokeEnabled` de Konva).
      ctx.shadowColor = hexRGBA(sombra.color || "#000000", sombra.opacidad ?? 1);
      ctx.shadowBlur = sombra.desenfoque ?? 0;
      ctx.shadowOffsetX = sombra.dx ?? 0;
      ctx.shadowOffsetY = sombra.dy ?? 0;
      if (contorno) {
        ctx.lineJoin = "round";
        ctx.lineWidth = contorno.grosor;
        ctx.strokeStyle = contorno.color || "#000000";
        ctx.strokeText(txt, px, y);
        ctx.shadowColor = "transparent";
        ctx.shadowBlur = 0;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 0;
      }
      ctx.fillStyle = relleno;
      ctx.fillText(txt, px, y);
      ctx.shadowColor = "transparent";
      ctx.shadowBlur = 0;
      ctx.shadowOffsetX = 0;
      ctx.shadowOffsetY = 0;
    } else {
      if (sombra) {
        ctx.fillStyle = sombra.color || "#000000";
        ctx.fillText(txt, px + (sombra.dx ?? 2), y + (sombra.dy ?? 2));
      }
      if (contorno) {
        ctx.lineJoin = "round";
        ctx.lineWidth = contorno.grosor;
        ctx.strokeStyle = contorno.color || "#000000";
        ctx.strokeText(txt, px, y);
      }
      ctx.fillStyle = relleno;
      ctx.fillText(txt, px, y);
    }
  };
  if (palabras.length <= 1) {
    pinta(linea, x);
    return;
  }
  const anchoPalabras = palabras.reduce((s, p) => s + ctx.measureText(p).width, 0);
  const hueco = (ancho - anchoPalabras) / (palabras.length - 1);
  let cx = x;
  for (const p of palabras) {
    pinta(p, cx);
    cx += ctx.measureText(p).width + hueco;
  }
}

function dibujarLogo(ctx, logo, logoImg, fuentes, familiaReal) {
  if (!logo) return;
  if (logo.tipo === "imagen" && logoImg) {
    dibujarImagenEnCaja(ctx, logoImg, logo.x, logo.y, logo.w, logo.h, "contain", [0.5, 0.5]);
    return;
  }
  // Wordmark de respaldo: chip de color con el texto.
  const wm = logo.wordmark || {};
  const texto = (wm.texto || "").trim();
  if (!texto) return;
  const familia = familiaReal(wm.familia || "sans");
  const tam = Math.round(logo.h * 0.42);
  ctx.font = `${wm.peso || 700} ${tam}px "${familia}"`;
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  const m = ctx.measureText(texto);
  const padX = 20, padY = 12;
  ctx.fillStyle = wm.fondo || "#E30613";
  ctx.fillRect(logo.x, logo.y, m.width + padX * 2, tam + padY * 2);
  ctx.fillStyle = wm.color || "#FFFFFF";
  ctx.fillText(texto, logo.x + padX, logo.y + padY);
}

// Dibuja el formato completo. `imgs` = {foto, logo, fondo} ya cargadas (o null).
export function dibujarSpec(ctx, { formato, fuentes, bindings, placeholder, imgs, familiaReal }) {
  const { lienzo } = formato;
  const w = lienzo.w, h = lienzo.h;
  const F = familiaReal || ((l) => (l === "condensada" ? "Barlow Condensed" : "Barlow"));
  const B = bindings || {};
  const I = imgs || {};

  // 1) Fondo + foto (o placeholder gris si no hay foto).
  if (placeholder || !I.foto) {
    if (placeholder) dibujarPlaceholder(ctx, w, h);
    else dibujarFondo(ctx, formato.fondo, w, h, I.fondo);
  } else {
    dibujarFondo(ctx, formato.fondo, w, h, I.fondo);
    const s = formato.foto_slot;
    dibujarImagenEnCaja(ctx, I.foto, s.x, s.y, s.w, s.h, s.ajuste || "cover", s.foco, s.zoom);
  }

  // 2) Overlay de legibilidad (solo si hay textos visibles, como en Pillow).
  const hayTitular = (formato.textos || []).some((t) => {
    const v = t.binding === "copy_in" ? B.copy_in : t.binding === "etiqueta_default" ? B.etiqueta_default : t.texto;
    return String(v || "").trim();
  });
  if (hayTitular && !placeholder) dibujarOverlayInferior(ctx, formato.overlay_inferior, 0, 0, w, h);
  else if (placeholder) dibujarOverlayInferior(ctx, formato.overlay_inferior, 0, 0, w, h);

  // 3) Capas de texto + logo, por z-order.
  const capas = [];
  for (const t of formato.textos || []) {
    const v = t.binding === "copy_in" ? B.copy_in : t.binding === "etiqueta_default" ? B.etiqueta_default : t.texto;
    capas.push({ z: t.z ?? 20, draw: () => dibujarTexto(ctx, t, v ?? "", fuentes, F) });
  }
  capas.push({ z: formato.logo?.z ?? 30, draw: () => dibujarLogo(ctx, formato.logo, I.logo, fuentes, F) });
  capas.sort((a, b) => a.z - b.z);
  for (const c of capas) c.draw();
}

// ===========================================================================
// Render del DOCUMENTO de capas (editor profesional). Misma rutina canvas-2D,
// pero sobre una lista de capas arbitrarias en vez de slots fijos. Comparte
// TODOS los dibujantes de arriba: única fuente de verdad cliente/servidor.
// ===========================================================================

// Normaliza el radio de esquinas a un cuádruple [tl,tr,br,bl]. `radios` (si viene como array de 4)
// manda sobre el `radio` uniforme. Cada esquina se acota a la mitad del lado menor de la caja.
function radiosEsquina(radio, radios, w, h) {
  const lim = Math.min(w / 2, h / 2);
  const r4 = Array.isArray(radios) && radios.length === 4
    ? radios
    : [radio || 0, radio || 0, radio || 0, radio || 0];
  return r4.map((r) => Math.max(0, Math.min(Number(r) || 0, lim)));
}

// Traza un rectángulo en el path actual. `r` puede ser un número (radio uniforme) o un cuádruple
// [tl,tr,br,bl] (radio por esquina). Sin radio (0 o todos 0) traza un rect plano (retrocompat).
function rutaRect(ctx, x, y, w, h, r, radios) {
  const [tl, tr, br, bl] = radiosEsquina(r, radios, w, h);
  if (!tl && !tr && !br && !bl) { ctx.rect(x, y, w, h); return; }
  ctx.moveTo(x + tl, y);
  ctx.arcTo(x + w, y, x + w, y + h, tr);
  ctx.arcTo(x + w, y + h, x, y + h, br);
  ctx.arcTo(x, y + h, x, y, bl);
  ctx.arcTo(x, y, x + w, y, tl);
  ctx.closePath();
}

// Cadena CSS `filter` para una capa imagen (brillo/contraste/saturación/desenfoque). El navegador
// la respeta siempre; @napi-rs/canvas la aplica si su build lo soporta (si no, la ignora).
function cssFiltro(f) {
  if (!f) return "";
  const partes = [];
  if (f.brillo != null && f.brillo !== 1) partes.push(`brightness(${f.brillo})`);
  if (f.contraste != null && f.contraste !== 1) partes.push(`contrast(${f.contraste})`);
  if (f.saturacion != null && f.saturacion !== 1) partes.push(`saturate(${f.saturacion})`);
  if (f.desenfoque) partes.push(`blur(${f.desenfoque}px)`);
  return partes.join(" ");
}

// Aplica la sombra REAL del canvas a partir de una capa `sombra` (envuelve un dibujo) y devuelve
// true si quedó activa (para resetearla después). Si no hay sombra, no toca nada.
function aplicarSombraCanvas(ctx, sombra) {
  if (!sombra) return false;
  ctx.shadowColor = hexRGBA(sombra.color || "#000000", sombra.opacidad ?? 1);
  ctx.shadowBlur = sombra.desenfoque ?? 0;
  ctx.shadowOffsetX = sombra.dx ?? 0;
  ctx.shadowOffsetY = sombra.dy ?? 0;
  return true;
}

function resetSombraCanvas(ctx) {
  ctx.shadowColor = "transparent";
  ctx.shadowBlur = 0;
  ctx.shadowOffsetX = 0;
  ctx.shadowOffsetY = 0;
}

function dibujarMarco(ctx, m) {
  const { x, y, w, h } = m;
  const conSombra = aplicarSombraCanvas(ctx, m.sombra);
  if (m.forma === "linea") {
    if (m.borde && m.borde.grosor > 0) {
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + w, y + h);
      ctx.lineWidth = m.borde.grosor;
      ctx.strokeStyle = m.borde.color || "#000000";
      ctx.stroke();
    }
    if (conSombra) resetSombraCanvas(ctx);
    return;
  }
  ctx.beginPath();
  // Catálogo de formas compartido (rect/redondeado, elipse, triángulo, rombo, polígonos, estrella,
  // flecha). "linea" se trata arriba; aquí van las formas con relleno/borde. `radios` (por esquina)
  // manda sobre `radio` en el rect.
  pathForma(ctx, m.forma, x, y, w, h, m.radio || 0, m.radios);
  // Relleno: degradado (lineal o radial, multi-stop) si `relleno_degradado`, si no el color sólido.
  if (m.relleno_degradado) {
    ctx.fillStyle = construirDegradado(ctx, x, y, w, h, m.relleno_degradado);
    ctx.fill();
  } else if (m.relleno) {
    ctx.fillStyle = m.relleno;
    ctx.fill();
  }
  if (m.borde && m.borde.grosor > 0) {
    ctx.lineWidth = m.borde.grosor;
    ctx.strokeStyle = m.borde.color || "#000000";
    ctx.stroke();
  }
  if (conSombra) resetSombraCanvas(ctx);
}

// VOLTEO (flip) de una capa imagen/logo: espejo alrededor del CENTRO de su caja. `flip_h` invierte
// izquierda<->derecha (scale(-1,1)), `flip_v` arriba<->abajo (scale(1,-1)). Compone con la rotación
// ya activa (se aplica dentro del mismo save/restore) y con el recorte por forma (la silueta se
// voltea junto al contenido). La SOMBRA de la imagen NO se voltea (se pinta antes): la dirección de
// luz es fija. Espejo del editor (Konva/CapaNodo), que aplica el mismo espejo con offset al centro.
function aplicarFlip(ctx, capa) {
  const sx = capa.flip_h ? -1 : 1;
  const sy = capa.flip_v ? -1 : 1;
  if (sx === 1 && sy === 1) return;
  const cx = capa.x + capa.w / 2, cy = capa.y + capa.h / 2;
  ctx.translate(cx, cy);
  ctx.scale(sx, sy);
  ctx.translate(-cx, -cy);
}

// Dibuja UNA capa (con su opacidad/rotación). `env` = {I: imágenes por objeto/media_id, B: bindings,
// F: familiaReal, final: boolean}.
//
// `visible: false` es una AYUDA DE EDICIÓN (ocultar una capa para ver fondos/transparencias detrás),
// NO una propiedad de la imagen final. Por eso solo se respeta en la PREVIA de edición (`env.final`
// falsy); en el render FINAL (`env.final === true`, p.ej. el PNG que hornea el servidor) TODAS las
// capas se pintan, incluidas las de grupos ocultos (el flag se propaga por `env` en la recursión).
function dibujarCapa(ctx, capa, env) {
  if (!env.final && capa.visible === false) return;
  ctx.save();
  const op = capa.opacidad ?? 1;
  if (op < 1) ctx.globalAlpha = op;
  // Modo de fusión de la capa: sin `mezcla` (o "normal") => "source-over" (idéntico al legado).
  const gco = MAPA_MEZCLA[capa.mezcla] || "source-over";
  if (gco !== "source-over") ctx.globalCompositeOperation = gco;
  const rot = capa.rotacion || 0;
  if (rot) {
    // Pivote de rotación IGUAL que el editor (Konva/CapaNodo): la esquina superior izquierda
    // (x,y) de la capa. EXCEPCIÓN: el marco ELIPSE, que Konva posiciona por su CENTRO y por tanto
    // rota alrededor del centro. Sin esto, una capa rotada (p. ej. una línea horizontal a 90°)
    // caía en otro sitio en el render final que en el lienzo: el pivote central mandaba la línea
    // vertical al centro del lienzo (de ahí el marco que salía como una "+").
    const elipse = capa.tipo === "marco" && capa.forma === "elipse";
    const cx = elipse ? capa.x + capa.w / 2 : capa.x;
    const cy = elipse ? capa.y + capa.h / 2 : capa.y;
    ctx.translate(cx, cy);
    ctx.rotate((rot * Math.PI) / 180);
    ctx.translate(-cx, -cy);
  }
  switch (capa.tipo) {
    case "imagen": {
      const img = env.I[capa.objeto];
      const filtro = cssFiltro(capa.filtros);
      if (filtro) ctx.filter = filtro;
      // Sombra de la capa imagen: cae sobre la SILUETA de la imagen (su forma). Como la imagen se
      // recorta a su caja (la sombra del drawImage quedaría dentro del clip y no se vería), pintamos
      // primero la silueta con la sombra activa, y luego la imagen recortada SIN sombra encima. La
      // silueta sigue la forma (elipse/redondeado/rect) para que la sombra cuadre con la foto.
      if (capa.sombra && img) {
        aplicarSombraCanvas(ctx, capa.sombra);
        ctx.fillStyle = "#000000";
        ctx.beginPath();
        // La silueta de la sombra sigue la FORMA de la imagen (mismo catálogo que su recorte).
        pathForma(ctx, capa.forma, capa.x, capa.y, capa.w, capa.h, capa.radio, capa.radios);
        ctx.fill();
        resetSombraCanvas(ctx);
      }
      // VOLTEO: espejo del contenido (clip+foto) alrededor del centro, tras pintar la sombra.
      aplicarFlip(ctx, capa);
      dibujarImagenEnCaja(ctx, img, capa.x, capa.y, capa.w, capa.h, capa.ajuste || "cover", capa.foco, capa.zoom, capa.forma, capa.radio, capa.radios, capa.crop, capa.filtros ? capa.filtros.duotono : null);
      if (filtro) ctx.filter = "none";
      break;
    }
    case "texto": {
      const v = capa.binding === "copy_in" ? env.B.copy_in
        : capa.binding === "etiqueta_default" ? env.B.etiqueta_default : capa.texto;
      dibujarTexto(ctx, capa, v ?? "", null, env.F);
      break;
    }
    case "logo":
      // `dibujarLogo` espera `logo.tipo` ∈ {imagen,wordmark}; en el documento ese campo es
      // `tipo_logo` (porque `tipo` ya es "logo"). Adaptamos sin tocar el dibujante compartido.
      // VOLTEO: espejo del logo (imagen o wordmark) alrededor del centro de su caja.
      aplicarFlip(ctx, capa);
      dibujarLogo(ctx, { ...capa, tipo: capa.tipo_logo }, env.I[capa.media_id], null, env.F);
      break;
    case "marco":
      dibujarMarco(ctx, capa);
      break;
    case "overlay":
      // La banda se posiciona DENTRO de la caja de la capa (x, y+h-band): `dibujarCapa` ya aplicó el
      // translate/rotate del pivote como en las demás capas, así un overlay movido/rotado cae en el
      // mismo sitio que el editor (Konva). Retrocompat: overlay a (0,0,W,H) => banda histórica.
      dibujarOverlayInferior(ctx, capa, capa.x, capa.y, capa.w, capa.h);
      break;
    case "grupo":
      for (const sub of capa.capas || []) dibujarCapa(ctx, sub, env);
      break;
    default:
      break;
  }
  ctx.restore();
}

// Dibuja un DOCUMENTO completo. `imgs` = mapa {objeto|media_id -> Image cargada (o null)}.
// `final: true` => render del PÍXEL FINAL: ignora `visible` y pinta TODAS las capas (el ocultar es
// solo ayuda de edición). Sin `final` (default) es la PREVIA de edición y respeta `visible`.
export function dibujarDocumento(ctx, { documento, imgs, bindings, familiaReal, final }) {
  const F = familiaReal || ((l) => (l === "condensada" ? "Barlow Condensed" : "Barlow"));
  const env = { I: imgs || {}, B: bindings || {}, F, final: final === true };
  const { formato, fondo } = documento;
  const w = formato.w, h = formato.h;

  const fondoImg = fondo && fondo.tipo === "imagen" ? env.I[(fondo.imagen || {}).media_id] : null;
  dibujarFondo(ctx, fondo, w, h, fondoImg);

  const capas = [...(documento.capas || [])].sort((a, b) => (a.z ?? 0) - (b.z ?? 0));
  for (const capa of capas) dibujarCapa(ctx, capa, env);
}
