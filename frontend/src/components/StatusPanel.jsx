export function StatusPanel({ tone = "info", title, children, action }) {
  return (
    <section className={`status-panel status-panel--${tone}`} role={tone === "error" ? "alert" : "status"}>
      <div className="status-icon" aria-hidden="true">
        {tone === "error" ? "!" : tone === "warning" ? "!" : "i"}
      </div>
      <div className="status-content">
        <h2>{title}</h2>
        <div>{children}</div>
      </div>
      {action ? <div className="status-action">{action}</div> : null}
    </section>
  );
}

export function LoadingDashboard() {
  return (
    <section className="loading-dashboard" aria-live="polite" aria-busy="true">
      <div className="loading-heading">
        <span className="loading-spinner" aria-hidden="true" />
        <div>
          <p className="eyebrow">Loading analysis</p>
          <h2>Retrieving the selected forecast comparison</h2>
        </div>
      </div>
      <div className="loading-metrics" aria-hidden="true">
        {Array.from({ length: 5 }, (_, index) => (
          <div className="loading-card" key={index} />
        ))}
      </div>
    </section>
  );
}
