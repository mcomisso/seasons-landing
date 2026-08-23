#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const NODE_MODULES = "/Users/matcom/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const sharp = require(path.join(NODE_MODULES, "sharp"));

const packDir = path.resolve(__dirname, "..");
const sourceDir = path.join(packDir, "source", "svg");
const exportDir = path.join(packDir, "exports");
const logoPath = path.resolve(packDir, "..", "..", "seasonslogo.png");

const C = {
  ink: "#070708",
  surface: "#111116",
  surface2: "#191820",
  white: "#F7F5F0",
  muted: "#B8B4AC",
  faint: "#6F6B66",
  amber: "#FFB43B",
  amberSoft: "#FFD889",
  purple: "#7251FF",
  purpleSoft: "#A99AFF",
  green: "#5BE29A",
};

const QUALIFICATION = "Example assumes a UK £9.99 monthly plan, subscription starting 3 April 2026, monthly renewal on the 3rd, watching after the 5 June finale, and no other Apple TV viewing during the release window. Prices and dates can change.";
const SOURCES = "Sources: Apple release schedule and Apple TV UK price. Checked 23 August 2026.";

fs.mkdirSync(sourceDir, { recursive: true });
for (const p of ["instagram", "tiktok", "reddit", "previews"]) {
  fs.mkdirSync(path.join(exportDir, p), { recursive: true });
}

const logoData = `data:image/png;base64,${fs.readFileSync(logoPath).toString("base64")}`;

function esc(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function lines(items, { x, y, size, lineHeight, fill = C.white, weight = 500, anchor = "start", letterSpacing = 0 }) {
  const tspans = items.map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : lineHeight}">${esc(line)}</tspan>`).join("");
  return `<text x="${x}" y="${y}" fill="${fill}" font-family="Helvetica Neue, Helvetica, Arial, sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" letter-spacing="${letterSpacing}">${tspans}</text>`;
}

function text(value, { x, y, size, fill = C.white, weight = 500, anchor = "start", letterSpacing = 0 }) {
  return `<text x="${x}" y="${y}" fill="${fill}" font-family="Helvetica Neue, Helvetica, Arial, sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" letter-spacing="${letterSpacing}">${esc(value)}</text>`;
}

function roundRect(x, y, width, height, radius, fill, stroke = "none", strokeWidth = 0) {
  return `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="${radius}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}"/>`;
}

function brand({ x = 70, y = 60, size = 58, labelSize = 23 } = {}) {
  return `<image href="${logoData}" x="${x}" y="${y}" width="${size}" height="${size}"/><text x="${x + size + 18}" y="${y + size * 0.69}" fill="${C.white}" font-family="Helvetica Neue, Helvetica, Arial, sans-serif" font-size="${labelSize}" font-weight="700" letter-spacing="4">SEASONS</text>`;
}

function base(width, height, body, { brandMark = true, accent = C.amber } = {}) {
  const pattern = Array.from({ length: 9 }, (_, i) => {
    const x = width - 70 - i * 96;
    const y = height * 0.12 + (i % 3) * 34;
    return `<circle cx="${x}" cy="${y}" r="6" fill="${i < 4 ? accent : C.surface2}" opacity="${i < 4 ? 0.7 : 0.55}"/>`;
  }).join("");
  return `<?xml version="1.0" encoding="UTF-8"?>
  <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <defs>
      <radialGradient id="glow" cx="82%" cy="10%" r="70%">
        <stop offset="0%" stop-color="${accent}" stop-opacity="0.16"/>
        <stop offset="48%" stop-color="${C.purple}" stop-opacity="0.06"/>
        <stop offset="100%" stop-color="${C.ink}" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="amberLine" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="${C.amber}" stop-opacity="0.2"/>
        <stop offset="50%" stop-color="${C.amber}"/>
        <stop offset="100%" stop-color="${C.amberSoft}"/>
      </linearGradient>
    </defs>
    <rect width="${width}" height="${height}" fill="${C.ink}"/>
    <rect width="${width}" height="${height}" fill="url(#glow)"/>
    ${pattern}
    ${brandMark ? brand({ x: width < 1000 ? 64 : 76, y: width < 1000 ? 56 : 66, size: width < 1000 ? 54 : 62 }) : ""}
    ${body}
  </svg>`;
}

function episodeTimeline({ x, y, width, dates = false, finale = true, billIndices = [], dotRadius = 15 }) {
  const step = width / 9;
  let svg = `<line x1="${x}" y1="${y}" x2="${x + width}" y2="${y}" stroke="${C.surface2}" stroke-width="8" stroke-linecap="round"/>`;
  for (let i = 0; i < 10; i += 1) {
    const cx = x + step * i;
    const billed = billIndices.includes(i);
    svg += `<circle cx="${cx}" cy="${y}" r="${dotRadius + (billed ? 4 : 0)}" fill="${billed ? C.amber : i === 9 ? C.green : C.purpleSoft}" stroke="${C.ink}" stroke-width="5"/>`;
    if (billed) {
      svg += `<line x1="${cx}" y1="${y - 82}" x2="${cx}" y2="${y - 30}" stroke="${C.amber}" stroke-width="5"/>`;
      svg += text("£9.99", { x: cx, y: y - 100, size: 24, fill: C.amberSoft, weight: 700, anchor: "middle" });
    }
  }
  if (finale) {
    const fx = x + width;
    svg += `<line x1="${fx}" y1="${y - 18}" x2="${fx}" y2="${y - 104}" stroke="${C.green}" stroke-width="5"/>`;
    svg += `<path d="M ${fx} ${y - 104} L ${fx + 54} ${y - 84} L ${fx} ${y - 62} Z" fill="${C.green}"/>`;
    svg += text("FINALE", { x: fx - 4, y: y + 64, size: 22, fill: C.green, weight: 700, anchor: "middle", letterSpacing: 2 });
  }
  if (dates) {
    svg += text("3 APR", { x, y: y + 70, size: 24, fill: C.muted, weight: 700, anchor: "middle" });
    svg += text("5 JUN", { x: x + width, y: y + 70, size: 24, fill: C.muted, weight: 700, anchor: "middle" });
  }
  return svg;
}

function footerLabel(value, width, height) {
  return text(value, { x: 70, y: height - 48, size: 22, fill: C.faint, weight: 600, letterSpacing: 0.5 });
}

function cta(x, y, width, label = "BUILD MY SAVINGS PLAN") {
  return `${roundRect(x, y, width, 88, 44, C.amber)}${text(label, { x: x + width / 2, y: y + 56, size: 28, fill: C.ink, weight: 800, anchor: "middle", letterSpacing: 1 })}`;
}

const assets = [];

function addAsset({ id, file, width, height, svg, platform, use, variant }) {
  assets.push({ id, file, width, height, svg, platform, use, variant });
}

// Instagram carousel
addAsset({
  id: "ig-carousel-01-hook", file: "instagram/carousel-01-hook.png", width: 1080, height: 1350, platform: "Instagram", use: "Carousel slide 1", variant: "Hook",
  svg: base(1080, 1350, `
    ${lines(["STOP PAYING", "FOR THE WAIT."], { x: 72, y: 330, size: 96, lineHeight: 100, weight: 800 })}
    ${lines(["Weekly episodes can keep", "a subscription running for months."], { x: 76, y: 575, size: 42, lineHeight: 56, fill: C.muted, weight: 500 })}
    ${episodeTimeline({ x: 100, y: 875, width: 850, dates: false, finale: true, dotRadius: 14 })}
    ${text("SWIPE TO SEE THE BILLING MATH", { x: 76, y: 1115, size: 25, fill: C.amberSoft, weight: 750, letterSpacing: 1.5 })}
    ${footerLabel("UK WORKED EXAMPLE  •  1 OF 5", 1080, 1350)}
  `),
});

addAsset({
  id: "ig-carousel-02-episodes", file: "instagram/carousel-02-episodes.png", width: 1080, height: 1350, platform: "Instagram", use: "Carousel slide 2", variant: "Release window",
  svg: base(1080, 1350, `
    ${text("10 WEEKLY EPISODES", { x: 72, y: 310, size: 78, weight: 800 })}
    ${lines(["One at the premiere,", "then one each week."], { x: 76, y: 405, size: 42, lineHeight: 54, fill: C.muted })}
    ${episodeTimeline({ x: 105, y: 760, width: 840, dates: true, finale: true, dotRadius: 16 })}
    ${roundRect(74, 970, 932, 126, 28, C.surface)}
    ${text("63 DAYS FROM PREMIERE TO FINALE", { x: 540, y: 1049, size: 34, fill: C.white, weight: 800, anchor: "middle", letterSpacing: 1 })}
    ${footerLabel("APPLE SCHEDULE  •  CHECKED 23 AUG 2026  •  2 OF 5", 1080, 1350)}
  `),
});

addAsset({
  id: "ig-carousel-03-premiere", file: "instagram/carousel-03-premiere-plan.png", width: 1080, height: 1350, platform: "Instagram", use: "Carousel slide 3", variant: "Premiere strategy",
  svg: base(1080, 1350, `
    ${text("SUBSCRIBE AT PREMIERE", { x: 72, y: 298, size: 66, weight: 800 })}
    ${text("The season crosses three billing dates.", { x: 76, y: 385, size: 38, fill: C.muted })}
    ${episodeTimeline({ x: 105, y: 710, width: 840, dates: true, finale: true, billIndices: [0, 4, 9], dotRadius: 13 })}
    ${text("3", { x: 76, y: 1020, size: 128, fill: C.amber, weight: 850 })}
    ${lines(["BILLING", "DATES"], { x: 220, y: 957, size: 46, lineHeight: 52, fill: C.white, weight: 800 })}
    ${text("3 Apr  •  3 May  •  3 Jun", { x: 930, y: 1002, size: 28, fill: C.amberSoft, weight: 700, anchor: "end" })}
    ${footerLabel("ASSUMED RENEWAL DATE: THE 3RD  •  3 OF 5", 1080, 1350)}
  `),
});

addAsset({
  id: "ig-carousel-04-wait", file: "instagram/carousel-04-wait-plan.png", width: 1080, height: 1350, platform: "Instagram", use: "Carousel slide 4", variant: "Wait strategy",
  svg: base(1080, 1350, `
    ${text("WAIT FOR THE FINALE", { x: 72, y: 298, size: 72, weight: 800 })}
    ${lines(["Watch after 5 June.", "Pay for one binge month."], { x: 76, y: 400, size: 42, lineHeight: 56, fill: C.muted })}
    ${episodeTimeline({ x: 105, y: 740, width: 840, dates: true, finale: true, dotRadius: 13 })}
    ${roundRect(655, 900, 290, 114, 57, C.amber)}
    ${text("£9.99 × 1", { x: 800, y: 971, size: 40, fill: C.ink, weight: 850, anchor: "middle" })}
    ${lines(["1 MONTH", "TO BINGE"], { x: 76, y: 940, size: 48, lineHeight: 54, weight: 850 })}
    ${footerLabel("ASSUMES NO OTHER APPLE TV VIEWING IN THE WINDOW  •  4 OF 5", 1080, 1350)}
  `),
});

addAsset({
  id: "ig-carousel-05-result", file: "instagram/carousel-05-result-cta.png", width: 1080, height: 1350, platform: "Instagram", use: "Carousel slide 5", variant: "Result and CTA",
  svg: base(1080, 1350, `
    ${text("POTENTIAL SAVING", { x: 74, y: 287, size: 38, fill: C.amberSoft, weight: 750, letterSpacing: 2 })}
    ${text("£19.98", { x: 70, y: 470, size: 152, fill: C.amber, weight: 850 })}
    ${lines(["Could avoid two £9.99 renewals", "in this worked example."], { x: 76, y: 555, size: 39, lineHeight: 52, fill: C.white, weight: 650 })}
    ${cta(72, 715, 660)}
    ${roundRect(72, 850, 936, 296, 26, C.surface)}
    ${text("WORKED-EXAMPLE ASSUMPTIONS", { x: 104, y: 905, size: 22, fill: C.amberSoft, weight: 800, letterSpacing: 1.2 })}
    ${lines(["Example assumes a UK £9.99 monthly plan, subscription starting", "3 April 2026, monthly renewal on the 3rd, watching after the", "5 June finale, and no other Apple TV viewing during the release", "window. Prices and dates can change.", "Sources: Apple release schedule + Apple TV UK price. Checked 23 Aug 2026."], { x: 104, y: 948, size: 24, lineHeight: 36, fill: C.muted, weight: 500 })}
    ${footerLabel("GETSEASONS.APP  •  5 OF 5", 1080, 1350)}
  `),
});

// Instagram stories
addAsset({
  id: "ig-story-01-hook", file: "instagram/story-01-hook.png", width: 1080, height: 1920, platform: "Instagram", use: "Story frame 1", variant: "Hook",
  svg: base(1080, 1920, `
    ${lines(["STOP", "PAYING", "FOR THE", "WAIT."], { x: 74, y: 430, size: 112, lineHeight: 116, weight: 850 })}
    ${lines(["Weekly releases can turn", "one show into months of bills."], { x: 78, y: 980, size: 46, lineHeight: 60, fill: C.muted })}
    ${episodeTimeline({ x: 110, y: 1320, width: 830, dates: false, finale: true, dotRadius: 14 })}
    ${text("TAP THROUGH FOR THE MATH", { x: 78, y: 1570, size: 28, fill: C.amberSoft, weight: 800, letterSpacing: 1.6 })}
    ${footerLabel("UK WORKED EXAMPLE  •  1 OF 3", 1080, 1920)}
  `),
});

addAsset({
  id: "ig-story-02-proof", file: "instagram/story-02-proof.png", width: 1080, height: 1920, platform: "Instagram", use: "Story frame 2", variant: "Proof",
  svg: base(1080, 1920, `
    ${text("10 WEEKLY EPISODES.", { x: 74, y: 390, size: 70, weight: 850 })}
    ${text("3 BILLING DATES.", { x: 74, y: 500, size: 70, fill: C.amber, weight: 850 })}
    ${text("1 MONTH TO BINGE.", { x: 74, y: 610, size: 70, weight: 850 })}
    ${episodeTimeline({ x: 110, y: 1010, width: 830, dates: true, finale: true, billIndices: [0, 4, 9], dotRadius: 13 })}
    ${roundRect(78, 1310, 924, 170, 34, C.surface)}
    ${text("3 × £9.99", { x: 270, y: 1414, size: 48, fill: C.amberSoft, weight: 850, anchor: "middle" })}
    ${text("→", { x: 540, y: 1412, size: 56, fill: C.faint, weight: 500, anchor: "middle" })}
    ${text("1 × £9.99", { x: 806, y: 1414, size: 48, fill: C.green, weight: 850, anchor: "middle" })}
    ${footerLabel("APPLE SCHEDULE + UK PRICE  •  CHECKED 23 AUG 2026  •  2 OF 3", 1080, 1920)}
  `),
});

addAsset({
  id: "ig-story-03-result", file: "instagram/story-03-result-cta.png", width: 1080, height: 1920, platform: "Instagram", use: "Story frame 3", variant: "Result and CTA",
  svg: base(1080, 1920, `
    ${text("POTENTIAL SAVING", { x: 76, y: 370, size: 40, fill: C.amberSoft, weight: 800, letterSpacing: 2 })}
    ${text("£19.98", { x: 70, y: 590, size: 170, fill: C.amber, weight: 850 })}
    ${lines(["Could avoid two £9.99 renewals", "in this worked example."], { x: 78, y: 690, size: 43, lineHeight: 56, weight: 650 })}
    ${cta(78, 900, 690)}
    ${roundRect(78, 1070, 924, 430, 28, C.surface)}
    ${text("ASSUMPTIONS + SOURCES", { x: 112, y: 1130, size: 24, fill: C.amberSoft, weight: 800, letterSpacing: 1 })}
    ${lines(["Example assumes a UK £9.99 monthly plan,", "subscription starting 3 April 2026, monthly renewal", "on the 3rd, watching after the 5 June finale, and", "no other Apple TV viewing during the release window.", "Prices and dates can change.", "", "Apple schedule + Apple TV UK price. Checked 23 Aug 2026."], { x: 112, y: 1180, size: 27, lineHeight: 42, fill: C.muted, weight: 500 })}
    ${footerLabel("GETSEASONS.APP  •  3 OF 3", 1080, 1920)}
  `),
});

addAsset({
  id: "ig-reel-cover", file: "instagram/reel-cover.png", width: 1080, height: 1920, platform: "Instagram", use: "Reel cover", variant: "Mechanism",
  svg: base(1080, 1920, `
    ${lines(["STOP", "PAYING", "FOR THE", "WAIT."], { x: 74, y: 470, size: 116, lineHeight: 120, weight: 850 })}
    ${episodeTimeline({ x: 110, y: 1120, width: 830, dates: false, finale: true, dotRadius: 15 })}
    ${lines(["10 episodes  •  3 bills  •  1 binge", "Worked example. Assumptions + sources in caption."], { x: 78, y: 1410, size: 35, lineHeight: 56, fill: C.muted, weight: 600 })}
    ${footerLabel("GETSEASONS.APP", 1080, 1920)}
  `),
});

// TikTok frames and cover
const tiktokFrames = [
  {
    id: "tt-frame-01-hook", file: "tiktok/frame-01-hook.png", use: "Video frame 0:00-0:04", variant: "Hook",
    body: `${lines(["STOP PAYING", "FOR THE WAIT."], { x: 74, y: 470, size: 106, lineHeight: 112, weight: 850 })}${lines(["Your weekly show can cross", "more billing dates than you think."], { x: 78, y: 790, size: 45, lineHeight: 60, fill: C.muted })}${episodeTimeline({ x: 110, y: 1200, width: 830, dates: false, finale: true, dotRadius: 14 })}${footerLabel("SOUND-OFF CAPTIONS  •  UK WORKED EXAMPLE", 1080, 1920)}`,
  },
  {
    id: "tt-frame-02-release", file: "tiktok/frame-02-release.png", use: "Video frame 0:04-0:08", variant: "Release window",
    body: `${text("10 WEEKLY EPISODES", { x: 74, y: 430, size: 78, weight: 850 })}${lines(["3 April premiere.", "5 June finale."], { x: 78, y: 560, size: 56, lineHeight: 76, fill: C.muted, weight: 650 })}${episodeTimeline({ x: 110, y: 1050, width: 830, dates: true, finale: true, dotRadius: 15 })}${roundRect(80, 1350, 920, 150, 34, C.surface)}${text("63 DAYS OF WAITING", { x: 540, y: 1444, size: 46, fill: C.white, weight: 850, anchor: "middle" })}${footerLabel("SOURCE: APPLE RELEASE SCHEDULE  •  CHECKED 23 AUG 2026", 1080, 1920)}`,
  },
  {
    id: "tt-frame-03-premiere", file: "tiktok/frame-03-premiere.png", use: "Video frame 0:08-0:12", variant: "Premiere strategy",
    body: `${text("START AT PREMIERE", { x: 74, y: 410, size: 76, weight: 850 })}${text("The season crosses 3 billing dates.", { x: 78, y: 520, size: 43, fill: C.muted })}${episodeTimeline({ x: 110, y: 1000, width: 830, dates: true, finale: true, billIndices: [0, 4, 9], dotRadius: 13 })}${text("3 × £9.99", { x: 74, y: 1390, size: 116, fill: C.amber, weight: 850 })}${text("3 Apr  •  3 May  •  3 Jun", { x: 80, y: 1470, size: 34, fill: C.amberSoft, weight: 700 })}${footerLabel("ASSUMED MONTHLY RENEWAL DATE: THE 3RD", 1080, 1920)}`,
  },
  {
    id: "tt-frame-04-wait", file: "tiktok/frame-04-wait.png", use: "Video frame 0:12-0:16", variant: "Wait strategy",
    body: `${text("WAIT FOR THE FINALE", { x: 74, y: 410, size: 72, weight: 850 })}${lines(["Watch after 5 June.", "Pay for one binge month."], { x: 78, y: 550, size: 50, lineHeight: 70, fill: C.muted, weight: 600 })}${episodeTimeline({ x: 110, y: 1050, width: 830, dates: true, finale: true, dotRadius: 13 })}${text("1 × £9.99", { x: 74, y: 1400, size: 116, fill: C.green, weight: 850 })}${footerLabel("ASSUMES NOTHING ELSE TO WATCH ON APPLE TV IN THE WINDOW", 1080, 1920)}`,
  },
  {
    id: "tt-frame-05-result", file: "tiktok/frame-05-result.png", use: "Video frame 0:16-0:20", variant: "Result",
    body: `${text("POTENTIAL SAVING", { x: 76, y: 420, size: 42, fill: C.amberSoft, weight: 800, letterSpacing: 2 })}${text("£19.98", { x: 70, y: 665, size: 184, fill: C.amber, weight: 850 })}${lines(["Could avoid two", "£9.99 renewals."], { x: 78, y: 805, size: 60, lineHeight: 78, weight: 750 })}${text("Worked example, not a guaranteed saving.", { x: 80, y: 1070, size: 35, fill: C.muted, weight: 600 })}${cta(80, 1260, 690)}${footerLabel("FULL ASSUMPTIONS + SOURCES NEXT", 1080, 1920)}`,
  },
  {
    id: "tt-frame-06-qualification", file: "tiktok/frame-06-qualification.png", use: "Video frame 0:20-0:24", variant: "Qualification and CTA",
    body: `${text("BUILD MY SAVINGS PLAN", { x: 74, y: 400, size: 68, weight: 850 })}${roundRect(74, 505, 932, 610, 30, C.surface)}${text("WORKED-EXAMPLE ASSUMPTIONS", { x: 110, y: 580, size: 25, fill: C.amberSoft, weight: 850, letterSpacing: 1 })}${lines(["Example assumes a UK £9.99 monthly plan,", "subscription starting 3 April 2026, monthly", "renewal on the 3rd, watching after the 5 June", "finale, and no other Apple TV viewing during", "the release window. Prices and dates can change.", "", "Sources: Apple release schedule and Apple TV UK", "price. Checked 23 August 2026."], { x: 110, y: 640, size: 30, lineHeight: 50, fill: C.muted, weight: 500 })}${text("GETSEASONS.APP", { x: 76, y: 1330, size: 46, fill: C.white, weight: 850, letterSpacing: 2 })}${footerLabel("SILENT VIDEO  •  ALL COPY BURNED IN", 1080, 1920)}`,
  },
];

for (const frame of tiktokFrames) {
  addAsset({ id: frame.id, file: frame.file, width: 1080, height: 1920, platform: "TikTok", use: frame.use, variant: frame.variant, svg: base(1080, 1920, frame.body) });
}

addAsset({
  id: "tt-cover", file: "tiktok/cover.png", width: 1080, height: 1920, platform: "TikTok", use: "Video cover", variant: "Hook",
  svg: base(1080, 1920, `${lines(["STOP", "PAYING", "FOR THE", "WAIT."], { x: 74, y: 500, size: 116, lineHeight: 120, weight: 850 })}${episodeTimeline({ x: 110, y: 1180, width: 830, dates: false, finale: true, dotRadius: 15 })}${text("10 EPISODES  •  3 BILLS  •  1 BINGE", { x: 78, y: 1460, size: 35, fill: C.muted, weight: 750 })}${footerLabel("WORKED EXAMPLE  •  ASSUMPTIONS + SOURCES IN CAPTION", 1080, 1920)}`),
});

// Reddit
addAsset({
  id: "reddit-link-card", file: "reddit/link-card-1200x628.png", width: 1200, height: 628, platform: "Reddit", use: "Link-card preview", variant: "Mechanism + proof",
  svg: base(1200, 628, `
    ${lines(["STOP PAYING", "FOR THE WAIT."], { x: 70, y: 228, size: 66, lineHeight: 70, weight: 850 })}
    ${text("10 episodes  •  3 bills  •  1 binge", { x: 74, y: 415, size: 34, fill: C.muted, weight: 650 })}
    ${episodeTimeline({ x: 690, y: 330, width: 420, dates: false, finale: true, dotRadius: 9 })}
    ${text("Worked example. Full assumptions + sources in post.", { x: 74, y: 520, size: 22, fill: C.faint, weight: 600 })}
  `),
});

addAsset({
  id: "reddit-proof-card", file: "reddit/native-proof-card-1080x1080.png", width: 1080, height: 1080, platform: "Reddit", use: "Native image post", variant: "Worked proof",
  svg: base(1080, 1080, `
    ${text("10 EPISODES  •  3 BILLS  •  1 BINGE", { x: 70, y: 265, size: 43, weight: 850 })}
    ${episodeTimeline({ x: 105, y: 480, width: 840, dates: true, finale: true, billIndices: [0, 4, 9], dotRadius: 11 })}
    ${text("POTENTIAL SAVING: £19.98", { x: 70, y: 675, size: 70, fill: C.amber, weight: 850 })}
    ${text("Could avoid two £9.99 renewals in this worked example.", { x: 74, y: 742, size: 29, fill: C.white, weight: 650 })}
    ${roundRect(70, 790, 940, 190, 24, C.surface)}
    ${lines(["Example assumes a UK £9.99 monthly plan starting 3 Apr 2026, renewal", "on the 3rd, watching after the 5 Jun finale, and no other Apple TV", "viewing in the release window. Prices and dates can change.", "Sources: Apple schedule + Apple TV UK price. Checked 23 Aug 2026."], { x: 100, y: 835, size: 20, lineHeight: 34, fill: C.muted, weight: 500 })}
  `),
});

async function render() {
  for (const asset of assets) {
    const svgFile = path.join(sourceDir, `${asset.id}.svg`);
    const pngFile = path.join(exportDir, asset.file);
    fs.writeFileSync(svgFile, asset.svg, "utf8");
    await sharp(Buffer.from(asset.svg)).png({ compressionLevel: 9, adaptiveFiltering: true }).toFile(pngFile);
  }

  const framePaths = tiktokFrames.map((frame) => path.join(exportDir, frame.file));
  const ffmpegArgs = ["-y"];
  for (const framePath of framePaths) ffmpegArgs.push("-i", framePath);
  const filters = framePaths.map((_, i) => `[${i}:v]scale=1080:1920,zoompan=z='min(zoom+0.00015,1.018)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=120:s=1080x1920:fps=30,setsar=1[v${i}]`);
  filters.push(`${framePaths.map((_, i) => `[v${i}]`).join("")}concat=n=${framePaths.length}:v=1:a=0[outv]`);
  ffmpegArgs.push("-filter_complex", filters.join(";"), "-map", "[outv]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", path.join(exportDir, "tiktok", "stop-paying-for-the-wait-24s.mp4"));
  const video = spawnSync("ffmpeg", ffmpegArgs, { encoding: "utf8" });
  if (video.status !== 0) {
    throw new Error(`ffmpeg failed:\n${video.stderr}`);
  }

  await makePreview("instagram-carousel-preview.png", assets.filter((a) => a.file.startsWith("instagram/carousel")), 5, 216, 270);
  await makePreview("instagram-story-preview.png", assets.filter((a) => a.file.startsWith("instagram/story")), 3, 216, 384);
  await makePreview("tiktok-storyboard-preview.png", tiktokFrames.map((f) => assets.find((a) => a.id === f.id)), 3, 216, 384);
  await makePreview("reddit-preview.png", assets.filter((a) => a.file.startsWith("reddit/")), 2, 360, 260);

  const machineManifest = {
    campaign: "Stop Paying for the Wait",
    generatedBy: "scripts/render-assets.js",
    deterministicInputs: {
      logo: path.relative(packDir, logoPath),
      qualification: QUALIFICATION,
      sources: SOURCES,
      checkedDate: "2026-08-23",
    },
    assets: assets.map(({ id, file, width, height, platform, use, variant }) => ({ id, file: `exports/${file}`, width, height, format: "PNG", platform, use, variant })),
    video: {
      file: "exports/tiktok/stop-paying-for-the-wait-24s.mp4",
      width: 1080,
      height: 1920,
      durationSeconds: 24,
      frameRate: 30,
      audio: "none",
      captions: "burned-in on-screen copy",
    },
  };
  fs.writeFileSync(path.join(packDir, "asset-manifest.json"), `${JSON.stringify(machineManifest, null, 2)}\n`, "utf8");
}

async function makePreview(filename, previewAssets, columns, thumbWidth, thumbHeight) {
  const gap = 24;
  const rows = Math.ceil(previewAssets.length / columns);
  const width = gap + columns * (thumbWidth + gap);
  const height = gap + rows * (thumbHeight + gap);
  const composites = [];
  for (let i = 0; i < previewAssets.length; i += 1) {
    const asset = previewAssets[i];
    const thumb = await sharp(path.join(exportDir, asset.file)).resize(thumbWidth, thumbHeight, { fit: "contain", background: C.ink }).png().toBuffer();
    composites.push({ input: thumb, left: gap + (i % columns) * (thumbWidth + gap), top: gap + Math.floor(i / columns) * (thumbHeight + gap) });
  }
  await sharp({ create: { width, height, channels: 4, background: "#222126" } }).composite(composites).png().toFile(path.join(exportDir, "previews", filename));
}

render().catch((error) => {
  console.error(error);
  process.exit(1);
});
