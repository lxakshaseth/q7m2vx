import { formatDateTime, formatMw, formatSignedMw } from "../utils/format";

const STATUS_LABELS = {
  matched: "Matched",
  missing_actual: "No actual",
  missing_forecast: "No matched forecast",
  missing_both: "No data",
};

function ValueOrMissing({ value, missingLabel = "Not available", signed = false }) {
  if (value === null || value === undefined) {
    return <span className="missing-value">{missingLabel}</span>;
  }

  return signed ? formatSignedMw(value) : formatMw(value);
}

export function IntervalTable({ intervals }) {
  return (
    <section className="table-section" aria-labelledby="table-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Audit trail</p>
          <h2 id="table-heading">Half-hourly delivery detail</h2>
        </div>
        <p>
          The forecast publication is the individual version selected for that delivery
          interval, not the decision cut-off.
        </p>
      </div>

      <div className="table-scroll" tabIndex="0" aria-label="Scrollable half-hourly delivery table">
        <table>
          <caption>
            All timestamps are UK local time. A missing forecast is retained as an
            explicit gap and does not enter the accuracy metrics.
          </caption>
          <thead>
            <tr>
              <th scope="col">Delivery start<br /><span>UK local</span></th>
              <th scope="col">Selected day-ahead forecast<br /><span>MW</span></th>
              <th scope="col">Actual generation<br /><span>MW</span></th>
              <th scope="col">Forecast error<br /><span>MW</span></th>
              <th scope="col">Absolute error<br /><span>MW</span></th>
              <th scope="col">Forecast publication<br /><span>UK local</span></th>
              <th scope="col">Availability</th>
            </tr>
          </thead>
          <tbody>
            {intervals.length === 0 ? (
              <tr>
                <td className="empty-table-message" colSpan="7">
                  No half-hourly delivery intervals were returned by the analysis service.
                </td>
              </tr>
            ) : (
              intervals.map((interval) => (
                <tr key={interval.deliveryStartUtc} className={`interval-row--${interval.status}`}>
                  <td data-label="Delivery start">
                    {formatDateTime(interval.deliveryStartLocal)}
                  </td>
                  <td data-label="Selected forecast">
                    <ValueOrMissing value={interval.forecastMw} missingLabel="No matched forecast" />
                  </td>
                  <td data-label="Actual generation">
                    <ValueOrMissing value={interval.actualMw} missingLabel="No actual value" />
                  </td>
                  <td data-label="Forecast error">
                    <ValueOrMissing value={interval.errorMw} signed missingLabel="—" />
                  </td>
                  <td data-label="Absolute error">
                    <ValueOrMissing value={interval.absoluteErrorMw} missingLabel="—" />
                  </td>
                  <td data-label="Forecast publication">
                    {interval.forecastPublishTimeLocal ? (
                      formatDateTime(interval.forecastPublishTimeLocal)
                    ) : (
                      <span className="missing-value">—</span>
                    )}
                  </td>
                  <td data-label="Availability">
                    <span className={`availability-badge availability-badge--${interval.status}`}>
                      {STATUS_LABELS[interval.status] || interval.status}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
