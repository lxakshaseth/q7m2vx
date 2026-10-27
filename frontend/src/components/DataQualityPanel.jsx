import { formatDateTime } from "../utils/format";

function QualityMeasure({ label, value, detail }) {
  return (
    <div className="quality-measure">
      <dt>{label}</dt>
      <dd>{value}</dd>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

export function DataQualityPanel({ metadata, metrics }) {
  const quality = metadata.dataQuality;
  const hasWarnings = metadata.warnings?.length > 0;

  return (
    <section className="quality-panel" aria-labelledby="quality-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Method and quality</p>
          <h2 id="quality-heading">Decision policy and data coverage</h2>
        </div>
        <p>
          The dashboard shows backend-selected values only; it does not estimate or
          fill missing intervals.
        </p>
      </div>

      <div className="quality-layout">
        <div className="policy-card">
          <h3>Decision cut-off</h3>
          <p className="policy-value">{metadata.decisionCutoffTime} Europe/London</p>
          <p>
            Applied on the preceding local calendar day. This is an adjustable demo
            assumption, not an assignment requirement.
          </p>
          <div className="policy-divider" />
          <h3>Forecast publication time</h3>
          <p>
            Each row reports the publication timestamp of the version selected at or
            before the decision cut-off. It can differ across delivery hours.
          </p>
          <div className="policy-divider" />
          <h3>Exact interval matching</h3>
          <p>
            WINDFOR is hourly and FUELHH is half-hourly. Values join only when their
            startTime is identical; no :30 forecast is invented or carried forward.
          </p>
        </div>

        <dl className="quality-grid">
          <QualityMeasure
            label="Expected delivery intervals"
            value={metrics.expectedIntervalCount}
            detail="Half-hourly grid"
          />
          <QualityMeasure
            label="Actual intervals available"
            value={metrics.actualIntervalCount}
            detail="Latest actual revision"
          />
          <QualityMeasure
            label="Eligible forecast intervals"
            value={metrics.eligibleForecastIntervalCount}
            detail="Before selected cut-off"
          />
          <QualityMeasure
            label="Matched intervals"
            value={metrics.matchedIntervalCount}
            detail="Used in metrics"
          />
          <QualityMeasure
            label="Actual revisions resolved"
            value={quality.actualRevisionsResolved}
            detail="Latest publication retained"
          />
          <QualityMeasure
            label="Forecast versions selected"
            value={quality.selectedNativeForecastCount}
            detail="Native hourly targets"
          />
        </dl>
      </div>

      <div className="quality-notes">
        <p>
          <strong>Forecast cadence:</strong> {metadata.analysisResolution}
        </p>
        <p>
          <strong>Publication history retrieved:</strong>{" "}
          {formatDateTime(metadata.forecastPublicationFromUtc)} to{" "}
          {formatDateTime(metadata.forecastPublicationToUtc)} UK local.
        </p>
        <p>
          <strong>Analysis retrieved:</strong> {formatDateTime(metadata.retrievedAtUtc)} UK
          local.
        </p>
      </div>

      <div className="data-sources" aria-labelledby="data-sources-heading">
        <div>
          <p className="eyebrow">Official data sources</p>
          <h3 id="data-sources-heading">Elexon BMRS generation data</h3>
          <p>
            The backend retrieves public source records directly, applies the selected
            decision cut-off, and returns the analysed values shown above.
          </p>
        </div>
        <ul className="data-source-list">
          <li>
            <a
              href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream"
              target="_blank"
              rel="noreferrer"
            >
              FUELHH actual generation
            </a>
            <span>Half-hourly Great Britain generation, filtered to WIND.</span>
          </li>
          <li>
            <a
              href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream"
              target="_blank"
              rel="noreferrer"
            >
              WINDFOR forecast history
            </a>
            <span>Published wind forecasts used for latest-before-cut-off selection.</span>
          </li>
        </ul>
      </div>

      {hasWarnings ? (
        <div className="quality-warnings" role="status">
          <h3>Backend data-quality notes</h3>
          <ul>
            {metadata.warnings.map((warning, index) => (
              <li key={`${warning}-${index}`}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
