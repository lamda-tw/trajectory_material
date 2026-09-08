#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

const COLORS = {
  navy: "#16324F",
  blue: "#2F75B5",
  paleBlue: "#DCE6F1",
  subtitle: "#E8F0F7",
  subtitleText: "#40576D",
  text: "#1F2937",
  border: "#D9E1E8",
  white: "#FFFFFF",
  average: "#E2F0D9",
  groupA: "#EDF4FB",
  groupB: "#F7FAFC",
};

const SUBTITLES = {
  "O2目标分天梯图": "O2业务成效分独立展示；行列均按已有数值的平均分降序，缺失组合留空。",
  "五项分段分天梯图": "五项关键分逐项执行分段映射后加权；行列均按平均分降序。",
  "五项分段分详表": "先按检查项分组，再在组内按题目行平均分降序；模型列按全表平均分降序。",
  "五项离散分天梯图": "五项关键分沿用阶梯离散映射后加权；行列均按平均分降序。",
  "五项离散分详表": "先按检查项分组，再在组内按题目行平均分降序；模型列按全表平均分降序。",
  "五项原始分天梯图": "五项关键检查项使用原始分加权；行列均按平均分降序。",
  "五项原始分详表": "先按检查项分组，再在组内按题目行平均分降序；模型列按全表平均分降序。",
  "全项原始分天梯图": "全部纳入all.raw的非O2检查项使用原始分加权；行列均按平均分降序。",
  "全项原始分详表": "展开全部all.raw检查项；检查项分组、题目组内降序、模型列全表降序。",
};

function logStage(message) {
  process.stderr.write(`[EI-XLSX] ${message}\n`);
}

async function validateWorkbookSheets(workbook, layouts) {
  const inspection = await workbook.inspect({
    kind: "sheet",
    include: "id,name",
    maxChars: 4000,
  });
  const actualNames = inspection.ndjson
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .filter((record) => record.kind === "sheet")
    .map((record) => record.name);
  const expectedNames = layouts.map((layout) => layout.name);
  if (JSON.stringify(actualNames) !== JSON.stringify(expectedNames)) {
    throw new Error(
      `workbook sheet inspection mismatch: actual=${JSON.stringify(actualNames)}`,
    );
  }
}

function args(argv) {
  const output = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error("invalid arguments");
    }
    output[key.slice(2)] = value;
  }
  output.operation ??= "all";
  if (!["all", "export", "preview"].includes(output.operation)) {
    throw new Error(`unsupported --operation: ${output.operation}`);
  }
  if (!output.input) throw new Error("missing --input");
  if (output.operation !== "preview" && !output.output) {
    throw new Error("missing --output");
  }
  if (output.operation !== "export" && !output["preview-dir"]) {
    throw new Error("missing --preview-dir");
  }
  return output;
}

async function artifactTool() {
  try {
    return await import("@oai/artifact-tool");
  } catch (initialError) {
    const modules = process.env.EVAL_NODE_MODULES;
    if (!modules) {
      throw new Error(`@oai/artifact-tool unavailable: ${initialError.message}`);
    }
    const entry = path.join(
      modules,
      "@oai",
      "artifact-tool",
      "dist",
      "artifact_tool.mjs",
    );
    return await import(pathToFileURL(entry).href);
  }
}

function columnName(index) {
  let value = index + 1;
  let output = "";
  while (value > 0) {
    value -= 1;
    output = String.fromCharCode(65 + (value % 26)) + output;
    value = Math.floor(value / 26);
  }
  return output;
}

function address(row, col, rows, cols) {
  return `${columnName(col)}${row}:${columnName(col + cols - 1)}${row + rows - 1}`;
}

function setTitle(sheet, reportId, label, columns) {
  const end = columnName(columns - 1);
  sheet.getRange(`A1:${end}1`).merge();
  sheet.getRange("A1").values = [[`${reportId} EI推演打分｜${label}`]];
  sheet.getRange(`A1:${end}1`).format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 16 },
    rowHeight: 30,
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${end}2`).merge();
  sheet.getRange("A2").values = [[SUBTITLES[label]]];
  sheet.getRange(`A2:${end}2`).format = {
    fill: COLORS.subtitle,
    font: { italic: true, color: COLORS.subtitleText, size: 10 },
    rowHeight: 24,
    verticalAlignment: "center",
    wrapText: true,
  };
}

function writeTable(sheet, rows, widths) {
  const columns = rows[0].length;
  const range = sheet.getRange(address(4, 0, rows.length, columns));
  range.values = rows;
  range.format = {
    font: { color: COLORS.text, size: 10 },
    borders: { preset: "inside", style: "thin", color: COLORS.border },
    verticalAlignment: "center",
  };
  const header = sheet.getRange(address(4, 0, 1, columns));
  header.format = {
    fill: COLORS.blue,
    font: { bold: true, color: COLORS.white, size: 10 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    rowHeight: 34,
    borders: { preset: "all", style: "thin", color: "#B8C7D9" },
  };
  if (rows.length > 1) {
    sheet.getRange(address(5, 0, rows.length - 1, columns)).format.rowHeight = 22;
  }
  widths.forEach((width, index) => {
    sheet.getRange(`${columnName(index)}:${columnName(index)}`).format.columnWidth = width;
  });
}

function setScoreFormat(range, values) {
  range.format.numberFormat = "0.00";
  range.format.horizontalAlignment = "center";
  const distinctScores = new Set(
    values.flat().filter((value) => typeof value === "number" && Number.isFinite(value)),
  );
  if (distinctScores.size > 1) {
    range.conditionalFormats.add("colorScale", {
      colors: ["#FECACA", "#FEF3C7", "#BBF7D0"],
      thresholds: ["min", "50%", "max"],
    });
  }
}

function setAverageFormat(range) {
  range.format = {
    fill: COLORS.average,
    font: { bold: true, color: COLORS.text, size: 10 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    numberFormat: "0.00",
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
}

function renderLadder(workbook, reportId, layout) {
  const sheet = workbook.worksheets.add(layout.name);
  const questionCount = layout.questions.length;
  const modelCount = layout.models.length;
  const columnCount = questionCount + 2;
  const averageColumn = columnName(columnCount - 1);
  const lastQuestionColumn = columnName(questionCount);
  const bodyStart = 5;
  const bodyEnd = bodyStart + modelCount - 1;
  const averageRow = bodyEnd + 1;

  setTitle(sheet, reportId, layout.name, columnCount);
  const rows = [["模型", ...layout.questions, "平均分"]];
  layout.models.forEach((model, index) => {
    rows.push([model, ...layout.values[index], null]);
  });
  rows.push(["平均分", ...layout.column_averages, layout.overall_average]);
  writeTable(sheet, rows, [28, ...layout.questions.map(() => 18), 12]);

  if (modelCount > 0 && questionCount > 0) {
    setScoreFormat(
      sheet.getRange(`B${bodyStart}:${lastQuestionColumn}${bodyEnd}`),
      layout.values,
    );
    sheet.getRange(`${averageColumn}${bodyStart}:${averageColumn}${bodyEnd}`).formulas =
      layout.models.map((_, index) => {
        const row = bodyStart + index;
        return [`=IFERROR(ROUND(AVERAGE(B${row}:${lastQuestionColumn}${row}),2),"")`];
      });
    sheet.getRange(`B${averageRow}:${lastQuestionColumn}${averageRow}`).formulas = [[
      ...layout.questions.map((_, index) => {
        const column = columnName(index + 1);
        return `=IFERROR(ROUND(AVERAGE(${column}${bodyStart}:${column}${bodyEnd}),2),"")`;
      }),
    ]];
    sheet.getRange(`${averageColumn}${averageRow}`).formulas = [[
      `=IFERROR(ROUND(AVERAGE(B${bodyStart}:${lastQuestionColumn}${bodyEnd}),2),"")`,
    ]];
  }
  setAverageFormat(sheet.getRange(`${averageColumn}${bodyStart}:${averageColumn}${averageRow}`));
  setAverageFormat(sheet.getRange(`A${averageRow}:${averageColumn}${averageRow}`));
  sheet.getRange(`A${bodyStart}:A${bodyEnd}`).format.font = { bold: true, color: COLORS.text, size: 10 };
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(1);
  return { sheet, rowCount: averageRow, columnCount };
}

function renderDetail(workbook, reportId, layout) {
  const sheet = workbook.worksheets.add(layout.name);
  const modelCount = layout.models.length;
  const columnCount = modelCount + 3;
  const averageColumn = columnName(columnCount - 1);
  const firstModelColumn = "C";
  const lastModelColumn = columnName(modelCount + 1);
  const bodyStart = 5;
  const bodyEnd = bodyStart + layout.rows.length - 1;
  const averageRow = bodyEnd + 1;

  setTitle(sheet, reportId, layout.name, columnCount);
  const rows = [["检查项", "题目", ...layout.models, "平均分"]];
  layout.rows.forEach((row) => {
    rows.push([row.check_id, row.question, ...row.values, null]);
  });
  rows.push(["平均分", "", ...layout.model_averages, layout.overall_average]);
  writeTable(sheet, rows, [24, 31, ...layout.models.map(() => 18), 12]);

  if (layout.rows.length > 0 && modelCount > 0) {
    setScoreFormat(
      sheet.getRange(`${firstModelColumn}${bodyStart}:${lastModelColumn}${bodyEnd}`),
      layout.rows.map((row) => row.values),
    );
    sheet.getRange(`${averageColumn}${bodyStart}:${averageColumn}${bodyEnd}`).formulas =
      layout.rows.map((_, index) => {
        const row = bodyStart + index;
        return [`=IFERROR(ROUND(AVERAGE(${firstModelColumn}${row}:${lastModelColumn}${row}),2),"")`];
      });
    sheet.getRange(`${firstModelColumn}${averageRow}:${lastModelColumn}${averageRow}`).formulas = [[
      ...layout.models.map((_, index) => {
        const column = columnName(index + 2);
        return `=IFERROR(ROUND(AVERAGE(${column}${bodyStart}:${column}${bodyEnd}),2),"")`;
      }),
    ]];
    sheet.getRange(`${averageColumn}${averageRow}`).formulas = [[
      `=IFERROR(ROUND(AVERAGE(${firstModelColumn}${bodyStart}:${lastModelColumn}${bodyEnd}),2),"")`,
    ]];
  }
  setAverageFormat(sheet.getRange(`${averageColumn}${bodyStart}:${averageColumn}${averageRow}`));
  setAverageFormat(sheet.getRange(`A${averageRow}:${averageColumn}${averageRow}`));

  let groupIndex = -1;
  layout.rows.forEach((row, index) => {
    if (row.group_start) groupIndex += 1;
    const excelRow = bodyStart + index;
    sheet.getRange(`A${excelRow}`).format = {
      fill: groupIndex % 2 === 0 ? COLORS.groupA : COLORS.groupB,
      font: { bold: true, color: COLORS.text, size: 10 },
      verticalAlignment: "center",
    };
  });
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(2);
  return { sheet, rowCount: averageRow, columnCount };
}

const options = args(process.argv.slice(2));
const payload = JSON.parse(await fs.readFile(path.resolve(options.input), "utf8"));
const layouts = payload.workbook_sheets;
if (!Array.isArray(layouts) || layouts.length !== 9) {
  throw new Error("aggregation payload must contain exactly nine workbook_sheets");
}

logStage("loading artifact-tool");
const { Workbook, SpreadsheetFile } = await artifactTool();
logStage("creating workbook");
const workbook = Workbook.create();
const rendered = layouts.map((layout) => {
  logStage(`building sheet: ${layout.name}`);
  if (layout.kind === "ladder") return renderLadder(workbook, payload.report_id, layout);
  if (layout.kind === "detail") return renderDetail(workbook, payload.report_id, layout);
  throw new Error(`unsupported EI sheet kind: ${layout.kind}`);
});
logStage("inspecting workbook sheets");
await validateWorkbookSheets(workbook, layouts);

if (options.operation !== "preview") {
  logStage("exporting XLSX");
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.resolve(options.output));
}

if (options.operation !== "export") {
  await fs.mkdir(path.resolve(options["preview-dir"]), { recursive: true });
  for (let index = 0; index < layouts.length; index += 1) {
    const layout = layouts[index];
    const dimensions = rendered[index];
    const previewRows = Math.min(dimensions.rowCount, 30);
    const previewColumns = Math.min(dimensions.columnCount, 12);
    logStage(`rendering preview: ${layout.name}`);
    const preview = await workbook.render({
      sheetName: layout.name,
      range: `A1:${columnName(previewColumns - 1)}${previewRows}`,
      scale: 1,
      format: "png",
    });
    await fs.writeFile(
      path.join(path.resolve(options["preview-dir"]), `${layout.name}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
}
logStage("completed");
