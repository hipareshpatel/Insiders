// Sort key for Indian fiscal period labels (FY runs April–March), mirroring
// pipeline/src/bse_intel/periods.py: "Q2FY27" -> 2026-09-30, "FY26" -> 2026-03-31.
const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function fyEnd(token: string): number {
  const year = Number(token);
  return year < 100 ? 2000 + year : year;
}

export function periodEnd(label: string): string {
  const s = label.toUpperCase().replace(/\s+/g, "");
  let m = s.match(/^Q([1-4])FY'?(\d{2,4})$/);
  if (m) {
    const end = fyEnd(m[2]);
    return [`${end - 1}-06-30`, `${end - 1}-09-30`, `${end - 1}-12-31`, `${end}-03-31`][Number(m[1]) - 1];
  }
  if ((m = s.match(/^9MFY'?(\d{2,4})$/))) return `${fyEnd(m[1]) - 1}-12-31`;
  if ((m = s.match(/^H([12])FY'?(\d{2,4})$/))) return m[1] === "1" ? `${fyEnd(m[2]) - 1}-09-30` : `${fyEnd(m[2])}-03-31`;
  if ((m = s.match(/^FY'?(\d{2,4})$/))) return `${fyEnd(m[1])}-03-31`;
  // a year that does not end in March ("YE:2025-12": VBL, ABB, Siemens), to the last day of its month
  if ((m = s.match(/^YE:(\d{4})-(\d{2})$/))) {
    const y = Number(m[1]), mo = Number(m[2]);
    return `${m[1]}-${m[2]}-${String(new Date(Date.UTC(y, mo, 0)).getUTCDate()).padStart(2, "0")}`;
  }
  if ((m = s.match(/^([A-Z]{3})-?(20\d{2})$/))) {
    const month = MONTHS.indexOf(m[1]);
    if (month >= 0) return `${m[2]}-${String(month + 1).padStart(2, "0")}-28`;
  }
  return s;
}

export function periodKind(label: string): string {
  const s = label.toUpperCase();
  if (s.startsWith("9M")) return "9M";
  if (s.startsWith("Q")) return "Quarter";
  if (s.startsWith("H")) return "Half-year";
  if (s.startsWith("FY")) return "Year";
  return "Month";
}
