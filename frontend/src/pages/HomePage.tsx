import { Link } from "react-router-dom";
import laundryRoomPhoto from "../assets/laundry-room.jpg";
import { MAX_ACTIVE_BOOKINGS, TIME_SLOTS } from "../slots";

export default function HomePage() {
  return (
    <main className="laundry-home">
      <div className="laundry-home-content">
        <section className="laundry-home-text">
          <p className="laundry-home-eyebrow">Föreningen Botan · Lund</p>
          <h1>Book the laundry room</h1>
          <p className="lead">
            Pick a free time in the calendar and the laundry room is yours. No lists on the door, no
            double bookings.
          </p>
          <div className="laundry-home-actions">
            <Link className="btn btn-primary btn-lg" to="/calendar">
              Go to calendar
            </Link>
            <Link className="btn btn-outline-secondary btn-lg" to="/login">
              Log in
            </Link>
          </div>
          <dl className="laundry-home-facts">
            <div>
              <dt>Three times a day</dt>
              <dd>{TIME_SLOTS.join(", ")}</dd>
            </div>
            <div>
              <dt>Up to {MAX_ACTIVE_BOOKINGS} bookings at a time</dt>
              <dd>Cancel one to pick another, so there are times for everyone.</dd>
            </div>
            <div>
              <dt>Up to two months ahead</dt>
              <dd>This month and the next are open for booking.</dd>
            </div>
          </dl>
        </section>
        {/* A photo of the building can be added next to this one: put the file in
            src/assets and add a second figure here. */}
        <figure className="laundry-home-figure">
          <img
            className="laundry-home-photo"
            src={laundryRoomPhoto}
            alt="A washing machine beside shelves with baskets, towels and plants"
          />
          <figcaption>
            Photo:{" "}
            <a href="https://unsplash.com/photos/a-washer-and-dryer-in-a-room-23coWmkTNSg">
              PlanetCare / Unsplash
            </a>
          </figcaption>
        </figure>
      </div>
    </main>
  );
}
