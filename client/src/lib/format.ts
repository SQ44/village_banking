export function currency(amount: number) {
  const formatter = new Intl.NumberFormat("en-ZM", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const abs = Math.abs(amount);
  const formatted = formatter.format(abs);
  return amount < 0 ? `-K ${formatted}` : `K ${formatted}`;
}

export function formatDate(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString();
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

