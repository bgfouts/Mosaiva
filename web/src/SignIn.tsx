const AUTH_ERRORS: Record<string, string> = {
  not_allowed: "That Google account is not on this record's list. Sign in with one of the two allowed accounts.",
  expired: "The sign-in took too long. Try again.",
  cancelled: "Sign-in was cancelled.",
  google: "Google could not finish the sign-in. Try again.",
};

export function SignIn({ error, problem }: { error: string; problem: string }) {
  return (
    <div className="signin">
      <div className="card signin-card">
        <p className="mark">Mosaiva</p>
        <p className="aside-copy">One private record for a complicated picture.</p>
        {error && (
          <p className="alert" role="alert">
            {AUTH_ERRORS[error] ?? "Sign-in did not finish. Try again."}
          </p>
        )}
        {problem ? (
          <p className="alert" role="alert">
            {problem}
          </p>
        ) : (
          <a className="button google" href="/api/auth/login">
            Sign in with Google
          </a>
        )}
        <p className="note">Only two Google accounts can open this record.</p>
      </div>
    </div>
  );
}
