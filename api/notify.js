import { Octokit } from "@octokit/rest";
import https from "https";
import { loadLastAssets, saveAssetsToGitHub } from "../utils/github.js";

const H1_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data/hackerone_data.json";
const BUGCROWD_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data/bugcrowd_data.json";

const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_USER_ID = process.env.TELEGRAM_USER_ID;

async function fetchJson(url) {
  const res = await fetch(url);
  return res.json();
}

function extractAssets(data, platform) {
  const assets = [];
  for (const program of data) {
    if (!program.bounty) continue;

    for (const asset of program.assets) {
      const type = asset.asset_type.toLowerCase();
      if (type !== "url" && type !== "wildcard") continue;

      assets.push({
        asset: asset.asset_identifier,
        program: program.name,
        platform,
        type: asset.asset_type,
        bounty: program.bounty,
      });
    }
  }
  return assets;
}

function getNewAssets(current, previous) {
  const oldSet = new Set(previous.map((a) => a.asset));
  return current.filter((a) => !oldSet.has(a.asset));
}

function sendTelegram(message) {
  const data = JSON.stringify({
    chat_id: TELEGRAM_USER_ID,
    text: message,
  });

  const options = {
    hostname: "api.telegram.org",
    path: `/bot${TELEGRAM_BOT_TOKEN}/sendMessage`,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Content-Length": Buffer.byteLength(data),
    },
  };

  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      res.on("data", () => {});
      res.on("end", () => resolve(true));
    });
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

function formatMessage(asset) {
  const time = new Date().toISOString().replace("T", " ").split(".")[0];
  return `🆕 New Asset Found

🔍 Asset: ${asset.asset}
🏢 Program: ${asset.program}
🌐 Platform: ${asset.platform}
📋 Type: ${asset.type}
💸 Bounty Eligible: Yes

Found at ${time}`;
}

export default async function handler(req, res) {
  try {
    const h1Data = await fetchJson(H1_URL);
    const bugcrowdData = await fetchJson(BUGCROWD_URL);

    const allAssets = [
      ...extractAssets(h1Data, "HackerOne"),
      ...extractAssets(bugcrowdData, "Bugcrowd"),
    ];

    const oldAssets = await loadLastAssets();
    const newAssets = getNewAssets(allAssets, oldAssets);

    for (const asset of newAssets) {
      const msg = formatMessage(asset);
      await sendTelegram(msg);
    }

    await saveAssetsToGitHub(allAssets);

    res.status(200).json({ success: true, new: newAssets.length });
  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, error: err.toString() });
  }
}
