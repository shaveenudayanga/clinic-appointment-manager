"use client";

import { useEffect, useId, useRef, useState } from "react";
import {
  api,
  ApiError,
  type Appointment,
  type ClinicInfo,
  type NLBookingResult,
  type Patient,
  type Practitioner,
} from "@/lib/api";
import { dateOf, dayDate, fromMinutes, quarterHours, shortDate, timeOf, toMinutes } from "@/lib/time";
import NLBookingBox from "./NLBookingBox";
import PatientPicker, { FieldError } from "./PatientPicker";
import RegisterPatient from "./RegisterPatient";
import { STATUS_BADGE, STATUS_LABEL } from "./status";

const LENGTHS = [15, 30, 45, 60, 90, 120];

export type PanelTarget =
  | { kind: "new"; date: string; practitionerId?: number; start?: string }
  | { kind: "existing"; appointment: Appointment; message?: string };

type FormField = "practitioner" | "patient" | "start" | "length" | "outcome";

// Which form field each backend error field belongs to.
const FIELD_FOR: Record<string, FormField> = {
  practitioner_id: "practitioner",
  patient_id: "patient",
  start: "start",
  end: "length",
  status: "outcome",
};

type Props = {
  target: PanelTarget;
  clinic: ClinicInfo;
  practitioners: Practitioner[];
  onClose: () => void;
  onSaved: (appointment: Appointment, message: string) => void;
};

export default function BookingPanel({ target, clinic, practitioners, onClose, onSaved }: Props) {
  const existing = target.kind === "existing" ? target.appointment : null;
  const editable = existing ? existing.allowed_actions.includes("edit") : true;

  const [practitionerId, setPractitionerId] = useState<number | "">(
    existing?.practitioner.id ?? (target.kind === "new" ? (target.practitionerId ?? "") : ""),
  );
  const [patient, setPatient] = useState<Patient | null>(existing?.patient ?? null);
  const [date, setDate] = useState(existing ? dateOf(existing.start_local) : target.kind === "new" ? target.date : "");
  const [start, setStart] = useState(
    existing ? timeOf(existing.start_local) : target.kind === "new" ? (target.start ?? "") : "",
  );
  const [length, setLength] = useState(
    existing ? toMinutes(timeOf(existing.end_local)) - toMinutes(timeOf(existing.start_local)) : 30,
  );
  const [notes, setNotes] = useState(existing?.notes ?? "");

  const [errors, setErrors] = useState<Partial<Record<FormField, string>>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [registering, setRegistering] = useState<string | null>(null); // search text, while registering
  // Names from a typed sentence that matched several records, or none. The user must choose.
  const [practitionerChoice, setPractitionerChoice] = useState<NLBookingResult["practitioner"]>(null);
  const [patientChoice, setPatientChoice] = useState<NLBookingResult["patient"]>(null);

  const id = useId();
  const errorId = (field: FormField) => (errors[field] ? `${id}-${field}-error` : undefined);
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (existing) headingRef.current?.focus();
  }, [existing]);

  const showError = (e: unknown) => {
    const err = e instanceof ApiError ? e : new ApiError(String(e), 0);
    const field = err.field ? FIELD_FOR[err.field] : undefined;
    if (field) setErrors({ [field]: err.message });
    else setGeneralError(err.message);
  };

  const run = async (action: () => Promise<Appointment>, message: string) => {
    setSaving(true);
    setErrors({});
    setGeneralError(null);
    try {
      onSaved(await action(), message);
    } catch (e) {
      showError(e);
    } finally {
      setSaving(false);
    }
  };

  /** Fill the form from a parsed sentence. A name is only filled in when it
   *  matches exactly one record; otherwise the user chooses. */
  const applySentence = (r: NLBookingResult) => {
    setErrors({});
    setGeneralError(null);
    if (r.practitioner) {
      const only = r.practitioner.matches.length === 1 ? r.practitioner.matches[0] : null;
      setPractitionerId(only ? only.id : "");
      setPractitionerChoice(only ? null : r.practitioner);
    }
    if (r.patient) {
      const only = r.patient.matches.length === 1 ? r.patient.matches[0] : null;
      setPatient(only);
      setPatientChoice(only ? null : r.patient);
    }
    if (r.date) setDate(r.date);
    if (r.start) setStart(r.start);
    if (r.duration_minutes) setLength(r.duration_minutes);
    if (r.notes) setNotes(r.notes);
  };

  const submit = () => {
    const missing: Partial<Record<FormField, string>> = {};
    if (practitionerId === "") missing.practitioner = "Choose a practitioner.";
    if (!patient) missing.patient = "Choose a patient.";
    if (!date || !start) missing.start = "Choose a date and start time.";
    if (Object.keys(missing).length) {
      setErrors(missing);
      setGeneralError(null);
      return;
    }
    const data = {
      practitioner_id: practitionerId as number,
      patient_id: patient!.id,
      start: `${date}T${start}`,
      end: `${date}T${fromMinutes(toMinutes(start) + length)}`,
      notes,
    };
    if (existing) run(() => api.updateAppointment(existing.id, data), "Changes saved.");
    else run(() => api.createAppointment(data), "Appointment booked.");
  };

  if (registering !== null) {
    const looksLikeName = /[a-z]/i.test(registering) && !/\d/.test(registering);
    return (
      <RegisterPatient
        initialName={looksLikeName ? registering : ""}
        onBack={() => setRegistering(null)}
        onDone={(p) => {
          setPatient(p);
          setPatientChoice(null);
          setErrors((e) => ({ ...e, patient: undefined }));
          setRegistering(null);
        }}
      />
    );
  }

  const quarterStarts = quarterHours(clinic.opens, clinic.closes);
  // A typed sentence may give a time that is not on the list; show it so the backend can judge it.
  const startTimes = start && !quarterStarts.includes(start) ? [...quarterStarts, start].sort() : quarterStarts;
  const lengths = LENGTHS.includes(length) ? LENGTHS : [...LENGTHS, length].sort((a, b) => a - b);
  const ends = start ? fromMinutes(toMinutes(start) + length) : null;
  const canComplete = existing?.allowed_actions.includes("complete");
  const canNoShow = existing?.allowed_actions.includes("no_show");
  const canCancel = existing?.allowed_actions.includes("cancel");

  return (
    <section aria-labelledby="panel-heading">
      <div className="flex items-start justify-between gap-2 border-b border-line px-4 py-3">
        <div>
          <h2 id="panel-heading" ref={headingRef} tabIndex={-1} className="text-base font-semibold">
            {existing ? "Appointment" : "Book appointment"}
          </h2>
          {existing && (
            <div className="mt-1 flex items-center gap-2">
              <span className={`border px-1.5 text-xs font-semibold ${STATUS_BADGE[existing.status]}`}>
                {STATUS_LABEL[existing.status]}
              </span>
              <span className="text-muted">
                {shortDate(dateOf(existing.start_local))}, {timeOf(existing.start_local)}–{timeOf(existing.end_local)}
              </span>
            </div>
          )}
        </div>
        <button type="button" className="btn" onClick={onClose}>
          Close
        </button>
      </div>

      {target.kind === "existing" && target.message && (
        <p className="border-b border-line bg-accent-soft px-4 py-2 font-medium text-accent" role="status">
          {target.message}
        </p>
      )}

      {!existing && clinic.nl_booking && <NLBookingBox onResult={applySentence} />}

      {existing?.status === "cancelled" && (
        <p className="border-b border-line px-4 py-2 text-muted">
          This appointment was cancelled. To book again, choose a free time in the book.
        </p>
      )}

      <form
        className="space-y-4 px-4 py-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <fieldset disabled={!editable || saving} className="space-y-4">
          <div>
            <label htmlFor={`${id}-practitioner`} className="mb-1 block font-medium">
              Practitioner
            </label>
            <select
              id={`${id}-practitioner`}
              className="field"
              value={practitionerId}
              autoFocus={!existing && practitionerId === ""}
              onChange={(e) => setPractitionerId(e.target.value ? Number(e.target.value) : "")}
              aria-invalid={!!errors.practitioner}
              aria-describedby={errorId("practitioner")}
            >
              <option value="">Choose a practitioner</option>
              {practitioners.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
            {practitionerChoice && (
              <NameChoice
                kind="practitioner"
                query={practitionerChoice.query}
                options={practitionerChoice.matches}
                onChoose={(p) => {
                  setPractitionerId(p.id);
                  setPractitionerChoice(null);
                }}
              />
            )}
            {errors.practitioner && <FieldError id={errorId("practitioner")} message={errors.practitioner} />}
          </div>

          <div>
            <span className="mb-1 block font-medium">Patient</span>
            {patientChoice && (
              <NameChoice
                kind="patient"
                query={patientChoice.query}
                options={patientChoice.matches}
                onChoose={(p) => {
                  setPatient(p);
                  setPatientChoice(null);
                }}
                onRegister={() => setRegistering(withoutTitle(patientChoice.query))}
              />
            )}
            <PatientPicker
              selected={patient}
              onSelect={(p) => {
                setPatient(p);
                if (p) setPatientChoice(null);
              }}
              onRegisterNew={setRegistering}
              error={errors.patient}
              autoFocus={!existing && practitionerId !== ""}
              disabled={!editable}
            />
          </div>

          <div>
            <label htmlFor={`${id}-date`} className="mb-1 block font-medium">
              Date
            </label>
            <div className="flex items-center gap-3">
              <input
                id={`${id}-date`}
                type="date"
                className="field w-44"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                aria-invalid={!!errors.start}
                aria-describedby={[date ? `${id}-date-words` : "", errorId("start") ?? ""].join(" ").trim() || undefined}
              />
              {date && (
                <span id={`${id}-date-words`} className="font-medium">
                  {dayDate(date)}
                </span>
              )}
            </div>
          </div>

          <div>
            <div className="flex items-end gap-3">
              <label>
                <span className="mb-1 block font-medium">Start</span>
                <select
                  className="field w-auto"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                  aria-invalid={!!errors.start}
                  aria-describedby={errorId("start")}
                >
                  <option value="">--:--</option>
                  {startTimes.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="mb-1 block font-medium">Length</span>
                <select
                  className="field w-auto"
                  value={length}
                  onChange={(e) => setLength(Number(e.target.value))}
                  aria-invalid={!!errors.length}
                  aria-describedby={errorId("length")}
                >
                  {lengths.map((m) => (
                    <option key={m} value={m}>
                      {m} min{LENGTHS.includes(m) ? "" : " (current)"}
                    </option>
                  ))}
                </select>
              </label>
              <span className="pb-1.5 text-muted">{ends ? `Ends ${ends}` : ""}</span>
            </div>
            {errors.start && <FieldError id={errorId("start")} message={errors.start} />}
            {errors.length && <FieldError id={errorId("length")} message={errors.length} />}
          </div>

          <label className="block">
            <span className="mb-1 block font-medium">Notes</span>
            <textarea
              className="field"
              rows={3}
              maxLength={500}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
        </fieldset>

        {generalError && <FieldError message={generalError} />}

        {editable && (
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? (existing ? "Saving…" : "Booking…") : existing ? "Save changes" : "Book appointment"}
          </button>
        )}
      </form>

      {existing && (canComplete || canNoShow) && (
        <div className="border-t border-line px-4 py-3">
          <h3 className="mb-2 font-medium">Record outcome</h3>
          <div className="flex gap-2">
            {canComplete && (
              <button
                type="button"
                className="btn"
                disabled={saving}
                onClick={() => run(() => api.updateAppointment(existing.id, { status: "completed" }), "Marked as completed.")}
              >
                Mark completed
              </button>
            )}
            {canNoShow && (
              <button
                type="button"
                className="btn"
                disabled={saving}
                onClick={() => run(() => api.updateAppointment(existing.id, { status: "no_show" }), "Marked as no-show.")}
              >
                Mark no-show
              </button>
            )}
          </div>
          {errors.outcome && <FieldError id={errorId("outcome")} message={errors.outcome} />}
        </div>
      )}

      {existing && canCancel && (
        <div className="border-t border-line px-4 py-3">
          {confirmingCancel ? (
            <div className="space-y-3">
              <p>
                Cancel the appointment for {existing.patient.full_name} (MRN {existing.patient.mrn}) on{" "}
                {shortDate(dateOf(existing.start_local))} at {timeOf(existing.start_local)}? The record is kept and the
                time becomes free for other bookings.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn btn-danger-solid"
                  disabled={saving}
                  onClick={() => run(() => api.cancelAppointment(existing.id), "Appointment cancelled.")}
                >
                  {saving ? "Cancelling…" : "Yes, cancel appointment"}
                </button>
                <button type="button" className="btn" autoFocus onClick={() => setConfirmingCancel(false)}>
                  Keep appointment
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className="btn btn-danger" onClick={() => setConfirmingCancel(true)}>
              Cancel appointment
            </button>
          )}
        </div>
      )}
    </section>
  );
}

/** Shown when a name from a typed sentence matched several records, or none. Never picks one. */
function NameChoice<T extends { id: number; label: string }>({
  kind,
  query,
  options,
  onChoose,
  onRegister,
}: {
  kind: "practitioner" | "patient";
  query: string;
  options: T[];
  onChoose: (option: T) => void;
  onRegister?: () => void;
}) {
  if (options.length === 0) {
    return (
      <div className="mt-1 border border-noshow bg-noshow-bg px-2 py-1.5 text-noshow-ink" role="status">
        No {kind} matches &ldquo;{query}&rdquo;.{" "}
        {kind === "patient" && onRegister ? (
          <button type="button" className="btn mt-1 block" onClick={onRegister}>
            Register new patient
          </button>
        ) : (
          "Choose one from the list."
        )}
      </div>
    );
  }
  return (
    <div className="mt-1 border border-noshow bg-noshow-bg px-2 py-1.5 text-noshow-ink" role="group" aria-label={`Choose ${kind}`}>
      <p className="mb-1">
        {options.length} {kind}s match &ldquo;{query}&rdquo;. Choose one:
      </p>
      <ul className="space-y-1">
        {options.map((option) => (
          <li key={option.id}>
            <button type="button" className="btn w-full text-left text-ink" onClick={() => onChoose(option)}>
              {option.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

const TITLES = /^(dr|doctor|mr|mrs|ms|miss|mx|prof|professor)\.?\s+/i;
const withoutTitle = (name: string) => name.trim().replace(TITLES, "");
