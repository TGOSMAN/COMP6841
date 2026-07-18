import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/GithubRepositories/COMP6841/Project_SomethingAwesome/Project";
const outputDir = path.join(root, "outputs", "requirements");
await fs.mkdir(outputDir, { recursive: true });

const requirements = [
  ["Safety and Ethics", "SAFE-01", "Mandatory ethics statement", "The site must clearly state that the CTF is for defensive awareness and does not condone illegal radio misuse.", "Implemented", "Homepage Safety and intent panel", "index.html#safety", "User planning DOCX: explicit safety statement requirement", "Keep the statement visible in report exports."],
  ["Safety and Ethics", "SAFE-02", "Sim-first, receive-only assessment", "Assessed activities must avoid live transmission and use local synthetic targets.", "Implemented", "Hero copy, GNU Radio docs, local TX chain labels", "index.html; docs/gnu-radio-workflow.md; challenge.html", "Planning DOCX: no SDR required and avoid transmit workflows", "Add a per-challenge safety footer before final release."],
  ["Challenge Structure", "STRUCT-01", "Four-level learning ladder", "The project should be organised into Basic, Moderate, Advanced, and Expert concepts.", "Implemented", "Homepage learning arc with four concept cards", "index.html#blueprint", "Planning DOCX: Basic, Moderate, Advanced, Expert sections", "Add progress indicators per level later."],
  ["Challenge Structure", "STRUCT-02", "Civilian contexts", "Scenarios should prefer civilian infrastructure rather than military framing.", "Implemented", "Tunnel signs, radio metadata, council audio, farm gate, city notice API", "data/challenges.json; server.py", "Planning DOCX: avoid military framing and use civilian contexts", "Review all future artifact names for the same rule."],
  ["Challenge Structure", "STRUCT-03", "Small step challenge format", "Each module should expose concrete subtasks and hints rather than single large leaps.", "Implemented", "Each challenge has steps, hints, concepts, objective, and artifacts", "data/challenges.json; challenge.js", "Planning DOCX: each context has three to four sub-challenges", "Split large future contexts into separate subpages."],
  ["GNU Radio Data Source", "GR-01", "RF profiles as source of truth", "Signal data should stem from editable radio profiles, not hand-authored browser JSON.", "Implemented", "Profile file drives generated captures", "radio/profiles/training_signals.json", "User correction: data should stem from a GNU Radio script", "Add GRC-generated top_block files per profile."],
  ["GNU Radio Data Source", "GR-02", "Generator script", "A repeatable script should export browser capture JSON and optional SigMF IQ artifacts.", "Implemented", "Generator emits captures/*.json, *.sigmf-meta, and *.sigmf-data", "radio/generate_gnuradio_artifacts.py", "Planning DOCX: GNU Radio projects export signalling data", "Move deterministic fallback behind real GNU Radio blocks when WSL is ready."],
  ["GNU Radio Data Source", "GR-03", "Generated provenance", "Capture artifacts should record the generator and source profile used to build them.", "Implemented", "generated_by and source_profile fields in generated captures", "captures/02-fsk-hop-scheme.json; captures/15-air-weather-voice.json", "Traceability requirement for evidence", "Add checksum manifest for generated artifacts."],
  ["GNU Radio Data Source", "GR-04", "Waveform downloads", "Waveform time-series data should be downloadable for external analysis.", "Partially Implemented", "Small SigMF preview files are generated for the current profiles", "captures/*.sigmf-data; captures/*.sigmf-meta", "Planning DOCX: waveform time-series downloadable", "Expose generated SigMF links on every relevant challenge card."],
  ["Instrument Workbench", "UI-01", "Waterfall and spectrum views", "The UI should look closer to spectrum/signal analysis tools than a decorative demo.", "Implemented", "Waterfall, spectrum trace, RBW/readouts, cursors, tuning and gain controls", "challenge.html; challenge.js; styles.css", "Planning DOCX: spectrum analyser, oscilloscope, logic analyser quality", "Consider ECharts/WebGL for higher-rate plotting."],
  ["Instrument Workbench", "UI-02", "Artifact preview, not raw JSON only", "Clicking artifacts should show a visual/data inspector before raw content.", "Implemented", "Artifact inspector renders signal preview, structured grid, text, or binary map", "challenge.js", "User request: artifact click should display waterfall/data UI", "Add download buttons and profile provenance badges."],
  ["Instrument Workbench", "UI-03", "Measurement controls", "Waterfall sections need pause/play, zoom, scrubber, and measurement cursors.", "Implemented", "Home waterfall and challenge analyser include play/pause, zoom, frame scrubber, and cursor deltas", "app.js; challenge.js; challenge.html", "User request: zoom both axes, cursors, pause/play", "Add draggable cursors and saved measurements."],
  ["Information Modes", "MODE-01", "Raw digital data", "The CTF must include raw packet/metadata recovery.", "Implemented", "Tunnel sign, broadcast metadata, city notice, and TLV modules", "data/challenges.json; tools/telemetry_decoder", "Planning DOCX: raw digital data transfer", "Add packet bit-viewer in the workbench."],
  ["Information Modes", "MODE-02", "Audio communications", "The CTF must include audio communications and user interaction.", "Implemented", "Council warning audio net with speech playback, transcript, and message submission", "challenge.html; challenge.js; server.py", "Planning DOCX: audio player interface and emergency audio context", "Replace browser speech synthesis with generated WAV artifacts later."],
  ["Information Modes", "MODE-03", "Steganographic communications", "The CTF should leave room for steganographic communications.", "Planned", "Homepage information-mode card marks it as a planned extension", "index.html#blueprint", "Planning DOCX: steganographic communications", "Add hidden symbol/audio-watermark challenge."],
  ["Information Modes", "MODE-04", "Radar-style signal", "The CTF should leave room for a basic radar-style or IC&S signal.", "Planned", "Homepage information-mode card and expert learning arc", "index.html#blueprint", "Planning DOCX: basic radar-style signal and IC&S expert context", "Add simple range/Doppler or IC&S grocery scenario."],
  ["Cyber Track", "CYBER-01", "RF-to-backend SQLi bridge", "Decoded RF values should become backend input in a deliberately vulnerable local endpoint.", "Implemented", "City Notice API Pivot and vulnerable/safe event endpoints", "data/challenges.json; server.py", "Planning DOCX: technical cyber component and SQLi", "Add solver notes comparing unsafe SQL to parameterized SQL."],
  ["Cyber Track", "CYBER-02", "Business logic and authorization", "The CTF should show that SQL-safe systems can still fail authorization or trust telemetry.", "Implemented", "Controlled interference exercise and secure quote rejection", "server.py; data/challenges.json", "Earlier project plan: business logic abuse", "Add fraud scoring/audit endpoint."],
  ["Cyber Track", "CYBER-03", "RF-origin web trust boundary", "RF-origin operator text should demonstrate output encoding and unsafe rendering risks.", "Implemented", "Untrusted Radio Note challenge and Attack/Secure Mode rendering", "server.py; index.html; challenge.js", "Earlier project plan: optional XSS if it supports story", "Clarify it as trust-boundary lesson in report."],
  ["Cyber Track", "CYBER-04", "Reverse engineering", "Learners should reverse packet/decoder logic as difficulty increases.", "Partially Implemented", "Telemetry decoder tools and decoder challenge artifacts exist", "tools/telemetry_decoder; data/challenges.json", "Planning DOCX: reverse engineer embedded C backends", "Add stripped binary and hard-mode firmware image."],
  ["Cyber Track", "CYBER-05", "Binary exploitation", "Advanced modules should include local synthetic parser vulnerabilities and safe comparisons.", "Partially Implemented", "Farm gate TLV parser fault plus vulnerable/safe parser source", "tools/tlv_parser; server.py; data/challenges.json", "Planning DOCX: parser flaw and binary exploit direction", "Add compiled training binaries and fuzz corpus."],
  ["Advanced/SOTA", "SOTA-01", "Advanced firmware/hardware lane", "The project should leave room for C/C++, HDL review, secure boot, and device trust.", "Planned", "Advanced learning card and developer extension plan", "index.html#blueprint; docs/developer-extension-plan.md", "Planning DOCX: HDL/C review and advanced security concepts", "Implement synthetic firmware manifest and HDL flaw task."],
  ["Advanced/SOTA", "SOTA-02", "Jamming side quest", "The project should include jamming types, counters, and defensive classification.", "Partially Implemented", "Controlled interference module and jamming research notes", "data/challenges.json; server.py; docs/developer-extension-plan.md", "Planning DOCX: four jamming topics with subtasks", "Add spot, sweep, barrage, follower, deceptive replay profiles."],
  ["Advanced/SOTA", "SOTA-03", "Propagation and receiver limits", "Harder levels should include path loss, multipath, Doppler, saturation, and adjacent-channel effects.", "Planned", "Research notes and generator source model hooks", "server.py; radio/profiles/training_signals.json", "Planning DOCX: radio propagation, jamming, hardware realism", "Add propagation profile parameters to generator."],
  ["Advanced/SOTA", "SOTA-04", "Integrated communications and sensing", "Expert levels should introduce IC&S and cognitive-radio concepts.", "Planned", "Expert learning card and mode-grid radar-style extension", "index.html#blueprint", "Planning DOCX: IC&S and cognitive radio expert concepts", "Build Qam grocery-store scenario."],
  ["Session and Randomisation", "RAND-01", "Per-session identity and flags", "Each learner session should have unique flags and identifiers.", "Implemented", "Session token generation, session user_data, per-task flag derivation", "server.py", "Planning DOCX: regenerated randomisation and unique flags", "Extend randomisation into generated payload fields."],
  ["Session and Randomisation", "RAND-02", "Randomized audio intercept", "Audio challenge data should vary per generated session.", "Implemented", "Council weather intercept randomizes site, zone, hazard, action, and AUTH code", "server.py", "Planning DOCX: regenerated randomisation", "Persist solved transcript evidence per session."],
  ["Verification", "TEST-01", "JSON validity", "Core challenge and capture data should validate structurally.", "Verified", "JSON validation performed for challenge metadata and generated captures", "data/challenges.json; captures/*.json", "Implementation QA", "Add CI script for JSON/profile validation."],
  ["Verification", "TEST-02", "Generated artifact run", "The project should regenerate RF artifacts from the generator before delivery.", "Verified", "Generator run emitted seven capture JSON files and SigMF preview pairs", "radio/generate_gnuradio_artifacts.py; captures/", "Implementation QA", "Add Makefile/PowerShell task for regeneration."],
  ["Verification", "TEST-03", "Browser smoke test", "The site should render after structural changes.", "Verified", "Home page and council audio challenge loaded with no console errors; artifact preview opened as a canvas with generated provenance", "localhost:8002", "Implementation QA", "Add automated browser smoke tests later."]
];

const evidenceRows = [
  ["Planning source", "COMP6841 Project Planning Further.docx", "Extracted safety, GNU Radio, information-mode, challenge-ladder, and SOTA requirements."],
  ["Web shell", "index.html", "Safety panel, learning arc, information modes, GNU Radio workflow summary."],
  ["Challenge metadata", "data/challenges.json", "Civilian contexts, context labels, steps, hints, artifacts, and generated-profile wording."],
  ["RF generator", "radio/generate_gnuradio_artifacts.py", "Profile-driven artifact exporter with optional SigMF IQ output."],
  ["RF profiles", "radio/profiles/training_signals.json", "Editable source of truth for centre frequency, span, modulation, sources, and metadata."],
  ["Generated captures", "captures/*.json", "Browser waterfall preview artifacts with generated_by and source_profile provenance."],
  ["SigMF artifacts", "captures/*.sigmf-meta; captures/*.sigmf-data", "Downloadable IQ preview files emitted by the generator."],
  ["Backend", "server.py", "Session flags, local endpoints, RF command handling, safe/attack mode, council audio protocol."],
  ["Challenge UI", "challenge.html; challenge.js", "RF workbench, audio intercept UI, terminal, artifact inspector, measurement controls."],
  ["Tools", "tools/telemetry_decoder; tools/tlv_parser", "Local RE/parser challenge assets and safe/vulnerable code paths."]
];

const groups = [...new Set(requirements.map((row) => row[0]))];

const workbook = Workbook.create();
const matrix = workbook.worksheets.add("Requirements Matrix");
const summary = workbook.worksheets.add("Coverage Summary");
const evidence = workbook.worksheets.add("Evidence Index");

for (const sheet of [matrix, summary, evidence]) {
  sheet.showGridLines = false;
}

matrix.getRange("A1:I1").merge();
matrix.getRange("A1").values = [["Signal Forge CTF Requirements and Evidence Matrix"]];
matrix.getRange("A2:I2").merge();
matrix.getRange("A2").values = [["Generated from the planning document and current implementation. RF capture JSON is treated as generated output from radio/profiles/training_signals.json."]];
matrix.getRange("A4:I4").values = [["Group", "Req ID", "Requirement", "Description", "Status", "Evidence", "Evidence Location", "Planning Source", "Next Evidence / Work"]];
matrix.getRange(`A5:I${requirements.length + 4}`).values = requirements;
matrix.freezePanes.freezeRows(4);

summary.getRange("A1:E1").merge();
summary.getRange("A1").values = [["Coverage Summary"]];
summary.getRange("A3:E3").values = [["Group", "Total", "Implemented", "Partial/Planned", "Verified/Pending"]];
summary.getRange(`A4:A${groups.length + 3}`).values = groups.map((group) => [group]);
summary.getRange(`B4:B${groups.length + 3}`).formulas = groups.map((_, i) => [[`=COUNTIF('Requirements Matrix'!$A$5:$A$${requirements.length + 4},A${i + 4})`]][0]);
summary.getRange(`C4:C${groups.length + 3}`).formulas = groups.map((_, i) => [[`=COUNTIFS('Requirements Matrix'!$A$5:$A$${requirements.length + 4},A${i + 4},'Requirements Matrix'!$E$5:$E$${requirements.length + 4},"Implemented")+COUNTIFS('Requirements Matrix'!$A$5:$A$${requirements.length + 4},A${i + 4},'Requirements Matrix'!$E$5:$E$${requirements.length + 4},"Verified")`]][0]);
summary.getRange(`D4:D${groups.length + 3}`).formulas = groups.map((_, i) => [[`=COUNTIFS('Requirements Matrix'!$A$5:$A$${requirements.length + 4},A${i + 4},'Requirements Matrix'!$E$5:$E$${requirements.length + 4},"Partially Implemented")+COUNTIFS('Requirements Matrix'!$A$5:$A$${requirements.length + 4},A${i + 4},'Requirements Matrix'!$E$5:$E$${requirements.length + 4},"Planned")`]][0]);
summary.getRange(`E4:E${groups.length + 3}`).formulas = groups.map((_, i) => [[`=COUNTIFS('Requirements Matrix'!$A$5:$A$${requirements.length + 4},A${i + 4},'Requirements Matrix'!$E$5:$E$${requirements.length + 4},"Pending Final Check")`]][0]);
summary.freezePanes.freezeRows(3);

evidence.getRange("A1:C1").merge();
evidence.getRange("A1").values = [["Evidence Index"]];
evidence.getRange("A3:C3").values = [["Evidence Type", "Location", "Notes"]];
evidence.getRange(`A4:C${evidenceRows.length + 3}`).values = evidenceRows;
evidence.freezePanes.freezeRows(3);

applySheetStyle(matrix, "A1:I2", "A4:I4", `A5:I${requirements.length + 4}`);
applySheetStyle(summary, "A1:E1", "A3:E3", `A4:E${groups.length + 3}`);
applySheetStyle(evidence, "A1:C1", "A3:C3", `A4:C${evidenceRows.length + 3}`);

matrix.getRange("A:A").format.columnWidth = 22;
matrix.getRange("B:B").format.columnWidth = 13;
matrix.getRange("C:C").format.columnWidth = 28;
matrix.getRange("D:D").format.columnWidth = 50;
matrix.getRange("E:E").format.columnWidth = 18;
matrix.getRange("F:F").format.columnWidth = 36;
matrix.getRange("G:G").format.columnWidth = 38;
matrix.getRange("H:H").format.columnWidth = 42;
matrix.getRange("I:I").format.columnWidth = 42;
matrix.getRange(`A5:I${requirements.length + 4}`).format.wrapText = true;
matrix.getRange(`A5:I${requirements.length + 4}`).format.verticalAlignment = "top";

summary.getRange("A:A").format.columnWidth = 28;
summary.getRange("B:E").format.columnWidth = 16;
summary.getRange(`B4:E${groups.length + 3}`).format.horizontalAlignment = "center";

evidence.getRange("A:A").format.columnWidth = 24;
evidence.getRange("B:B").format.columnWidth = 46;
evidence.getRange("C:C").format.columnWidth = 72;
evidence.getRange(`A4:C${evidenceRows.length + 3}`).format.wrapText = true;

const statusRange = matrix.getRange(`E5:E${requirements.length + 4}`);
statusRange.conditionalFormats.add("containsText", { text: "Implemented", format: { fill: "#D9EAD3", font: { color: "#14532D" } } });
statusRange.conditionalFormats.add("containsText", { text: "Verified", format: { fill: "#D9EAD3", font: { color: "#14532D" } } });
statusRange.conditionalFormats.add("containsText", { text: "Partially", format: { fill: "#FEF3C7", font: { color: "#92400E" } } });
statusRange.conditionalFormats.add("containsText", { text: "Planned", format: { fill: "#E0F2FE", font: { color: "#075985" } } });
statusRange.conditionalFormats.add("containsText", { text: "Pending", format: { fill: "#FEE2E2", font: { color: "#991B1B" } } });

const inspectMatrix = await workbook.inspect({
  kind: "table",
  sheetId: "Requirements Matrix",
  range: "A1:I12",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 9,
  maxChars: 5000
});
console.log(inspectMatrix.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 3000
});
console.log(errors.ndjson);

for (const sheetName of ["Requirements Matrix", "Coverage Summary", "Evidence Index"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  const previewBytes = new Uint8Array(await preview.arrayBuffer());
  await fs.writeFile(path.join(outputDir, `${sheetName.replaceAll(" ", "_")}.png`), previewBytes);
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(path.join(outputDir, "Signal_Forge_CTF_Requirements_Evidence.xlsx"));

function applySheetStyle(sheet, titleRange, headerRange, bodyRange) {
  sheet.getRange(titleRange).format = {
    fill: "#0F172A",
    font: { bold: true, color: "#FFFFFF", size: 16 },
    horizontalAlignment: "left",
    verticalAlignment: "center",
    wrapText: true
  };
  sheet.getRange(headerRange).format = {
    fill: "#155E75",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#CBD5E1" }
  };
  sheet.getRange(bodyRange).format = {
    fill: "#F8FAFC",
    font: { color: "#0F172A", size: 10 },
    borders: { preset: "all", style: "thin", color: "#E2E8F0" },
    verticalAlignment: "top",
    wrapText: true
  };
}
