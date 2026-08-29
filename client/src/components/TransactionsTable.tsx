import type { Transaction } from "../types";

interface Props {
  transactions: Transaction[];
}

const statusLabel: Record<string, string> = {
  pending: "Pending",
  completed: "Completed",
  failed: "Failed",
};

export function TransactionsTable({ transactions }: Props) {
  if (!transactions.length) {
    return (
      <section className="panel">
        <header className="panel-header">
          <h3>Ledger</h3>
        </header>
        <p>No activity yet.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <header className="panel-header">
        <h3>Ledger</h3>
      </header>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Type</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => (
              <tr key={tx.id}>
                <td>{new Date(tx.created_at).toLocaleDateString()}</td>
                <td className="capitalize">{tx.type.replace(/_/g, " ")}</td>
                <td className="currency">K {tx.amount.toFixed(2)}</td>
                <td>
                  <span className={`status-badge status-${tx.status}`}>{statusLabel[tx.status]}</span>
                </td>
                <td>
                  {tx.description}
                  {tx.provider === "lipila" && (
                    <small>
                      Lipila
                      {tx.provider_status && tx.provider_status !== "succeeded"
                        ? ` · ${tx.provider_status.replace(/_/g, " ")}`
                        : " · confirmed"}
                    </small>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
