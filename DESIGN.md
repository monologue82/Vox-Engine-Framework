# VoxEngine DESIGN.md

> A plain-text design system for AI agents. Follow this document to produce pixel-consistent UI.
> Based on Google Stitch DESIGN.md format — [awesome-design-md](https://github.com/VoltAgent/awesome-design-md)

---

## 1. Visual Theme & Atmosphere

VoxEngine is a **warm, editorial voice-AI platform**. The visual language draws from premium editorial publications — clean, airy, and human-centered.

**Mood keywords:** editorial, warm, airy, refined, human, precise
**Density:** airy — generous whitespace, no clutter
**Design philosophy:** "Clarity through reduction." Every element earns its place. No decorative fluff — only purposeful design that guides the user's eye through: **Speak → Translate → Hear**.

**Key visual signatures:**
- Off-white canvas (`#f5f5f5`) with warm near-black ink (`#292524`)
- Atmospheric pastel gradient orbs (mint → peach → lavender → sky) floating in the background — blurred, low-opacity, decorative only
- Sans-serif display type (Plus Jakarta Sans Light 300) for headings — modern, airy, editorial
- Sans-serif body type (Inter) for UI — clean, modern, readable
- Pill-shaped CTAs — warm near-black, no harsh colors
- Subtle hairlines (`#e7e5e4`) for card boundaries
- Single shadow tier — soft, barely perceptible

**What VoxEngine is NOT:**
- NOT a dark-mode-first app (light, airy default)
- NOT a flashy, color-saturated tool
- NOT a dense dashboard (breathe!)

---

## 2. Color Palette & Roles

### Surfaces

| Token | Hex | Role |
|---|---|---|
| `--color-canvas` | `#f5f5f5` | Page background — off-white |
| `--color-canvas-soft` | `#fafafa` | Lighter section background |
| `--color-surface-card` | `#ffffff` | Pure white cards |
| `--color-surface-strong` | `#f0efed` | Badge backgrounds, hover states |
| `--color-surface-dark` | `#0c0a09` | Rare dark hero sections |

### Ink / Text

| Token | Hex | Role |
|---|---|---|
| `--color-ink` | `#0c0a09` | Display headings, primary text |
| `--color-primary` | `#292524` | Primary CTA buttons, active links |
| `--color-primary-active` | `#0c0a09` | Button press / hover state |
| `--color-body` | `#4e4e4e` | Default body text |
| `--color-body-strong` | `#292524` | Emphasized body text |
| `--color-muted` | `#777169` | Subtitles, secondary info |
| `--color-muted-soft` | `#a8a29e` | Disabled text, placeholders |

### Hairlines / Borders

| Token | Hex | Role |
|---|---|---|
| `--color-hairline` | `#e7e5e4` | Default 1px card/divider border |

### Semantic

| Token | Hex | Role |
|---|---|---|
| `--color-success` | `#16a34a` | Success, connected status |
| `--color-error` | `#dc2626` | Errors, disconnected status |
| `--color-warning` | `#f59e0b` | Warnings |
| `--color-info` | `#3b82f6` | Info, processing status |
| `--color-data` | `#8b5cf6` | Data / debug / purple |

### Atmospheric Gradients (orbs only, never UI elements)

| Token | Hex |
|---|---|
| `--color-orb-mint` | `#a7e5d3` |
| `--color-orb-peach` | `#f4c5a8` |
| `--color-orb-lavender` | `#c8b8e0` |
| `--color-orb-sky` | `#a8c8e8` |

---

## 3. Typography Rules

### Font Families

| Role | Stack |
|---|---|
| Display (headings) | `'Plus Jakarta Sans', 'Inter', system-ui, sans-serif` |
| Body / UI | `'Inter', 'Plus Jakarta Sans', system-ui, sans-serif` |
| Monospace (code, logs) | `'JetBrains Mono', 'SF Mono', 'Fira Code', monospace` |

### Hierarchy Table

| Token | Family | Size | Weight | Line-height | Letter-spacing | Use |
|---|---|---|---|---|---|---|
| `display-xl` | Plus Jakarta Sans | 48px | 300 | 1.08 | -0.96px | Page hero |
| `display-lg` | Plus Jakarta Sans | 36px | 300 | 1.17 | -0.36px | Section heads |
| `display-md` | Plus Jakarta Sans | 28px | 300 | 1.2 | -0.28px | Card group titles |
| `title-md` | Inter | 20px | 600 | 1.35 | 0 | Component titles |
| `title-sm` | Inter | 16px | 600 | 1.4 | 0 | List labels |
| `body-md` | Inter | 16px | 400 | 1.6 | 0 | Default body |
| `body-strong` | Inter | 16px | 600 | 1.5 | 0 | Emphasized body |
| `body-sm` | Inter | 14px | 400 | 1.5 | 0 | Secondary body |
| `caption` | Inter | 13px | 500 | 1.4 | 0.3px | Section labels |
| `caption-uppercase` | Inter | 12px | 600 | 1.4 | 0.96px | Badges, tags |
| `button` | Inter | 15px | 500 | 1.0 | 0 | CTA buttons |
| `mono-sm` | JetBrains Mono | 13px | 400 | 1.6 | 0 | Debug logs, code |

---

## 4. Component Stylings

### 4.1 Buttons

**Primary Button (`.btn-primary`)**
- Background: `--color-primary` (#292524)
- Text: white (#ffffff)
- Font: `button` token (Inter 15px/500)
- Padding: 10px 20px, height: 40px
- Radius: `9999px` (pill)
- Hover: background → `--color-primary-active` (#0c0a09), lift 1px, shadow `0 8px 30px rgba(0,0,0,0.08)`
- Active: translateY(0)
- Disabled: opacity 0.5, pointer-events none
- Transition: all 0.2s ease

**Secondary Button (`.btn-secondary`)**
- Background: `--color-surface-strong` (#f0efed)
- Text: `--color-body-strong` (#292524)
- Same sizing/radius as primary
- Hover: background → `--color-hairline` (#e7e5e4)

**Danger Button (`.btn-danger`)**
- Background: `--color-error` (#dc2626)
- Text: white
- Hover: background → #b91c1c

**Large variant (`.btn-lg`)**: padding 14px 28px, height 48px, font 16px

### 4.2 Cards

**Default Card (`.card`)**
- Background: white (#ffffff)
- Radius: 16px (`--radius-xl`)
- Padding: 24px
- Border: 1px solid `--color-hairline`
- Shadow: `0 2px 8px rgba(0,0,0,0.02)` (barely visible)
- Hover (optional): shadow → `0 4px 16px rgba(0,0,0,0.04)`, lift -2px

**Card Header (`.card-header`)**
- Bottom border: 1px solid `--color-hairline`
- Padding-bottom: 20px
- Margin-bottom: 24px
- Icon color: `--color-primary`

### 4.3 Form Elements

**Select / Input (`.form-input`)**
- Background: `--color-canvas-soft` (#fafafa)
- Border: 1px solid `--color-hairline`
- Radius: 8px (`--radius-md`)
- Padding: 12px 16px, height: 44px
- Font: Inter 15px
- Focus: border → `--color-primary`, ring `0 0 0 3px rgba(41,37,36,0.08)`
- Hover: border → `--color-muted-soft`

**Textarea**
- Same styling as input
- Min-height: 120px
- Resize: vertical
- Line-height: 1.6

### 4.4 Status Indicators

**Status Dot (`.status-dot`)**
- Size: 10px × 10px, radius: 50%
- `.online`: `--color-success` with glow `0 0 8px rgba(22,163,74,0.4)`
- `.offline`: `--color-error` with glow `0 0 8px rgba(220,38,38,0.4)`
- `.loading`: `--color-warning` with pulse animation

**Status Banner (`.status-indicator`)**
- Flex row with icon + text
- Padding: 12px 16px, radius: 8px
- `.idle`: bg `rgba(119,113,105,0.1)`, text `--color-muted`
- `.translating`/`.processing`: bg `rgba(59,130,246,0.1)`, text `--color-info`, icon spin
- `.complete`/`.connected`: bg `rgba(22,163,74,0.1)`, text `--color-success`
- `.error`: bg `rgba(220,38,38,0.1)`, text `--color-error`

### 4.5 Log Panel (`.log-panel`)
- Background: `--color-canvas-soft`
- Radius: 12px, padding: 20px
- Height: 300px, overflow-y: auto
- Font: JetBrains Mono 13px
- Custom scrollbar: 6px width, track `--color-hairline`, thumb `--color-muted-soft`

### 4.6 Stats Cards (`.stat-card`)
- Background: `--color-canvas-soft`
- Radius: 8px, padding: 20px
- Text-align: center
- Value: Inter 600 24px, `--color-body-strong`
- Label: Inter 13px, `--color-muted`

### 4.7 Navigation (`.top-nav`)
- Height: 64px
- Background: `--color-canvas`
- Bottom border: 1px solid `--color-hairline`
- Sticky top, z-index: 100
- Links: Inter 15px/500, `--color-body`, hover → `--color-ink`

### 4.8 Waveform Visualization
- Container: `--color-canvas-soft`, radius 12px, min-height 120px
- Bars: 3px wide, gradient `--color-primary` → `--color-muted-soft`
- Active bars: gradient `--color-success` → `--color-primary`
- Height transition: 0.05s ease

### 4.9 Progress Bar
- Height: 4px, radius: 2px
- Track: `--color-hairline`
- Fill: linear gradient lavender → sky
- Width transition: 0.3s ease

---

## 5. Layout Principles

### Spacing Scale
Base unit: **4px**

| Token | Value |
|---|---|
| `--spacing-xs` | 8px |
| `--spacing-sm` | 12px |
| `--spacing-base` | 16px |
| `--spacing-md` | 20px |
| `--spacing-lg` | 24px |
| `--spacing-xl` | 32px |
| `--spacing-xxl` | 48px |
| `--spacing-section` | 96px |

### Container
- Max-width: 1200px (full-page), 1400px (debug/workbench pages)
- Horizontal padding: 24px
- Center-aligned via `margin: 0 auto`

### Grid
- 2-column grid for side-by-side layouts (`.grid-2`)
- 4-column grid for stat cards (`.grid-4`)
- Gap: 24px (`--spacing-lg`)
- Collapse to single column below 768px

### Whitespace Philosophy
- Section rhythm: 96px between major sections
- Card internal padding: 24px minimum
- Between cards: 24px gap
- "Breathe" — when in doubt, add more space. Clutter is the enemy.

---

## 6. Depth & Elevation

Single shadow tier system. No heavy drop shadows — subtlety is key.

| Level | Treatment |
|---|---|
| Flat (canvas) | No shadow, `--color-canvas` background |
| Card (resting) | `0 2px 8px rgba(0,0,0,0.02)` — barely visible |
| Card (hovered) | `0 4px 16px rgba(0,0,0,0.04)` + translateY(-2px) |
| Elevated (dropdowns, tooltips) | `0 8px 30px rgba(0,0,0,0.08)` |
| Hairline border | 1px `--color-hairline` on all cards |

**Rule:** Every card has a 1px hairline border. Shadows alone are not enough — the hairline anchors the card on the canvas.

---

## 7. Do's and Don'ts

### DO
- ✅ Use the spacing tokens — never hardcode random px values
- ✅ Use the color tokens — never use raw hex values in components
- ✅ Use the typography tokens — stick to the hierarchy
- ✅ Keep cards white on off-white canvas
- ✅ Add 1px hairline border to every card
- ✅ Use pill buttons (9999px radius) for all CTAs
- ✅ Keep gradient orbs in the background only, blurred, low opacity
- ✅ Animate with `ease` timing, 0.2s–0.3s duration
- ✅ Use monospace for all debug/log/code output
- ✅ Keep the 3-step workflow clear: Speak → Translate → Hear

### DON'T
- ❌ Don't use saturated/bright colors on UI elements
- ❌ Don't use box-shadows without hairline borders on cards
- ❌ Don't use dark backgrounds (except rare hero sections)
- ❌ Don't mix serif and sans-serif in the same text block
- ❌ Don't use hardcoded pixel values — tokens only
- ❌ Don't animate with linear timing — always `ease`
- ❌ Don't create dense layouts — respect whitespace
- ❌ Don't use emoji in UI text (icons from Font Awesome only)
- ❌ Don't use more than 2 font families on a page

---

## 8. Responsive Behavior

### Breakpoints
- **Desktop:** > 900px — full 2/4-column grid
- **Tablet/Mobile:** ≤ 900px — single column stack

### Collapsing Strategy
- Grid columns collapse to single column
- Stat grids (4-col) collapse to 2-col on mobile
- Cards stack vertically
- Navigation remains sticky but links may wrap

### Touch Targets
- Minimum touch target: 40px × 40px
- Buttons always ≥ 40px height
- Form inputs always ≥ 44px height

---

## 9. Agent Prompt Guide

### Quick Color Reference
```
Primary CTA: #292524 (warm near-black)
Page BG:    #f5f5f5 (off-white)
Card BG:    #ffffff (white)
Body text:  #4e4e4e (warm gray)
Success:    #16a34a
Error:      #dc2626
Hairline:   #e7e5e4
```

### Ready-to-Use Prompts

**"Build a new page for VoxEngine"**
```
Use the VoxEngine DESIGN.md. Off-white canvas (#f5f5f5), warm near-black ink (#292524), 
Inter for body, Plus Jakarta Sans Light for headings. White cards with 1px #e7e5e4 hairlines 
and 16px radius. Pill buttons (#292524, 9999px radius). Generous whitespace (24px gaps, 
24px card padding). Monospace logs. Atmospheric gradient orbs in background only.
```

**"Add a status indicator"**
```
Follow VoxEngine DESIGN.md status indicator patterns: 10px circle with color + glow, 
or banner with icon+text in rounded 8px container with 10% opacity semantic backgrounds.
```

**"Style a form"**
```
Follow VoxEngine DESIGN.md: #fafafa background, 1px #e7e5e4 border, 8px radius, 
12px 16px padding, Inter 15px. Focus ring: #292524 border + 3px rgba(41,37,36,0.08) glow.
```

**"Create an animation"**
```
Follow VoxEngine DESIGN.md: ease timing, 0.2s–0.3s duration. Subtle lift on hover 
(translateY(-1px) + shadow increase). No linear animations. No bouncing/flashy effects.
Fade-in for new elements, pulse for loading states, blink for streaming cursors.
```