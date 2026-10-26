import { formatIsoDateForDisplay } from "../utils/format";

const DELIVERY_DATES = Array.from({ length: 31 }, (_, index) => {
  const day = String(index + 1).padStart(2, "0");
  return `2026-01-${day}`;
});

const CUTOFF_TIMES = Array.from({ length: 48 }, (_, index) => {
  const hour = String(Math.floor(index / 2)).padStart(2, "0");
  const minute = index % 2 === 0 ? "00" : "30";
  return `${hour}:${minute}`;
});

export function AnalysisFilters({
  deliveryDate,
  decisionCutoffTime,
  isLoading,
  onDeliveryDateChange,
  onDecisionCutoffChange,
  onRefresh,
}) {
  return (
    <section className="filter-card" aria-labelledby="filter-heading">
      <div className="filter-copy">
        <p className="eyebrow">View controls</p>
        <h2 id="filter-heading">Choose the decision context</h2>
        <p>
          Results refresh when you change either selection. Times are shown in
          Europe/London.
        </p>
      </div>

      <form
        className="filter-controls"
        onSubmit={(event) => {
          event.preventDefault();
          onRefresh();
        }}
      >
        <label className="control-field" htmlFor="delivery-date">
          <span>Delivery date</span>
          <select
            id="delivery-date"
            value={deliveryDate}
            onChange={(event) => onDeliveryDateChange(event.target.value)}
          >
            {DELIVERY_DATES.map((date) => (
              <option key={date} value={date}>
                {formatIsoDateForDisplay(date)}
              </option>
            ))}
          </select>
        </label>

        <label className="control-field" htmlFor="decision-cutoff">
          <span>Day-before decision cut-off</span>
          <select
            id="decision-cutoff"
            value={decisionCutoffTime}
            onChange={(event) => onDecisionCutoffChange(event.target.value)}
            aria-describedby="cutoff-help"
          >
            {CUTOFF_TIMES.map((time) => (
              <option key={time} value={time}>
                {time}
              </option>
            ))}
          </select>
        </label>

        <button className="refresh-button" type="submit" disabled={isLoading}>
          {isLoading ? "Refreshing…" : "Refresh analysis"}
        </button>
      </form>

      <p className="assumption-note" id="cutoff-help">
        <span aria-hidden="true">i</span>
        <span>
          <strong>{decisionCutoffTime} Europe/London</strong> is a configurable demo
          assumption. The assignment does not specify a required decision time.
        </span>
      </p>
    </section>
  );
}
