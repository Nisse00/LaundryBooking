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

export interface CurrentUser {
  /** null when nobody is logged in */
  username: string | null;
  isAdmin: boolean;
}

/** A row in the admin's list of users */
export interface AdminUser {
  username: string;
  isAdmin: boolean;
  activeBookings: number;
}

export async function getUser(): Promise<CurrentUser> {
  return await request<CurrentUser>("/user");
}

export async function login(username: string, password: string): Promise<void> {
  await request("/login", "POST", { username, password });
}

export async function register(
  username: string,
  password: string,
  inviteCode: string,
): Promise<void> {
  await request("/register", "POST", { username, password, inviteCode });
}

/** Whether creating an account requires the invite code. */
export async function inviteCodeRequired(): Promise<boolean> {
  return (await request<{ inviteCodeRequired: boolean }>("/registration")).inviteCodeRequired;
}

export async function logout(): Promise<void> {
  await request("/logout", "POST");
}

/** Admins only. */
export async function getUsers(): Promise<AdminUser[]> {
  return (await request<{ users: AdminUser[] }>("/users")).users;
}

/** Admins only. A one-time code that lets the user choose a new password. */
export async function createResetCode(
  username: string,
): Promise<{ code: string; validHours: number }> {
  return await request(`/users/${encodeURIComponent(username)}/reset-code`, "POST");
}

/** Choose a new password with a code from an admin. Logs you in. */
export async function resetPassword(
  username: string,
  code: string,
  password: string,
): Promise<void> {
  await request("/reset-password", "POST", { username, code, password });
}

/** Admins only. Also removes the user's bookings. */
export async function deleteUser(username: string): Promise<void> {
  await request(`/users/${encodeURIComponent(username)}`, "DELETE");
}

/** All bookings from today onwards. */
export async function getBookings(): Promise<Booking[]> {
  return (await request<{ bookings: Booking[] }>("/bookings")).bookings;
}

export async function createBooking(date: string, slot: number): Promise<void> {
  await request("/bookings", "POST", { date, slot });
}

/** Your own booking, or anyone's if you are an admin. */
export async function cancelBooking(date: string, slot: number): Promise<void> {
  await request(`/bookings/${date}/${slot}`, "DELETE");
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
