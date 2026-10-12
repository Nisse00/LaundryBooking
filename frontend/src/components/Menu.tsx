import { useState } from "react";
import Button from "react-bootstrap/Button";
import Offcanvas from "react-bootstrap/Offcanvas";
import { Link } from "react-router-dom";

interface MenuProps {
  readonly username: string | null;
  readonly onLogOut: () => void;
}

/** Menu button that opens a panel on the left with account actions and navigation. */
export default function Menu({ username, onLogOut }: MenuProps) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <>
      <Button variant="outline-secondary" onClick={() => setOpen(true)} aria-expanded={open}>
        ☰ Menu
      </Button>
      <Offcanvas show={open} onHide={close} placement="start">
        <Offcanvas.Header closeButton>
          <Offcanvas.Title>
            {username ? `Logged in as ${username}` : "Not logged in"}
          </Offcanvas.Title>
        </Offcanvas.Header>
        <Offcanvas.Body>
          <div className="laundry-menu-items">
            {username ? (
              <Button
                variant="primary"
                onClick={() => {
                  close();
                  onLogOut();
                }}
              >
                Log out
              </Button>
            ) : (
              <>
                <Link className="btn btn-primary" to="/login">
                  Log in
                </Link>
                <Link className="btn btn-outline-primary" to="/create-account">
                  Create account
                </Link>
              </>
            )}
          </div>
          <hr className="laundry-menu-divider" />
          <nav className="laundry-menu-items">
            <Link className="btn btn-outline-secondary" to="/">
              Start page
            </Link>
          </nav>
        </Offcanvas.Body>
      </Offcanvas>
    </>
  );
}
