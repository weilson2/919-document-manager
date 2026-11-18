import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { build } from "esbuild";

const output = "../src/document_manager/editor/assets";
const result = await build({
  entryPoints: { app: "src/main.ts" },
  outdir: output,
  bundle: true,
  format: "iife",
  target: "chrome140",
  minify: true,
  legalComments: "eof",
  metafile: true,
  write: false,
});

const packages = new Set();
for (const source of Object.keys(result.metafile.inputs)) {
  const path = source.split("node_modules/").at(-1);
  if (path === source) continue;
  const parts = path.split("/");
  packages.add(parts.slice(0, path.startsWith("@") ? 2 : 1).join("/"));
}

const notices = [];
for (const name of [...packages].sort()) {
  const root = join("node_modules", name);
  const metadata = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
  let license;
  for (const candidate of ["LICENSE", "LICENSE.md", "LICENSE.txt", "license"]) {
    license = await readFile(join(root, candidate), "utf8").catch((error) => {
      if (error.code !== "ENOENT") throw error;
    });
    if (license) break;
  }
  if (!license) throw new Error(`Missing license for ${name}`);
  notices.push(`${name} ${metadata.version}\n${license.trim()}`);
}

const assets = result.outputFiles.map(({ path, contents }) => ({
  path,
  contents: Buffer.from(contents),
}));
assets.push({
  path: join(output, "third-party-licenses.txt"),
  contents: Buffer.from(notices.join("\n\n") + "\n"),
});

for (const { path, contents } of assets) {
  if (process.argv.includes("--check")) {
    if (!contents.equals(await readFile(path))) throw new Error(`Rebuild outdated asset ${path}`);
  } else {
    await writeFile(path, contents);
  }
}
