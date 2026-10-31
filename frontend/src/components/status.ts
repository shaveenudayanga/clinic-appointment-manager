import type { Status } from "@/lib/api";

export const STATUS_LABEL: Record<Status, string> = {
  booked: "Booked",
  completed: "Completed",
  cancelled: "Cancelled",
  no_show: "No-show",
};

/** Block colours: a left stripe, a tinted background and dark text. Always shown with the label. */
export const STATUS_BLOCK: Record<Status, string> = {
  booked: "border-l-booked bg-booked-bg text-booked-ink",
  completed: "border-l-completed bg-completed-bg text-completed-ink",
  no_show: "border-l-noshow bg-noshow-bg text-noshow-ink",
  cancelled: "border-l-cancelled bg-cancelled-bg text-cancelled-ink line-through",
};

export const STATUS_BADGE: Record<Status, string> = {
  booked: "border-booked text-booked-ink bg-booked-bg",
  completed: "border-completed text-completed-ink bg-completed-bg",
  no_show: "border-noshow text-noshow-ink bg-noshow-bg",
  cancelled: "border-cancelled text-cancelled-ink bg-cancelled-bg",
};
