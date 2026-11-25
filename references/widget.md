# 盘前 / 盘后可视化卡片

用户反馈（2026-11-26）：这张卡"挺好的"，盘前、盘后固定出。

## 什么时候出

- 场景是盘前或盘后的正式回答，而且当前环境有内联可视化工具（例如 `show_widget`）时，先出卡片，再写角色内文字。
- 没有可视化工具（纯终端、API）时不出，照 `formats.md` 只写文字。
- 追问、闲聊、短答不出。同一会话同一场景只出一次；数据重跑后可以再出一次。
- 卡片是出戏的数据面板，不写人设口吻的话；人设的话写在卡片外面的正文里，正文不要把卡片上的数字再全报一遍。

## 数据从哪来

全部取自 `daily_card.py` 和 `analog.py` 的输出，不另外取数，不编数字。缺哪一项，就删掉那一块，不留空格子。

| 卡片位置 | 取自 |
|---|---|
| 大字阶段 | 卡片最后一行 `=> 估值基调：X` |
| 上证点位与涨跌 | 第一行 `日期 … 上证`、`[情绪]` 的上证当日 |
| 右上角状态 | 盘前：`[盘前时点]` 就绪写"盘前已就绪"，未就绪写"盘前未就绪：美股未收"（warning 色）。盘后：写"盘后 · 收盘 MM-DD" |
| 分位条 | `[F1蓝筹]` 上证50 滚动 PE 与 2005 起分位 |
| A50 条件线 | `[A50条件线]` 的基准、偏弱线、修复线、现报。只在盘前出 |
| 指标格（6 个） | 全A 中位 PE 分位（`[F1]`）、破净占比与分位（`[R8补]`）、股债差与分位（`[R18]`）、融资余额 20 日（`[F6]`）、宽基 ETF 5 日与 z（`[F4]`）、中证红利股息率与 10Y 差（`[红利银行]`） |
| 警报 | `[信号灯]` 四盏。灭的用中性 pill；亮的用 danger 色并写一句为什么亮 |
| 最像的历史 | `analog.py` 前两个书中案例 + 第一个历史月末，带距离和之后 60 日 |
| 隔夜 | `[隔夜]`，盘前出，盘后删 |
| 脚注 | `[脚注]` 那一行，加"模拟李大霄，依据其著作，非本人，不构成投资建议" |

盘后把 A50 条件线换成"明天看什么"一行：点名一个指标和阈值（同 `formats.md` 盘后模板）。

## 算位置

- 分位条：竖线 `left` = 分位百分数（69% 就写 `left:69%`）。
- A50 条件线：偏弱线固定在 20%，修复线固定在 80%，现价圆点
  `left = 20 + 60 × (现价 − 偏弱线) / (修复线 − 偏弱线)`，限制在 3%–97%。
  例：偏弱 12,346、修复 12,446、现报 12,437 → 20 + 60 × 91/100 = 74.6%。

## 模板（照抄结构，只换数）

按顺序：标题行 → 分位条 → A50（盘前）/ 明天看什么（盘后）→ 指标格 → 警报 → 最像的历史 → 隔夜（盘前）→ 三个追问按钮 → 脚注。按钮用 `sendPrompt`，盘前给"明早重跑盘前""盘中看一眼""讲讲那段历史"，盘后给"明天盘前怎么看""这周怎么看""讲讲那段历史"。

```html
<style>
.k{background:var(--bg-neutral);border-radius:var(--radius);padding:12px 14px}
.kl{font-size:13px;color:var(--text-secondary);margin:0 0 4px}
.kv{font-size:22px;font-weight:500;margin:0;font-variant-numeric:tabular-nums}
.ks{font-size:12px;color:var(--text-muted);margin:2px 0 0}
.sec{font-size:13px;color:var(--text-secondary);margin:1.25rem 0 8px}
.row{display:flex;justify-content:space-between;font-size:13px;padding:6px 0;border-bottom:0.5px solid var(--border)}
.pill{font-size:12px;padding:2px 10px;border-radius:var(--radius);background:var(--bg-neutral);color:var(--text-secondary)}
</style>
<h2 class="sr-only">{一句话摘要：阶段、分位、是否就绪、警报}</h2>
<div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:8px;padding:0.5rem 0 0">
  <div style="display:flex;align-items:baseline;gap:12px">
    <span style="font-family:var(--font-voice);font-size:44px;font-weight:500;line-height:1">{阶段}</span>
    <span style="font-size:13px;color:var(--text-secondary)">估值基调 · 上证 {点位}（{涨跌}）</span>
  </div>
  <span class="pill" style="background:var(--bg-warning);color:var(--text-warning)"><i class="ti ti-clock" aria-hidden="true" style="font-size:14px;vertical-align:-2px"></i> {状态}</span>
</div>

<p class="sec">上证50 滚动 PE 分位（2005 起）</p>
<div style="position:relative;height:26px">
  <div style="position:absolute;inset:9px 0;border-radius:4px;display:flex;overflow:hidden">
    <div style="width:20%;background:var(--bg-success)"></div>
    <div style="width:60%;background:var(--bg-neutral)"></div>
    <div style="width:20%;background:var(--bg-danger)"></div>
  </div>
  <div style="position:absolute;left:{分位}%;top:2px;width:2px;height:22px;background:var(--text-primary)"></div>
</div>
<div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text-muted)">
  <span>勇气 &lt;20%</span><span style="color:var(--text-primary)">{分位}%（PE {PE}）</span><span>淡泊 &gt;80%</span>
</div>

<p class="sec">明早开盘看 A50（日盘收 {基准}）</p>
<div style="position:relative;height:44px">
  <div style="position:absolute;left:0;right:0;top:20px;height:2px;background:var(--border-strong)"></div>
  <div style="position:absolute;left:20%;top:12px;width:2px;height:18px;background:var(--text-danger)"></div>
  <div style="position:absolute;left:20%;top:32px;font-size:12px;color:var(--text-danger);transform:translateX(-50%)">偏弱 {偏弱线}</div>
  <div style="position:absolute;left:80%;top:12px;width:2px;height:18px;background:var(--text-success)"></div>
  <div style="position:absolute;left:80%;top:32px;font-size:12px;color:var(--text-success);transform:translateX(-50%)">修复 {修复线}</div>
  <div style="position:absolute;left:{圆点}%;top:14px;width:12px;height:12px;border-radius:50%;background:var(--text-primary);border:2px solid var(--surface-1);transform:translateX(-50%)"></div>
  <div style="position:absolute;left:{圆点}%;top:-4px;font-size:12px;color:var(--text-primary);transform:translateX(-50%)">现 {现报}</div>
</div>

<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:1.25rem">
  <div class="k"><p class="kl">{指标名}</p><p class="kv">{数值}</p><p class="ks">{一句白话}</p></div>
  <!-- 共 6 格 -->
</div>

<p class="sec">警报</p>
<div style="display:flex;flex-wrap:wrap;gap:8px">
  <span class="pill"><i class="ti ti-circle" aria-hidden="true" style="font-size:12px"></i> {名称} 灭</span>
  <!-- 亮的：style="background:var(--bg-danger);color:var(--text-danger)"，图标 ti-alert-triangle，写"{名称} 亮：{原因}" -->
</div>

<p class="sec">最像的历史</p>
<div class="row"><span>{案例 id 与名称}</span><span style="color:var(--text-secondary)">距离 {d} · 之后 60 日 {r60}</span></div>

<p class="sec">隔夜</p>
<div style="display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--text-secondary);font-variant-numeric:tabular-nums">
  <span>{名称} {涨跌}</span>
</div>

<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:1.25rem">
  <button onclick="sendPrompt('{追问}')">{按钮文字} ↗</button>
</div>
<p style="font-size:12px;color:var(--text-muted);margin:12px 0 0">{脚注} · 模拟李大霄，依据其著作，非本人，不构成投资建议</p>
```

实际输出时删掉模板里的 `<!-- -->` 注释。

## 写法约束

- 指标格的小字是一句白话（"杠杆在退""小盘便宜，蓝筹不贵"），不写判断性的买卖话。
- 颜色只表示含义：分位条的勇气/淡泊区、A50 两条线、亮起的警报。其余一律中性色。
- 数字照抄卡片，保留卡片的小数位，不四舍五入成另一个数。
