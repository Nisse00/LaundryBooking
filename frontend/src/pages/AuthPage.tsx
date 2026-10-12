import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { errorMessage, inviteCodeRequired, login, register } from "../api";

// Keep in sync with MIN_PASSWORD_LENGTH in backend/server.py
const MIN_PASSWORD_LENGTH = 8;

interface AuthPageProps {
  readonly mode: "login" | "register";
}

export default function AuthPage({ mode }: AuthPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [askForInviteCode, setAskForInviteCode] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const title = mode === "login" ? "Log in" : "Create account";

  useEffect(() => {
    if (mode !== "register") return;
    inviteCodeRequired()
      .then(setAskForInviteCode)
      .catch((err) => setError(errorMessage(err)));
  }, [mode]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      // Trimmed so a stray space at the end of a field can't lock you out
      if (mode === "login") {
        await login(username.trim(), password.trim());
      } else {
        await register(username.trim(), password.trim(), inviteCode.trim());
      }
      navigate("/calendar");
    } catch (err) {
      setError(errorMessage(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="d-flex justify-content-center align-items-center vh-100">
      <div className="w-50">
        <h1 className="text-center">{title}</h1>
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
            <label htmlFor="password">Password</label>
            <input
              type="password"
              className="form-control"
              id="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? MIN_PASSWORD_LENGTH : undefined}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {askForInviteCode && (
            <div className="form-group">
              <label htmlFor="invite-code">Invite code</label>
              <input
                type="text"
                className="form-control"
                id="invite-code"
                autoComplete="off"
                required
                aria-describedby="invite-code-help"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
              />
              <small id="invite-code-help" className="form-text text-muted">
                You get the code from the board of the association.
              </small>
            </div>
          )}
          {error && (
            <div className="alert alert-danger mt-3" role="alert">
              {error}
            </div>
          )}
          <button type="submit" className="btn btn-primary w-100 mt-3" disabled={submitting}>
            {title}
          </button>
        </form>
        {mode === "login" && (
          <p className="text-center mt-3">
            <Link to="/reset-password">Forgot your password?</Link>
          </p>
        )}
      </div>
    </div>
  );
}
