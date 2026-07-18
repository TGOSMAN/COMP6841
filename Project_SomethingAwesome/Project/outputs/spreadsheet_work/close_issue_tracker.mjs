import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "C:/GithubRepositories/COMP6841/Project_SomethingAwesome/Project/outputs/requirements/Signal_Forge_CTF_Tasks.xlsx";
const outputDir = "C:/GithubRepositories/COMP6841/Project_SomethingAwesome/Project/outputs/spreadsheet_work";

const closures = [
  "Closed: live Python parser now streams FFT rows, tuned samples, parser fields, and OOK tunnel capture replaces the incorrect FSK hopping artifact. Evidence: radio/live_signal_pipeline.py, server.py, challenge.js, captures/01-tunnel-ook-sign.json.",
  "Closed: artifact cards now provide Inspect and Download actions; /api/rf/raw exports raw complex16 IQ; receiver/TX buttons gain active visual states. Evidence: challenge.js, challenge.html, styles.css, server.py.",
  "Closed: introductory signal tasks auto-centre on the live profile; acquisition tasks use a survey preset without giving the exact answer in the receiver status. Evidence: resetAnalysisView() in challenge.js.",
  "Closed: tuned-audio monitor added; task tips no longer rely on explicit receiver answer text. Evidence: analysis-audio control and toggleTunedAudio() in challenge.html/challenge.js.",
  "Closed: live generator uses smooth noise, raised burst envelopes, and smoothed hop transitions; artifact renderer also uses smooth background/envelopes. Evidence: radio/live_signal_pipeline.py and rowsForArtifact()/sourcePower() in challenge.js.",
  "Closed: on-page mission effect stage now updates signs, warning lights, relay nodes, or gate controller state from RF command results. Evidence: effect-stage markup/CSS and updateEffectFromRf() in challenge.js.",
  "Closed: weak pseudorandom hopping implemented for weather/civilian obscured tasks with LCG slot state in the live parser. Evidence: weak_prng profile in radio/live_signal_pipeline.py.",
  "Closed: scriptable live/raw interfaces now exist beside /api/script/terminal: /api/rf/live for parser frames and /api/rf/raw for raw samples. Evidence: server.py and script interface metadata.",
  "Closed: advanced tasks now expose reverse-engineering source, local binary images, and HDL artifacts. Evidence: tools/re_binaries/*, tools/hdl/*, and regenerated data/challenges.json.",
  "Closed: waterfalls are now generated from task/context-specific Python live profiles; tunnel artifact no longer shows FSK hopping, and advanced profiles no longer reuse toll-themed labels. Evidence: radio/live_signal_pipeline.py and data/challenges.json.",
];

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Issue_Tracking");

await fs.mkdir(outputDir, { recursive: true });
const before = await workbook.render({ sheetName: "Issue_Tracking", range: "A1:X11", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "Issue_Tracking_before.png"), new Uint8Array(await before.arrayBuffer()));

const range = sheet.getRange("A1:X11");
const values = range.values;
const headers = values[0].map((value) => String(value ?? "").trim().toLowerCase());
const statusCol = headers.findIndex((header) => header === "status");
const evidenceCol = headers.findIndex((header) => header.includes("evidence"));
const resolvedStatusCol = statusCol >= 0 ? statusCol : 23;
const resolvedEvidenceCol = evidenceCol >= 0 ? evidenceCol : 9;

for (let row = 1; row <= closures.length; row += 1) {
  sheet.getCell(row, resolvedStatusCol).values = [["Closed"]];
  sheet.getCell(row, resolvedEvidenceCol).values = [[closures[row - 1]]];
}

const after = await workbook.render({ sheetName: "Issue_Tracking", range: "A1:X11", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "Issue_Tracking_after.png"), new Uint8Array(await after.arrayBuffer()));

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "issue tracker formula error scan",
});

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Issue_Tracking",
  range: "A1:X11",
  include: "values",
  tableMaxRows: 12,
  tableMaxCols: 24,
  maxChars: 12000,
});

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(workbookPath);

console.log(JSON.stringify({
  workbookPath,
  statusCol: resolvedStatusCol,
  evidenceCol: resolvedEvidenceCol,
  errors: errors.ndjson,
  check: check.ndjson.slice(0, 2000),
}, null, 2));
