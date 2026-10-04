const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  LevelFormat, PageOrientation,
} = require("docx");

// ---------------------------------------------------------------- helpers
const MONO = "Consolas";
const BODY = "Calibri";

const PAGE_W = 12240;          // US Letter, DXA
const MARGIN = 1080;           // 0.75"
const CONTENT_W = PAGE_W - 2 * MARGIN;

const GREY = "F2F2F2";
const HEADER_BG = "1F3864";
const CODE_BG = "F7F7F7";
const GOOD = "1E7A32";
const BAD = "B02418";

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.after === undefined ? 120 : opts.after, line: 276 },
    alignment: opts.align,
    children: [new TextRun({
      text,
      font: opts.font || BODY,
      size: opts.size || 21,          // half-points -> 10.5pt
      bold: opts.bold,
      italics: opts.italics,
      color: opts.color,
    })],
  });
}

function runsPara(runs, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.after === undefined ? 120 : opts.after, line: 276 },
    children: runs,
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
    children: [new TextRun({ text, font: BODY, size: 30, bold: true, color: HEADER_BG })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
    children: [new TextRun({ text, font: BODY, size: 24, bold: true, color: HEADER_BG })],
  });
}

// Code block: one Paragraph per line, shaded, monospace.
function code(lines, tint) {
  return lines.map((line, i) => new Paragraph({
    spacing: { after: i === lines.length - 1 ? 140 : 0, line: 240 },
    shading: { type: ShadingType.CLEAR, fill: tint || CODE_BG },
    indent: { left: 220, right: 220 },
    border: {
      left: { style: BorderStyle.SINGLE, size: 12, color: tint === "FDECEA" ? BAD : (tint === "E8F5EA" ? GOOD : "BFBFBF"), space: 6 },
    },
    children: [new TextRun({ text: line || " ", font: MONO, size: 18 })],
  }));
}

function rule() {
  return new Paragraph({
    spacing: { before: 60, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "C9C9C9", space: 1 } },
    children: [new TextRun({ text: "" })],
  });
}

function cell(children, width, opts = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: opts.valign,
    children,
  });
}

function table(widths, header, rows) {
  const headerRow = new TableRow({
    tableHeader: true,
    children: header.map((t, i) => cell(
      [new Paragraph({
        spacing: { after: 0 },
        children: [new TextRun({ text: t, font: BODY, size: 19, bold: true, color: "FFFFFF" })],
      })],
      widths[i], { fill: HEADER_BG })),
  });

  const bodyRows = rows.map((r, ri) => new TableRow({
    children: r.map((c, i) => cell(
      Array.isArray(c) ? c : [new Paragraph({
        spacing: { after: 0 },
        children: [new TextRun({
          text: String(c),
          font: (i > 0 && /^[\d.,+\-x%]+$/.test(String(c))) ? MONO : BODY,
          size: 19,
        })],
      })],
      widths[i], { fill: ri % 2 ? GREY : undefined })),
  }));

  return new Table({
    columnWidths: widths,
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    rows: [headerRow, ...bodyRows],
  });
}

// ---------------------------------------------------------------- content
const children = [];

// Title block
children.push(new Paragraph({
  spacing: { after: 60 },
  children: [new TextRun({ text: "PERSON A  —  DEMAND SIDE", font: BODY, size: 40, bold: true, color: HEADER_BG })],
}));
children.push(new Paragraph({
  spacing: { after: 40 },
  children: [new TextRun({
    text: "Dataset fixes for qaoa_dataset_pondicherry",
    font: BODY, size: 24, color: "444444",
  })],
}));
children.push(new Paragraph({
  spacing: { after: 260 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: HEADER_BG, space: 4 } },
  children: [new TextRun({
    text: "Project: QAOA for Joint Dark Store Location Selection and Inventory Allocation in Hyperlocal Quick Commerce",
    font: BODY, size: 19, italics: true, color: "666666",
  })],
}));

children.push(table(
  [2400, CONTENT_W - 2400],
  ["Field", "Value"],
  [
    ["Name", "_______________________________"],
    ["Script sections you own", "Section 2 (demand zones), Section 3 (products), Section 4 (zone x product demand)"],
    ["Number of fixes", "6  —  fixes 1, 5, 6, 8, 12, 13"],
    ["You need from others", "Nothing. You can start immediately."],
    ["You must hand over", "total_volume to Person B  ·  zone_speed to Person C"],
    ["Reference file", "person_a_demand.py"],
  ]
));

children.push(h1("Why your part comes first"));
children.push(p(
  "All 13 fixes sit in one script. If three people edit the same file at the same time, work gets lost. " +
  "So the script is split by section and each person owns different sections."));
children.push(p(
  "Your part has no dependencies, so you start on day one. But Person B cannot finish their most important " +
  "fix until you give them one number (total_volume), and Person C cannot fix the delivery times until you " +
  "give them the zone speeds. You are the blocker for both of them."));

children.push(h1("Your six fixes at a glance"));
children.push(table(
  [700, 3560, 2200, 2400],
  ["Fix", "What is wrong now", "Before", "After"],
  [
    ["1", "Demand is 10 times too small. Each order has a fraction of an item.", "0.10 - 0.25 items/order", "4.42 - 5.24 items/order"],
    ["5", "Product shares add to 1.18, not 1.00. Dairy is counted twice.", "1.18", "1.0000"],
    ["6", "unit_volume_liters exists but is never used anywhere.", "column unused", "14,422 L/day carried"],
    ["8", "Population density does not affect orders at all.", "corr = -0.105", "corr = +0.873"],
    ["12", "demand_std_dev does not match the Poisson demand it describes.", "15-35% of value", "sqrt(mean)"],
    ["13", "A stray +1 inflates every demand value.", "+20-30% too high", "removed"],
  ]
));

// ------------------------------------------------------------------ FIX 1
children.push(h1("Fix 1  —  Demand is 10 times too small"));
children.push(runsPara([
  new TextRun({ text: "Priority: ", font: BODY, size: 21, bold: true }),
  new TextRun({ text: "CRITICAL", font: BODY, size: 21, bold: true, color: BAD }),
  new TextRun({ text: "     Location: Section 4, the mean_demand line", font: BODY, size: 21, color: "666666" }),
]));
children.push(h2("What is wrong"));
children.push(p("There is an unexplained division by 10. Measured across all 20 zones:"));
children.push(table(
  [2200, 2600, 2200, 1860],
  ["zone_id", "avg_daily_orders", "total units", "items per order"],
  [
    ["Z01", "217", "33", "0.152"],
    ["Z02", "288", "43", "0.149"],
    ["Z03", "123", "21", "0.171"],
  ]
));
children.push(p(
  "Every order contains between 0.10 and 0.25 items. That is physically impossible — an order has at least " +
  "one item in it. A real quick-commerce basket holds 4 to 6 items. This means demand_zones.csv and " +
  "zone_sku_demand.csv describe two different worlds, so any cost calculated from them is meaningless.",
  { after: 180 }));
children.push(h2("Old code"));
children.push(...code([
  "mean_demand = max(1, zone_orders * share",
  "                  * np.random.uniform(0.8, 1.2) / 10)",
], "FDECEA"));
children.push(h2("New code"));
children.push(...code([
  "ITEMS_PER_ORDER = 5.0     # put this at the TOP of the file",
  "",
  "mean_units = orders * ITEMS_PER_ORDER * sku_share[sid]",
], "E8F5EA"));
children.push(h2("How to check"));
children.push(p("Items per order must come out between 4 and 6.", { after: 200 }));
children.push(rule());

// ------------------------------------------------------------------ FIX 5
children.push(h1("Fix 5  —  Product shares add to 1.18, not 1.00"));
children.push(runsPara([
  new TextRun({ text: "Priority: ", font: BODY, size: 21, bold: true }),
  new TextRun({ text: "SHOULD FIX", font: BODY, size: 21, bold: true, color: "B8860B" }),
  new TextRun({ text: "     Location: Section 4, the category_share dictionary", font: BODY, size: 21, color: "666666" }),
]));
children.push(h2("What is wrong"));
children.push(p(
  "The dictionary values add up to 1.00 across the seven categories. But Dairy contains TWO products — " +
  "SKU01 Fresh Milk and SKU03 Eggs — and the full 0.18 Dairy share is given to each of them separately."));
children.push(...code([
  "sum over categories : 1.00",
  "sum applied per-SKU : 1.18     <-- 18% too much demand",
]));
children.push(h2("New code"));
children.push(...code([
  "n_in_category = sku_df['category'].value_counts().to_dict()",
  "sku_share = {row[0]: CATEGORY_SHARE[row[2]] / n_in_category[row[2]]",
  "             for row in skus}",
  "",
  "# this line stops the bug ever coming back",
  "assert abs(sum(sku_share.values()) - 1.0) < 1e-9",
], "E8F5EA"));
children.push(p("Dairy becomes 0.09 for milk and 0.09 for eggs. Do not delete the assert line.", { after: 200 }));
children.push(rule());

// ------------------------------------------------------------------ FIX 6
children.push(h1("Fix 6  —  unit_volume_liters is never used"));
children.push(runsPara([
  new TextRun({ text: "Priority: ", font: BODY, size: 21, bold: true }),
  new TextRun({ text: "SHOULD FIX", font: BODY, size: 21, bold: true, color: "B8860B" }),
  new TextRun({ text: "     Location: Section 4, and it feeds Person B", font: BODY, size: 21, color: "666666" }),
]));
children.push(h2("What is wrong"));
children.push(p(
  "Product volumes range from 0.15 litres (potato chips) to 1.20 litres (bananas), but store capacity is " +
  "counted in flat units. So a packet of chips takes the same shelf space as a bottle of water. The column " +
  "sits in skus.csv doing nothing."));
children.push(h2("New code"));
children.push(...code([
  "volume_of = dict(zip(sku_df['sku_id'],",
  "                     sku_df['unit_volume_liters']))",
  "",
  "vol = round(units * volume_of[sid], 2)",
  "# add demand_volume_liters as a new column",
  "",
  "total_volume = demand_df['demand_volume_liters'].sum()",
], "E8F5EA"));
children.push(runsPara([
  new TextRun({ text: "total_volume is the number Person B needs. ", font: BODY, size: 21, bold: true }),
  new TextRun({ text: "Without it they cannot fix the capacity bug, which is the most important fix in the whole project.", font: BODY, size: 21 }),
], { after: 200 }));
children.push(rule());

// ------------------------------------------------------------------ FIX 8
children.push(h1("Fix 8  —  Population density does nothing"));
children.push(runsPara([
  new TextRun({ text: "Priority: ", font: BODY, size: 21, bold: true }),
  new TextRun({ text: "GOOD TO FIX", font: BODY, size: 21, bold: true, color: "666666" }),
  new TextRun({ text: "     Location: Section 2", font: BODY, size: 21, color: "666666" }),
]));
children.push(h2("What is wrong"));
children.push(p(
  "Density and orders are drawn as two separate random numbers, so density never affects anything. " +
  "The measured correlation is -0.105 — essentially zero, and slightly negative, meaning denser zones " +
  "order very slightly less. A reviewer will notice this."));
children.push(h2("New code"));
children.push(...code([
  "ORDERS_PER_DENSITY   = 1 / 60.0",
  "ZONE_TYPE_ORDER_MULT = {'commercial': 1.30,",
  "                        'mixed': 1.00,",
  "                        'residential': 0.85}",
  "",
  "orders = int(round(density * ORDERS_PER_DENSITY",
  "                   * ZONE_TYPE_ORDER_MULT[ztype]",
  "                   * RNG.uniform(0.90, 1.10)))",
], "E8F5EA"));
children.push(p("Correlation must come out above 0.8.", { after: 200 }));
children.push(rule());

// ----------------------------------------------------------------- FIX 12
children.push(h1("Fix 12  —  demand_std_dev contradicts the demand"));
children.push(runsPara([
  new TextRun({ text: "Priority: ", font: BODY, size: 21, bold: true }),
  new TextRun({ text: "GOOD TO FIX", font: BODY, size: 21, bold: true, color: "666666" }),
  new TextRun({ text: "     Location: Section 4", font: BODY, size: 21, color: "666666" }),
]));
children.push(h2("What is wrong"));
children.push(p(
  "Demand is generated from a Poisson distribution, whose standard deviation is the square root of the mean. " +
  "But the std column is set to an unrelated 15-35% of the value. For a mean of 4, the true Poisson std is " +
  "2.0 while the file says about 1.0. The mean and the std describe different distributions, so any " +
  "stochastic or robust optimisation built on them would be wrong."));
children.push(h2("Old code"));
children.push(...code([
  "demand_std = round(avg_daily_demand",
  "                   * np.random.uniform(0.15, 0.35), 2)",
], "FDECEA"));
children.push(h2("New code"));
children.push(...code([
  "std_dev = round(math.sqrt(mean_units), 2)",
], "E8F5EA"));
children.push(rule());

// ----------------------------------------------------------------- FIX 13
children.push(h1("Fix 13  —  The +1 inflates every demand value"));
children.push(runsPara([
  new TextRun({ text: "Priority: ", font: BODY, size: 21, bold: true }),
  new TextRun({ text: "GOOD TO FIX", font: BODY, size: 21, bold: true, color: "666666" }),
  new TextRun({ text: "     Location: Section 4", font: BODY, size: 21, color: "666666" }),
]));
children.push(h2("What is wrong"));
children.push(p(
  "Adding 1 shifts the whole distribution, so the real mean becomes mean + 1 rather than mean. " +
  "With means around 3 to 5, that is a 20-30% inflation stacked on top of every other error."));
children.push(h2("Old code"));
children.push(...code([
  "avg_daily_demand = int(np.random.poisson(mean_demand) + 1)",
], "FDECEA"));
children.push(h2("New code"));
children.push(...code([
  "units = max(1, int(RNG.poisson(mean_units)))",
], "E8F5EA"));
children.push(p("max(1, ...) keeps demand positive without shifting the distribution.", { after: 200 }));
children.push(rule());

// ------------------------------------------------------- EXTRA: zone speed
children.push(h1("Small extra job  —  one road speed per zone"));
children.push(p(
  "This is two lines, but Person C cannot do their fix 9 without it. In the old script a fresh random speed " +
  "was drawn inside Person C's double loop, once for all 200 site-zone pairs. That made delivery time stop " +
  "depending properly on distance — two places the same distance away got different times."));
children.push(...code([
  "AVG_SPEED_KMPH = {'commercial': 18,",
  "                  'residential': 24,",
  "                  'mixed': 21}",
  "",
  "zone_speed[zid] = AVG_SPEED_KMPH[ztype] * RNG.uniform(0.92, 1.08)",
  "",
  "# save it as a column so Person C just reads the CSV",
  "# new column name: avg_road_speed_kmph",
], "E8F5EA"));
children.push(p("Person C must NOT draw their own speeds. That is what caused the bug.", { after: 220 }));

// ------------------------------------------------------------ verification
children.push(h1("Verification — this is the output you must produce"));
children.push(p(
  "Run person_a_demand.py. All six checks must say PASS before you hand anything over. " +
  "This is the real output from the corrected code:", { after: 160 }));
children.push(table(
  [900, 3560, 2200, 2200],
  ["Fix", "Check", "Result", "Was"],
  [
    ["1", "items per order is 4 to 6", "4.42 - 5.24", "0.10 - 0.25"],
    ["5", "product shares sum to 1.0", "1.0000", "1.18"],
    ["6", "demand_volume_liters exists", "14,422 L/day", "missing"],
    ["8", "density/orders correlation > 0.8", "0.873", "-0.105"],
    ["12", "std equals sqrt(mean)", "consistent", "unrelated"],
    ["13", "no +1 shift", "smallest 41 units", "inflated"],
  ]
));

children.push(h2("Files you produce"));
children.push(...code([
  "demand_zones.csv       (new column: avg_road_speed_kmph)",
  "skus.csv               (new column: demand_share)",
  "zone_sku_demand.csv    (new column: demand_volume_liters)",
]));

children.push(h2("Numbers you hand over"));
children.push(table(
  [2200, 2400, CONTENT_W - 4600],
  ["To whom", "What", "Why they need it"],
  [
    ["Person B", "total_volume = 14,421.7 L/day", "To size store capacity. Their fix 2 is the single most important fix in the project and it is blocked until you send this."],
    ["Person C", "avg_road_speed_kmph column", "To calculate delivery times. It is already in demand_zones.csv, so they just read the file."],
  ]
));

// ---------------------------------------------------------------- checklist
children.push(h1("Your checklist"));
const checklist = [
  "Items per order is between 4 and 6",
  "Product shares add to exactly 1.0 and the assert line is present",
  "zone_sku_demand.csv has a demand_volume_liters column",
  "Density and orders correlation is above 0.8",
  "demand_std_dev equals sqrt(mean)",
  "No +1 anywhere in the demand line",
  "demand_zones.csv has an avg_road_speed_kmph column",
  "Sent total_volume to Person B",
  "Sent the zone speeds to Person C",
];
checklist.forEach((t) => {
  children.push(runsPara([
    new TextRun({ text: "[    ]     ", font: MONO, size: 21 }),
    new TextRun({ text: t, font: BODY, size: 21 }),
  ], { after: 90 }));
});

children.push(new Paragraph({
  spacing: { before: 320 },
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: "C9C9C9", space: 6 } },
  children: [new TextRun({
    text: "Full details for all 13 fixes: PONDICHERRY_DATASET_FIXES.txt   ·   Team split: PONDICHERRY_FIXES_BY_PERSON.txt   ·   Working code: person_a_demand.py",
    font: BODY, size: 17, color: "777777", italics: true,
  })],
}));

// ---------------------------------------------------------------- document
const doc = new Document({
  numbering: { config: [] },
  styles: {
    default: { document: { run: { font: BODY, size: 21 } } },
  },
  sections: [{
    properties: {
      page: {
        size: { width: PAGE_W, height: 15840, orientation: PageOrientation.PORTRAIT },
        margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("Person_A_Dataset_Fixes.docx", buf);
  console.log("wrote Person_A_Dataset_Fixes.docx", buf.length, "bytes");
});
