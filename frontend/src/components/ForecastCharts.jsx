import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  formatAxisMw,
  formatChartTime,
  formatDateTime,
  formatMw,
  formatSignedMw,
} from "../utils/format";

function buildChartData(intervals) {
  return intervals.map((interval) => ({
    time: interval.deliveryStartLocal,
    actual: interval.actualMw,
    forecast: interval.forecastMw,
    error: interval.errorMw,
    status: interval.status,
    forecastPublishTime: interval.forecastPublishTimeLocal,
  }));
}

function TooltipShell({ title, point, children }) {
  if (!point) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__title">{title}</p>
      <p className="chart-tooltip__time">{formatDateTime(point.time)} UK local</p>
      {children}
    </div>
  );
}

function GenerationTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0].payload;
  return (
    <TooltipShell title="Generation comparison" point={point}>
      <dl className="chart-tooltip__list">
        <div>
          <dt>Actual generation</dt>
          <dd>{formatMw(point.actual)} MW</dd>
        </div>
        <div>
          <dt>Selected day-ahead forecast</dt>
          <dd>{formatMw(point.forecast)} MW</dd>
        </div>
        <div>
          <dt>Forecast publication</dt>
          <dd>
            {point.forecastPublishTime
              ? `${formatDateTime(point.forecastPublishTime)} UK local`
              : "No forecast matched for this delivery hour"}
          </dd>
        </div>
      </dl>
    </TooltipShell>
  );
}

function ErrorTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0].payload;
  const hasMatchedValues = point.error !== null && point.error !== undefined;
  return (
    <TooltipShell title="Forecast error" point={point}>
      <dl className="chart-tooltip__list">
        <div>
          <dt>Forecast − actual</dt>
          <dd>{formatSignedMw(point.error)} MW</dd>
        </div>
        <div>
          <dt>Interpretation</dt>
          <dd>
            {hasMatchedValues
              ? point.error >= 0
                ? "Over-forecast"
                : "Under-forecast"
              : "No matched values"}
          </dd>
        </div>
      </dl>
    </TooltipShell>
  );
}

function ChartEmpty({ children }) {
  return <div className="chart-empty">{children}</div>;
}

export function ForecastCharts({ intervals }) {
  const data = buildChartData(intervals);
  const hasGenerationData = data.some(
    (point) => point.actual !== null || point.forecast !== null,
  );
  const hasErrorData = data.some((point) => point.error !== null);

  return (
    <section className="chart-section" aria-labelledby="charts-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Hourly forecast performance</p>
          <h2 id="charts-heading">Delivery-day profile</h2>
        </div>
        <p>
          Two consecutive half-hourly FUELHH actual observations are averaged to match each hourly forecast window.
        </p>
      </div>

      <div className="chart-grid">
        <article className="chart-card">
          <div className="chart-card__heading">
            <div>
              <h3>Actual generation and selected day-ahead forecast</h3>
              <p>Hourly delivery intervals · MW</p>
            </div>
          </div>
          {hasGenerationData ? (
            <div
              className="chart-canvas"
              role="img"
              aria-label="Line chart comparing actual wind generation and the selected day-ahead forecast in megawatts over the delivery day"
            >
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={data} margin={{ top: 12, right: 20, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="#dce4ec" strokeDasharray="3 4" vertical={false} />
                  <XAxis
                    dataKey="time"
                    minTickGap={32}
                    tickFormatter={formatChartTime}
                    tick={{ fill: "#52606d", fontSize: 12 }}
                    axisLine={{ stroke: "#b9c7d4" }}
                    tickLine={false}
                  />
                  <YAxis
                    width={58}
                    tickFormatter={formatAxisMw}
                    tick={{ fill: "#52606d", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    label={{ value: "MW", angle: -90, position: "insideLeft", fill: "#52606d" }}
                  />
                  <Tooltip content={<GenerationTooltip />} cursor={{ stroke: "#9eb0bf" }} />
                  <Legend verticalAlign="top" align="right" iconType="plainline" />
                  <Line
                    type="monotone"
                    dataKey="actual"
                    name="Actual generation"
                    stroke="#0e7490"
                    strokeWidth={2.5}
                    dot={false}
                    activeDot={{ r: 4 }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="forecast"
                    name="Selected day-ahead forecast"
                    stroke="#ef8b32"
                    strokeWidth={2.5}
                    strokeDasharray="6 4"
                    dot={{ r: 2.5, fill: "#ef8b32", strokeWidth: 0 }}
                    activeDot={{ r: 4 }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <ChartEmpty>No actual or eligible forecast values are available to plot.</ChartEmpty>
          )}
        </article>

        <article className="chart-card">
          <div className="chart-card__heading">
            <div>
              <h3>Forecast error</h3>
              <p>Forecast − actual · MW</p>
            </div>
            <span className="zero-key"><i aria-hidden="true" /> Zero error</span>
          </div>
          {hasErrorData ? (
            <div
              className="chart-canvas"
              role="img"
              aria-label="Bar chart showing forecast error in megawatts over the delivery day, with zero marked"
            >
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={data} margin={{ top: 12, right: 20, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="#dce4ec" strokeDasharray="3 4" vertical={false} />
                  <XAxis
                    dataKey="time"
                    minTickGap={32}
                    tickFormatter={formatChartTime}
                    tick={{ fill: "#52606d", fontSize: 12 }}
                    axisLine={{ stroke: "#b9c7d4" }}
                    tickLine={false}
                  />
                  <YAxis
                    width={58}
                    tickFormatter={formatAxisMw}
                    tick={{ fill: "#52606d", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    label={{ value: "MW", angle: -90, position: "insideLeft", fill: "#52606d" }}
                  />
                  <Tooltip content={<ErrorTooltip />} cursor={{ fill: "rgba(45, 89, 119, 0.08)" }} />
                  <Legend verticalAlign="top" align="right" />
                  <ReferenceLine
                    y={0}
                    stroke="#405568"
                    strokeWidth={1.5}
                    label={{ value: "0 MW", position: "insideTopRight", fill: "#405568", fontSize: 11 }}
                  />
                  <Bar
                    dataKey="error"
                    name="Forecast error"
                    radius={[2, 2, 0, 0]}
                    isAnimationActive={false}
                  >
                    {data.map((point) => (
                      <Cell
                        key={point.time}
                        fill={
                          point.error === null || point.error === undefined
                            ? "#c5d0d7"
                            : point.error >= 0
                              ? "#dc6b3d"
                              : "#197c82"
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <ChartEmpty>
              Forecast error cannot be calculated until at least one actual and eligible
              forecast value are matched.
            </ChartEmpty>
          )}
        </article>
      </div>
    </section>
  );
}
