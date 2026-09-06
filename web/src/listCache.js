// 侧栏切走再回来时，列表页会被卸掉。这里记住上一份，先画出卡片，再在后台刷新。
const bag = new Map();

export function recall(key) {
  return bag.has(key) ? bag.get(key) : undefined;
}

export function remember(key, value) {
  bag.set(key, value);
  return value;
}

export function forgetLists() {
  bag.clear();
}
