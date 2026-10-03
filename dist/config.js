window.SKILLOR_API_URL = window.SKILLOR_API_URL ||
  (location.hostname === "localhost" || location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : localStorage.getItem("skillor_api_url") || "");
