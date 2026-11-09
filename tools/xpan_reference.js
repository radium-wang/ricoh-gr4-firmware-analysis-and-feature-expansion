#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Offline reference for the proposed GR IV XPAN composition, icon and JPEG.
// This does not run on or communicate with the camera.

const path = require('node:path');
let sharp;
try {
  sharp = require('sharp');
} catch {
  // The same bundled dependency is used by make_hasselblad_goodbye.js.
  sharp = require(path.join(path.dirname(path.dirname(process.execPath)), 'node_modules', 'sharp'));
}

function centerCrop(width, height) {
  const target = 65 / 24;
  const cropWidth = width / height < target
    ? width : Math.max(1, Math.min(width, Math.round(height * target)));
  const cropHeight = width / height < target
    ? Math.max(1, Math.min(height, Math.round(width / target))) : height;
  return {
    left: Math.floor((width - cropWidth) / 2),
    top: Math.floor((height - cropHeight) / 2),
    width: cropWidth,
    height: cropHeight,
  };
}

async function main() {
  if (process.argv.length !== 4) {
    throw new Error('usage: node tools/xpan_reference.js INPUT_IMAGE OUTPUT_PREFIX');
  }
  const input = process.argv[2];
  const prefix = process.argv[3];
  const { data, info } = await sharp(input).rotate().png().toBuffer({ resolveWithObject: true });
  const { width, height } = info;
  const crop = centerCrop(width, height);
  const savedPath = path.resolve(`${prefix}.jpg`);
  const previewPath = path.resolve(`${prefix}.preview.png`);

  await sharp(data).extract(crop).jpeg({ quality: 92 }).toFile(savedPath);

  const bottom = crop.top + crop.height;
  const badgeWidth = Math.min(100, Math.round(width * 0.2));
  const badgeHeight = Math.min(32, Math.round(height * 0.1));
  const badgeX = width - badgeWidth - 12;
  const badgeY = 12;
  const fontSize = Math.max(10, Math.round(badgeHeight * 0.52));
  const overlay = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <rect x="0" y="0" width="${width}" height="${crop.top}" fill="black"/>
    <rect x="0" y="${bottom}" width="${width}" height="${height - bottom}" fill="black"/>
    <rect x="${badgeX}" y="${badgeY}" width="${badgeWidth}" height="${badgeHeight}" fill="#111" stroke="white" stroke-width="2"/>
    <text x="${badgeX + badgeWidth / 2}" y="${badgeY + badgeHeight / 2}" dominant-baseline="central" text-anchor="middle" fill="white" font-family="sans-serif" font-size="${fontSize}" font-weight="bold">XPAN</text>
  </svg>`);
  await sharp(data).composite([{ input: overlay }]).png().toFile(previewPath);

  console.log(`source: ${width}×${height}`);
  console.log(`center crop: x=${crop.left}, y=${crop.top}, ${crop.width}×${crop.height}`);
  console.log(`output ratio: ${(crop.width / crop.height).toFixed(6)} (target 65:24)`);
  console.log(`saved: ${savedPath}`);
  console.log(`preview: ${previewPath}`);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
