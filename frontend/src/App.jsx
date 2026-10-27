import { useEffect, useState } from "react";
import { getDailyAnalysis } from "./api/client";
import { AnalysisFilters } from "./components/AnalysisFilters";
import { DashboardHeader } from "./components/DashboardHeader";
import { DataQualityPanel } from "./components/DataQualityPanel";
import { ForecastCharts } from "./components/ForecastCharts";
import { IntervalTable } from "./components/IntervalTable";
import { MetricCard } from "./components/MetricCard";
import { LoadingDashboard, StatusPanel } from "./components/StatusPanel";
import { formatMw, formatPercent } from "./utils/format";

const DEFAULT_DELIVERY_DATE = "2026-01-15";
const DEFAULT_DECISION_CUTOFF = "12:00";

function MetricSummary({ metrics }) {
  const coverageIsPartial =
    metrics.forecastCoveragePercent !== null && metrics.forecastCoveragePercent < 100;
  const hasMissingIntervals =
    metrics.missingActualIntervalCount > 0 || metrics.missingForecastIntervalCount > 0;
  const biasDetail =
    metrics.biasMw === null
      ? "Requires matched values"
      : metrics.biasMw > 0
        ? "Positive = over-forecast"
        : metrics.biasMw < 0
          ? "Negative = under-forecast"
          : "No average bias";

  return (
    <section className="metrics-section" aria-labelledby="metrics-heading">
      <div className="section-heading section-heading--metrics">
        <div>
          <p className="eyebrow">Selected delivery-day results</p>
          <h2 id="metrics-heading">Forecast accuracy summary</h2>
        </div>
        <p>Metrics use matched actual and cutoff-eligible forecast intervals only.</p>
      </div>

      <div className="metric-grid">
        <MetricCard
          label="Mean Absolute Error (MAE)"
          value={formatMw(metrics.maeMw)}
          unit="MW"
          detail="Typical miss across matched intervals"
          status="teal"
        />
        <MetricCard
          label="Root Mean Squared Error (RMSE)"
          value={formatMw(metrics.rmseMw)}
          unit="MW"
          detail="Weights larger misses more heavily"
          status="navy"
        />
        <MetricCard
          label="Weighted Absolute Percentage Error (WAPE)"
          value={formatPercent(metrics.wapePercent)}
          unit="%"
          detail="Absolute error relative to actual generation"
          status="amber"
        />
        <MetricCard
          label="Forecast bias"
          value={formatMw(metrics.biasMw)}
          unit="MW"
          detail={biasDetail}
          status={metrics.biasMw !== null && metrics.biasMw > 0 ? "coral" : "teal"}
        />
        <MetricCard
          label="Matched delivery intervals"
          value={metrics.matchedIntervalCount}
          unit={`of ${metrics.expectedIntervalCount} expected`}
          detail={
            hasMissingIntervals || coverageIsPartial
              ? "Gaps are excluded; see data quality"
              : "All available actual intervals covered"
          }
          status={coverageIsPartial || hasMissingIntervals ? "amber" : "navy"}
        />
        <MetricCard
          label="Forecast coverage"
          value={formatPercent(metrics.forecastCoveragePercent)}
          unit={metrics.forecastCoveragePercent === null ? "" : "%"}
          detail="Matched intervals relative to available actuals"
          status={coverageIsPartial || hasMissingIntervals ? "amber" : "teal"}
        />
      </div>
    </section>
  );
}

function CoverageNotice({ metrics, metadata }) {
  const noActuals = metrics.actualIntervalCount === 0;
  const noMatches = metrics.matchedIntervalCount === 0;
  const hasPartialCoverage =
    metrics.missingActualIntervalCount > 0 ||
    metrics.missingForecastIntervalCount > 0 ||
    metrics.matchedIntervalCount < metrics.expectedIntervalCount;

  if (noActuals) {
    return (
      <StatusPanel tone="warning" title="No actual generation is available for this delivery day">
        <p>
          The backend returned the expected half-hourly grid but no actual wind values.
          Accuracy metrics remain unavailable rather than being estimated.
        </p>
      </StatusPanel>
    );
  }

  if (noMatches) {
    return (
      <StatusPanel tone="warning" title="No forecast could be matched">
        <p>
          Actual generation is available, but no forecast shares an exact start time
          and meets the selected {metadata.decisionCutoffTime} Europe/London cut-off.
          No accuracy metric has been calculated.
        </p>
      </StatusPanel>
    );
  }

  if (hasPartialCoverage) {
    const isHourly = metadata.alignmentMethod === "hourly_aggregated";
    return (
      <StatusPanel tone="warning" title="Partial coverage — interpret the metrics with care">
        <p>
          {metrics.matchedIntervalCount} of {metrics.expectedIntervalCount} expected{" "}
          {isHourly ? "hourly" : "half-hourly"} delivery intervals are matched.{" "}
          {isHourly
            ? "Consecutive half-hours are averaged ((:00 + :30)/2); any delivery hour with an incomplete actual pair is marked missing and excluded from metrics."
            : "WINDFOR is hourly, so exact start-time matching intentionally leaves intervening :30 rows without a forecast; all gaps remain visible and are excluded from metrics."}
        </p>
      </StatusPanel>
    );
  }

  return null;
}

function EmptyDataNotice({ deliveryDate }) {
  return (
    <StatusPanel tone="warning" title="No delivery intervals were returned">
      <p>
        The analysis service returned no half-hourly rows for {deliveryDate}. No
        placeholder values or estimated metrics have been shown. Try refreshing the
        analysis, or select another January delivery date.
      </p>
    </StatusPanel>
  );
}

export default function App() {
  const [deliveryDate, setDeliveryDate] = useState(DEFAULT_DELIVERY_DATE);
  const [decisionCutoffTime, setDecisionCutoffTime] = useState(DEFAULT_DECISION_CUTOFF);
  const [alignmentMethod, setAlignmentMethod] = useState("hourly_aggregated");
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [viewState, setViewState] = useState({
    status: "loading",
    data: null,
    error: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    setViewState({ status: "loading", data: null, error: null });

    getDailyAnalysis({
      deliveryDate,
      decisionCutoffTime,
      alignmentMethod,
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) {
          setViewState({ status: "ready", data, error: null });
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setViewState({ status: "error", data: null, error });
        }
      });

    return () => controller.abort();
  }, [deliveryDate, decisionCutoffTime, alignmentMethod, refreshIndex]);

  const refreshAnalysis = () => setRefreshIndex((index) => index + 1);
  const isLoading = viewState.status === "loading";
  const response = viewState.data;
  const hasIntervals = Boolean(response?.intervals?.length);
  const liveMessage =
    viewState.status === "loading"
      ? "Loading selected delivery analysis."
      : viewState.status === "ready"
        ? "Selected delivery analysis loaded."
        : "Selected delivery analysis could not be loaded.";
  const retryButton = (
    <button className="secondary-button" type="button" onClick={refreshAnalysis}>
      Try again
    </button>
  );

  return (
    <div className="app-shell">
      <DashboardHeader
        deliveryDate={deliveryDate}
        decisionCutoffTime={decisionCutoffTime}
      />

      <main>
        <AnalysisFilters
          deliveryDate={deliveryDate}
          decisionCutoffTime={decisionCutoffTime}
          alignmentMethod={alignmentMethod}
          isLoading={isLoading}
          onDeliveryDateChange={setDeliveryDate}
          onDecisionCutoffChange={setDecisionCutoffTime}
          onAlignmentMethodChange={setAlignmentMethod}
          onRefresh={refreshAnalysis}
        />

        <p className="screen-reader-only" aria-live="polite">
          {liveMessage}
        </p>

        {isLoading ? <LoadingDashboard /> : null}

        {viewState.status === "error" ? (
          <StatusPanel
            tone="error"
            title="The selected analysis could not be loaded"
            action={retryButton}
          >
            <p>{viewState.error.message}</p>
            <p className="status-panel__hint">
              The dashboard has not substituted any sample or estimated values.
            </p>
          </StatusPanel>
        ) : null}

        {response ? (
          <div className="analysis-content">
            {hasIntervals ? (
              <>
                <CoverageNotice metrics={response.metrics} metadata={response.metadata} />
                <MetricSummary metrics={response.metrics} />
                <ForecastCharts intervals={response.intervals} />
                <IntervalTable intervals={response.intervals} />
              </>
            ) : (
              <EmptyDataNotice deliveryDate={deliveryDate} />
            )}
            <DataQualityPanel metadata={response.metadata} metrics={response.metrics} />
          </div>
        ) : null}
      </main>

      <footer className="app-footer">
        <p>
          Data is retrieved and analysed by the backend from Elexon BMRS FUELHH and
          WINDFOR sources. Values shown here are live analysis results, not embedded
          sample data.
        </p>
      </footer>
    </div>
  );
}
