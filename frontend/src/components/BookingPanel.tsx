"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Appointment, type ClinicInfo, type Patient, type Practitioner } from "@/lib/api";
import { dateOf, fromMinutes, quarterHours, shortDate, timeOf, toMinutes } from "@/lib/time";
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
          setErrors((e) => ({ ...e, patient: undefined }));
          setRegistering(null);
        }}
      />
    );
  }

  const startTimes = quarterHours(clinic.opens, clinic.closes);
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
          <label className="block">
            <span className="mb-1 block font-medium">Practitioner</span>
            <select
              className="field"
              value={practitionerId}
              autoFocus={!existing && practitionerId === ""}
              onChange={(e) => setPractitionerId(e.target.value ? Number(e.target.value) : "")}
              aria-invalid={!!errors.practitioner}
            >
              <option value="">Choose a practitioner</option>
              {practitioners.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
            {errors.practitioner && <FieldError message={errors.practitioner} />}
          </label>

          <div>
            <span className="mb-1 block font-medium">Patient</span>
            <PatientPicker
              selected={patient}
              onSelect={setPatient}
              onRegisterNew={setRegistering}
              error={errors.patient}
              autoFocus={!existing && practitionerId !== ""}
              disabled={!editable}
            />
          </div>

          <label className="block">
            <span className="mb-1 block font-medium">Date</span>
            <input
              type="date"
              className="field w-44"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              aria-invalid={!!errors.start}
            />
          </label>

          <div>
            <div className="flex items-end gap-3">
              <label>
                <span className="mb-1 block font-medium">Start</span>
                <select
                  className="field w-auto"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                  aria-invalid={!!errors.start}
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
            {errors.start && <FieldError message={errors.start} />}
            {errors.length && <FieldError message={errors.length} />}
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
          {errors.outcome && <FieldError message={errors.outcome} />}
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
