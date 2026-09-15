# Handoff: garmin-web "Morning Brief" redesign

> **Source of record**: Claude Design project「デザインシステム提案依頼」
> (https://claude.ai/design/p/6bb2bcf1-a731-4bb8-970b-919ad0e73861), folder
> `design_handoff_morning_brief/`. The HTML mocks (`design/*.dc.html`, viewable
> in a browser with the bundled `support.js`) live there and are **not** checked
> in; this file is the handoff README verbatim, kept as the design record for
> Epic #1115 (#1116 P0 … #1122 P3c).

## Overview

garmin-web (packages/garmin-web/frontend, Vite + React 19 + TypeScript + Tailwind v4 + ECharts) の全6ページを
「Morning Brief」デザインシステムへ移行する。
目的は **情報の優先順位が一目で分かること**: 各ページ冒頭に「判定 + 行動」の1文、
数字は等幅で罫線区切り、色は例外(注意/悪/今日)にだけ使う。既存の IA(1ページ1問い、
QueryBoundary によるカード単位の失敗、URL に持つフィルタ)は変更しない。

## About the Design Files

`design/*.dc.html` は **HTML で作ったデザインリファレンス**(静的モック、サンプルデータ入り)であり、
そのまま出荷するコードではない。既存の React コンポーネント構造・Tailwind v4 `@theme`・
`react-router`・`@tanstack/react-query`・ECharts をそのまま使い、**見た目だけを置き換える**こと。
ブラウザで直接開けば見た目を確認できる(Google Fonts を参照)。

- `design/Design System - Morning Brief.dc.html` — トークン・タイポ・コンポーネント仕様(最初に読む)
- `design/Home Redesign - Morning Brief.dc.html` — `/`
- `design/Activity Detail Redesign - Morning Brief.dc.html` — `/activities/:id`
- `design/Plan Redesign - Morning Brief.dc.html` — `/plan`
- `design/Condition Redesign - Morning Brief.dc.html` — `/condition`
- `design/Performance Redesign - Morning Brief.dc.html` — `/performance`
- `design/Goal Redesign - Morning Brief.dc.html` — `/goal`
- `design/Audit Report & Roadmap.dc.html` — 現状の問題点と根拠(なぜ変えるか)

## Fidelity

**High-fidelity.** 色・書体・サイズ・余白・罫線は最終値。ただしチャート領域は
「斜線プレースホルダー + 仕様ラベル」で表現しているので、ECharts のオプションはラベルの指示
(系列色・基準帯・点線)に従って既存 `chartTheme.ts` を更新して実装する。
サンプルデータの文言は既存 API の値で置き換える(文言テンプレートは各画面の節を参照)。

## Design Tokens

### Tailwind v4 `@theme` (src/index.css を置き換え)

```css
@import "tailwindcss";

@theme {
  --font-sans: "BIZ UDPGothic", "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;   /* 数値・日付・ラベル */
  /* --font-display / --font-numeric は削除。numeric → mono に一括置換 */

  --color-paper:      #f4f1ea;  /* body 背景 */
  --color-surface:    #fbfaf7;  /* 操作可能な面のみ(ほぼ使わない) */
  --color-hairline:   #dcd7cc;  /* 罫線 */
  --color-hairline-strong: #1c1b18; /* セクション冒頭の罫線 = ink */
  --color-ink:        #1c1b18;  /* 見出し・数値 */
  --color-ink-soft:   #3d3a34;  /* 本文 */
  --color-ink-muted:  #6b675e;  /* 補足・ラベル (5.0:1 on paper) */
  --color-ink-faint:  #9a9489;  /* 月外セルなど非活性 */
  --color-well:       #ebe7de;  /* バー背景・スケルトン */

  --color-accent:      #1f6f6b; /* 今日・リンク・主操作 */
  --color-accent-tint: #e6f0ef;
  --color-status-good: #2f7a45; /* テキストのみ、塗らない */
  --color-status-warn: #9a5b12;
  --color-warn-tint:   #fdf1e4;
  --color-warn-line:   #e7c9a4;
  --color-status-bad:  #a83a2e;
  --color-bad-tint:    #fbe7e3;
  --color-bad-line:    #e6b3ab;
  --color-star:        #b07a1d; /* ★評価 */

  /* metric colors (chartTheme.ts と同期) */
  --color-metric-hr:      #b8433f;
  --color-metric-pace:    #1f6f6b;
  --color-metric-cadence: #b07a1d;
  --color-metric-power:   #6a4fb3;
  --color-metric-form:    #6a4fb3;
  --color-metric-elevation:#6b675e;
  --color-metric-compare: #c9c3b6; /* 比較系列・基準線 */
  /* HR zones: 単色明度ランプ */
  --color-zone-1: #e8c9c7; --color-zone-2: #d49c98; --color-zone-3: #c2716c;
  --color-zone-4: #b8433f; --color-zone-5: #8a2e2a;

  --radius-sm: 2px;  --radius-md: 4px;   /* xl / 2xl / full / shadow は使わない */
}

@layer base {
  body { @apply bg-paper font-sans text-ink antialiased; }
  a { @apply text-accent; }
  a:hover { @apply underline; }
}
```

フォント: `npm i @fontsource/biz-udpgothic @fontsource/ibm-plex-mono` → `main.tsx` で
`@fontsource/biz-udpgothic/400.css`, `/700.css`, `@fontsource/ibm-plex-mono/400.css`, `/500.css`, `/600.css` を import。
`@fontsource/zen-kaku-gothic-new`, `@fontsource/barlow-condensed` は削除。

### Type scale (Tailwind class → 値)

| 用途 | class | 値 |
|---|---|---|
| Verdict Line (h1) | `text-[36px] md:text-[40px] leading-[1.15] font-bold tracking-[-0.01em]` | 36–40 / 1.15 / 700 |
| Verdict 後半 | `font-normal text-ink-soft` | 同サイズ、400、ink-soft |
| h1 (通常) | `text-[28px] leading-tight font-bold` | 28 / 1.2 / 700 |
| h2 セクション | `text-lg font-bold` | 18 / 1.4 / 700 |
| body | `text-[15px] leading-[1.7] text-ink-soft` | 15 / 1.7 |
| caption | `text-xs leading-normal text-ink-muted` | 12 / 1.5 |
| KPI xl | `font-mono text-[40px] leading-none font-medium` | 40 / 1 / 500 |
| KPI (vitals) | `font-mono text-[30px] leading-none font-medium` | 30 / 1 / 500 |
| KPI 単位 | `text-[13px] text-ink-muted ml-[3px]` | 13 |
| mono label | `font-mono text-xs text-ink-muted` | 12 |
| Status tag | `font-mono text-[11px] font-medium tracking-[0.04em] px-1.5 py-[3px] rounded-sm` | 11 |

### Spacing / shape

- スケール 4 / 8 / 12 / 16 / 24 / 32 / 48。セクション間 `gap-12`(48)、ブロック内 `gap-4`、行内 `gap-2`。
- 本文幅 `max-w-[880px]`(Plan のみ `max-w-[960px]`)、左右 `px-6`。
- 角丸: `rounded-sm`(2px)タグ/セル、`rounded-md`(4px)面。**shadow・rounded-xl・bg-gradient・SVG 等高線は全廃。**
- 区切り: `border-t border-ink`(セクション冒頭の強い罫)、`border-b border-hairline`(行区切り)。

## Shared Components (置き換え・新規)

| 既存 | 変更 |
|---|---|
| `components/Layout.tsx` | 2段ヘッダー。1段目: ブランド(`text-[15px] font-bold`)+ 右端に日付 `font-mono text-xs text-ink-muted` (`YYYY-MM-DD DDD`)。2段目: nav 6 リンク `gap-5 text-sm`、active は `font-bold text-ink border-b-2 border-ink -mb-px`、非 active は `text-ink-muted`。`flex-wrap` で折り返し(横スクロール禁止)。ヘッダー全体 `border-b border-hairline`、sticky・shadow なし。`<main>` は `max-w-[880px] mx-auto px-6 pt-10 pb-24 flex flex-col gap-12`。skip link は維持。 |
| `components/Card.ts` `CARD_CLASS` | `"border-t border-hairline pt-4"` に変更(白カード廃止)。`Card.test.ts` の禁止文字列も更新し、`rounded-xl`, `shadow-sm`, `bg-gradient-to-br` を新たに禁止。 |
| `components/SectionHeading.tsx` | eyebrow(英語アイブロウ)を削除。`as="h2"` は `text-lg font-bold`。新 prop `note?: string` を右に `font-mono text-xs text-ink-muted` で。 |
| `components/StatusBadge.tsx` | 丸ピル廃止。`font-mono text-[11px] font-medium tracking-[0.04em] px-1.5 py-[3px] rounded-sm border`。tone: `good` → `border-hairline text-ink-soft`(無塗り)、`info` → 同じ、`warn` → `bg-warn-tint border-warn-line text-status-warn`、`bad` → `bg-bad-tint border-bad-line text-status-bad`。新 tone `today` → `bg-accent text-paper border-accent`。 |
| **新規** `components/VerdictLine.tsx` | `{ verdict: string; verdictTone?: "neutral"\|"warn"\|"bad"; rest: string; lead?: string; actions?: ReactNode }`。`<h1>` に `verdict`(700)+ `rest`(400, ink-soft)。tone warn/bad のときだけ verdict を status 色に。`lead` は `text-[15px] leading-[1.7] text-ink-soft max-w-[640px]`。 |
| **新規** `components/VitalsRow.tsx` | `{ items: { label; value; unit?; note; noteTone?: "muted"\|"warn"\|"bad"; to? }[] }`。`grid grid-cols-2 md:grid-cols-4 border-t border-ink border-b border-hairline`。各セル `py-4`、最初以外 `pl-4`、最後以外 `pr-4 border-r border-hairline`。label mono 12 muted / value mono 30 500 / note 12(warn は `text-status-warn font-bold`)。`to` があれば `<Link>` でセル全体をリンク。 |
| **新規** `components/SectionBlock.tsx` | `{ title; note?; children }` → `grid md:grid-cols-[160px_1fr] gap-x-8 gap-y-4 scroll-mt-[60px]`。左に `<h2 text-lg font-bold>` と note(mono 12 muted または body 13 muted)。 |
| **新規** `components/CoachNote.tsx` | `{ children; source?: { label; to } }` → `border-l-2 border-ink pl-4 py-0.5 text-[15px] leading-[1.7] text-ink-soft`。source は mono 12 accent リンク、`ml-2 whitespace-nowrap`。 |
| **新規** `components/ChartHeader.tsx` | チャート上の1行: `flex items-baseline gap-3 font-mono text-xs text-ink-muted`、先頭 `text-ink font-semibold`、右端 `ml-auto` にステータス文。 |
| `components/SectionNav.tsx` | 白カード → `sticky top-0 z-20 bg-paper border-b border-hairline flex gap-5 text-sm overflow-x-auto`。リンク `py-2.5 pb-3 text-ink-muted whitespace-nowrap`、現在位置(IntersectionObserver)は `text-ink font-bold border-b-2 border-ink -mb-px`。 |
| `components/EmptyState.tsx` | `text-sm text-ink-muted`、CLI コマンドは `font-mono bg-well px-1.5 rounded-sm text-ink`。 |
| `components/CardSkeleton.tsx` | 罫線 + `font-mono text-[28px] text-metric-compare tracking-[0.1em]` の「——」のみ。パルスアニメなし。 |
| `components/chartTheme.ts` | 下記「Charts」参照。 |
| `components/Disclosure.tsx` | トリガーを `font-mono text-[13px] text-accent` の「… ↓」テキストリンクに。展開時「↑」。 |

## Charts (`chartTheme.ts` / ECharts 共通)

- `INK_COLOR = "#1c1b18"`, `GRID_LINE_COLOR = "#dcd7cc"`, `AXIS_LABEL_COLOR = "#6b675e"`, `CHART_FONT_SIZE = 11`, `textStyle.fontFamily = "IBM Plex Mono"`。
- `METRIC_COLORS`: heart_rate `#b8433f`, speed `#1f6f6b`, cadence `#b07a1d`, power / GCT / VO / VR `#6a4fb3`, elevation `#6b675e`, vo2max / weight / objective 主系列 `INK_COLOR`, 比較系列(Garmin VO2max 等)`#c9c3b6`, hrv `INK_COLOR`, ef `#1f6f6b`, acwr `#3d3a34`, heat_cost `#9a5b12`, fat_mass `#b07a1d`, lean_mass `#1f6f6b`。
- `ZONE_COLORS = ["#e8c9c7","#d49c98","#c2716c","#b8433f","#8a2e2a"]`。
- 基準帯(個人ベースライン・最適帯)は `markArea` `rgba(28,27,24,0.06)`。閾値線は `markLine` 点線: 注意 `#9a5b12`, 高リスク `#a83a2e`。ラベルは mono 11。
- `splitLine` は Y のみ表示(`xAxis.splitLine.show = false`)、`axisLine` なし、`legend` は不要なら省略(直接ラベル)。
- 棒の `borderRadius` は 0。ホームにチャートは置かない(`Sparkline.tsx` は削除)。

## Screens

### 1. Home `/` — `Home Redesign - Morning Brief.dc.html`

Layout: `flex flex-col gap-12`。
1. **VerdictLine** — verdict = `RECOMMENDATION_LABELS[recommendation]` + 「。」、rest = 当日処方から
   `今日は{sessionLabel} {target_km}km、心拍 {hr_high} 以下。`(処方なし → `今日の処方はありません。`)。
   tone: rest → bad, easy → warn, それ以外 neutral。lead = `reasons[0]`、基準外メトリクスがあれば
   `<span class="text-status-warn font-bold">` で強調。actions: 主ボタン「今日のメニュー詳細」(`px-4 py-2.5 bg-ink text-paper text-sm font-bold rounded-sm`、`/plan` へ)と mono リンク「判定の根拠 → コンディション」(`/condition`)。
2. **VitalsRow** 4 セル: HRV 夜間(`latest_ms` ms、note `基準内 · {lo}–{hi}` / 基準外は warn `+{delta} · 上振れ {days}日目`)、安静時心拍(`median_7d`)、睡眠 / 準備度(`74 / 68` を `/` mono 13 muted 区切り、note 睡眠時間)、負荷 ACWR(note `{status label} · 週 {load_km}km`)。各セルは `/condition#recovery` 等へリンク。**Hero のチップと SnapshotTiles は削除**(重複排除)。
3. **今週** — 見出し `今週` + mono note `MM/DD – MM/DD · {phase} {n}/{total}週 · 計画 {km}km`、右に「月間計画 →」。
   **WeekStrip**: `grid grid-cols-7 border-t border-ink border-l border-hairline`、各セル `border-r border-b border-hairline p-3 min-h-[118px] flex flex-col gap-1.5`。
   日付 mono 12 muted(今日は accent 600 + `TODAY` 10px tracking)。セッション名 14 bold、目標 mono 12。
   状態: 今日 `bg-accent-tint`、休養指示/代替 `bg-warn-tint` + 文字 status-warn、休養日は名前を muted 400。
   下に **CoachNote**(`recommendations[0]`、source = `/weekly-reviews/:weekStart`)。
4. **進捗** 2 列 `grid md:grid-cols-2 gap-8 border-t border-hairline pt-6`。左: レース(`pickFeaturedRace` 維持)—mono 12 `{race_name} · {priority}`、数字 mono 44 + 「日」15 bold、mono 13 `予測 … · 目標 … · {gap}`。右(`border-l border-hairline pl-8`): 前回のラン 1 本のみ — mono 12 `前回 · MM/DD DDD · {name}`、距離 mono 44 + km、`{pace}/km · {hr}bpm`、`評価 {stars} — {summary lead}` + 「すべてのラン →」。**RecentRuns の 5 行リストは廃止。**

### 2. Activity Detail `/activities/:id` — `Activity Detail Redesign`

`gap-12`、各セクションは **SectionBlock**(左 160px ラベル列)。
1. ヘッダ: 「← 一覧」mono 13 / 1 行目 mono 13 muted `YYYY-MM-DD DDD · HH:MM · {sessionLabel}(処方 {target})`、右端に VersionSelect を mono 12 テキスト「分析 v{n} · MM/DD HH:MM ▾」。
   `<h1 text-[36px]>` = activity_name + ★評価(`font-mono font-medium text-[28px] text-star tracking-[0.05em]`)。
   結論 1 文 `text-lg leading-[1.6]` = `splitLead(summary).lead`、改善点があればその要点を `text-status-warn font-bold` で。
   **KPI dl** = VitalsRow 流儀で 距離 / 時間 / 平均ペース / 平均心拍(mono 40)、心拍セルに note `上限 {hr_high} · 超過 {mm:ss}`。
   その下 mono 13 muted `前回比({days}日前・{type} {km}): ペース {±}秒/km · HR {±} · GCT {±}ms · ケイデンス {±}`(VsPreviousChips を1行テキストに)。
2. **SectionNav**(sticky)。
3. 総合評価: body 15、強み `✓`(ink) / 改善 `!`(status-warn bold)の `flex gap-3` リスト(各先頭 1 件ずつではなく全件、4 件超で Disclosure)、`next_action` を **CoachNote** 太字で、末尾 Disclosure リンク「強み・改善点をすべて見る(n / m) ↓」。
4. タイムシリーズ: トグルは mono 12。ON = `bg-ink text-paper rounded-sm px-2.5 py-1` + 先頭に metric 色の 14×2px バー、OFF = `border border-hairline text-ink-soft`。既定 ON は HR とペース。5 番目以降は「+ パワー / 高度 / 上下動 / 上下動比」リンクで展開。チャート高 260。
5. コース: Leaflet、タイル grayscale(`filter: grayscale(1) opacity(.85)`)、トラック ink 2px。
6. スプリット: `font-mono text-sm`、ヘッダ mono 11 muted `border-b border-ink`、行 `border-b border-hairline py-2`。比例バーは維持、色 `rgba(31,111,107,.14)`(ペース)/ `rgba(184,67,63,.14)`(HR)。**フォーム異常が検出されたスプリット行は `bg-warn-tint`、該当セル値を `text-status-warn font-semibold`。** 10 行超は「全 n スプリットと解説を表示 ↓」で Disclosure。
7. フェーズ評価: `grid grid-cols-[120px_80px_1fr]` 行(名前 15 bold / ★ mono 13 star / 評価 14 + `実際: …` mono 12 muted)。タイムラインの丸ドットは廃止。
8. 効率分析: 見出し右に ★。GCT / VO / VR は VitalsRow 3 列(mono 28)、期待値差が悪化方向なら note を warn。lead 文 15、Disclosure「分析の詳細 ↓」。

### 3. Plan `/plan` — `Plan Redesign`

`max-w-[960px]`、`gap-8`。
1. 月ナビ: 「← 8月」「10月 →」を **副ボタン**(`px-3 py-[7px] border border-ink text-[13px] font-bold rounded-sm`)、中央 `<h1 text-[28px]>` `YYYY年M月`、右端「週次レビュー一覧 →」。
2. 月の要約 1 文 `text-xl leading-[1.5]`: `{phase}期 {n}/{total} 週。` bold + `今月の処方 {prescribed} 本のうち {done} 本実施・{replaced} 本代替、{遅れなし|遅れ n 本}。今週のロングは {km}km に伸びる。` 400。
   その下 dl mono: 計画 km / 実績 km / 実施率 `{done}/{resolved}` + `確定分` / ポイント練 `週{n}`(値 mono 18 500)。
3. **BlockBands** → 1 本の帯: `grid grid-cols-[96px_repeat(7,1fr)]` の 2 列目以降に `grid-cols-{daysInView}` で日単位のスパン。ビルド系 = `bg-ink text-paper`、カットバック/テーパー = `bg-warn-tint text-status-warn border border-warn-line`、レース = `bg-bad-tint text-status-bad`。高さ 22、mono 11 tracking、内容 `{phase} · {title} · MM/DD – MM/DD · ポイント練 週{n} · 体重 {mode}`。
4. **MonthGrid**: `<table>` → CSS grid 行(`grid-cols-[96px_repeat(7,1fr)] border-b border-hairline`)、ヘッダ mono 12 muted `border-b border-ink`。
   週ヘッダ列(`/weekly-reviews/:weekStart` リンク、`border-r border-hairline`): 週ラベル mono 13 600(レビューあり = accent、なし = ink)、実施 `d/p 実施`(tone 判定は `adherenceTone` を維持、warn/bad のみ着色、進行中は `0/4 · 進行中`、未処方は `未処方`)、週合計 km または `計画 {km}km` / `ロング {km}km`。
   **DayCell** `p-2.5 pr-2 min-h-[96px] border-r border-hairline flex flex-col gap-1`: 日 mono 12 muted / セッション 13 / 3 行目 mono 12。
   - done: セッション **bold** + 実績 `{km} · {pace} · {hr}` を ink(実績行の有無が「実施」の表現。StatusBadge は使わない)。ロングは ★n(`text-star mono 11`)を名前の右に。
   - prescribed(未来): セッション bold + 目標 `{km}km ≤{hr}` muted。
   - replaced: `bg-warn-tint`、日付・文字 status-warn、`<s>元セッション 目標</s> → 代替内容`。
   - skipped: 名前と目標に `line-through text-ink-muted`。
   - rest 指示(完全休養): `bg-warn-tint`、名前 bold status-warn、理由 12。
   - today: `bg-accent-tint`、日付 accent 600 + `TODAY`。
   - 月外: 全体 `text-ink-faint`。
   - ラダー目標のみの日(未処方週の最終列): `ロング目標` muted 13 + 目標 mono 12 muted。
   - 凡例を表の下に mono 12 で 1 行(モックの文言)。
5. 直近レビューの **CoachNote**(`/weekly-reviews/:weekStart` リンク)。

### 4. Condition `/condition` — `Condition Redesign`

1. VerdictLine: `回復はほぼ正常。` / `回復不足。` 等 + rest に基準外項目と注意点件数。lead は `reasons[0]`。
2. VitalsRow 4(HRV / RHR / 睡眠・準備度・Body Battery を `/` 区切り / ACWR)。id `today`。
3. `id="form-anomaly"` 今週の注意点(SectionBlock、note `直近{weeks}週 · {scanned}本を走査`): フラグ 0 件 → body 15 muted「直近のランでフォームの異常は検出されていません。」。1 件以上 → 各フラグを `bg-warn-tint border border-warn-line rounded-md px-5 py-4`、1 行目 mono 13 status-warn `MM/DD DDD · {type} {km}` + `異常 {n}件(高 {m})` + 右端「ランを見る →」、2 行目 body 15 ink = `top_recommendation`。
4. `id="recovery"` 回復トレンド: **RHR と HRV を 2 枚の単系列チャート(高 150)** に分割、各上に ChartHeader(`安静時心拍 · 4週 · 基準帯 lo–hi · 右端: 直近 n 日 基準超(warn)`)。基準帯 markArea、超過点だけ `#9a5b12`。
5. 個人基準との差: WellnessBaselineChart を **z スコア横棒**に置換。`grid grid-cols-[110px_1fr_90px]` 行、トラック `h-2.5 bg-well`、中央線 1px ink、棒は中央から左右へ(不利方向 = 右、`|z|>1.5` は `bg-status-warn` + 値 warn bold、それ以外 ink)。脚注 mono 12「基準 = 直近 28 日の中央値 ± MAD。|z| > 1.5 を『基準外』とする。」
6. `id="training-load"` 訓練負荷: 1 行 mono 13 `ACWR {x} · 急性 {a}km / 慢性週平均 {c}km · 12 週` → チャート 200(棒 ink、ACWR 線 ink-soft 右軸、最適帯 markArea、1.5 に bad 点線のみ)。high_risk の alert は `bg-bad-tint border-bad-line text-status-bad rounded-md px-4 py-3 text-sm`。
7. 体組成: dl mono(体重 / 体脂肪 / 除脂肪、値 mono 20)+ チャート 160。

### 5. Performance `/performance` — `Performance Redesign`

1. 1 行目: mono 13 muted `週次トレンド · MM/DD – MM/DD · 解説 v{n}`、右端に 週/月 セグメント(`inline-flex border border-hairline rounded-sm font-mono text-[13px]`、選択 = `bg-ink text-paper px-3 py-1.5`)。
2. VerdictLine: `速くなっている。` / `停滞。` / `落ちている。` + rest に主要根拠。lead は narration の先頭段落(`ClampedProse` 相当)、「コーチ解説の全文 ↓」で TrendNarrationCard 全文を Disclosure。
3. VitalsRow 4: 客観 VDOT / 効率 EF / クリティカルスピード / 耐久性 デカップリング(目標未達は warn)。
4. SectionNav(9 項目、sticky)。
5. 9 セクションを SectionBlock で縦 1 列(2 列グリッド廃止)。各: 上に mono 13 の要約 1 行(`今週 62.7km · 4週平均 58.1 …`) → チャート 160–200。
   効率推移のみ `grid grid-cols-[2fr_1fr]` で右にゾーン分布(`grid-cols-[28px_1fr_40px]` 行、トラック `h-2 bg-well`、塗り ZONE_COLORS)。

### 6. Goal `/goal` — `Goal Redesign`

1. VerdictLine: `目標 {target} に対して予測 {pred}。` + `あと {days} 日、{順調|前倒し|遅れ}。差 {gap} は{要因}で埋める。` lead に VDOT 推移と到達見込み。
2. **A/B 2 列** `grid md:grid-cols-2 border-t border-ink border-b border-hairline`(左 `pr-8 border-r`、右 `pl-8`): 1 行目 mono 12 `[A] {race} · YYYY-MM-DD DDD · {type} {km}`(A タグ `bg-ink text-paper`、B タグ `border border-ink`)、日数 mono 64 500 + 「日」18 bold、dl 3 列 mono(目標 / 予測(VDOT x) / 差、差が負なら status-warn)、notes 13。
3. 予測の推移(新規チャート 180): 予測フルタイム ink、目標 点線、レース日縦線、必要な傾きを hairline。データは `race-readiness` の履歴が無ければ省略可。
4. 現フェーズ: `current_focus` を `text-xl font-bold`、`parseFocusNotes` の節を `grid-cols-[160px_1fr]` の罫線行に(4 件目以降は「ルール(n件) 展開 ↓」)。
5. その他のレース: `grid-cols-[120px_1fr_100px_90px_70px]` 罫線行(日付 mono / 名前 bold / 種別 / 目標 / `{priority} · {status}` mono 11)。RaceCard は廃止。
6. 昨季の振り返り: `grid-cols-[120px_1fr]` 行、左に季節ラベル + 期間 mono 12、右 narrative 14、`key_learnings` は `border-l-2 border-ink pl-3` で「学び:」太字(2 件目以降は「学びを表示 ↓」)。

## Interactions & Behavior

- ナビ active: `border-b-2 border-ink font-bold`。hover: `text-ink`(下線なし)。リンク hover は `underline`。
- VitalsRow / 進捗セル全体がリンクのときは `hover:bg-surface`。
- SectionNav の現在位置は IntersectionObserver(`rootMargin: -60px 0px -70%`)で更新。`scroll-mt-[60px]`。
- Disclosure トリガーは常にテキストリンク(「… ↓ / ↑」)。
- `stagger-in` アニメーションは削除(`index.css` から `@keyframes stagger-rise` を除去)。`prefers-reduced-motion` 配慮不要になる。
- Loading: `CardSkeleton`(罫線 + 「——」)。Error: `bg-bad-tint border border-bad-line text-status-bad rounded-md px-4 py-3 text-sm` + 副ボタン「再試行」。
- 空状態: `EmptyState`(text-sm muted + mono CLI コマンド)。
- レスポンシブ: `md` 未満で VitalsRow は 2 列、SectionBlock は 1 列(ラベルが上)、Goal の A/B は縦積み、WeekStrip / MonthGrid は横スクロール許容。モバイル最適化は現時点で対象外。

## State Management

既存の hooks(`useRecoveryStatus`, `useMonthPlan`, `useWeeklyReviews`, `useTrainingLoad`, `useRecoveryTrend`,
`useWellnessBaselineDeviation`, `useRaceReadiness`, `useGoal`, `useActivities`, `useTrendNarration` 等)を
そのまま使う。新しい API は不要。追加が必要なロジック:
- `utils/verdict.ts`(新規): `homeVerdict(status, todayPrescription)`, `conditionVerdict(...)`, `performanceVerdict(narration, kpis)`, `goalVerdict(readiness, race)` — 各ページの VerdictLine 文字列を組む純関数(テストしやすく)。
- `utils/format.ts`: `formatDateLabel(iso) → "MM/DD DDD"`(DDD = MON…)と `formatHeaderDate(date) → "YYYY-MM-DD DDD"` を追加し、日付表記をこの 2 種 + `YYYY年M月` に統一。
- `utils/baselineZ.ts`(新規): WellnessBaselineDeviation → z スコア(中央値 ± MAD)。

## Implementation Order (Phase 0 → 3)

1. **Phase 0 — トークン**: `index.css` 置換、fontsource 差替え、`chartTheme.ts` 更新、`CARD_CLASS` / `StatusBadge` / `SectionHeading` / `SectionNav` / `EmptyState` / `CardSkeleton` / `Disclosure` / `Layout` を上表どおりに変更。`ConditionCard.tsx` と `TrainingLoadBlock.tsx` の直書き `emerald-100` 等をトークンへ。`Card.test.ts` の禁止リストに `rounded-xl` `rounded-2xl` `shadow-sm` `bg-gradient` `rounded-full` を追加。この時点で全ページが新パレットで動くこと(見た目は暫定)。
2. **Phase 1 — 共通プリミティブ + Home**: `VerdictLine` `VitalsRow` `SectionBlock` `CoachNote` `ChartHeader` を追加。`Dashboard.tsx` を仕様 1 に組み替え(`TodayHero` `SnapshotTiles` `Sparkline` `RecentRuns` は削除、`ThisWeekPlan` → `WeekStrip`、`RaceProgress` → 進捗左列)。テストを新構造に更新。
3. **Phase 2 — Plan / ActivityDetail**: `MonthGrid` を grid 化、`DayCell` の状態表現、`BlockBands` を帯に。ActivityDetail のヘッダ・トグル・スプリット行ハイライト・フェーズ行。`HeroHeader` から等高線 SVG とグラデーションを除去(`CONTOUR_PATTERN` 定数は 3 ファイルとも削除)。
4. **Phase 3 — Condition / Performance / Goal**: 各 VerdictLine、Condition の 2 枚チャート化と z スコア棒、Performance の 1 列化 + 週/月セグメント、Goal の 2 列 hero と表化。

各 Phase の完了条件: `npm run build && npm run test` が通り、`grep -rn "rounded-xl\|shadow-sm\|bg-gradient\|font-display\|font-numeric" src/` が 0 件。

## Assets

- フォント: BIZ UDPGothic(400/700)、IBM Plex Mono(400/500/600)— いずれも @fontsource(SIL OFL)。
- アイコン・画像なし。★は文字(U+2605 / U+2606)。矢印は「→ ← ↓ ↑ ▾」の文字。
- 等高線 SVG(`CONTOUR_PATTERN`)は削除。
