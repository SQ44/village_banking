import { useState } from "react";

import { Api } from "../api";
import type { Transaction, TransactionPayload, TransactionType } from "../types";

interface Props {
  accountId?: number;
  onCreated: (transaction: Transaction) => Promise<void> | void;
}

// Lipila collects for money coming in and pays out for money going out. Fees
// and interest are ledger-only entries with no counterparty to charge.
const LIPILA_TYPES: TransactionType[] = ["deposit", "withdrawal", "loan_disbursement", "loan_repayment"];
const COLLECTION_TYPES: TransactionType[] = ["deposit", "loan_repayment"];

export function TransactionForm({ accountId, onCreated }: Props) {
  const [form, setForm] = useState<TransactionPayload>({
    account_id: 0,
    amount: 0,
    type: "deposit",
    status: "completed",
    use_lipila: false,
    channel: "mobile_money",
    phone_number: "",
  });
  const [customFields, setCustomFields] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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

  const usesLipila = form.use_lipila ?? false;
  const isCollection = COLLECTION_TYPES.includes(form.type);
  const canUseLipila = LIPILA_TYPES.includes(form.type);
  const channel = form.channel ?? "mobile_money";
  const needsPhone = usesLipila && channel !== "bank";

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
    setNotice(null);
    try {
      const parsedCustom = customFields.trim() ? JSON.parse(customFields) : {};
      const payload: TransactionPayload = {
        ...form,
        account_id: accountId,
        amount: Number(form.amount),
        custom_fields: parsedCustom,
      };
      if (!usesLipila) {
        delete payload.channel;
        delete payload.phone_number;
      }
      const tx = await Api.createTransaction(payload);
      await onCreated(tx);

      if (tx.card_redirect_url) {
        // The card is authorised on Lipila's own page, not here.
        setNotice("Opening the card payment page…");
        window.location.assign(tx.card_redirect_url);
        return;
      }
      if (tx.provider === "lipila" && tx.status === "pending") {
        setNotice(
          isCollection
            ? "Sent. The member must approve the prompt on their phone — the balance updates once Lipila confirms."
            : "Payout requested. The balance is held until Lipila confirms it was paid.",
        );
      }
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
        <p>Push deposits, withdrawals, or loan flows. Route through Lipila to move real money.</p>
      </header>
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}
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
      {!usesLipila && (
        <label>
          Status
          <select name="status" value={form.status} onChange={handleChange}>
            <option value="pending">Pending</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </label>
      )}
      <label>
        Description
        <input name="description" value={form.description ?? ""} onChange={handleChange} />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          name="use_lipila"
          checked={usesLipila}
          onChange={handleChange}
          disabled={!canUseLipila}
        />
        Pay with Lipila
      </label>
      {usesLipila && (
        <>
          <label>
            Channel
            <select name="channel" value={channel} onChange={handleChange}>
              <option value="mobile_money">Mobile Money</option>
              {isCollection && <option value="card">Card</option>}
              {!isCollection && <option value="bank">Bank Account</option>}
            </select>
          </label>
          {needsPhone && (
            <label>
              Phone Number
              <input
                name="phone_number"
                value={form.phone_number ?? ""}
                onChange={handleChange}
                placeholder="0977123456"
                required
              />
            </label>
          )}
          <p className="hint">
            {isCollection
              ? "The balance moves only once Lipila confirms the payment."
              : "Funds are held from the balance now and returned if the payout fails."}
          </p>
        </>
      )}
      <label>
        Custom Fields (JSON)
        <textarea
          value={customFields}
          onChange={(e) => setCustomFields(e.target.value)}
          rows={4}
          placeholder={
            '{\n  "customer_email": "member@example.com",\n  "account_number": "0123456789",\n  "bank_code": "044"\n}'
          }
        />
      </label>
      <button type="submit" disabled={busy}>
        {busy ? "Saving..." : "Save Transaction"}
      </button>
    </form>
  );
}
