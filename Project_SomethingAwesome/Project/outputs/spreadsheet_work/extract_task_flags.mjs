import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "C:/GithubRepositories/COMP6841/Project_SomethingAwesome/Project/outputs/requirements/Signal_Forge_CTF_Tasks.xlsx";

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook",
  include: "sheets,dimensions,definedNames",
  maxChars: 12000,
});

const taskTable = await workbook.inspect({
  kind: "table",
  sheetId: "CTF_TASK_SHEET",
  range: "A1:Z80",
  include: "values,formats,comments",
  tableMaxRows: 80,
  tableMaxCols: 26,
  maxChars: 50000,
});

const flags = await workbook.inspect({
  kind: "match",
  searchTerm: "CTF\\{|FLAG\\{|FLAG|flag",
  options: { useRegex: true, maxResults: 200 },
  summary: "literal flag and flag-location scan",
});

console.log(JSON.stringify({
  workbookPath,
  summary: summary.ndjson,
  taskTable: taskTable.ndjson,
  flags: flags.ndjson,
}, null, 2));
