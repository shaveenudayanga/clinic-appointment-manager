// Display helpers. Times arrive from the backend already in Sydney time
// (e.g. "2026-11-03T15:00:00+11:00"), so the browser never converts zones;
// it only reads the date and HH:MM parts and does minute arithmetic. The
// current Sydney time also comes from the backend (GET /api/clinic).

export const dateOf = (local: string) => local.slice(0, 10);
export const timeOf = (local: string) => local.slice(11, 16);

export function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

export function fromMinutes(total: number): string {
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** Every 15-minute start time from `opens` up to (not including) `closes`. */
export function quarterHours(opens: string, closes: string): string[] {
  const times: string[] = [];
  for (let t = toMinutes(opens); t < toMinutes(closes); t += 15) times.push(fromMinutes(t));
  return times;
}

function dateParts(isoDate: string, options: Intl.DateTimeFormatOptions) {
  const [y, m, d] = isoDate.split("-").map(Number);
  // A calendar date with no time zone: format it in UTC so it never shifts.
  const parts = new Intl.DateTimeFormat("en-AU", { ...options, timeZone: "UTC" }).formatToParts(
    new Date(Date.UTC(y, m - 1, d)),
  );
  return Object.fromEntries(parts.map((p) => [p.type, p.value]));
}

/** "Monday 2 November 2026" */
export function longDate(isoDate: string): string {
  const p = dateParts(isoDate, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return `${p.weekday} ${p.day} ${p.month} ${p.year}`;
}

/** "Mon 2 Nov" */
export function shortDate(isoDate: string): string {
  const p = dateParts(isoDate, { weekday: "short", day: "numeric", month: "short" });
  return `${p.weekday} ${p.day} ${p.month}`;
}
