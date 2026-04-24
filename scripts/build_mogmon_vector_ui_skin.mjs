#!/usr/bin/env node

import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");
const uiRoot = resolve(root, "assets/images/ui");
const outputRoot = resolve(root, "output/mogmon-ui-vector-src");
const rasterRoot = resolve(root, "output/mogmon-ui-vector-raster");

function loadSharp() {
  const localRequire = createRequire(import.meta.url);
  try {
    return localRequire("sharp");
  } catch {
    const tempaiTownBackendPackage = resolve(__dirname, "../../../aura/tempaitown/backend/package.json");
    if (!existsSync(tempaiTownBackendPackage)) {
      throw new Error(
        `sharp is not installed locally and TempaiTown backend package was not found: ${tempaiTownBackendPackage}`,
      );
    }
    return createRequire(tempaiTownBackendPackage)("sharp");
  }
}

const sharp = loadSharp();

const palette = {
  ink: "#141922",
  ink2: "#1f2632",
  steel0: "#2a3342",
  steel1: "#3c4a5d",
  steel2: "#68788a",
  steel3: "#a8b6c3",
  paper0: "#cabd96",
  paper1: "#eadbb6",
  paper2: "#fff0c9",
  cyan0: "#1b7779",
  cyan1: "#38d8d0",
  cyan2: "#b8fff3",
  gold0: "#8a6527",
  gold1: "#e1ad3f",
  gold2: "#ffe097",
  rust0: "#743e37",
  rust1: "#ce7657",
  rust2: "#ffc08a",
  violet0: "#4d4666",
  violet1: "#9487bd",
  violet2: "#ded4ff",
  red: "#dc705c",
  green: "#4fd4a4",
  blue: "#54a5dd",
};

const accents = [
  [palette.rust0, palette.rust1, palette.rust2],
  [palette.cyan0, palette.cyan1, palette.cyan2],
  [palette.steel1, palette.steel2, palette.steel3],
  [palette.gold0, palette.gold1, palette.gold2],
  [palette.violet0, palette.violet1, palette.violet2],
];

function svgWrap(width, height, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" shape-rendering="crispEdges">
<rect width="${width}" height="${height}" fill="none"/>
${body}
</svg>
`;
}

function rect(x, y, width, height, fill, extra = "") {
  return `<rect x="${x}" y="${y}" width="${width}" height="${height}" fill="${fill}"${extra}/>`;
}

function line(x1, y1, x2, y2, stroke, extra = "") {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${stroke}"${extra}/>`;
}

function polygon(points, fill, extra = "") {
  return `<polygon points="${points.map(point => point.join(",")).join(" ")}" fill="${fill}"${extra}/>`;
}

function circle(cx, cy, r, fill, extra = "") {
  return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}"${extra}/>`;
}

function grid(width, height, minor, major, accent) {
  const parts = [];
  for (let x = 0; x <= width; x += minor) {
    parts.push(line(x, 0, x, height, palette.ink2, ' opacity="0.34"'));
  }
  for (let y = 0; y <= height; y += minor) {
    parts.push(line(0, y, width, y, palette.ink2, ' opacity="0.34"'));
  }
  for (let x = 0; x <= width; x += major) {
    parts.push(line(x, 0, x, height, accent, ' opacity="0.42"'));
  }
  for (let y = 0; y <= height; y += major) {
    parts.push(line(0, y, width, y, accent, ' opacity="0.42"'));
  }
  return parts.join("\n");
}

function scanlines(width, height, opacity = 0.18) {
  const parts = [];
  for (let y = 0; y < height; y += 2) {
    parts.push(line(0, y, width, y, palette.ink, ` opacity="${opacity}"`));
  }
  return parts.join("\n");
}

function rivet(x, y, accent) {
  return [
    rect(x - 1, y, 3, 1, palette.steel3),
    rect(x, y - 1, 1, 3, palette.steel3),
    rect(x, y, 1, 1, accent),
    rect(x + 1, y + 1, 1, 1, palette.ink),
  ].join("\n");
}

function panel(width, height, accent = accents[1], options = {}) {
  const [dark, mid, light] = accent;
  const fill = options.light ? palette.paper1 : palette.steel0;
  const inner = options.light ? palette.paper2 : palette.ink2;
  const parts = [
    rect(0, 0, width, height, palette.ink),
    rect(1, 1, width - 2, height - 2, dark),
    rect(2, 2, width - 4, height - 4, palette.steel1),
    rect(4, 5, width - 8, Math.max(1, height - 10), fill),
    rect(5, 7, width - 10, Math.max(1, height - 13), inner, ' opacity="0.92"'),
    line(4, 3, width - 5, 3, light),
    line(4, 4, width - 5, 4, mid),
  ];

  if (width > 30 && height > 18) {
    parts.push(
      rivet(8, 4, light),
      rivet(width - 9, 4, light),
      rivet(8, height - 5, light),
      rivet(width - 9, height - 5, light),
    );
  } else if (width > 14) {
    parts.push(rivet(5, 4, light), rivet(width - 6, 4, light));
  }

  if (options.grid) {
    parts.push(grid(width, height, options.grid, options.grid * 4, mid));
  }

  if (options.scanlines) {
    parts.push(scanlines(width, height, 0.14));
  }

  return parts.join("\n");
}

function battleInfo(width, height, accent = accents[3]) {
  const [dark, mid, light] = accent;
  const barY = Math.max(11, height - 11);
  return [
    rect(0, 3, width - 1, height - 4, palette.ink, ' opacity="0.88"'),
    polygon(
      [
        [2, 2],
        [width - 16, 2],
        [width - 2, 12],
        [width - 2, height - 3],
        [13, height - 3],
        [2, height - 13],
      ],
      dark,
    ),
    rect(5, 5, width - 20, height - 10, palette.steel0),
    rect(8, 8, width - 28, Math.max(3, height - 18), palette.ink2),
    line(5, 4, width - 17, 4, light),
    line(5, 5, width - 17, 5, mid),
    rect(width - 34, barY, 25, 4, palette.green),
    rect(width - 34, barY + 4, 25, 2, palette.cyan0),
    rivet(9, 5, light),
    rivet(width - 19, 8, light),
    scanlines(width, height, 0.12),
  ].join("\n");
}

function messageBox(width, height) {
  const parts = [
    rect(0, 0, width, height, palette.ink),
    rect(2, 2, width - 4, height - 4, palette.cyan0),
    rect(4, 4, width - 8, height - 8, palette.ink2),
    rect(10, 13, width - 20, height - 26, palette.steel0),
    rect(14, 19, width - 28, height - 38, "#243145"),
    line(10, 12, width - 11, 12, palette.cyan2),
    line(10, height - 13, width - 11, height - 13, palette.gold1),
    line(14, 19, width - 15, 19, palette.cyan1),
    line(14, height - 20, width - 15, height - 20, palette.ink),
    polygon(
      [
        [0, 0],
        [36, 0],
        [24, 11],
        [0, 11],
      ],
      palette.gold0,
    ),
    polygon(
      [
        [width, height],
        [width - 36, height],
        [width - 24, height - 11],
        [width, height - 11],
      ],
      palette.rust0,
    ),
    scanlines(width, height, 0.12),
  ];
  for (let x = 24; x < width - 20; x += 40) {
    parts.push(rivet(x, 7, palette.cyan2));
  }
  return parts.join("\n");
}

function starterLeftRail(height) {
  const railWidth = 108;
  const railRight = railWidth - 1;
  const parts = [
    rect(0, 0, railWidth, height, "#151d2a", ' opacity="0.94"'),
    rect(2, 2, railWidth - 6, height - 4, "#243145", ' opacity="0.28"'),
    rect(0, 0, railWidth, 20, palette.ink, ' opacity="0.72"'),
    rect(2, 108, railWidth - 6, 48, "#171f2d", ' opacity="0.94"'),
    rect(2, 156, railWidth - 6, 22, palette.ink, ' opacity="0.82"'),
    rect(8, 38, 92, 54, "#202b3a", ' opacity="0.42"'),
    line(0, 20, railWidth, 20, palette.cyan1, ' opacity="0.46"'),
    line(4, 108, railWidth - 6, 108, palette.cyan2, ' opacity="0.52"'),
    line(4, 156, railWidth - 6, 156, palette.steel2, ' opacity="0.45"'),
    line(railRight, 0, railRight, height, palette.cyan1, ' opacity="0.62"'),
    line(railRight - 2, 0, railRight - 2, height, palette.ink, ' opacity="0.76"'),
    line(railRight - 4, 0, railRight - 4, height, palette.steel2, ' opacity="0.32"'),
    `<ellipse cx="54" cy="84" rx="42" ry="9" fill="${palette.ink}" opacity="0.46" stroke="${palette.cyan2}" stroke-opacity="0.28"/>`,
    rect(4, 4, 18, 2, palette.cyan2, ' opacity="0.55"'),
    rect(26, 4, 40, 2, palette.steel3, ' opacity="0.28"'),
    rect(72, 4, 28, 2, palette.cyan1, ' opacity="0.36"'),
    rect(4, 114, 96, 2, palette.steel2, ' opacity="0.28"'),
    rect(4, 146, 96, 2, palette.steel2, ' opacity="0.20"'),
  ];

  for (let y = 112; y < 156; y += 8) {
    parts.push(line(4, y, railWidth - 8, y, palette.steel2, ' opacity="0.10"'));
  }
  for (let x = 8; x < railWidth - 8; x += 16) {
    parts.push(line(x, 112, x, 154, palette.cyan1, ' opacity="0.08"'));
  }

  return parts.join("\n");
}

function background(width, height, mode = "title") {
  const isParty = mode === "party";
  const skyA = isParty ? "#2f384a" : "#303a50";
  const skyB = isParty ? "#4d5a70" : "#546b86";
  const groundA = isParty ? "#272d3a" : "#2c3a4d";
  const accent = mode === "starter" ? palette.cyan1 : mode === "summary" ? palette.violet1 : palette.gold1;
  const parts = [
    `<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${skyA}"/><stop offset="0.55" stop-color="${skyB}"/><stop offset="1" stop-color="${groundA}"/></linearGradient></defs>`,
    rect(0, 0, width, height, "url(#sky)"),
    rect(0, Math.floor(height * 0.58), width, Math.ceil(height * 0.42), palette.ink2, ' opacity="0.74"'),
    line(0, Math.floor(height * 0.58), width, Math.floor(height * 0.58), accent, ' opacity="0.82"'),
    grid(width, height, 8, 40, accent),
  ];

  const skylineY = Math.floor(height * 0.44);
  for (let x = 8; x < width; x += 34) {
    const towerW = 14 + ((x / 2) % 13);
    const towerH = 20 + (x % 37);
    parts.push(rect(x, skylineY - towerH, towerW, towerH, palette.ink, ' opacity="0.65"'));
    parts.push(line(x, skylineY - towerH, x + towerW, skylineY - towerH, palette.steel3, ' opacity="0.34"'));
  }

  const vanishX = Math.floor(width / 2);
  const horizon = Math.floor(height * 0.6);
  for (let x = -width; x <= width * 2; x += 24) {
    parts.push(line(vanishX, horizon, x, height, palette.cyan2, ' opacity="0.20"'));
  }
  for (let y = horizon + 8; y < height; y += 14) {
    parts.push(line(0, y, width, y, palette.steel3, ' opacity="0.16"'));
  }

  parts.push(
    `<ellipse cx="${Math.floor(width * 0.27)}" cy="${Math.floor(height * 0.77)}" rx="${Math.floor(width * 0.16)}" ry="${Math.floor(height * 0.1)}" fill="${palette.steel1}" opacity="0.42" stroke="${palette.cyan2}" stroke-opacity="0.38"/>`,
  );
  parts.push(
    `<ellipse cx="${Math.floor(width * 0.76)}" cy="${Math.floor(height * 0.74)}" rx="${Math.floor(width * 0.16)}" ry="${Math.floor(height * 0.1)}" fill="${palette.steel1}" opacity="0.36" stroke="${palette.gold2}" stroke-opacity="0.36"/>`,
  );
  if (mode === "starter") {
    parts.push(starterLeftRail(height));
  }
  parts.push(scanlines(width, height, 0.16));
  return parts.join("\n");
}

function selector(width, height, accent = accents[1], thick = false) {
  const [dark, mid, light] = accent;
  const inset = thick ? 0 : 1;
  return [
    rect(0, 0, width, height, "none"),
    rect(inset, inset, width - inset * 2, height - inset * 2, dark),
    rect(
      inset + 1,
      inset + 1,
      width - inset * 2 - 2,
      height - inset * 2 - 2,
      "none",
      ` stroke="${light}" stroke-width="${thick ? 2 : 1}"`,
    ),
    rect(inset + 3, inset + 3, Math.max(1, width - inset * 2 - 6), 1, mid),
    rivet(inset + 3, inset + 3, light),
    rivet(width - inset - 4, inset + 3, light),
    rivet(inset + 3, height - inset - 4, light),
    rivet(width - inset - 4, height - inset - 4, light),
  ].join("\n");
}

function arrow(width, height, reverse = false, accent = accents[3]) {
  const [, mid, light] = accent;
  const points = reverse
    ? [
        [width - 1, 0],
        [1, Math.floor(height / 2)],
        [width - 1, height - 1],
      ]
    : [
        [0, 0],
        [width - 1, Math.floor(height / 2)],
        [0, height - 1],
      ];
  return [
    polygon(points, palette.ink),
    polygon(
      points.map(([x, y]) => [reverse ? x - 1 : x + 1, y]),
      light,
    ),
    polygon(
      points.map(([x, y]) => [reverse ? x - 2 : x + 2, y]),
      mid,
    ),
  ].join("\n");
}

function icon(width, height, kind) {
  const cx = Math.floor(width / 2);
  const cy = Math.floor(height / 2);
  const parts = [rect(0, 0, width, height, "none")];
  if (kind === "settings") {
    parts.push(circle(cx, cy, 8, palette.steel2), circle(cx, cy, 4, palette.ink2), circle(cx, cy, 2, palette.cyan1));
    for (let i = 0; i < 8; i += 1) {
      const angle = (Math.PI * 2 * i) / 8;
      const x = Math.round(cx + Math.cos(angle) * 9);
      const y = Math.round(cy + Math.sin(angle) * 9);
      parts.push(rect(x - 1, y - 1, 3, 3, palette.gold1));
    }
  } else if (kind === "language") {
    parts.push(circle(cx, cy, 9, palette.cyan0, ` stroke="${palette.cyan2}" stroke-width="2"`));
    parts.push(line(cx - 8, cy, cx + 8, cy, palette.cyan2), line(cx, cy - 8, cx, cy + 8, palette.cyan2));
    parts.push(
      `<path d="M ${cx - 6} ${cy - 7} C ${cx - 2} ${cy - 2}, ${cx - 2} ${cy + 2}, ${cx - 6} ${cy + 7}" fill="none" stroke="${palette.cyan2}" stroke-width="1"/>`,
    );
    parts.push(
      `<path d="M ${cx + 6} ${cy - 7} C ${cx + 2} ${cy - 2}, ${cx + 2} ${cy + 2}, ${cx + 6} ${cy + 7}" fill="none" stroke="${palette.cyan2}" stroke-width="1"/>`,
    );
  } else if (kind === "link" || kind === "unlink") {
    parts.push(rect(2, 6, 7, 4, palette.cyan1), rect(7, 6, 7, 4, palette.gold1));
    parts.push(rect(3, 7, 5, 2, palette.ink2), rect(8, 7, 5, 2, palette.ink2));
    if (kind === "unlink") {
      parts.push(line(2, 14, 14, 2, palette.red, ' stroke-width="2"'));
    }
  } else if (kind === "saving") {
    parts.push(rect(2, 1, 12, 14, palette.steel1), rect(4, 3, 8, 4, palette.cyan1), rect(5, 10, 6, 4, palette.paper1));
  } else {
    parts.push(panel(width, height, accents[2]));
  }
  return parts.join("\n");
}

function meter(width, height, color = palette.green) {
  return [
    rect(0, 0, width, height, palette.ink),
    rect(1, 1, width - 2, Math.max(1, height - 2), color),
    line(1, 1, width - 2, 1, palette.paper2),
    line(1, height - 2, width - 2, height - 2, palette.cyan0),
  ].join("\n");
}

const assets = [];

function addAsset(path, width, height, body, baseWidth = Math.min(width, 160)) {
  assets.push({ path, width, height, body, baseWidth });
}

for (let index = 1; index <= 5; index += 1) {
  const accent = accents[index - 1];
  addAsset(`windows/window_${index}.png`, 24, 24, panel(24, 24, accent), 24);
  addAsset(`windows/window_${index}_thin.png`, 24, 24, panel(24, 24, accent, { light: index === 3 }), 24);
  addAsset(`windows/window_${index}_xthin.png`, 24, 24, panel(24, 24, accent, { light: index === 4 }), 24);
}

addAsset("bg.png", 320, 240, background(320, 240, "title"), 160);
addAsset("starter_select_bg.png", 320, 180, background(320, 180, "starter"), 160);
addAsset("party_bg.png", 320, 180, background(320, 180, "party"), 160);
addAsset("party_bg_double.png", 320, 180, background(320, 180, "party"), 160);
addAsset("party_bg_double_manage.png", 320, 180, background(320, 180, "party"), 160);
addAsset("summary_bg.png", 320, 180, background(320, 180, "summary"), 160);
addAsset("egg_list_bg.png", 320, 180, background(320, 180, "summary"), 160);
addAsset("egg_summary_bg.png", 320, 180, background(320, 180, "summary"), 160);
addAsset("egg_summary_bg_blank.png", 320, 180, background(320, 180, "summary"), 160);
addAsset("pokedex_summary_bg.png", 320, 180, background(320, 180, "summary"), 160);

addAsset("overlay_message.png", 512, 96, messageBox(512, 96), 256);
addAsset("starter_container_bg.png", 173, 159, panel(173, 159, accents[1], { grid: 8 }), 96);
addAsset("summary_profile.png", 214, 159, panel(214, 159, accents[4], { grid: 8 }), 112);
addAsset("summary_moves.png", 214, 159, panel(214, 159, accents[1], { grid: 8 }), 112);
addAsset("summary_stats.png", 214, 159, panel(214, 159, accents[3], { grid: 8 }), 112);
addAsset("summary_moves_effect.png", 100, 62, panel(100, 62, accents[1]), 64);
addAsset("summary_moves_overlay_row.png", 211, 20, panel(211, 20, accents[1]), 128);
addAsset("summary_moves_cursor.png", 211, 32, selector(211, 32, accents[1]), 128);
addAsset("summary_status.png", 106, 16, panel(106, 16, accents[3]), 80);

for (const name of [
  "pbinfo_player.png",
  "pbinfo_player_stats.png",
  "pbinfo_player_mini.png",
  "pbinfo_player_mini_stats.png",
]) {
  addAsset(name, 130, 42, battleInfo(130, 42, accents[3]), 96);
}
for (const name of ["pbinfo_enemy_mini.png", "pbinfo_enemy_mini_stats.png"]) {
  addAsset(name, 130, 31, battleInfo(130, 31, accents[1]), 96);
}
for (const name of ["pbinfo_enemy_boss.png", "pbinfo_enemy_boss_stats.png"]) {
  addAsset(name, 178, 31, battleInfo(178, 31, accents[0]), 128);
}
addAsset("party_slot.png", 175, 144, panel(175, 144, accents[1], { grid: 8 }), 96);
addAsset("party_slot_main.png", 110, 294, panel(110, 294, accents[3], { grid: 8 }), 80);
addAsset("party_slot_main_short.png", 110, 246, panel(110, 246, accents[3], { grid: 8 }), 80);
addAsset("party_slot_hp_bar.png", 100, 7, meter(100, 7, palette.green), 100);
addAsset("party_slot_hp_overlay.png", 80, 9, meter(80, 9, palette.green), 80);
addAsset("party_slot_overlay_hp.png", 80, 9, meter(80, 9, palette.green), 80);
addAsset("party_exp_bar.png", 34, 14, meter(34, 14, palette.blue), 34);

addAsset(
  "overlay_hp.png",
  48,
  6,
  `${meter(48, 2, palette.green)}<g transform="translate(0 2)">${meter(48, 2, palette.gold1)}</g><g transform="translate(0 4)">${meter(48, 2, palette.red)}</g>`,
  48,
);
addAsset(
  "overlay_hp_boss.png",
  96,
  12,
  `${meter(96, 4, palette.green)}<g transform="translate(0 4)">${meter(96, 4, palette.gold1)}</g><g transform="translate(0 8)">${meter(96, 4, palette.red)}</g>`,
  96,
);
addAsset("overlay_exp.png", 85, 2, meter(85, 2, palette.blue), 85);
addAsset("summary_stats_overlay_exp.png", 64, 3, meter(64, 3, palette.blue), 64);

addAsset(
  "scroll_bar.png",
  5,
  155,
  [rect(0, 0, 5, 155, palette.ink), rect(1, 1, 3, 153, palette.steel1), rect(2, 3, 1, 149, palette.cyan1)].join("\n"),
  5,
);
addAsset("scroll_bar_handle.png", 3, 2, rect(0, 0, 3, 2, palette.gold1), 3);
addAsset("select_cursor.png", 18, 18, selector(18, 18, accents[1]), 18);
addAsset("select_cursor_highlight.png", 18, 18, selector(18, 18, accents[3]), 18);
addAsset("select_cursor_highlight_thick.png", 18, 18, selector(18, 18, accents[3], true), 18);
addAsset("select_cursor_pokerus.png", 18, 18, selector(18, 18, accents[4], true), 18);
addAsset("select_gen_cursor.png", 26, 16, selector(26, 16, accents[1]), 26);
addAsset("select_gen_cursor_highlight.png", 26, 16, selector(26, 16, accents[3], true), 26);
addAsset("cursor.png", 6, 10, arrow(6, 10), 6);
addAsset("cursor_reverse.png", 6, 10, arrow(6, 10, true), 6);
addAsset("cursor_tera.png", 12, 15, selector(12, 15, accents[4], true), 12);
addAsset("bmenu_sel.png", 44, 16, selector(44, 16, accents[3]), 44);
addAsset("mmenu_sel.png", 74, 16, selector(74, 16, accents[3]), 74);
addAsset("boolean_sel.png", 26, 16, selector(26, 16, accents[3]), 26);
addAsset("namebox.png", 100, 20, panel(100, 20, accents[3]), 80);
addAsset("prompt.png", 7, 25, `${arrow(7, 10)}<g transform="translate(0 15)">${arrow(7, 10, true)}</g>`, 7);

addAsset("settings_icon.png", 23, 23, icon(23, 23, "settings"), 23);
addAsset("language_icon.png", 23, 23, icon(23, 23, "language"), 23);
addAsset("link_icon.png", 16, 16, icon(16, 16, "link"), 16);
addAsset("unlink_icon.png", 16, 16, icon(16, 16, "unlink"), 16);
addAsset("saving_icon.png", 16, 16, icon(16, 16, "saving"), 16);

async function renderAsset(asset) {
  const svgSource = svgWrap(asset.width, asset.height, asset.body);
  const svgPath = resolve(outputRoot, asset.path.replace(/\.png$/, ".svg"));
  const rawPath = resolve(rasterRoot, asset.path);
  const outPath = resolve(uiRoot, asset.path);
  await mkdir(dirname(svgPath), { recursive: true });
  await mkdir(dirname(rawPath), { recursive: true });
  await mkdir(dirname(outPath), { recursive: true });
  await writeFile(svgPath, svgSource, "utf8");

  const raw = await sharp(Buffer.from(svgSource))
    .resize(asset.width, asset.height, { fit: "fill" })
    .png({ compressionLevel: 9 })
    .toBuffer();
  await writeFile(rawPath, raw);

  const baseWidth = Math.max(1, Math.min(asset.baseWidth, asset.width));
  const baseHeight = Math.max(1, Math.round((asset.height * baseWidth) / asset.width));
  const pixelified = await sharp(raw)
    .ensureAlpha()
    .resize(baseWidth, baseHeight, { kernel: sharp.kernel.nearest, fit: "fill" })
    .resize(asset.width, asset.height, { kernel: sharp.kernel.nearest, fit: "fill" })
    .png({ compressionLevel: 9 })
    .toBuffer();

  await writeFile(outPath, pixelified);
  return asset.path;
}

async function main() {
  const rendered = [];
  for (const asset of assets) {
    rendered.push(await renderAsset(asset));
  }

  process.stdout.write(
    `${JSON.stringify(
      {
        generated: rendered.length,
        svgSource: outputRoot,
        rasterSource: rasterRoot,
      },
      null,
      2,
    )}\n`,
  );
}

main().catch(error => {
  process.stderr.write(`${error instanceof Error ? error.stack || error.message : String(error)}\n`);
  process.exit(1);
});
