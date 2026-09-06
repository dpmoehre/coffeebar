/** 平面图平移缩放：屏幕 = k * 投影 + (x, y)。和 SVG translate 再 scale 一致。 */

export function unview(svgX, svgY, view) {
  const k = view.k || 1;
  return [(svgX - view.x) / k, (svgY - view.y) / k];
}

export function zoomAt(view, svgX, svgY, factor, minK = 0.7, maxK = 8) {
  const k = Math.min(maxK, Math.max(minK, view.k * factor));
  return {
    k,
    x: svgX - ((svgX - view.x) * k) / view.k,
    y: svgY - ((svgY - view.y) * k) / view.k,
  };
}

export function clientToSvg(svg, clientX, clientY) {
  if (!svg?.getScreenCTM) return null;
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
  return [p.x, p.y];
}
