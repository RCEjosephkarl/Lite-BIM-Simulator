/** Small CSV reader for custom truss text, including headers/quotes/CRLF. */
export function writeCsv(rows: unknown[][]): string {
  return rows.map(row => row.map(value => `"${String(value).replace(/"/g, '""')}"`).join(",")).join("\n");
}
export function csvRows(raw: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = "", quoted = false, closed = false;
  const finishCell = () => { row.push(cell.trim()); cell = ""; closed = false; };
  const finishRow = () => { finishCell(); if (row.some(Boolean)) rows.push(row); row = []; };
  for (let index = 0; index < raw.length; index++) {
    const char = raw[index];
    if (quoted) {
      if (char === '"') {
        if (raw[index + 1] === '"') { cell += '"'; index++; }
        else { quoted = false; closed = true; }
      } else cell += char;
    } else if (char === '"' && !cell.trim() && !closed) quoted = true;
    else if (char === ',') finishCell();
    else if (char === '\n' || char === '\r') {
      finishRow(); if (char === '\r' && raw[index + 1] === '\n') index++;
    } else if (closed && char.trim()) throw new Error("Unexpected text after a quoted CSV field.");
    else cell += char;
  }
  if (quoted) throw new Error("Custom CSV contains an unclosed quoted field.");
  finishRow();
  return rows;
}

export function customRows(raw: string, header: string[]): string[][] {
  const rows = csvRows(raw);
  if (rows[0]?.map(cell => cell.toLowerCase()).join(",") === header.join(",")) rows.shift();
  for (const [index, row] of rows.entries()) {
    if (row.length !== header.length || row.some(cell => !cell))
      throw new Error(`Custom CSV row ${index + 1} requires ${header.join(", ")}.`);
  }
  return rows;
}
