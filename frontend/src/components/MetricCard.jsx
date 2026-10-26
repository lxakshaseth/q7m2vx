export function MetricCard({ label, value, unit, detail, status = "neutral" }) {
  return (
    <article className={`metric-card metric-card--${status}`}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">
        <span>{value}</span>
        {unit ? <small>{unit}</small> : null}
      </p>
      <p className="metric-detail">{detail}</p>
    </article>
  );
}
