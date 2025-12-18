import type { DashboardStats } from "../types";

interface Props {
  stats?: DashboardStats;
}

export function DashboardCards({ stats }: Props) {
  const cards = [
    { label: "Members", value: stats?.member_count ?? 0 },
    { label: "Vault Balance", value: stats?.total_balance ?? 0, currency: true },
    { label: "Pending Txns", value: stats?.pending_transactions ?? 0 },
  ];

  return (
    <div className="dashboard-grid">
      {cards.map((card) => (
        <article key={card.label} className="card">
          <p className="card-label">{card.label}</p>
          <p className="card-value">
            {card.currency
              ? `K ${card.value.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
              : card.value}
          </p>
        </article>
      ))}
    </div>
  );
}
