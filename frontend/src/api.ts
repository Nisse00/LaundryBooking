// Client for the Flask backend in backend/server.py.
// Requests are same-origin: in development Vite proxies /api (see vite.config.ts).

const API_ROOT = "/api/laundry";

export interface Booking {
  /** YYYY-MM-DD */
  date: string;
  /** 1, 2 or 3 – index into TIME_SLOTS plus one */
  slot: number;
  /** True when the booking belongs to the logged-in user */
  mine: boolean;
  /** Username of whoever booked it; null unless you are logged in */
  bookedBy: string | null;
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(API_ROOT + path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.message ?? "Something went wrong. Please try again.");
  }
  return data as T;
}

export async function getUser(): Promise<string | null> {
  return (await request<{ username: string | null }>("/user")).username;
}

export async function login(username: string, password: string): Promise<void> {
  await request("/login", "POST", { username, password });
}

export async function register(username: string, password: string): Promise<void> {
  await request("/register", "POST", { username, password });
}

export async function logout(): Promise<void> {
  await request("/logout", "POST");
}

/** All bookings from today onwards. */
export async function getBookings(): Promise<Booking[]> {
  return (await request<{ bookings: Booking[] }>("/bookings")).bookings;
}

export async function createBooking(date: string, slot: number): Promise<void> {
  await request("/bookings", "POST", { date, slot });
}

export async function cancelBooking(date: string, slot: number): Promise<void> {
  await request(`/bookings/${date}/${slot}`, "DELETE");
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
