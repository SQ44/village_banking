import { useState } from "react";

import { Api } from "../api";
import type { Transaction, TransactionPayload } from "../types";

interface Props {
  accountId?: number;
  onCreated: (transaction: Transaction) => Promise<void> | void;
}

export function TransactionForm({ accountId, onCreated }: Props) {
  const [form, setForm] = useState<TransactionPayload>({
    account_id: 0,
    amount: 0,
    type: "deposit",
    status: "completed",
    use_lenco: false,
  });
  const [customFields, setCustomFields] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!accountId) {
    return (
      <section className="panel">
        <header className="panel-header">
          <h3>Transactions</h3>
          <p>Select an account to capture transactions.</p>
        </header>
      </section>
    );
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name } = e.target;
    const value =
      e.target instanceof HTMLInputElement && e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const parsedCustom = customFields.trim() ? JSON.parse(customFields) : {};
      const payload = {
        ...form,
        account_id: accountId,
        amount: Number(form.amount),
        custom_fields: parsedCustom,
      };
      const tx = await Api.createTransaction(payload);
      await onCreated(tx);
      setForm((prev) => ({ ...prev, amount: 0, description: "" }));
      setCustomFields("{}");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add transaction");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <header className="panel-header">
        <h3>Transactions</h3>
        <p>Push deposits, withdrawals, or loan flows. Toggle Lenco Pay when you need automated settlement.</p>
      </header>
      {error && <p className="error">{error}</p>}
      <label>
        Amount
        <input name="amount" type="number" step="0.01" value={form.amount} onChange={handleChange} required />
      </label>
      <label>
        Type
        <select name="type" value={form.type} onChange={handleChange}>
          <option value="deposit">Deposit</option>
          <option value="withdrawal">Withdrawal</option>
          <option value="loan_disbursement">Loan Disbursement</option>
          <option value="loan_repayment">Loan Repayment</option>
        </select>
      </label>
      <label>
        Status
        <select name="status" value={form.status} onChange={handleChange}>
          <option value="pending">Pending</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
      </label>
      <label>
        Description
        <input name="description" value={form.description ?? ""} onChange={handleChange} />
      </label>
      <label className="checkbox">
        <input type="checkbox" name="use_lenco" checked={form.use_lenco ?? false} onChange={handleChange} />
        Trigger Lenco Pay
      </label>
      <label>
        Custom Fields (JSON)
        <textarea
          value={customFields}
          onChange={(e) => setCustomFields(e.target.value)}
          rows={4}
          placeholder='{\n  "customer_email": "member@example.com",\n  "customer_phone": "+2348000000",\n  "account_number": "0123456789",\n  "bank_code": "044"\n}'
        />
      </label>
      <button type="submit" disabled={busy}>
        {busy ? "Saving..." : "Save Transaction"}
      </button>
    </form>
  );
}
