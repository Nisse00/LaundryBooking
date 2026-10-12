// Keep in sync with MAX_ACTIVE_BOOKINGS in backend/server.py
export const MAX_ACTIVE_BOOKINGS = 3;

export const TIME_SLOTS = ["08:00-12:00", "12:00-16:00", "16:00-20:00"] as const;

export type SlotStatus = "free" | "expired" | "taken" | "mine";

export const SLOT_STYLES: Record<SlotStatus, { readonly button: string; readonly label: string }> =
  {
    free: { button: "btn-success", label: "Free to book" },
    expired: { button: "btn-secondary", label: "Unavailable" },
    taken: { button: "btn-danger", label: "Booked by someone else" },
    mine: { button: "btn-primary", label: "Your current booking" },
  };
