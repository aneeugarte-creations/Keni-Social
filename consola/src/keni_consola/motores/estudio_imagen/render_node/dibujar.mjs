// Dibujo determinista de un FORMATO del spec sobre un contexto canvas-2D.
//
// Es la ÚNICA fuente de verdad del render: el servidor (@napi-rs/canvas) lo usa para producir
// el PNG final, y el editor muestra una "vista real" pidiendo ese mismo render al servidor. No
// depende de napi ni del DOM: recibe el `ctx`, las imágenes ya cargadas y un resolutor de
// familia de fuente. Coordenadas en px sobre el lienzo del formato.

const GRIS_PLACEHOLDER = "#3f4246"; // == (63,66,70) de lienzo_placeholder (Pillow)
const BORDE_PLACEHOLDER = "#969a9e"; // == (150,154,158)

function hexRGBA(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
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

function dibujarImagenEnCaja(ctx, img, x, y, w, h, ajuste, foco) {
  if (!img) return;
  const iw = img.width, ih = img.height;
  const escala = ajuste === "contain" ? Math.min(w / iw, h / ih) : Math.max(w / iw, h / ih);
  const dw = iw * escala, dh = ih * escala;
  const fx = foco ? foco[0] : 0.5, fy = foco ? foco[1] : 0.45;
  const dx = x + (w - dw) * fx;
  const dy = y + (h - dh) * fy;
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();
  ctx.drawImage(img, dx, dy, dw, dh);
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
    const g = ctx.createLinearGradient(0, 0, 0, h); // vertical (ángulo 180 por defecto)
    g.addColorStop(0, fondo.degradado.desde);
    g.addColorStop(1, fondo.degradado.hasta);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  } else if (fondo.tipo === "imagen" && fondoImg) {
    dibujarImagenEnCaja(ctx, fondoImg, 0, 0, w, h, fondo.imagen.ajuste || "cover", [0.5, 0.5]);
  }
}

function dibujarOverlayInferior(ctx, ov, w, h) {
  if (!ov) return;
  const band = Math.max(1, Math.floor(h * (ov.alto_frac ?? 0.58)));
  const g = ctx.createLinearGradient(0, h - band, 0, h);
  // rampa t**1.5 sobre alpha máx (paridad con degradado_inferior de Pillow).
  const aMax = (ov.alpha ?? 238) / 255;
  for (let i = 0; i <= 10; i++) {
    const t = i / 10;
    g.addColorStop(t, hexRGBA(ov.color || "#111315", aMax * Math.pow(t, 1.5)));
  }
  ctx.fillStyle = g;
  ctx.fillRect(0, h - band, w, band);
}

function dibujarTexto(ctx, t, valor, fuentes, familiaReal) {
  const texto = (t.mayusculas ? String(valor).toUpperCase() : String(valor)).trim();
  if (!texto) return; // binding vacío (p. ej. pleca "" ) => se omite la capa
  const familia = familiaReal(t.familia);
  const fontFor = (tam) => `${t.peso || 700} ${Math.round(tam)}px "${familia}"`;
  const aj = t.auto_ajuste || { max_lineas: 4, tam_min: 40 };
  const { lineas, altoLinea } = ajustar(
    ctx, texto, t.w, 0, fontFor, t.tamano, aj.tam_min, aj.max_lineas, t.interlineado || 1.14,
  );
  ctx.textBaseline = "top";
  ctx.textAlign = t.alineacion === "centro" ? "center" : t.alineacion === "derecha" ? "right" : "left";
  const tx = t.alineacion === "centro" ? t.x + t.w / 2 : t.alineacion === "derecha" ? t.x + t.w : t.x;

  // Alto total del bloque (con el padding del chip arriba y abajo si hay chip).
  const py = t.chip ? (t.chip.pad_y ?? 14) : 0;
  const blockH = lineas.length * altoLinea + (t.chip ? py * 2 : 0);
  // ANCLA: por defecto el bloque crece hacia ABAJO desde `t.y` (su borde superior). Con
  // `ancla: "abajo"`, `t.y` es el borde INFERIOR y el bloque crece hacia ARRIBA: así un
  // titular de 1 o de 4 líneas queda siempre pegado al borde inferior seguro, sin desbordarse.
  const top = t.ancla === "abajo" ? t.y - blockH : t.y;

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
    if (justif && !ultima) {
      dibujarLineaJustificada(ctx, ln, t.x, y, t.w, t.color, t.sombra);
    } else {
      if (t.sombra) {
        ctx.fillStyle = t.sombra.color || "#000000";
        ctx.fillText(ln, (justif ? t.x : tx) + (t.sombra.dx ?? 2), y + (t.sombra.dy ?? 2));
      }
      ctx.fillStyle = t.color;
      ctx.fillText(ln, justif ? t.x : tx, y);
    }
    y += altoLinea;
  }
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
function dibujarLineaJustificada(ctx, linea, x, y, ancho, color, sombra) {
  const palabras = linea.split(/\s+/).filter(Boolean);
  ctx.textAlign = "left";
  if (palabras.length <= 1) {
    if (sombra) { ctx.fillStyle = sombra.color || "#000000"; ctx.fillText(linea, x + (sombra.dx ?? 2), y + (sombra.dy ?? 2)); }
    ctx.fillStyle = color;
    ctx.fillText(linea, x, y);
    return;
  }
  const anchoPalabras = palabras.reduce((s, p) => s + ctx.measureText(p).width, 0);
  const hueco = (ancho - anchoPalabras) / (palabras.length - 1);
  let cx = x;
  for (const p of palabras) {
    if (sombra) { ctx.fillStyle = sombra.color || "#000000"; ctx.fillText(p, cx + (sombra.dx ?? 2), y + (sombra.dy ?? 2)); }
    ctx.fillStyle = color;
    ctx.fillText(p, cx, y);
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
    dibujarImagenEnCaja(ctx, I.foto, s.x, s.y, s.w, s.h, s.ajuste || "cover", s.foco);
  }

  // 2) Overlay de legibilidad (solo si hay textos visibles, como en Pillow).
  const hayTitular = (formato.textos || []).some((t) => {
    const v = t.binding === "copy_in" ? B.copy_in : t.binding === "etiqueta_default" ? B.etiqueta_default : t.texto;
    return String(v || "").trim();
  });
  if (hayTitular && !placeholder) dibujarOverlayInferior(ctx, formato.overlay_inferior, w, h);
  else if (placeholder) dibujarOverlayInferior(ctx, formato.overlay_inferior, w, h);

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

// Traza un rectángulo (redondeado si r>0) en el path actual.
function rutaRect(ctx, x, y, w, h, r) {
  if (!r) { ctx.rect(x, y, w, h); return; }
  const rr = Math.min(r, w / 2, h / 2);
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
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

function dibujarMarco(ctx, m) {
  const { x, y, w, h } = m;
  if (m.forma === "linea") {
    if (m.borde && m.borde.grosor > 0) {
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + w, y + h);
      ctx.lineWidth = m.borde.grosor;
      ctx.strokeStyle = m.borde.color || "#000000";
      ctx.stroke();
    }
    return;
  }
  ctx.beginPath();
  if (m.forma === "elipse") ctx.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
  else rutaRect(ctx, x, y, w, h, m.radio || 0);
  if (m.relleno) { ctx.fillStyle = m.relleno; ctx.fill(); }
  if (m.borde && m.borde.grosor > 0) {
    ctx.lineWidth = m.borde.grosor;
    ctx.strokeStyle = m.borde.color || "#000000";
    ctx.stroke();
  }
}

// Dibuja UNA capa (con su opacidad/rotación). `env` = {I: imágenes por objeto/media_id, B: bindings, F: familiaReal}.
function dibujarCapa(ctx, capa, env) {
  if (capa.visible === false) return;
  ctx.save();
  const op = capa.opacidad ?? 1;
  if (op < 1) ctx.globalAlpha = op;
  const rot = capa.rotacion || 0;
  if (rot) {
    const cx = capa.x + capa.w / 2, cy = capa.y + capa.h / 2;
    ctx.translate(cx, cy);
    ctx.rotate((rot * Math.PI) / 180);
    ctx.translate(-cx, -cy);
  }
  switch (capa.tipo) {
    case "imagen": {
      const img = env.I[capa.objeto];
      const filtro = cssFiltro(capa.filtros);
      if (filtro) ctx.filter = filtro;
      dibujarImagenEnCaja(ctx, img, capa.x, capa.y, capa.w, capa.h, capa.ajuste || "cover", capa.foco);
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
      dibujarLogo(ctx, { ...capa, tipo: capa.tipo_logo }, env.I[capa.media_id], null, env.F);
      break;
    case "marco":
      dibujarMarco(ctx, capa);
      break;
    case "overlay":
      dibujarOverlayInferior(ctx, capa, capa.w, capa.h);
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
export function dibujarDocumento(ctx, { documento, imgs, bindings, familiaReal }) {
  const F = familiaReal || ((l) => (l === "condensada" ? "Barlow Condensed" : "Barlow"));
  const env = { I: imgs || {}, B: bindings || {}, F };
  const { formato, fondo } = documento;
  const w = formato.w, h = formato.h;

  const fondoImg = fondo && fondo.tipo === "imagen" ? env.I[(fondo.imagen || {}).media_id] : null;
  dibujarFondo(ctx, fondo, w, h, fondoImg);

  const capas = [...(documento.capas || [])].sort((a, b) => (a.z ?? 0) - (b.z ?? 0));
  for (const capa of capas) dibujarCapa(ctx, capa, env);
}
