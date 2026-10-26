const configuredApiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(message, { status, payload } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function buildUrl(path, query = {}) {
  const url = new URL(`${configuredApiBaseUrl}${path}`, window.location.origin);

  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, value);
    }
  });

  return url;
}

function messageFromPayload(payload, fallback) {
  if (typeof payload?.detail === "string") {
    return payload.detail;
  }

  if (typeof payload?.detail?.message === "string") {
    return payload.detail.message;
  }

  return fallback;
}

async function request(path, { query, signal } = {}) {
  let response;

  try {
    response = await fetch(buildUrl(path, query), {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") {
      throw error;
    }

    throw new ApiError(
      "The dashboard could not reach the analysis service. Check that the backend is running.",
    );
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : null;

  if (!response.ok) {
    throw new ApiError(
      messageFromPayload(payload, `Analysis request failed (${response.status}).`),
      { status: response.status, payload },
    );
  }

  if (!payload) {
    throw new ApiError("The analysis service returned an unexpected response.", {
      status: response.status,
    });
  }

  return payload;
}

/**
 * Request the backend's already-calculated day view. Forecast selection,
 * cadence expansion and metrics deliberately remain server-side.
 */
export function getDailyAnalysis({ deliveryDate, decisionCutoffTime, signal }) {
  return request("/intervals", {
    query: {
      delivery_date: deliveryDate,
      decision_cutoff_time: decisionCutoffTime,
    },
    signal,
  });
}
