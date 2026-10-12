import { SLOT_STYLES, SlotStatus, TIME_SLOTS } from "../slots";

interface CalendarBoxProps {
  readonly day: number;
  /** One status per entry in TIME_SLOTS */
  readonly slots: readonly SlotStatus[];
  /** Called with the slot number (1-3) */
  readonly onSlotClick: (slot: number) => void;
}

export default function CalendarBox({ day, slots, onSlotClick }: CalendarBoxProps) {
  return (
    <div className="card">
      <div className="card-body">
        <h5 className="card-title calendar-day-title">{day}</h5>
        <ul className="calendar-slots">
          {TIME_SLOTS.map((time, idx) => (
            <li key={time} className="calendar-slot">
              <span>{time}</span>
              <button
                type="button"
                className={`btn ${SLOT_STYLES[slots[idx]].button}`}
                onClick={() => onSlotClick(idx + 1)}
                disabled={slots[idx] === "expired"}
                aria-label={`${time}: ${SLOT_STYLES[slots[idx]].label}`}
              />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
