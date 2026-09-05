-- coffeebar 第一期（豆子）建表脚本。幂等，每次启动执行。
-- 口径见 docs/002-🚧-豆子档案与小主机架构.md

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── 豆子：卡是品种，袋子是批次 ────────────────────────────────

CREATE TABLE IF NOT EXISTS bean (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT    NOT NULL,
  origin      TEXT,                      -- 产地 / 产区
  varietal    TEXT,                      -- 豆种，包装上一般印 Varietal
  producer    TEXT,                      -- 处理厂 / 庄园 / 水洗站
  altitude    TEXT,                      -- 海拔，常是范围（1500-2200m），存文本
  process     TEXT,                      -- 处理法
  roast       TEXT,                      -- 浅烘 / 中烘 / 深烘
  water_temp  INTEGER,                   -- 建议水温 °C
  note        TEXT,
  created_at  TEXT    NOT NULL,
  updated_at  TEXT    NOT NULL
);

-- 一支豆可以同时有几袋：一袋在喝、几袋未开封。
-- 冲的时候扣哪一袋由人选，不自动 FIFO。
CREATE TABLE IF NOT EXISTS bean_lot (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  bean_id     INTEGER NOT NULL REFERENCES bean(id) ON DELETE CASCADE,
  nominal_g   REAL    NOT NULL,          -- 包装标称，入库必填，默认就用它当可用克重
  measured_g  REAL,                      -- 开袋实称，可选且通常为空（刚拆袋不会称）
  price       REAL,                      -- 这袋买入价
  bought_on   TEXT,                       -- 购入日
  opened_on   TEXT,                       -- 开封日
  closed_at   TEXT,                       -- 非空 = 已关袋（这袋用完了）
  note        TEXT,
  created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lot_bean ON bean_lot(bean_id);

-- ── 两类事件，分工不同 ──────────────────────────────────────

-- 只改数的管理动作：没有「谁喝的」，不算钱
CREATE TABLE IF NOT EXISTS stock_event (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  lot_id   INTEGER NOT NULL REFERENCES bean_lot(id) ON DELETE CASCADE,
  kind     TEXT    NOT NULL CHECK (kind IN ('intake', 'measure', 'adjust', 'close_lot')),
  delta_g  REAL    NOT NULL DEFAULT 0,   -- 对账面的增减；intake/measure 记 0
  note     TEXT,
  at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_lot ON stock_event(lot_id);

-- 谁喝的：实体表，不是写死在流水里的字符串。
-- 改名只改这一行，历史记录自动跟着变；停用不删。
CREATE TABLE IF NOT EXISTS person (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL UNIQUE,
  active     INTEGER NOT NULL DEFAULT 1, -- 0 = 停用（选人列表里不出现，记录仍在）
  created_at TEXT    NOT NULL
);

-- 基酒：卡是酒名，瓶子是批次。同样的酒再买一瓶只加批次。
CREATE TABLE IF NOT EXISTS bottle (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  kind       TEXT,                      -- 大类：威士忌 / 金酒 / 朗姆 …
  category   TEXT,                      -- 细类：单一麦芽 / 波本 / 伦敦干金
  origin     TEXT,                      -- 产地，如苏格兰高地
  abv        REAL,                      -- 酒精度 % vol
  flavor     TEXT,                      -- 风味类型：柑橘甜、泥煤、香草焦糖
  note       TEXT,
  created_at TEXT    NOT NULL,
  updated_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS bottle_lot (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  bottle_id   INTEGER NOT NULL REFERENCES bottle(id) ON DELETE CASCADE,
  nominal_ml  REAL    NOT NULL,          -- 标称容量，入库必填
  price       REAL,                      -- 这瓶买入价
  bought_on   TEXT,
  opened_on   TEXT,
  closed_at   TEXT,                      -- 非空 = 这瓶倒完了
  note        TEXT,
  created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blot_bottle ON bottle_lot(bottle_id);

CREATE TABLE IF NOT EXISTS bottle_stock_event (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  lot_id   INTEGER NOT NULL REFERENCES bottle_lot(id) ON DELETE CASCADE,
  kind     TEXT    NOT NULL CHECK (kind IN ('intake', 'adjust', 'close_lot')),
  delta_ml REAL    NOT NULL DEFAULT 0,
  note     TEXT,
  at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bstock_lot ON bottle_stock_event(lot_id);

CREATE TABLE IF NOT EXISTS bottle_tag (
  bottle_id INTEGER NOT NULL REFERENCES bottle(id) ON DELETE CASCADE,
  tag_id    INTEGER NOT NULL REFERENCES tag(id)    ON DELETE CASCADE,
  PRIMARY KEY (bottle_id, tag_id)
);

CREATE TABLE IF NOT EXISTS bottle_photo (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  bottle_id  INTEGER NOT NULL REFERENCES bottle(id) ON DELETE CASCADE,
  kind       TEXT    NOT NULL CHECK (kind IN ('pack', 'label')),  -- 瓶+盒 / 酒标
  path       TEXT    NOT NULL,
  created_at TEXT    NOT NULL
);

-- 喝掉一次。咖啡扣 bean_lot，酒扣 bottle_lot，同一张表避免双记。
CREATE TABLE IF NOT EXISTS consumption_event (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  kind          TEXT    NOT NULL DEFAULT 'coffee' CHECK (kind IN ('coffee', 'drink')),
  lot_id        INTEGER REFERENCES bean_lot(id) ON DELETE CASCADE,
  bottle_lot_id INTEGER REFERENCES bottle_lot(id) ON DELETE CASCADE,
  person_id     INTEGER REFERENCES person(id),          -- 可空：没记是谁
  amount_g      REAL,                                   -- 咖啡：当次实际粉量
  amount_ml     REAL,                                   -- 酒：当次倒了多少毫升
  unit_cost     REAL,                                   -- 当时单价快照（元/克 或 元/毫升）
  brew_method   TEXT,
  brew_ratio    REAL,
  brew_total_s  INTEGER,
  brew_stages   TEXT,
  note          TEXT,
  at            TEXT    NOT NULL,
  voided_at     TEXT,
  void_reason   TEXT,
  CHECK (
    (kind = 'coffee' AND lot_id IS NOT NULL AND amount_g IS NOT NULL)
    OR (kind = 'drink' AND bottle_lot_id IS NOT NULL AND amount_ml IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_cons_lot    ON consumption_event(lot_id);
CREATE INDEX IF NOT EXISTS idx_cons_at     ON consumption_event(at);
CREATE INDEX IF NOT EXISTS idx_cons_void   ON consumption_event(voided_at);

-- 改归属人留痕
CREATE TABLE IF NOT EXISTS consumption_audit (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  cons_id       INTEGER NOT NULL REFERENCES consumption_event(id) ON DELETE CASCADE,
  field         TEXT    NOT NULL,
  old_value     TEXT,
  new_value     TEXT,
  at            TEXT    NOT NULL
);

-- ── 标签、杯测、冲煮默认值 ──────────────────────────────────

CREATE TABLE IF NOT EXISTS tag (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS bean_tag (
  bean_id INTEGER NOT NULL REFERENCES bean(id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES tag(id)  ON DELETE CASCADE,
  PRIMARY KEY (bean_id, tag_id)
);

-- 杯测：1–10 八个维度
CREATE TABLE IF NOT EXISTS bean_score (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  bean_id   INTEGER NOT NULL REFERENCES bean(id) ON DELETE CASCADE,
  dry       REAL, flavor REAL, aftertaste REAL, acidity REAL,
  sweetness REAL, body   REAL, balance    REAL, overall REAL,
  comment   TEXT,
  at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_score_bean ON bean_score(bean_id);

-- 冲煮只存默认值（方式 + 上次粉量 + 比例），各段渲染时算，不存算好的段
CREATE TABLE IF NOT EXISTS brew_guide (
  bean_id INTEGER PRIMARY KEY REFERENCES bean(id) ON DELETE CASCADE,
  method  TEXT NOT NULL DEFAULT 'v60',
  dose_g  REAL NOT NULL DEFAULT 15,
  ratio   REAL NOT NULL DEFAULT 16,
  note    TEXT   -- 店家豆卡上的推荐：滤器、研磨刻度、水质、目标时长等
);

-- ── 照片与补货（表先建好，接口后做） ────────────────────────

CREATE TABLE IF NOT EXISTS bean_photo (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  bean_id    INTEGER NOT NULL REFERENCES bean(id) ON DELETE CASCADE,
  -- 包装 / 豆盘 / 店家豆卡，都可缺
  kind       TEXT    NOT NULL CHECK (kind IN ('pack', 'tray', 'card')),
  path       TEXT    NOT NULL,                                   -- data/photos/ 下的相对路径
  created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS restock_photo (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  bean_id    INTEGER NOT NULL REFERENCES bean(id) ON DELETE CASCADE,
  path       TEXT    NOT NULL,
  note       TEXT,
  created_at TEXT    NOT NULL
);

-- 冲一次留下的过程照：称豆 / 粉床 / 冲完，都可以缺
CREATE TABLE IF NOT EXISTS consumption_photo (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  cons_id    INTEGER NOT NULL REFERENCES consumption_event(id) ON DELETE CASCADE,
  kind       TEXT    NOT NULL CHECK (kind IN ('beans', 'bed', 'finish')),
  path       TEXT    NOT NULL,
  created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cons_photo ON consumption_photo(cons_id);

-- 每支豆的安全库存（克）：低于它进补货清单
CREATE TABLE IF NOT EXISTS restock_rule (
  bean_id   INTEGER PRIMARY KEY REFERENCES bean(id) ON DELETE CASCADE,
  min_g     REAL NOT NULL DEFAULT 0,
  min_days  REAL NOT NULL DEFAULT 3
);

-- ── 写锁：网页之间软锁可接管，非网页来源硬拒绝 ──────────────

CREATE TABLE IF NOT EXISTS write_lock (
  resource     TEXT PRIMARY KEY,          -- 例如 bean:12
  session_id   TEXT NOT NULL,
  holder       TEXT,                      -- 显示用：哪台在编辑
  acquired_at  TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL
);
