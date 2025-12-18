import { useState } from "react";

import { Api } from "../api";
import type { InterestPreview, Transaction } from "../types";

interface Props {
  accountId?: number;
  onApplied: (transaction: Transaction) => Promise<void> | void;
}

const today = () => new Date().toISOString().slice(0, 10);
const thirtyDaysAgo = () => {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10);
};

export function InterestPanel({ accountId, onApplied }: Props) {
  const [range, setRange] = useState({ start: thirtyDaysAgo(), end: today() });
  const [preview, setPreview] = useState<InterestPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!accountId) {
    return null;
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setRange((prev) => ({ ...prev, [name]: value }));
  };

  const handlePreview = async () => {
    if (!accountId) return;
    setBusy(true);
    setError(null);
    try {
      const payload = { account_id: accountId, start: `${range.start}T00:00:00Z`, end: `${range.end}T23:59:59Z` };
      const response = await Api.previewInterest(payload);
      setPreview(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to preview interest");
    } finally {
      setBusy(false);
    }
  };

  const handleApply = async () => {
    if (!accountId) return;
    setBusy(true);
    setError(null);
    try {
      const payload = { account_id: accountId, start: `${range.start}T00:00:00Z`, end: `${range.end}T23:59:59Z` };
      const txn = await Api.applyInterest(payload);
      await onApplied(txn);
      setPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to apply interest");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <header className="panel-header">
        <h3>Interest Tools</h3>
        <p>Preview and apply profit for the selected member.</p>
      </header>
      {error && <p className="error">{error}</p>}
      <div className="grid-2">
        <label>
          Period Start
          <input type="date" name="start" value={range.start} onChange={handleChange} />
        </label>
        <label>
          Period End
          <input type="date" name="end" value={range.end} onChange={handleChange} />
        </label>
      </div>
      <div className="interest-actions">
        <button type="button" onClick={handlePreview} disabled={busy}>
          Preview
        </button>
        <button type="button" onClick={handleApply} disabled={busy || !preview}>
          Apply Interest
        </button>
      </div>
      {preview && (
        <div className="interest-preview">
          <p>
            Projected interest: <strong>K {preview.projected_amount.toFixed(2)}</strong>
          </p>
          <p>
            Annual rate: <strong>{preview.annual_rate}%</strong>
          </p>
        </div>
      )}
    </section>
  );
}
