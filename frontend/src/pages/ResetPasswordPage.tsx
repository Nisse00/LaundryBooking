import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { errorMessage, resetPassword } from "../api";

// Keep in sync with MIN_PASSWORD_LENGTH in backend/server.py
const MIN_PASSWORD_LENGTH = 8;

/** Choose a new password with a one-time code from an admin. */
export default function ResetPasswordPage() {
  const [username, setUsername] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await resetPassword(username.trim(), code.trim(), password.trim());
      navigate("/calendar");
    } catch (err) {
      setError(errorMessage(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="d-flex justify-content-center align-items-center vh-100">
      <div className="w-50">
        <h1 className="text-center">Choose a new password</h1>
        <p className="text-center">
          Ask the board of the association for a reset code, then fill it in here.
        </p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              type="text"
              className="form-control"
              id="username"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label htmlFor="reset-code">Reset code</label>
            <input
              type="text"
              className="form-control"
              id="reset-code"
              autoComplete="off"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">New password</label>
            <input
              type="password"
              className="form-control"
              id="password"
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && (
            <div className="alert alert-danger mt-3" role="alert">
              {error}
            </div>
          )}
          <button type="submit" className="btn btn-primary w-100 mt-3" disabled={submitting}>
            Save new password
          </button>
        </form>
        <p className="text-center mt-3">
          <Link to="/login">Back to log in</Link>
        </p>
      </div>
    </div>
  );
}
