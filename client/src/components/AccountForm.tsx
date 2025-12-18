import { useState } from "react";

import { Api } from "../api";
import type { Account, SavingsProduct } from "../types";

interface Props {
  products: SavingsProduct[];
  onCreated: (account: Account) => Promise<void> | void;
}

export function AccountForm({ products, onCreated }: Props) {
  const [form, setForm] = useState({ name: "", email: "", group_name: "", product_id: "", initial_deposit: 0 });
  const [customFields, setCustomFields] = useState("{}");
  const [isSubmitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const parsedCustom = customFields.trim() ? JSON.parse(customFields) : {};
      const payload = {
        name: form.name,
        email: form.email || undefined,
        group_name: form.group_name || undefined,
        product_id: form.product_id ? Number(form.product_id) : undefined,
        initial_deposit: Number(form.initial_deposit) || 0,
        custom_fields: parsedCustom,
      };
      const account = await Api.createAccount(payload);
      await onCreated(account);
      setForm({ name: "", email: "", group_name: "", product_id: "", initial_deposit: 0 });
      setCustomFields("{}");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create account");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <header className="panel-header">
        <h3>New Member</h3>
        <p>Capture members and optionally attach them to savings products.</p>
      </header>
      {error && <p className="error">{error}</p>}
      <label>
        Name
        <input name="name" value={form.name} onChange={handleChange} required />
      </label>
      <label>
        Email
        <input name="email" type="email" value={form.email} onChange={handleChange} />
      </label>
      <label>
        Group / Cell
        <input name="group_name" value={form.group_name} onChange={handleChange} />
      </label>
      <label>
        Savings Product
        <select name="product_id" value={form.product_id} onChange={handleChange}>
          <option value="">Standard (5% APY)</option>
          {products.map((product) => (
            <option key={product.id} value={product.id}>
              {product.name} ({product.interest_rate}% APR)
            </option>
          ))}
        </select>
      </label>
      <label>
        Initial Deposit
        <input name="initial_deposit" type="number" step="0.01" value={form.initial_deposit} onChange={handleChange} />
      </label>
      <label>
        Custom Fields (JSON)
        <textarea value={customFields} onChange={(e) => setCustomFields(e.target.value)} rows={4} />
      </label>
      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Saving..." : "Create Member"}
      </button>
    </form>
  );
}
