import { formatIsoDateForDisplay } from "../utils/format";

export function DashboardHeader({ deliveryDate, decisionCutoffTime }) {
  return (
    <header className="dashboard-header">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div>
          <p className="eyebrow">Great Britain wind generation analysis</p>
          <h1>Wind Forecast Intelligence</h1>
          <p className="header-subtitle">
            Evaluates national wind generation forecasts against actual Great Britain
            generation.
          </p>
        </div>
      </div>

      <dl className="header-context" aria-label="Current analysis scope">
        <div>
          <dt>Analysis period</dt>
          <dd>January 2026</dd>
        </div>
        <div>
          <dt>Selected delivery</dt>
          <dd>{formatIsoDateForDisplay(deliveryDate)}</dd>
        </div>
        <div>
          <dt>Decision cut-off</dt>
          <dd>{decisionCutoffTime} Europe/London</dd>
        </div>
      </dl>
    </header>
  );
}
