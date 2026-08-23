#!/usr/bin/env node

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const NODE_MODULES = "/Users/matcom/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const sharp = require(path.join(NODE_MODULES, "sharp"));
const packDir = path.resolve(__dirname, "..");
const manifest = JSON.parse(fs.readFileSync(path.join(packDir, "asset-manifest.json"), "utf8"));
const failures = [];
const verifiedFiles = [];

function fail(message) {
  failures.push(message);
}

async function verify() {
  for (const asset of manifest.assets) {
    const file = path.join(packDir, asset.file);
    if (!fs.existsSync(file)) {
      fail(`Missing ${asset.file}`);
      continue;
    }
    const stat = fs.statSync(file);
    if (stat.size === 0) {
      fail(`Empty ${asset.file}`);
      continue;
    }
    const metadata = await sharp(file).metadata();
    if (metadata.width !== asset.width || metadata.height !== asset.height) {
      fail(`${asset.file}: expected ${asset.width}x${asset.height}, got ${metadata.width}x${metadata.height}`);
    }
    if (metadata.format !== "png") {
      fail(`${asset.file}: expected PNG, got ${metadata.format}`);
    }
    verifiedFiles.push(file);
  }

  const videoFile = path.join(packDir, manifest.video.file);
  if (!fs.existsSync(videoFile) || fs.statSync(videoFile).size === 0) {
    fail(`Missing or empty ${manifest.video.file}`);
  } else {
    const probe = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate", "-of", "json", videoFile], { encoding: "utf8" });
    if (probe.status !== 0) {
      fail(`ffprobe failed for ${manifest.video.file}: ${probe.stderr}`);
    } else {
      const info = JSON.parse(probe.stdout);
      const videoStream = info.streams.find((stream) => stream.codec_type === "video");
      const audioStreams = info.streams.filter((stream) => stream.codec_type === "audio");
      if (!videoStream || videoStream.width !== 1080 || videoStream.height !== 1920) fail("TikTok video is not 1080x1920");
      if (!videoStream || videoStream.codec_name !== "h264") fail("TikTok video is not H.264");
      if (!videoStream || videoStream.r_frame_rate !== "30/1") fail("TikTok video is not 30 fps");
      if (Math.abs(Number(info.format.duration) - 24) > 0.01) fail(`TikTok video duration is ${info.format.duration}, expected 24 seconds`);
      if (audioStreams.length !== 0) fail("TikTok video unexpectedly contains audio");
    }
    verifiedFiles.push(videoFile);
  }

  const exactTextChecks = [
    ["source/svg/ig-carousel-05-result.svg", ["POTENTIAL SAVING", "£19.98", "Example assumes a UK £9.99 monthly plan", "Prices and dates can change", "Sources: Apple release schedule"]],
    ["source/svg/ig-story-03-result.svg", ["POTENTIAL SAVING", "£19.98", "subscription starting 3 April 2026", "no other Apple TV viewing"]],
    ["source/svg/tt-frame-06-qualification.svg", ["Example assumes a UK £9.99 monthly plan", "5 June", "Prices and dates can change", "Checked 23 August 2026"]],
    ["source/svg/reddit-proof-card.svg", ["POTENTIAL SAVING: £19.98", "Could avoid two £9.99 renewals", "Prices and dates can change"]],
  ];

  for (const [relativeFile, snippets] of exactTextChecks) {
    const file = path.join(packDir, relativeFile);
    if (!fs.existsSync(file)) {
      fail(`Missing source check file ${relativeFile}`);
      continue;
    }
    const contents = fs.readFileSync(file, "utf8");
    for (const snippet of snippets) {
      if (!contents.includes(snippet)) fail(`${relativeFile} is missing exact text: ${snippet}`);
    }
  }

  const previewFiles = fs.readdirSync(path.join(packDir, "exports", "previews"), { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".png"))
    .map((entry) => path.join(packDir, "exports", "previews", entry.name));
  for (const file of previewFiles) {
    if (fs.statSync(file).size === 0) fail(`Empty preview ${path.relative(packDir, file)}`);
    verifiedFiles.push(file);
  }

  if (failures.length > 0) {
    console.error(failures.join("\n"));
    process.exit(1);
  }

  const uniqueFiles = [...new Set(verifiedFiles)].sort();
  const hashes = uniqueFiles.map((file) => {
    const digest = crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
    return `${digest}  ${path.relative(packDir, file)}`;
  });
  fs.writeFileSync(path.join(packDir, "provenance", "verification-sha256.txt"), `${hashes.join("\n")}\n`, "utf8");

  console.log(`Verified ${manifest.assets.length} PNG exports, ${previewFiles.length} previews, and one 24-second silent H.264 MP4.`);
  console.log("Exact claim, qualification, and source-label checks passed.");
}

verify().catch((error) => {
  console.error(error);
  process.exit(1);
});
