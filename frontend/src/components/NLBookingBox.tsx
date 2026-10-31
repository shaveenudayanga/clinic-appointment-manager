"use client";

import { useState } from "react";
import { api, ApiError, type NLBookingResult } from "@/lib/api";
import { longDate } from "@/lib/time";
import { FieldError } from "./PatientPicker";

type Props = { onResult: (result: NLBookingResult) => void };

/** Type a booking in plain words; the backend suggests form values. Nothing is
 *  saved here: the user checks the form and presses "Book appointment". */
export default function NLBookingBox({ onResult }: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const submit = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.parseBooking(text.trim());
      onResult(result);
      setNotice(summary(result));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please fill in the form yourself.");
    } finally {
      setBusy(false); // the typed sentence is kept either way
    }
  };

  return (
    <form
      className="space-y-2 border-b border-line px-4 py-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="nl-text" className="block font-medium">
        Describe the booking <span className="font-normal text-muted">(optional)</span>
      </label>
      <textarea
        id="nl-text"
        className="field"
        rows={2}
        maxLength={300}
        value={text}
        placeholder="e.g. Book Mr Perera with Dr Silva next Tuesday at 3pm for 30 minutes"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        aria-describedby={error ? "nl-error" : notice ? "nl-notice" : undefined}
      />
      <button type="submit" className="btn" disabled={busy || !text.trim()}>
        {busy ? "Reading…" : "Fill in form"}
      </button>
      {error && <FieldError id="nl-error" message={error} />}
      {notice && (
        <p id="nl-notice" className="text-accent" role="status">
          {notice}
        </p>
      )}
    </form>
  );
}

function summary(r: NLBookingResult): string {
  const when = [r.date ? longDate(r.date) : null, r.start ? `at ${r.start}` : null].filter(Boolean).join(" ");
  const toChoose = [r.practitioner, r.patient].some((m) => m && m.matches.length !== 1);
  return (
    `Filled in from your sentence${when ? `: ${when}` : ""}. ` +
    (toChoose ? "Some names need your choice below. " : "") +
    "Check every field, then book."
  );
}
