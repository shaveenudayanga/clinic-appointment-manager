import { expect, test, type Page } from "@playwright/test";

// The seed puts appointments on "the next clinic day" after the default day,
// so every flow starts there: all its times are in the future whatever the
// date and time the tests run.
//
// Set SCREENSHOTS=1 to also save screenshots for the README (make screenshots).

const SILVA = "Dr Anika Silva (Cardiology, Provider No. 000101AA)";
const saveScreenshots = !!process.env.SCREENSHOTS;

async function openNextClinicDay(page: Page, { screenshotFirstDay = false } = {}) {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: /Book with/ }).first()).toBeVisible();
  // The default day has the most demo data, including the same-name practitioners and patients.
  if (screenshotFirstDay) await page.screenshot({ path: "../docs/screenshots/appointment-book.png" });
  const firstDay = await page.getByRole("heading", { level: 1 }).textContent();
  await page.getByRole("button", { name: "Next day ›" }).click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(firstDay!);
  await expect(page.getByRole("button", { name: /Book with/ }).first()).toBeVisible();
}

async function choosePatient(page: Page, search: string, label: string) {
  const box = page.getByRole("combobox", { name: "Search patient" });
  await box.fill(search);
  await expect(page.getByRole("option", { name: label })).toBeVisible();
  await box.press("Enter");
  await expect(page.getByText(label)).toBeVisible();
}

const bookButton = (page: Page) => page.getByRole("button", { name: "Book appointment", exact: true }).last();

test("book an appointment from a free slot", async ({ page }) => {
  await openNextClinicDay(page, { screenshotFirstDay: saveScreenshots });

  await page.getByRole("button", { name: `Book with ${SILVA} at 09:00` }).click();
  await expect(page.getByRole("heading", { name: "Book appointment" })).toBeVisible();
  await expect(page.getByLabel("Practitioner", { exact: true })).toHaveValue(/\d+/);
  await expect(page.getByLabel("Start")).toHaveValue("09:00");
  // The date picker's own format follows the browser; the date is also shown in words.
  await expect(page.getByLabel("Date", { exact: true })).toHaveAccessibleDescription(/^(Mon|Tue|Wed|Thu|Fri) \d{1,2} [A-Z][a-z]{2} \d{4}$/);

  await choosePatient(page, "000125", "Liam O'Connor (MRN 000125, DOB 27 Jan 1992)");
  await expect(page.getByText("Ends 09:30")).toBeVisible();
  if (saveScreenshots) await page.screenshot({ path: "../docs/screenshots/booking-panel.png" });

  await bookButton(page).click();
  await expect(page.getByText("Appointment booked.")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "09:00 to 09:30, Liam O'Connor (MRN 000125, DOB 27 Jan 1992), Booked" }),
  ).toBeVisible();
});

test("a clash shows its error under the practitioner field", async ({ page }) => {
  await openNextClinicDay(page);

  // Dr Silva (000101AA) has 11:00-11:30 booked on this day; 10:45 for 30 minutes runs into it.
  await page.getByRole("button", { name: `Book with ${SILVA} at 10:45` }).click();
  await choosePatient(page, "000132", "Isla Robinson (MRN 000132, DOB 16 Aug 1996)");
  await page.getByLabel("Notes").fill("Kept after the error");
  await bookButton(page).click();

  const message = /^Dr Anika Silva \(Cardiology, Provider No\. 000101AA\) already has an appointment from .* 11:00 to 11:30\.$/;
  await expect(page.getByLabel("Practitioner", { exact: true })).toHaveAccessibleDescription(message);
  await expect(page.getByLabel("Start")).not.toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("Notes")).toHaveValue("Kept after the error");
  if (saveScreenshots) await page.screenshot({ path: "../docs/screenshots/clash-error.png" });
});

test("cancel an appointment, then see it with Show cancelled", async ({ page }) => {
  await openNextClinicDay(page);
  const booked = "09:00 to 09:20, Grace Nguyen (MRN 000128, DOB 14 Feb 1958), Booked";
  const cancelled = "09:00 to 09:20, Grace Nguyen (MRN 000128, DOB 14 Feb 1958), Cancelled";
  await expect(page.getByLabel("Show cancelled (0)")).not.toBeChecked();

  await page.getByRole("button", { name: booked }).click();
  await page.getByRole("button", { name: "Cancel appointment" }).click();
  await page.getByRole("button", { name: "Yes, cancel appointment" }).click();
  await expect(page.getByText("Appointment cancelled.")).toBeVisible();

  // Hidden by default: a cancelled slot is free time.
  await expect(page.getByRole("button", { name: cancelled })).toHaveCount(0);
  await page.getByLabel("Show cancelled (1)").check();
  await expect(page.getByRole("button", { name: cancelled })).toBeVisible();
});
