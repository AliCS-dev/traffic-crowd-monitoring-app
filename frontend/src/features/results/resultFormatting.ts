export function formatLabel(value: string): string {
  const label = value.trim().replaceAll("_", " ");
  return label ? label[0].toUpperCase() + label.slice(1) : "Unknown";
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Unknown time"
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

export function formatConfidence(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}
