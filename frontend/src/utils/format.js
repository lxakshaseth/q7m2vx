const MW_FORMATTER = new Intl.NumberFormat("en-GB", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

const WHOLE_MW_FORMATTER = new Intl.NumberFormat("en-GB", {
  maximumFractionDigits: 0,
});

const PERCENT_FORMATTER = new Intl.NumberFormat("en-GB", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

const DATE_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const TIME_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

function toDate(value) {
  return value ? new Date(value) : null;
}

export function formatMw(value, { whole = false } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return (whole ? WHOLE_MW_FORMATTER : MW_FORMATTER).format(value);
}

export function formatSignedMw(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return `${value > 0 ? "+" : ""}${formatMw(value)}`;
}

export function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return PERCENT_FORMATTER.format(value);
}

export function formatDate(value) {
  const date = toDate(value);
  return date && !Number.isNaN(date.getTime()) ? DATE_FORMATTER.format(date) : "—";
}

export function formatTime(value) {
  const date = toDate(value);
  return date && !Number.isNaN(date.getTime()) ? TIME_FORMATTER.format(date) : "—";
}

export function formatDateTime(value) {
  const date = toDate(value);
  return date && !Number.isNaN(date.getTime())
    ? DATE_TIME_FORMATTER.format(date)
    : "—";
}

export function formatChartTime(value) {
  return formatTime(value);
}

export function formatAxisMw(value) {
  if (Math.abs(value) >= 1000) {
    return `${Math.round(value / 1000)}k`;
  }

  return `${Math.round(value)}`;
}

export function formatIsoDateForDisplay(value) {
  if (!value) {
    return "—";
  }

  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}
