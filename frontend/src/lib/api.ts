// Typed client for the FastAPI backend. Every rule lives in the backend; this
// file only sends requests and turns error responses into ApiError.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Status = "booked" | "completed" | "cancelled" | "no_show";
export type Action = "edit" | "cancel" | "complete" | "no_show";

export type Practitioner = {
  id: number;
  provider_number: string;
  full_name: string;
  specialty: string;
  label: string;
};

export type Patient = {
  id: number;
  mrn: string;
  full_name: string;
  date_of_birth: string; // yyyy-mm-dd
  label: string;
};

export type Appointment = {
  id: number;
  practitioner: Practitioner;
  patient: Patient;
  start_local: string; // e.g. 2026-11-03T15:00:00+11:00 (Sydney time)
  end_local: string;
  status: Status;
  allowed_actions: Action[];
  notes: string;
};

export type ClinicInfo = {
  name: string;
  timezone: string;
  now_local: string; // current Sydney time, e.g. 2026-11-02T10:12:00+11:00
  today: string;
  default_date: string;
  opens: string; // HH:MM
  closes: string;
  min_minutes: number;
  max_minutes: number;
  nl_booking: boolean;
  selected_date: string;
  is_open: boolean;
  previous_date: string;
  next_date: string;
};

/** Request field an error is about, as named by the backend. */
export type ErrorField =
  | "practitioner_id"
  | "patient_id"
  | "start"
  | "end"
  | "status"
  | "full_name"
  | "date_of_birth";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string | null = null,
    public field: ErrorField | null = null,
    public matches: Patient[] = [],
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Can't reach the server. Check that the backend is running.", 0);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      body?.detail ?? `Something went wrong (error ${response.status}).`,
      response.status,
      body?.code ?? null,
      body?.field ?? null,
      body?.matches ?? [],
    );
  }
  return body as T;
}

const post = (body: unknown) => ({ method: "POST", body: JSON.stringify(body) });
const patch = (body: unknown) => ({ method: "PATCH", body: JSON.stringify(body) });

export const api = {
  clinic: (date?: string) => request<ClinicInfo>(`/api/clinic${date ? `?date=${date}` : ""}`),
  practitioners: () => request<Practitioner[]>("/api/practitioners"),
  searchPatients: (q: string) => request<Patient[]>(`/api/patients?q=${encodeURIComponent(q)}`),
  registerPatient: (data: { full_name: string; date_of_birth: string; allow_duplicate?: boolean }) =>
    request<Patient>("/api/patients", post(data)),
  appointmentsForDay: (date: string) => request<Appointment[]>(`/api/appointments?date=${date}`),
  appointment: (id: number) => request<Appointment>(`/api/appointments/${id}`),
  createAppointment: (data: AppointmentInput) => request<Appointment>("/api/appointments", post(data)),
  updateAppointment: (id: number, data: Partial<AppointmentInput> & { status?: Status }) =>
    request<Appointment>(`/api/appointments/${id}`, patch(data)),
  cancelAppointment: (id: number) => request<Appointment>(`/api/appointments/${id}/cancel`, { method: "POST" }),
};

export type AppointmentInput = {
  practitioner_id: number;
  patient_id: number;
  start: string; // Sydney wall-clock time, yyyy-mm-ddTHH:MM
  end: string;
  notes: string;
};
