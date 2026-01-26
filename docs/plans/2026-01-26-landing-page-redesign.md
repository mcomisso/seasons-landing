# Seasons Landing Page Redesign

**Date:** 2026-01-26
**Status:** Approved
**Goal:** Create a designer-quality landing page that feels "clever + essential" with emphasis on iOS downloads

---

## Design Principles

1. **Clever** — Emphasize smart optimization and money-saving intelligence
2. **Essential** — Focus on the pain point urgency (wasted money on unused subscriptions)
3. **Minimal** — Fewer sections, more whitespace (like myvinyls.app)
4. **Streaming-native** — Use Netflix/Disney+ visual patterns to feel familiar to the target audience

---

## Visual System

### Colors
- **Background:** Dark gradient (deep purple-black, #0f0c29 → #302b63 → #24243e)
- **Primary accent:** Purple gradient (#6C4EFF → #9D7CFF)
- **Text:** White headlines, gray (#9CA3AF) body text
- **Glows:** Purple ambient lighting behind key elements

### Typography
- **Headlines:** Bold, large (5xl-7xl), tight leading
- **Body:** Light weight, generous line height, muted color
- **Episode markers:** Small, uppercase, muted purple

### Effects
- Subtle film grain texture on background
- Purple glow/bloom behind phone screenshots
- Hover lift + glow on interactive cards
- Streaming-style gradient overlays on feature cards

---

## Page Structure

### 1. Hero Section (100vh)

**Layout:** Full viewport, centered content

**Elements:**
- Top-left: Seasons "S" logo mark only (no nav clutter)
- Center:
  1. Headline: "Stop paying for shows you're not watching."
  2. Subheadline: "Seasons tells you exactly when to subscribe and cancel — so you only pay for what you love."
  3. Phone screenshot (`phone.png`) with purple glow
  4. App Store download button
  5. "4.8★ on the App Store" as subtle social proof

**Visual:** Phone floats with soft purple glow, like a screen illuminating a dark room

---

### 2. Features Section (Streaming-Style Cards)

**Layout:** Three cards in horizontal row (responsive to stack on mobile)

**Card structure:**
- Large app screenshot
- Gradient overlay at bottom (transparent → dark)
- Feature title + one-line description over gradient

**The three features:**

| Feature | Screenshot | Title | Description |
|---------|------------|-------|-------------|
| 1 | `horizontal.png` | "Your Timeline, Your Rules" | See all your subscriptions on one timeline. Know exactly what's costing you. |
| 2 | `phone.png` (calendar crop) | "Never Miss a Premiere" | Get notified when new seasons drop. Subscribe at the perfect moment. |
| 3 | Subscriptions view from `backgroundSite.png` | "Cancel with Confidence" | See which services have nothing left to watch. Cancel without FOMO. |

**Visual:** Rounded corners, subtle border, hover lift effect, Netflix-style row aesthetic

---

### 3. How It Works (Episode Arc)

**Layout:** Three columns, minimal typography-focused design

**Structure:**
```
EP 01                    EP 02                    EP 03
─────                    ─────                    ─────
"Add Your Shows"         "Watch the Timeline"     "Save Money"

Search any show or       Seasons tracks when      Cancel services with
movie. We'll tell you    new seasons drop and     nothing left to watch.
where it's streaming.    which subs are worth     Keep the ones you love.
                         keeping.
```

**Visual:**
- Episode markers in small muted purple
- Titles in bold white
- Dashed connecting line between episodes
- Payoff line below: "Season Finale: You stop wasting money."

---

### 4. Final CTA Section

**Layout:** Centered, no container/card

**Elements:**
1. Headline: "Your streaming budget deserves better."
2. Large App Store download button
3. Reassurance: "Free to download. No credit card required."
4. Secondary: "Android coming soon — join the waitlist" (links to form below)

**Visual:** `2phones.png` as subtle background element, purple ambient glow from center

---

### 5. Android Waitlist (Secondary)

**Layout:** Collapsible or scroll-to section, not prominent

**Elements:**
- Small heading: "Android Version Coming Soon"
- HubSpot email form (existing integration)

---

### 6. Footer

**Layout:** Single row, minimal

**Elements (left to right):**
- Seasons "S" logo (small)
- Links: Privacy · Terms
- Social icons: Twitter, Facebook
- © 2024 MYV Studios

**Visual:** Muted gray text (~60% opacity), thin purple border-top at 10% opacity

---

## Assets Usage

| Asset | Usage |
|-------|-------|
| `seasonslogo.png` | Header logo mark, footer |
| `phone.png` | Hero section (main), Feature 2 |
| `horizontal.png` | Feature 1 (timeline/Gantt view) |
| `backgroundSite.png` | Feature 3 (subscriptions view - cropped) |
| `2phones.png` | CTA section background element |
| `App Store.svg` | Download buttons |

---

## Removed Elements

- Stats section (10K users, 50K shows, $200K saved) — aspirational/unverified
- Heavy navigation bar
- Multiple CTA styles
- Template attribution in visible footer

---

## Technical Notes

- Keep Tailwind CSS via CDN (no build process)
- Maintain HubSpot form integration
- Maintain analytics scripts (HubSpot, Ahrefs)
- Add subtle CSS animations (fade-in on scroll, hover effects)
- Ensure mobile-first responsive design
