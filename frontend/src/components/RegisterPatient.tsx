"use client";

import { useState } from "react";
import { api, ApiError, type Patient } from "@/lib/api";
import { birthDate } from "@/lib/time";
import { FieldError } from "./PatientPicker";

type Props = {
  initialName: string;
  onDone: (patient: Patient) => void; // a new or existing patient was chosen
  onBack: () => void;
};

/** Register a new patient. The backend assigns the MRN and warns about
 *  existing patients with the same name and date of birth. */
export default function RegisterPatient({ initialName, onDone, onBack }: Props) {
  const [fullName, setFullName] = useState(initialName);
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [matches, setMatches] = useState<Patient[]>([]);

  const submit = async (allowDuplicate = false) => {
    if (!fullName.trim()) return setError(new ApiError("Please enter the patient's full name.", 0, null, "full_name"));
    if (!dateOfBirth) return setError(new ApiError("Please enter the date of birth.", 0, null, "date_of_birth"));
    setSaving(true);
    setError(null);
    try {
      onDone(
        await api.registerPatient({ full_name: fullName, date_of_birth: dateOfBirth, allow_duplicate: allowDuplicate }),
      );
    } catch (e) {
      const err = e as ApiError;
      if (err.code === "possible_duplicate") setMatches(err.matches);
      else setError(err);
    } finally {
      setSaving(false);
    }
  };

  const fieldError = (field: string) => (error?.field === field ? error.message : undefined);
  const generalError = error && !["full_name", "date_of_birth"].includes(error.field ?? "") ? error.message : null;

  return (
    <section aria-labelledby="register-heading">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 id="register-heading" className="text-base font-semibold">
          Register new patient
        </h2>
        <button type="button" className="btn" onClick={onBack}>
          Back to booking
        </button>
      </div>

      {matches.length > 0 ? (
        <div className="space-y-3 px-4 py-3">
          <div className="border border-noshow bg-noshow-bg px-3 py-2 text-noshow-ink" role="alert">
            {matches.length === 1 ? "A patient" : `${matches.length} patients`} with this name and date of birth
            already {matches.length === 1 ? "exists" : "exist"}. Is this the same person?
          </div>
          <ul className="divide-y divide-line-soft border border-line bg-white">
            {matches.map((patient) => (
              <li key={patient.id} className="flex items-center justify-between gap-2 px-3 py-2">
                <span>{patient.label}</span>
                <button type="button" className="btn btn-primary" onClick={() => onDone(patient)}>
                  Use this patient
                </button>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <button type="button" className="btn" disabled={saving} onClick={() => submit(true)}>
              {saving ? "Registering…" : "Register as a new patient anyway"}
            </button>
            <button type="button" className="btn" onClick={() => setMatches([])}>
              Edit details
            </button>
          </div>
        </div>
      ) : (
        <form
          className="space-y-3 px-4 py-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div>
            <label htmlFor="register-name" className="mb-1 block font-medium">
              Full name
            </label>
            <input
              id="register-name"
              className="field"
              value={fullName}
              autoFocus
              onChange={(e) => setFullName(e.target.value)}
              aria-invalid={!!fieldError("full_name")}
              aria-describedby={fieldError("full_name") ? "register-name-error" : undefined}
            />
            {fieldError("full_name") && <FieldError id="register-name-error" message={fieldError("full_name")!} />}
          </div>
          <div>
            <label htmlFor="register-dob" className="mb-1 block font-medium">
              Date of birth
            </label>
            <div className="flex items-center gap-3">
              <input
                id="register-dob"
                type="date"
                className="field w-44"
                value={dateOfBirth}
                onChange={(e) => setDateOfBirth(e.target.value)}
                aria-invalid={!!fieldError("date_of_birth")}
                aria-describedby={
                  [dateOfBirth ? "register-dob-words" : "", fieldError("date_of_birth") ? "register-dob-error" : ""]
                    .join(" ")
                    .trim() || undefined
                }
              />
              {dateOfBirth && (
                <span id="register-dob-words" className="font-medium">
                  {birthDate(dateOfBirth)}
                </span>
              )}
            </div>
            {fieldError("date_of_birth") && (
              <FieldError id="register-dob-error" message={fieldError("date_of_birth")!} />
            )}
          </div>
          <div>
            <span className="mb-1 block font-medium">MRN</span>
            <span className="text-muted">Assigned automatically</span>
          </div>
          {generalError && <FieldError message={generalError} />}
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "Registering…" : "Register patient"}
          </button>
        </form>
      )}
    </section>
  );
}
