import { KeyRound, Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "../lib/api";
import { PASSWORD_RULES } from "../lib/auth";
import { Alert, PasswordChecklist, PasswordField } from "./AuthShell";

/** Change the signed-in account's password (current password required; other devices are signed out). */
export default function ChangePasswordForm({ onDone }: { onDone?: (message: string) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setOk(null);
    if (!current) return setError("Enter your current password.");
    if (!PASSWORD_RULES.every((r) => r.test(next))) return setError("The new password does not meet all the requirements.");
    if (next === current) return setError("Choose a password different from your current one.");
    if (next !== confirm) return setError("The new passwords do not match.");
    setBusy(true);
    try {
      const res = await api.changePassword(current, next);
      setOk(res.message);
      setCurrent("");
      setNext("");
      setConfirm("");
      onDone?.(res.message);
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {error && <Alert>{error}</Alert>}
      {ok && <Alert kind="success">{ok}</Alert>}
      <PasswordField label="Current password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      <div>
        <PasswordField label="New password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        <PasswordChecklist password={next} />
      </div>
      <PasswordField label="Confirm new password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      <button
        type="submit"
        disabled={busy}
        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-forest-800 px-4 py-3 text-sm font-semibold text-white transition duration-200 ease-smooth hover:bg-forest-700 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />} Change password
      </button>
    </form>
  );
}
