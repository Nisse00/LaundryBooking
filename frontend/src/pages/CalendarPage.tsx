import { useEffect, useState } from "react";
import { errorMessage, getUser, logout } from "../api";
import Calendar from "../components/Calendar";
import Menu from "../components/Menu";

export default function CalendarPage() {
  const [username, setUsername] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getUser()
      .then((user) => {
        setUsername(user.username);
        setIsAdmin(user.isAdmin);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  async function handleLogOut() {
    try {
      await logout();
      setUsername(null);
      setIsAdmin(false);
      setError("");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="laundry-page">
      <div className="laundry-topbar">
        <Menu username={username} isAdmin={isAdmin} onLogOut={handleLogOut} />
        <span>{username ? `Logged in as ${username}` : "Not logged in"}</span>
      </div>
      {error && (
        <div className="alert alert-danger container mt-3" role="alert">
          {error}
        </div>
      )}
      <Calendar username={username} isAdmin={isAdmin} />
    </div>
  );
}
