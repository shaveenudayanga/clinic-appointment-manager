"use client";

import type { Appointment, Practitioner } from "@/lib/api";
import { quarterHours, timeOf, toMinutes } from "@/lib/time";
import { STATUS_BLOCK, STATUS_LABEL } from "./status";

const ROW_HEIGHT = 22; // pixels per 15 minutes

type Props = {
  practitioners: Practitioner[];
  appointments: Appointment[]; // already filtered (cancelled hidden or not)
  opens: string;
  closes: string;
  nowMinutes: number | null; // minutes since midnight if the day shown is today
  selectedAppointmentId: number | null;
  selectedSlot: { practitionerId: number; start: string } | null;
  onSlotClick: (practitioner: Practitioner, start: string) => void;
  onAppointmentClick: (appointment: Appointment) => void;
};

export default function DayGrid(props: Props) {
  const { practitioners, appointments, opens, closes, nowMinutes } = props;
  const slots = quarterHours(opens, closes);
  const dayStart = toMinutes(opens);
  const height = slots.length * ROW_HEIGHT;
  const showNow = nowMinutes !== null && nowMinutes >= dayStart && nowMinutes <= toMinutes(closes);

  return (
    <div className="min-w-full w-max">
      {/* Column headers stay visible while scrolling */}
      <div className="sticky top-0 z-30 flex border-b border-line bg-white">
        <div className="sticky left-0 z-10 w-16 shrink-0 border-r border-line bg-white" />
        {practitioners.map((p) => (
          <div key={p.id} className="min-w-56 flex-1 border-r border-line px-2 py-1.5">
            <div className="font-semibold">{p.full_name}</div>
            <div className="text-xs text-muted">{p.specialty}</div>
            <div className="text-xs text-muted">Provider No. {p.provider_number}</div>
          </div>
        ))}
      </div>

      <div className="relative flex bg-white">
        {/* Time labels */}
        <div className="sticky left-0 z-20 w-16 shrink-0 border-r border-line bg-white" style={{ height }}>
          {slots.map((time, i) => (
            <div
              key={time}
              className={`absolute right-2 text-xs tabular-nums text-muted ${i === 0 ? "" : "-translate-y-1/2"}`}
              style={{ top: i * ROW_HEIGHT }}
            >
              {time.endsWith(":00") || time.endsWith(":30") ? time : ""}
            </div>
          ))}
        </div>

        {practitioners.map((p) => (
          <PractitionerColumn
            {...props}
            key={p.id}
            practitioner={p}
            appointments={appointments.filter((a) => a.practitioner.id === p.id)}
            slots={slots}
            dayStart={dayStart}
            height={height}
            nowMinutes={showNow ? nowMinutes : null}
          />
        ))}

        {showNow && (
          <div
            className="pointer-events-none absolute left-0 right-0 z-20 border-t-2 border-danger"
            style={{ top: ((nowMinutes! - dayStart) / 15) * ROW_HEIGHT }}
            aria-hidden="true"
          >
            <span className="sticky left-0 -mt-2.5 inline-block bg-danger px-1 text-xs tabular-nums text-white">
              Now
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function PractitionerColumn({
  practitioner,
  appointments,
  slots,
  dayStart,
  height,
  nowMinutes,
  selectedAppointmentId,
  selectedSlot,
  onSlotClick,
  onAppointmentClick,
}: Props & {
  practitioner: Practitioner;
  slots: string[];
  dayStart: number;
  height: number;
}) {
  const placed = layoutLanes(appointments);

  return (
    <div className="relative min-w-56 flex-1 border-r border-line" style={{ height }}>
      {/* Free slots, one button per 15 minutes, underneath the appointment blocks */}
      {slots.map((time, i) => {
        const isPast = nowMinutes !== null && toMinutes(time) + 15 <= nowMinutes;
        const isSelected = selectedSlot?.practitionerId === practitioner.id && selectedSlot.start === time;
        return (
          <button
            key={time}
            type="button"
            onClick={() => onSlotClick(practitioner, time)}
            aria-label={`Book with ${practitioner.label} at ${time}`}
            className={`group absolute left-0 right-0 border-t text-left text-xs ${
              time.endsWith(":00") ? "border-line" : "border-line-soft"
            } ${isPast ? "bg-page/70" : ""} ${
              isSelected ? "bg-accent-soft outline-2 -outline-offset-2 outline-accent" : "hover:bg-accent-soft focus-visible:bg-accent-soft"
            }`}
            style={{ top: i * ROW_HEIGHT, height: ROW_HEIGHT }}
          >
            <span className={`pl-2 text-accent ${isSelected ? "" : "invisible group-hover:visible group-focus-visible:visible"}`}>
              + Book {time}
            </span>
          </button>
        );
      })}

      {appointments.length === 0 && (
        <p className="pointer-events-none absolute left-2 top-1 text-xs text-muted">No appointments on this day</p>
      )}

      {placed.map(({ appointment: a, lane, lanes }) => {
        const start = timeOf(a.start_local);
        const end = timeOf(a.end_local);
        const top = ((toMinutes(start) - dayStart) / 15) * ROW_HEIGHT;
        const blockHeight = ((toMinutes(end) - toMinutes(start)) / 15) * ROW_HEIGHT;
        const oneLine = blockHeight < ROW_HEIGHT * 2;
        const status = STATUS_LABEL[a.status];
        const isSelected = a.id === selectedAppointmentId;
        return (
          <button
            key={a.id}
            type="button"
            onClick={() => onAppointmentClick(a)}
            title={`${start}–${end} ${status}\n${a.patient.label}${a.notes ? `\n${a.notes}` : ""}`}
            aria-label={`${start} to ${end}, ${a.patient.label}, ${status}`}
            className={`absolute z-10 flex flex-col justify-start overflow-hidden border border-l-4 border-line px-1.5 text-left text-xs leading-[18px] ${
              STATUS_BLOCK[a.status]
            } ${isSelected ? "outline-2 -outline-offset-1 outline-accent" : ""}`}
            style={{
              top: top + 1,
              height: blockHeight - 2,
              left: `calc(${(lane / lanes) * 100}% + 2px)`,
              width: `calc(${100 / lanes}% - 4px)`,
            }}
          >
            {oneLine ? (
              <span className="block truncate">
                <span className="tabular-nums">{start}</span> <span className="font-semibold">{status}</span> ·{" "}
                {a.patient.full_name} · {a.patient.mrn}
              </span>
            ) : (
              <>
                <span className="block truncate">
                  <span className="tabular-nums">
                    {start}–{end}
                  </span>{" "}
                  <span className="font-semibold">{status}</span>
                </span>
                <span className="block truncate">
                  {a.patient.full_name} · MRN {a.patient.mrn}
                </span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Place overlapping appointments side by side. Only a cancelled appointment
 *  can overlap another, so this matters only when cancelled ones are shown. */
function layoutLanes(appointments: Appointment[]) {
  // Same start time: active appointments take the left lane, cancelled ones go to the right.
  const sorted = [...appointments].sort(
    (a, b) =>
      a.start_local.localeCompare(b.start_local) ||
      Number(a.status === "cancelled") - Number(b.status === "cancelled") ||
      a.id - b.id,
  );
  const placed: { appointment: Appointment; lane: number; lanes: number }[] = [];
  let group: typeof placed = [];
  let laneEnds: string[] = [];
  let groupEnd = "";

  const closeGroup = () => {
    group.forEach((item) => (item.lanes = laneEnds.length));
    group = [];
    laneEnds = [];
  };

  for (const appointment of sorted) {
    if (group.length && appointment.start_local >= groupEnd) closeGroup();
    let lane = laneEnds.findIndex((end) => end <= appointment.start_local);
    if (lane === -1) lane = laneEnds.push(appointment.end_local) - 1;
    else laneEnds[lane] = appointment.end_local;
    const item = { appointment, lane, lanes: 1 };
    group.push(item);
    placed.push(item);
    groupEnd = group.length === 1 || appointment.end_local > groupEnd ? appointment.end_local : groupEnd;
  }
  closeGroup();
  return placed;
}
