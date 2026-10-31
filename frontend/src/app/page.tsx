"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import BookingPanel, { type PanelTarget } from "@/components/BookingPanel";
import DayGrid from "@/components/DayGrid";
import { api, type Appointment, type ClinicInfo, type Practitioner } from "@/lib/api";
import { dateOf, longDate, timeOf, toMinutes } from "@/lib/time";

export default function AppointmentBook() {
  const [clinic, setClinic] = useState<ClinicInfo | null>(null); // includes info about the selected date
  const [practitioners, setPractitioners] = useState<Practitioner[]>([]);
  const [date, setDate] = useState<string | null>(null);
  const [appointments, setAppointments] = useState<Appointment[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadCount, setReloadCount] = useState(0); // reloads the selected day
  const [startAttempt, setStartAttempt] = useState(0); // retries the first load
  const [showCancelled, setShowCancelled] = useState(false);
  const [panel, setPanel] = useState<{ target: PanelTarget; key: string } | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  const reload = useCallback(() => setReloadCount((n) => n + 1), []);

  // First load: practitioners and the default clinic day.
  useEffect(() => {
    Promise.all([api.practitioners(), api.clinic()])
      .then(([people, info]) => {
        setPractitioners(people);
        setDate(info.default_date);
      })
      .catch((e) => setLoadError(e.message));
  }, [startAttempt]);

  // The selected day: clinic info for that date and its appointments.
  useEffect(() => {
    if (!date) return;
    let stale = false;
    setAppointments(null);
    Promise.all([api.clinic(date), api.appointmentsForDay(date)])
      .then(([info, list]) => {
        if (stale) return;
        setClinic(info);
        setAppointments(list);
        setLoadError(null);
      })
      .catch((e) => !stale && setLoadError(e.message));
    return () => {
      stale = true;
    };
  }, [date, reloadCount]);

  // Refresh the current time (for the "now" line) once a minute.
  useEffect(() => {
    if (!date) return;
    const timer = setInterval(() => api.clinic(date).then(setClinic).catch(() => {}), 60_000);
    return () => clearInterval(timer);
  }, [date]);

  const openPanel = (target: PanelTarget, key: string) => {
    openerRef.current = document.activeElement as HTMLElement | null;
    setPanel({ target, key });
  };

  const closePanel = useCallback(() => {
    setPanel(null);
    setTimeout(() => openerRef.current?.focus());
  }, []);

  useEffect(() => {
    if (!panel) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closePanel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panel, closePanel]);

  const onSaved = (appointment: Appointment, message: string) => {
    const savedDate = dateOf(appointment.start_local);
    if (savedDate !== date) setDate(savedDate);
    else reload();
    setPanel({ target: { kind: "existing", appointment, message }, key: `appt-${appointment.id}-${Date.now()}` });
  };

  if (loadError && !appointments) {
    return (
      <main className="p-6">
        <p className="mb-3">Can&apos;t load appointments. {loadError}</p>
        <button
          type="button"
          className="btn"
          onClick={() => {
            setLoadError(null);
            if (date) reload();
            else setStartAttempt((n) => n + 1);
          }}
        >
          Try again
        </button>
      </main>
    );
  }

  if (!clinic || !date) {
    return <main className="p-6 text-muted">Loading appointments…</main>;
  }

  const cancelledCount = appointments?.filter((a) => a.status === "cancelled").length ?? 0;
  const visible = appointments?.filter((a) => showCancelled || a.status !== "cancelled") ?? [];
  const isToday = dateOf(clinic.now_local) === date;
  const selectedSlot =
    panel?.target.kind === "new" && panel.target.date === date && panel.target.practitionerId && panel.target.start
      ? { practitionerId: panel.target.practitionerId, start: panel.target.start }
      : null;
  const selectedAppointmentId = panel?.target.kind === "existing" ? panel.target.appointment.id : null;

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-white px-4 py-2">
        <span className="font-semibold">{clinic.name}</span>
        <nav className="flex gap-1" aria-label="Choose day">
          <button type="button" className="btn" onClick={() => setDate(clinic.previous_date)}>
            &lsaquo; Previous day
          </button>
          <button type="button" className="btn" onClick={() => setDate(clinic.default_date)}>
            Today
          </button>
          <button type="button" className="btn" onClick={() => setDate(clinic.next_date)}>
            Next day &rsaquo;
          </button>
        </nav>
        <h1 className="text-lg font-semibold" aria-live="polite">
          {longDate(date)}
        </h1>
        <label className="flex items-center gap-2">
          <span className="sr-only">Go to date</span>
          <input
            type="date"
            className="field w-40"
            value={date}
            onChange={(e) => e.target.value && setDate(e.target.value)}
          />
        </label>
        <div className="ml-auto flex items-center gap-4">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={showCancelled} onChange={(e) => setShowCancelled(e.target.checked)} />
            Show cancelled ({cancelledCount})
          </label>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => openPanel({ kind: "new", date }, `new-${Date.now()}`)}
          >
            Book appointment
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1 overflow-auto">
          {!clinic.is_open ? (
            <div className="p-6">
              <p className="mb-3">The clinic is closed on {longDate(date)}.</p>
              <button type="button" className="btn" onClick={() => setDate(clinic.next_date)}>
                Go to {longDate(clinic.next_date)}
              </button>
            </div>
          ) : appointments === null ? (
            <p className="p-6 text-muted">Loading appointments…</p>
          ) : practitioners.length === 0 ? (
            <p className="p-6 text-muted">No practitioners have been set up yet.</p>
          ) : (
            <DayGrid
              practitioners={practitioners}
              appointments={visible}
              opens={clinic.opens}
              closes={clinic.closes}
              nowMinutes={isToday ? toMinutes(timeOf(clinic.now_local)) : null}
              selectedAppointmentId={selectedAppointmentId}
              selectedSlot={selectedSlot}
              onSlotClick={(p, start) =>
                openPanel({ kind: "new", date, practitionerId: p.id, start }, `new-${p.id}-${start}-${Date.now()}`)
              }
              onAppointmentClick={(a) => openPanel({ kind: "existing", appointment: a }, `appt-${a.id}-${Date.now()}`)}
            />
          )}
          {loadError && appointments && (
            <p className="sticky bottom-0 border-t border-line bg-danger-soft px-4 py-2 text-danger" role="alert">
              {loadError}
            </p>
          )}
        </main>

        {panel && (
          <aside
            className="w-[448px] shrink-0 overflow-y-auto border-l border-line bg-white"
            aria-label="Booking panel"
          >
            <BookingPanel
              key={panel.key}
              target={panel.target}
              clinic={clinic}
              practitioners={practitioners}
              onClose={closePanel}
              onSaved={onSaved}
            />
          </aside>
        )}
      </div>
    </div>
  );
}
