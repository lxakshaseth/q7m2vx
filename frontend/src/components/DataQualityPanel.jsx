import { formatDateTime, formatIsoDateForDisplay, formatPercent } from "../utils/format";

function QualityMeasure({ label, value, detail, highlight }) {
  return (
    <div className={`quality-measure ${highlight ? "quality-measure--highlight" : ""}`}>
      <dt>{label}</dt>
      <dd>{value !== null && value !== undefined ? value.toLocaleString("en-GB") : "—"}</dd>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function CoverageCard({
  title,
  eyebrow,
  badge,
  coverage,
  alignmentMethod,
}) {
  const isHourly = alignmentMethod === "hourly_aggregated";
  const denominatorText =
    coverage.coverageDenominator ||
    (isHourly
      ? "available actual intervals (complete pairs)"
      : "available actual intervals");
  const coverageDisplay =
    coverage.forecastCoveragePercent !== null &&
    coverage.forecastCoveragePercent !== undefined
      ? formatPercent(coverage.forecastCoveragePercent)
      : "—";

  return (
    <div className="coverage-card">
      <div className="coverage-header">
        <div>
          <span className="coverage-badge">{badge}</span>
          <p className="eyebrow">{eyebrow}</p>
          <h3>{title}</h3>
        </div>
        <div className="coverage-summary-note">
          Coverage: <strong>{coverageDisplay}</strong>
          <div>
            <small>
              Denominator: {coverage.matchedIntervalCount} matched /{" "}
              {coverage.completeActualPairsCount} {denominatorText}
            </small>
          </div>
        </div>
      </div>

      <dl className="quality-grid quality-grid--coverage">
        <QualityMeasure
          label={isHourly ? "Expected hourly forecast intervals" : "Expected intervals"}
          value={coverage.expectedIntervalCount}
          detail={isHourly ? "Target delivery hours" : "Half-hourly delivery grid"}
        />
        <QualityMeasure
          label={isHourly ? "Available half-hourly FUELHH records" : "Actual observations"}
          value={coverage.actualHalfHourlyRecordCount}
          detail="Raw half-hourly WIND outturn"
        />
        <QualityMeasure
          label={isHourly ? "Complete hourly actual pairs" : "Complete actual intervals"}
          value={coverage.completeActualPairsCount}
          detail={isHourly ? "Both :00 and :30 present" : "Valid actual outturns"}
        />
        <QualityMeasure
          label="Incomplete pairs"
          value={coverage.incompleteActualPairsCount}
          detail={
            coverage.incompleteActualPairsCount > 0
              ? "Missing half-hour excluded from metrics"
              : "Zero missing half-hours"
          }
          highlight={coverage.incompleteActualPairsCount > 0}
        />
        <QualityMeasure
          label="Eligible forecasts"
          value={coverage.eligibleForecastCount}
          detail="Published at or before 12:00 cutoff"
        />
        <QualityMeasure
          label="Matched intervals"
          value={coverage.matchedIntervalCount}
          detail="Both forecast & complete actual available"
        />
        <QualityMeasure
          label="Unmatched intervals"
          value={coverage.unmatchedIntervalCount}
          detail={
            coverage.unmatchedIntervalCount > 0
              ? "Expected intervals missing forecast or actual"
              : "Full delivery alignment"
          }
          highlight={coverage.unmatchedIntervalCount > 0}
        />
        <QualityMeasure
          label="Forecast coverage"
          value={coverageDisplay}
          detail={`Denominator: ${coverage.matchedIntervalCount} / ${coverage.completeActualPairsCount} ${denominatorText}`}
        />
      </dl>
    </div>
  );
}

export function DataQualityPanel({
  metadata,
  metrics,
  monthlyMetrics,
  dayCoverage,
  monthlyCoverage,
  deliveryDate,
}) {
  const quality = metadata.dataQuality;
  const hasWarnings = metadata.warnings?.length > 0;
  const isHourly = metadata.alignmentMethod === "hourly_aggregated";

  // Resolve monthly coverage, falling back gracefully if from legacy payload
  const resolvedMonthlyCoverage = monthlyCoverage || {
    expectedIntervalCount:
      monthlyMetrics?.expectedIntervalCount ?? quality.expectedNativeForecastTargetCount,
    actualHalfHourlyRecordCount:
      quality.normalizedActualIntervalCount || quality.sourceActualRecordCount,
    completeActualPairsCount: quality.completeActualPairsCount,
    incompleteActualPairsCount: quality.incompleteActualPairsCount,
    eligibleForecastCount:
      monthlyMetrics?.eligibleForecastIntervalCount ?? quality.selectedNativeForecastCount,
    matchedIntervalCount:
      monthlyMetrics?.matchedIntervalCount ?? quality.selectedNativeForecastCount,
    unmatchedIntervalCount: Math.max(
      0,
      (monthlyMetrics?.expectedIntervalCount ?? quality.expectedNativeForecastTargetCount) -
        (monthlyMetrics?.matchedIntervalCount ?? quality.selectedNativeForecastCount)
    ),
    forecastCoveragePercent: monthlyMetrics?.forecastCoveragePercent,
    coverageDenominator: isHourly
      ? "available actual intervals (complete pairs)"
      : "available actual intervals",
  };

  // Resolve selected day coverage, falling back gracefully if from legacy payload
  const resolvedDayCoverage = dayCoverage || {
    expectedIntervalCount: metrics.expectedIntervalCount,
    actualHalfHourlyRecordCount: isHourly
      ? metrics.actualIntervalCount * 2
      : metrics.actualIntervalCount,
    completeActualPairsCount: metrics.actualIntervalCount,
    incompleteActualPairsCount: 0,
    eligibleForecastCount: metrics.eligibleForecastIntervalCount,
    matchedIntervalCount: metrics.matchedIntervalCount,
    unmatchedIntervalCount: Math.max(
      0,
      metrics.expectedIntervalCount - metrics.matchedIntervalCount
    ),
    forecastCoveragePercent: metrics.forecastCoveragePercent,
    coverageDenominator: isHourly
      ? "available actual intervals (complete pairs)"
      : "available actual intervals",
  };

  return (
    <section className="quality-panel" aria-labelledby="quality-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Data quality & audit</p>
          <h2 id="quality-heading">Decision policy and data coverage audit</h2>
        </div>
        <p>
          Data coverage and error metrics are audited separately across the January 2026
          benchmark period and the chosen delivery date. The service matches forecasts
          strictly against available actuals without extrapolation or data fabrication.
        </p>
      </div>

      <div className="policy-card">
        <h3>Decision cut-off</h3>
        <p className="policy-value">{metadata.decisionCutoffTime} Europe/London</p>
        <p>
          Applied on the preceding local calendar day. This is an adjustable demo
          assumption, not an assignment requirement.
        </p>
        <div className="policy-divider" />
        <h3>Forecast publication selection</h3>
        <p>
          For each delivery hour, the pipeline selects the latest forecast published at or
          before the 12:00 day-ahead cutoff. Missing forecasts or publication versions
          published after the cutoff are never backfilled or substituted.
        </p>
        <div className="policy-divider" />
        <h3>Cadence alignment</h3>
        <p>
          {isHourly
            ? "Hourly aggregated: two consecutive half-hourly FUELHH outturn observations (:00 and :30) are averaged ((Actual_00 + Actual_30)/2.0) to match each 1-hour WINDFOR delivery window without duplicating forecasts. Delivery hours with incomplete actual pairs are marked missing and excluded from error metrics."
            : "Exact interval matching: values match only on identical startTime; intervening :30 half-hours remain missing without fabricating data."}
        </p>
      </div>

      {/* Requirement 1 & 2: Dedicated January Monthly Data Coverage Section */}
      <CoverageCard
        title="January monthly data coverage"
        eyebrow="Full-month benchmark audit (January 1–31, 2026)"
        badge="Full month (744 hours)"
        coverage={resolvedMonthlyCoverage}
        alignmentMethod={metadata.alignmentMethod}
      />

      {/* Requirement 1 & 3: Dedicated Selected Delivery-Day Data Coverage Section */}
      <CoverageCard
        title="Selected delivery-day data coverage"
        eyebrow={`Selected delivery date · ${formatIsoDateForDisplay(deliveryDate)}`}
        badge="Selected day (24 hours)"
        coverage={resolvedDayCoverage}
        alignmentMethod={metadata.alignmentMethod}
      />

      <div className="quality-layout quality-layout--audit">
        <div className="policy-card">
          <h3>Data ingestion and normalization audit</h3>
          <p>
            Low-level reconciliation across source streams from Elexon BMRS before error
            calculations.
          </p>
          <dl className="quality-grid">
            <QualityMeasure
              label="Actual exact duplicates removed"
              value={quality.actualExactDuplicatesRemoved}
              detail="Bit-identical FUELHH rows"
            />
            <QualityMeasure
              label="Actual revisions resolved"
              value={quality.actualRevisionsResolved}
              detail="Latest published revision retained"
            />
            <QualityMeasure
              label="Forecast duplicates removed"
              value={quality.forecastExactDuplicatesRemoved}
              detail="Identical WINDFOR versions"
            />
            <QualityMeasure
              label="Forecast versions retained"
              value={quality.normalizedForecastVersionCount}
              detail="Evaluated across cutoff window"
            />
          </dl>
        </div>
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
