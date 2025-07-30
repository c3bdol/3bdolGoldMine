import { Octokit } from "@octokit/rest";

const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
const GITHUB_REPO = process.env.GITHUB_REPO; // Format: username/repo
const GITHUB_FILENAME = process.env.GITHUB_FILENAME || "data.json";

const octokit = new Octokit({ auth: GITHUB_TOKEN });

export async function loadLastAssets() {
  const [owner, repo] = GITHUB_REPO.split("/");
  try {
    const res = await octokit.repos.getContent({
      owner,
      repo,
      path: GITHUB_FILENAME,
    });

    const content = Buffer.from(res.data.content, "base64").toString("utf8");
    return JSON.parse(content);
  } catch (e) {
    return []; // First time: no data yet
  }
}

export async function saveAssetsToGitHub(data) {
  const [owner, repo] = GITHUB_REPO.split("/");
  const content = Buffer.from(JSON.stringify(data, null, 2)).toString("base64");

  try {
    const old = await octokit.repos.getContent({
      owner,
      repo,
      path: GITHUB_FILENAME,
    });

    await octokit.repos.createOrUpdateFileContents({
      owner,
      repo,
      path: GITHUB_FILENAME,
      message: "Update asset list",
      content,
      sha: old.data.sha,
    });
  } catch {
    await octokit.repos.createOrUpdateFileContents({
      owner,
      repo,
      path: GITHUB_FILENAME,
      message: "Initial asset list",
      content,
    });
  }
}
