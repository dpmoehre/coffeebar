-- coffeebar 第一期（豆子）建表脚本。幂等，每次启动执行。
-- 口径见 docs/002-🚧-豆子档案与小主机架构.md

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── 账号：每人一份私库。公共豆种以后另表，这一期先把归属立住 ──

CREATE TABLE IF NOT EXISTS account (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  email          TEXT    NOT NULL UNIQUE,
  password_hash  TEXT    NOT NULL,
  email_verified INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT    NOT NULL,
  claimed_at     TEXT,
  status         TEXT    NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS auth_session (
  token      TEXT    PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  created_at TEXT    NOT NULL,
  expires_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_account ON auth_session(account_id);

CREATE TABLE IF NOT EXISTS auth_token (
  token      TEXT    PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  purpose    TEXT    NOT NULL CHECK (purpose IN ('verify', 'reset', 'export')),
  created_at TEXT    NOT NULL,
  expires_at TEXT    NOT NULL,
  used_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_token_account ON auth_token(account_id);

-- ── 豆子：卡是品种，袋子是批次 ────────────────────────────────

CREATE TABLE IF NOT EXISTS bean (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id    INTEGER REFERENCES account(id),
  name        TEXT    NOT NULL,
  origin      TEXT,                      -- 产地 / 产区
  varietal    TEXT,                      -- 豆种，包装上一般印 Varietal
  producer    TEXT,                      -- 处理厂 / 庄园 / 水洗站
  altitude    TEXT,                      -- 海拔，常是范围（1500-2200m），存文本
  process     TEXT,                      -- 处理法
  roast       TEXT,                      -- 浅烘 / 中烘 / 深烘
  water_temp  INTEGER,                   -- 建议水温 °C
  note        TEXT,
  deleted_at  TEXT,                      -- 非空 = 从豆库收起；流水和花掉的钱还在统计里
  visibility  TEXT    NOT NULL DEFAULT 'private',  -- private 只自己 / public 公开
  certified_at TEXT,                     -- 管理员审过并认证
  certified_by INTEGER REFERENCES account(id),
  review_note TEXT,
  places_verified_at TEXT,               -- 地图钉校对过
  kingdom_id  INTEGER,                   -- 收入咖啡王国后挂到公共豆种
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
  owner_id   INTEGER REFERENCES account(id),
  name       TEXT    NOT NULL,
  active     INTEGER NOT NULL DEFAULT 1, -- 0 = 停用（选人列表里不出现，记录仍在）
  created_at TEXT    NOT NULL,
  UNIQUE (owner_id, name)
);

-- 基酒：卡是酒名，瓶子是批次。同样的酒再买一瓶只加批次。
CREATE TABLE IF NOT EXISTS bottle (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id   INTEGER REFERENCES account(id),
  name       TEXT    NOT NULL,
  kind       TEXT,                      -- 大类：威士忌 / 金酒 / 朗姆 …
  category   TEXT,                      -- 细类：单一麦芽 / 波本 / 伦敦干金
  origin     TEXT,                      -- 产地，如苏格兰高地
  abv        REAL,                      -- 酒精度 % vol
  flavor     TEXT,                      -- 风味类型：柑橘甜、泥煤、香草焦糖
  note       TEXT,
  deleted_at TEXT,                      -- 非空 = 从酒库收起；流水和花掉的钱还在统计里
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

-- 鸡尾酒配方。辅料只写在 note / steps，不建库存。
CREATE TABLE IF NOT EXISTS recipe (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id   INTEGER REFERENCES account(id),
  name       TEXT    NOT NULL,
  steps      TEXT,
  note       TEXT,
  created_at TEXT    NOT NULL,
  updated_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS recipe_line (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id  INTEGER NOT NULL REFERENCES recipe(id) ON DELETE CASCADE,
  spirit_id  INTEGER NOT NULL REFERENCES bottle(id),
  amount_ml  REAL    NOT NULL,
  sort       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rline_recipe ON recipe_line(recipe_id);

-- 推荐酒单：一条纯饮（基酒）或鸡尾酒。listed=0 编辑区能看见，正面不出现。
CREATE TABLE IF NOT EXISTS menu_item (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id   INTEGER REFERENCES account(id),
  kind       TEXT    NOT NULL CHECK (kind IN ('neat', 'cocktail')),
  spirit_id  INTEGER REFERENCES bottle(id),
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  sort       INTEGER NOT NULL DEFAULT 0,
  listed     INTEGER NOT NULL DEFAULT 1,
  created_at TEXT    NOT NULL,
  CHECK (
    (kind = 'neat' AND spirit_id IS NOT NULL AND recipe_id IS NULL)
    OR (kind = 'cocktail' AND recipe_id IS NOT NULL AND spirit_id IS NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_menu_owner ON menu_item(owner_id, sort);

-- 酒单一巡：鸡尾酒多行扣瓶，杯数按巡算 1。酒卡上老的「倒一杯」没有 serve。
CREATE TABLE IF NOT EXISTS drink_serve (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id     INTEGER REFERENCES account(id),
  kind         TEXT    NOT NULL CHECK (kind IN ('neat', 'cocktail')),
  menu_item_id INTEGER REFERENCES menu_item(id) ON DELETE SET NULL,
  recipe_id    INTEGER REFERENCES recipe(id) ON DELETE SET NULL,
  person_id    INTEGER REFERENCES person(id),
  name         TEXT    NOT NULL,
  note         TEXT,
  at           TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_serve_owner ON drink_serve(owner_id, at);

-- 喝掉一次。咖啡扣 bean_lot，酒扣 bottle_lot，同一张表避免双记。
CREATE TABLE IF NOT EXISTS consumption_event (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  kind          TEXT    NOT NULL DEFAULT 'coffee' CHECK (kind IN ('coffee', 'drink')),
  lot_id        INTEGER REFERENCES bean_lot(id) ON DELETE CASCADE,
  bottle_lot_id INTEGER REFERENCES bottle_lot(id) ON DELETE CASCADE,
  serve_id      INTEGER REFERENCES drink_serve(id),
  person_id     INTEGER REFERENCES person(id),          -- 可空：没记是谁
  amount_g      REAL,                                   -- 咖啡：当次实际粉量
  amount_ml     REAL,                                   -- 酒：当次倒了多少毫升
  unit_cost     REAL,                                   -- 当时单价快照（元/克 或 元/毫升）
  brew_method   TEXT,
  brew_ratio    REAL,
  brew_total_s  INTEGER,
  brew_stages   TEXT,
  note          TEXT,
  as_cup        INTEGER NOT NULL DEFAULT 1,              -- 0：整袋补录，克重和钱进统计，不算杯
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
-- serve_id 索引放 db.py：老库第一遍执行时这列还没有

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

-- 冲一次留下的过程照：称豆 / 粉床 / 冲完 / 器具（称盘、壶、滤杯），都可以缺
CREATE TABLE IF NOT EXISTS consumption_photo (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  cons_id    INTEGER NOT NULL REFERENCES consumption_event(id) ON DELETE CASCADE,
  kind       TEXT    NOT NULL CHECK (kind IN ('beans', 'bed', 'finish', 'gear')),
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

-- 豆子在地图上的落点。一张卡可有多个（拼配、庄园另标）。
-- source=gazetteer 词典推测；source=click 人在图上点的。有手定点就不再被改产地冲掉。
CREATE TABLE IF NOT EXISTS bean_place (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  bean_id    INTEGER NOT NULL REFERENCES bean(id) ON DELETE CASCADE,
  lat        REAL    NOT NULL,
  lng        REAL    NOT NULL,
  label      TEXT,
  source     TEXT    NOT NULL CHECK (source IN ('gazetteer', 'click')),
  created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_place_bean ON bean_place(bean_id);

-- ── 咖啡器具：私人台面 + 管理员收录的公共目录 ──────────────
-- 器具挂在账号上，不是「谁喝的」。冲煮建议按这张台面来。

CREATE TABLE IF NOT EXISTS gear_catalog (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  name           TEXT    NOT NULL,
  kind           TEXT    NOT NULL CHECK (kind IN ('dripper', 'kettle', 'grinder', 'scale', 'server', 'other')),
  family         TEXT,
  brand          TEXT,
  model          TEXT,
  brew_method    TEXT,
  note           TEXT,
  source_gear_id INTEGER,
  collected_by   INTEGER REFERENCES account(id) ON DELETE SET NULL,
  created_at     TEXT    NOT NULL,
  updated_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gear_catalog_photo (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  catalog_id INTEGER NOT NULL REFERENCES gear_catalog(id) ON DELETE CASCADE,
  path       TEXT    NOT NULL,
  created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gcat_photo ON gear_catalog_photo(catalog_id);

CREATE TABLE IF NOT EXISTS user_gear (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id    INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  catalog_id  INTEGER REFERENCES gear_catalog(id) ON DELETE SET NULL,
  name        TEXT    NOT NULL,
  kind        TEXT    NOT NULL CHECK (kind IN ('dripper', 'kettle', 'grinder', 'scale', 'server', 'other')),
  family      TEXT,
  brand       TEXT,
  model       TEXT,
  brew_method TEXT,
  note        TEXT,
  created_at  TEXT    NOT NULL,
  updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ugear_owner ON user_gear(owner_id);
CREATE INDEX IF NOT EXISTS idx_ugear_catalog ON user_gear(catalog_id);

CREATE TABLE IF NOT EXISTS user_gear_photo (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  gear_id    INTEGER NOT NULL REFERENCES user_gear(id) ON DELETE CASCADE,
  path       TEXT    NOT NULL,
  created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ugear_photo ON user_gear_photo(gear_id);

-- ── 咖啡王国：公共豆种。大家杯测、评价、收藏都挂这里，不挂私人袋子 ──

CREATE TABLE IF NOT EXISTS kingdom_bean (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  name           TEXT    NOT NULL,
  origin         TEXT,
  varietal       TEXT,
  producer       TEXT,
  altitude       TEXT,
  process        TEXT,
  roast          TEXT,
  note           TEXT,
  source_bean_id INTEGER,
  collected_by   INTEGER REFERENCES account(id) ON DELETE SET NULL,
  created_at     TEXT    NOT NULL,
  updated_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS kingdom_photo (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  kingdom_id  INTEGER NOT NULL REFERENCES kingdom_bean(id) ON DELETE CASCADE,
  path        TEXT    NOT NULL,
  created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kphoto ON kingdom_photo(kingdom_id);

CREATE TABLE IF NOT EXISTS kingdom_score (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  kingdom_id  INTEGER NOT NULL REFERENCES kingdom_bean(id) ON DELETE CASCADE,
  author_id   INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  dry         REAL, flavor REAL, aftertaste REAL, acidity REAL,
  sweetness   REAL, body   REAL, balance    REAL, overall REAL,
  comment     TEXT,
  created_at  TEXT    NOT NULL,
  updated_at  TEXT    NOT NULL,
  UNIQUE (kingdom_id, author_id)
);
CREATE INDEX IF NOT EXISTS idx_kscore ON kingdom_score(kingdom_id);

CREATE TABLE IF NOT EXISTS kingdom_score_photo (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  score_id    INTEGER NOT NULL REFERENCES kingdom_score(id) ON DELETE CASCADE,
  path        TEXT    NOT NULL,
  created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kscore_photo ON kingdom_score_photo(score_id);

CREATE TABLE IF NOT EXISTS kingdom_favorite (
  kingdom_id INTEGER NOT NULL REFERENCES kingdom_bean(id) ON DELETE CASCADE,
  account_id INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  created_at TEXT    NOT NULL,
  PRIMARY KEY (kingdom_id, account_id)
);

-- ── 写锁：网页之间软锁可接管，非网页来源硬拒绝 ──────────────

CREATE TABLE IF NOT EXISTS write_lock (
  resource     TEXT PRIMARY KEY,          -- 例如 bean:12
  session_id   TEXT NOT NULL,
  holder       TEXT,                      -- 显示用：哪台在编辑
  acquired_at  TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL
);
