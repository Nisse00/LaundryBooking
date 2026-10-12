import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AdminUser,
  CurrentUser,
  deleteUser,
  errorMessage,
  getUser,
  getUsers,
  logout,
} from "../api";
import Menu from "../components/Menu";

interface Notice {
  readonly kind: "success" | "danger";
  readonly text: string;
}

/** Lets an admin see all accounts and remove the ones no longer in use. */
export default function AdminPage() {
  // null until we know who is logged in
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const navigate = useNavigate();

  const fail = (err: unknown) => setNotice({ kind: "danger", text: errorMessage(err) });

  const refreshUsers = useCallback(async () => {
    try {
      setUsers(await getUsers());
    } catch (err) {
      fail(err);
    }
  }, []);

  useEffect(() => {
    getUser()
      .then((current) => {
        setUser(current);
        if (current.isAdmin) refreshUsers();
      })
      .catch(fail);
  }, [refreshUsers]);

  async function handleLogOut() {
    try {
      await logout();
      navigate("/calendar");
    } catch (err) {
      fail(err);
    }
  }

  async function handleDelete(target: AdminUser) {
    const bookings =
      target.activeBookings > 0 ? ` and their ${target.activeBookings} upcoming booking(s)` : "";
    if (!window.confirm(`Delete the account ${target.username}${bookings}?`)) return;
    try {
      await deleteUser(target.username);
      setNotice({ kind: "success", text: `The account ${target.username} was deleted.` });
    } catch (err) {
      fail(err);
    }
    await refreshUsers();
  }

  return (
    <div className="laundry-page">
      <div className="laundry-topbar">
        <Menu username={user?.username ?? null} isAdmin={user?.isAdmin} onLogOut={handleLogOut} />
        <Link to="/calendar">Back to the calendar</Link>
      </div>
      <div className="container">
        <h1 className="pt-4">Users</h1>
        {notice && (
          <div className={`alert alert-${notice.kind} mt-3`} role="alert">
            {notice.text}
          </div>
        )}
        {user && !user.isAdmin && (
          <div className="alert alert-warning mt-3" role="alert">
            Only an admin can manage users.
          </div>
        )}
        {user?.isAdmin && (
          <table className="table table-striped align-middle text-start mt-3">
            <thead>
              <tr>
                <th scope="col">Username</th>
                <th scope="col">Upcoming bookings</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {users.map((row) => (
                <tr key={row.username}>
                  <td>
                    {row.username}
                    {row.isAdmin && <span className="badge text-bg-secondary ms-2">Admin</span>}
                  </td>
                  <td>{row.activeBookings}</td>
                  <td className="text-end">
                    {row.username !== user.username && (
                      <button
                        type="button"
                        className="btn btn-outline-danger btn-sm"
                        onClick={() => handleDelete(row)}
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
