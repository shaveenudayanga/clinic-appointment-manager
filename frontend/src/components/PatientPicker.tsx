"use client";

import { useEffect, useId, useRef, useState } from "react";
import { api, type Patient } from "@/lib/api";

type Props = {
  selected: Patient | null;
  onSelect: (patient: Patient | null) => void;
  onRegisterNew: (searchText: string) => void;
  error?: string;
  autoFocus?: boolean;
  disabled?: boolean;
};

/** Search by name, MRN or date of birth. Shows full labels so same-name patients can be told apart. */
export default function PatientPicker({ selected, onSelect, onRegisterNew, error, autoFocus, disabled }: Props) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Patient[] | null>(null);
  const [active, setActive] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(null);
      return;
    }
    let stale = false;
    const timer = setTimeout(() => {
      api
        .searchPatients(q)
        .then((found) => {
          if (stale) return;
          setResults(found);
          setActive(0);
          setLoadError(null);
        })
        .catch((e) => !stale && setLoadError(e.message));
    }, 200);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [query]);

  const choose = (patient: Patient) => {
    onSelect(patient);
    setQuery("");
    setResults(null);
  };

  if (selected) {
    return (
      <div>
        <div className="flex items-start justify-between gap-2">
          <span className="py-1">{selected.label}</span>
          {!disabled && (
            <button
              type="button"
              className="btn"
              onClick={() => {
                onSelect(null);
                setTimeout(() => inputRef.current?.focus());
              }}
            >
              Change
            </button>
          )}
        </div>
        {error && <FieldError id={`${id}-error`} message={error} />}
      </div>
    );
  }

  const sameNames = duplicateNames(results ?? []);
  const listId = `${id}-list`;

  return (
    <div>
      <input
        ref={inputRef}
        id={`${id}-input`}
        className="field"
        placeholder="Name, MRN or date of birth (dd/mm/yyyy)"
        autoComplete="off"
        autoFocus={autoFocus}
        value={query}
        role="combobox"
        aria-label="Search patient"
        aria-expanded={!!results?.length}
        aria-controls={listId}
        aria-activedescendant={results?.length ? `${listId}-${active}` : undefined}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (!results?.length) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((i) => Math.min(i + 1, results.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(results[active]);
          }
        }}
      />

      {results && results.length > 0 && (
        <ul id={listId} role="listbox" aria-label="Matching patients" className="mt-1 border border-line bg-white">
          {results.map((patient, i) => (
            <li
              key={patient.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={`cursor-pointer px-2 py-1 ${i === active ? "bg-accent-soft" : ""}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault(); // keep focus in the input
                choose(patient);
              }}
            >
              {patient.label}
            </li>
          ))}
        </ul>
      )}

      {sameNames.map(([name, count]) => (
        <p key={name} className="mt-1 text-xs text-noshow-ink">
          {count} patients named {name}. Check the MRN and date of birth.
        </p>
      ))}

      {results && results.length === 0 && (
        <div className="mt-1">
          <p className="text-muted">No patient matches &ldquo;{query.trim()}&rdquo;.</p>
          <button type="button" className="btn mt-1" onClick={() => onRegisterNew(query.trim())}>
            Register new patient
          </button>
        </div>
      )}

      {loadError && <FieldError message={loadError} />}
      {error && <FieldError id={`${id}-error`} message={error} />}
    </div>
  );
}

function duplicateNames(patients: Patient[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const p of patients) counts.set(p.full_name, (counts.get(p.full_name) ?? 0) + 1);
  return [...counts].filter(([, count]) => count > 1);
}

export function FieldError({ message, id }: { message: string; id?: string }) {
  return (
    <p id={id} className="mt-1 text-danger" role="alert">
      {message}
    </p>
  );
}
