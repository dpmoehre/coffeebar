// 把 Tailwind v4 打出来的 @layer 拆开。
// 搜狗 / 360 等双核或偏旧的 Chromium 不认 @layer，整段工具类会被丢掉。

function skipString(css, i) {
  const q = css[i];
  let j = i + 1;
  while (j < css.length) {
    if (css[j] === "\\") {
      j += 2;
      continue;
    }
    if (css[j] === q) return j + 1;
    j += 1;
  }
  return css.length;
}

function matchingBrace(css, open) {
  let depth = 0;
  let i = open;
  while (i < css.length) {
    const c = css[i];
    if (c === '"' || c === "'") {
      i = skipString(css, i);
      continue;
    }
    if (c === "{") depth += 1;
    else if (c === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
    i += 1;
  }
  return -1;
}

function stripRelativeColorSupports(css) {
  let out = css;
  const startRe = /@supports[^{]*\{/g;
  let guard = 0;
  while (guard < 16) {
    guard += 1;
    startRe.lastIndex = 0;
    let found = null;
    let m = startRe.exec(out);
    while (m) {
      if (/rgb\s*\(\s*from/i.test(m[0])) {
        found = m;
        break;
      }
      m = startRe.exec(out);
    }
    if (!found) break;
    const open = found.index + found[0].length - 1;
    const close = matchingBrace(out, open);
    if (close < 0) break;
    out = out.slice(0, found.index) + out.slice(close + 1);
  }
  return out;
}

export function flattenCssLayers(css) {
  let out = String(css).replace(/@layer\s+[\w\s,-]+;/g, "");
  const startRe = /@layer\s+[\w\s,-]+\{/g;
  let guard = 0;
  while (guard < 32) {
    guard += 1;
    startRe.lastIndex = 0;
    const m = startRe.exec(out);
    if (!m) break;
    const open = m.index + m[0].length - 1;
    const close = matchingBrace(out, open);
    if (close < 0) break;
    out = out.slice(0, m.index) + out.slice(open + 1, close) + out.slice(close + 1);
  }
  return stripRelativeColorSupports(out);
}
