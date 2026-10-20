"use strict";

const state = {runs: [], view: "scenario", run_id: null, data: null, artifact: null, offset: 0, total: 0, job_id: sessionStorage.getItem("gsm_job"), uploads: [], selection: 0};
const titles = {
  scenario: ["Price scenario", "Explore price changes within the model’s supported scope."],
  simulation: ["Marketplace simulation", "Requests, driver offers, completed trips and gross pay."],
  demand: ["Prepared demand", "Verified request rates and the frozen fleet snapshot for simulation."],
  policy: ["Policies and experiments", "Finite policy comparisons, independent checks and experiment handoff."],
  observed: ["Observed market", "Public TLC completed trips · New York local time · USD."],
  method: ["Method evaluation", "Compare fitted responses with known synthetic effects."],
  actions: ["Run & data", "Add a CSV or create a new result with the Python engine."]
};
const policy_views = {compare_policies: ["policy_comparison.json", "policy_summary.csv"], evaluate_policies: ["policy_evaluation.json", "policy_evaluation_summary.csv"], plan_experiment: ["experiment_plan.json", "experiment_schedule.csv"], reconcile_experiment: ["experiment_reconciliation.json"], export_handoff: ["handoff.json"]};
const $ = (selector) => document.querySelector(selector);
const format_value = (value, digits = 2) => value === null || value === undefined ? "—" : typeof value === "number" ? value.toLocaleString(undefined, {maximumFractionDigits: digits}) : typeof value === "object" ? JSON.stringify(value) : String(value);

function element(tag, text, class_name) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (class_name) node.className = class_name;
  return node;
}

function message(text, error = false) {
  const node = $("#message");
  node.hidden = !text;
  node.textContent = text || "";
  node.dataset.error = String(error);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  const token = sessionStorage.getItem("gsm_token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, {...options, headers});
  if (response.status === 401) $("#access-form").hidden = false;
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map((item) => `${item.loc.join(".")}: ${item.msg}`).join("; ") : body.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response;
}

async function post_json(path, data) {
  return (await api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)})).json();
}

async function perform(button, task) {
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  message("");
  try { await task(); }
  catch (error) { message(error.message, true); }
  finally { button.disabled = false; button.removeAttribute("aria-busy"); }
}

function options_for(select, values, selected) {
  select.replaceChildren(...values.map(([value, label]) => {
    const option = element("option", label);
    option.value = value;
    return option;
  }));
  if (values.some(([value]) => String(value) === String(selected))) select.value = selected;
}

function matches_view(run) {
  if (state.view === "simulation") return run.stages.includes("simulate_marketplace");
  if (state.view === "demand") return run.stages.includes("prepare_demand");
  if (state.view === "policy") return Object.keys(policy_views).some((stage) => run.stages.includes(stage));
  return run.stages.some((stage) => ["fit", "freeze_choice"].includes(stage));
}

function view_for_run(run) {
  if (run.stages.includes("simulate_marketplace")) return "simulation";
  if (Object.keys(policy_views).some((stage) => run.stages.includes(stage))) return "policy";
  if (run.stages.includes("prepare_demand")) return "demand";
  return "scenario";
}

async function load_runs(preferred) {
  const payload = await (await api("/api/runs")).json();
  state.runs = payload.runs;
  const dgp = $("#dgp-filter").value;
  const seed = $("#seed-filter").value;
  options_for($("#dgp-filter"), [["", "All DGPs"], ...[...new Set(state.runs.map((run) => run.dgp))].sort().map((value) => [value, value])], dgp);
  options_for($("#seed-filter"), [["", "All seeds"], ...[...new Set(state.runs.map((run) => run.seed))].sort((a, b) => a - b).map((value) => [value, value])], seed);
  const initial = preferred || state.run_id || new URLSearchParams(location.search).get("run") || payload.initial_run_id;
  const requested = state.runs.find((run) => run.run_id === initial);
  if (requested && state.view !== "actions" && !matches_view(requested)) {
    await change_view(view_for_run(requested), initial);
  } else if (state.view !== "actions") await select_runs(initial);
  update_action();
}

async function select_runs(preferred) {
  const matching = state.runs.filter((run) => matches_view(run) && (!$("#dgp-filter").value || run.dgp === $("#dgp-filter").value) && (!$("#seed-filter").value || String(run.seed) === $("#seed-filter").value));
  options_for($("#run-select"), matching.map((run) => [run.run_id, run.run_id]), preferred);
  if (!matching.length) {
    state.run_id = null;
    state.data = null;
    $("#results").replaceChildren(element("p", "No completed run matches this view. Choose another filter or create a run in Run & data.", "notice"));
    $("#explorer").hidden = $("#audit").hidden = $("#scenario-controls").hidden = true;
    $("#run-note").textContent = "";
    return;
  }
  await load_run($("#run-select").value);
}

async function change_view(view, preferred) {
  state.selection += 1;
  state.view = view;
  $("#view-title").textContent = titles[view][0];
  $("#view-description").textContent = titles[view][1];
  document.querySelectorAll("nav button").forEach((button) => {
    if (button.dataset.view === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  $("#actions").hidden = view !== "actions";
  ["#run-picker", "#run-note", "#results"].forEach((selector) => $(selector).hidden = view === "actions");
  $("#scenario-controls").hidden = $("#explorer").hidden = $("#audit").hidden = true;
  message("");
  if (view === "actions") { update_action(); return; }
  await select_runs(preferred || state.run_id);
}

function metrics(container, values) {
  const list = element("dl", undefined, "metrics");
  for (const [label, value] of values) {
    const item = element("div", undefined, "metric");
    item.append(element("dt", label), element("dd", format_value(value)));
    list.append(item);
  }
  container.append(list);
}

function table(container, rows, columns) {
  container.replaceChildren();
  if (!rows.length) { container.append(element("p", "No rows in this selection.", "muted")); return; }
  columns = columns || [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const wrapper = element("div", undefined, "table-wrap");
  wrapper.tabIndex = 0;
  wrapper.setAttribute("aria-label", "Scrollable data table");
  const output = element("table");
  const head = element("thead");
  const header = element("tr");
  columns.forEach((column) => { const th = element("th", column); th.scope = "col"; header.append(th); });
  head.append(header);
  const body = element("tbody");
  for (const row of rows) {
    const tr = element("tr");
    columns.forEach((column) => { const td = element("td", format_value(row[column], 6)); td.title = td.textContent; tr.append(td); });
    body.append(tr);
  }
  output.append(head, body);
  wrapper.append(output);
  container.append(wrapper);
}

function json_details(container, title, value) {
  const details = element("details");
  details.append(element("summary", title), element("pre", JSON.stringify(value, null, 2)));
  container.append(details);
}

function bars(container, rows, label_key, value_key, before_key) {
  if (!rows.length) return;
  const max_value = Math.max(...rows.flatMap((row) => [Math.abs(row[value_key] || 0), Math.abs(row[before_key] || 0)]), 0.00001);
  const chart = element("div", undefined, "chart");
  chart.setAttribute("role", "figure");
  chart.setAttribute("aria-label", `${value_key} by ${label_key}; exact values also appear in the table`);
  rows.slice(0, 24).forEach((row) => {
    for (const key of before_key ? [before_key, value_key] : [value_key]) {
      if (row[key] === null || row[key] === undefined) continue;
      const line = element("div", undefined, "chart-row");
      const label = element("span", `${row[label_key]}${before_key ? key === before_key ? " · before" : " · after" : ""}`, "chart-label");
      label.title = label.textContent;
      const track = element("div", undefined, "bar-track");
      const bar = element("div", undefined, `bar${key === before_key ? " before" : ""}${row[key] < 0 ? " negative" : ""}`);
      bar.style.width = `${Math.abs(row[key]) / max_value * 100}%`;
      track.append(bar);
      line.append(label, track, element("span", format_value(row[key], 3), "chart-value"));
      chart.append(line);
    }
  });
  container.append(chart);
}

async function load_run(run_id) {
  const selection = ++state.selection;
  $("#results").replaceChildren(element("p", "Verifying source artifacts…", "muted"));
  $("#explorer").hidden = $("#audit").hidden = $("#scenario-controls").hidden = true;
  const data = await (await api(`/api/runs/${encodeURIComponent(run_id)}`)).json();
  if (selection !== state.selection) return;
  state.run_id = run_id;
  state.data = data;
  const url = new URL(location.href);
  url.searchParams.set("run", run_id);
  history.replaceState(null, "", url);
  $("#run-note").textContent = `${run_id} · ${data.manifest.created_at} · checksums verified`;
  $("#audit-json").textContent = JSON.stringify(data.manifest, null, 2);
  $("#audit").hidden = false;
  $("#results").replaceChildren();
  let preferred;
  const prefix = `runs/${run_id}/`;
  if (state.view === "scenario") {
    const config = data.manifest.choice_source?.source_config || data.manifest.config;
    options_for($("#estimator"), Object.keys(data.manifest.model_results || {}).map((value) => [value, value]), config.model.scenario_estimator);
    options_for($("#zone"), [["", "All zones"], ...(data.zones || []).map((value) => [value, value])]);
    $("#n-sessions").value = config.scenario.n_sessions;
    $("#scenario-controls").hidden = false;
    await forecast();
    return;
  } else if (state.view === "simulation") {
    render_simulation(data.simulation);
    preferred = prefix + "requests.csv";
  } else if (state.view === "method") {
    $("#results").append(element("p", "Controlled simulation · evidence C. A single run does not measure interval coverage. Hidden confounding remains a limitation.", "notice"));
    if (Object.values(data.manifest.model_results || {}).includes("not_identified")) $("#results").append(element("p", "Prices move together in this run. Their separate responses cannot be identified; check each estimator’s status before interpreting coefficients.", "notice"));
    preferred = prefix + "method_metrics.csv";
  } else if (state.view === "demand") {
    json_details($("#results"), "Demand readiness, scope and assumptions", data.results["demand_result.json"]);
    preferred = prefix + "demand_plan.csv";
  } else if (state.view === "observed") {
    if (!data.manifest.observed_build) {
      $("#results").append(element("p", "This run uses synthetic contexts. No observed TLC trips are attached.", "notice"));
      return;
    }
    preferred = data.manifest.observed_build.mart.replaceAll("\\", "/");
  } else if (state.view === "policy") {
    const stage = Object.keys(policy_views).find((name) => data.manifest.stages[name]?.status === "succeeded");
    const [result_name, table_name] = policy_views[stage];
    const result = await read_json_artifact(prefix + result_name);
    if (selection !== state.selection) return;
    $("#results").append(element("p", "Synthetic evidence C · GSM calibration, real profit and deployment remain unevaluated.", "notice"));
    if (stage === "compare_policies") {
      metrics($("#results"), [["Selected policy", result.selected_policy_id || "None qualifies"], ["Trajectories", result.attempted_trajectories], ["Failed trajectories", result.failed_trajectories]]);
      $("#results").append(element("p", result.uncertainty.method, "muted"), element("p", result.guardrail_scope, "muted"));
      $("#results").append(element("h2", "Policy objective · point estimates"));
      bars($("#results"), result.decisions, "policy_id", "score");
      const decisions = element("div");
      table(decisions, result.decisions.map((row) => ({Policy: row.policy_id, Score: row.score, "Conservative gain": row.conservative_gain, Guardrails: row.guardrails.length ? [...new Set(row.guardrails.map((guardrail) => guardrail.status))].join(", ") : "Not declared", Decision: row.status, Reasons: row.reasons.join("; ") || "—"})));
      $("#results").append(decisions);
      json_details($("#results"), "Conditional economics", result.economics);
    } else if (stage === "plan_experiment") {
      json_details($("#results"), "Power and sample-size assumptions", result.power);
      json_details($("#results"), "Frozen prediction", result.prediction);
    }
    json_details($("#results"), "Results and assumptions", result);
    preferred = prefix + (table_name || result_name);
  }
  const files = data.files.filter((name) => !name.endsWith(".parquet") || !data.files.includes(name.replace(/\.parquet$/, ".csv")));
  options_for($("#artifact-select"), files.map((name) => [name, name.startsWith(prefix) ? name.slice(prefix.length) : name]), preferred);
  $("#explorer").hidden = !files.length;
  $("#table-filters").hidden = !["observed", "method"].includes(state.view);
  document.querySelectorAll("[data-observed-filter]").forEach((label) => label.hidden = state.view !== "observed");
  $("#method-filter").hidden = state.view !== "method";
  options_for($("#table-estimator"), [["", "All estimators"], ...Object.keys(data.manifest.model_results || {}).map((value) => [value, value])]);
  $("#table-filters").reset();
  state.offset = 0;
  if (files.length) await load_artifact();
}

function render_simulation(data) {
  const {result, spec} = data;
  const {summary, scope, offers, earnings} = result;
  const root = $("#results");
  root.append(element("p", `Evidence ${result.evidence_level} · ${result.source_kind} · ${result.calibration_status}. Operational confidence intervals are unavailable.`, "notice"));
  root.append(element("p", `${scope.horizon_start} to ${scope.horizon_end}`, "muted"));
  metrics(root, [[scope.online_drivers === undefined ? "Roster vehicles" : "Online drivers", scope.online_drivers ?? scope.vehicles], ["Created requests", summary.created_requests], ["Completed trips", summary.completed_trips], ["Mean pickup wait (seconds)", summary.mean_wait_seconds]]);
  metrics(root, [["Idle vehicle-hours", summary.idle_hours], ["Open requests at end", summary.open_requests_end], ["Canceled requests", summary.canceled_requests], ["Expired requests", summary.expired_requests]]);
  root.append(element("p", `${result.wait_population || "Wait population unavailable"}. Observed waits: ${format_value(summary.wait_observed_requests)}; censored: ${format_value(summary.wait_censored_requests)}.`, "muted"));
  if (offers) {
    root.append(element("h2", "Driver offers"));
    metrics(root, [["Offer acceptance", offers.acceptance_rate === null ? null : `${(offers.acceptance_rate * 100).toFixed(1)}%`], ["Accepted offers", offers.accepted], ["Rejected offers", offers.rejected], ["Timed-out offers", offers.timed_out], ["Withdrawn offers", offers.withdrawn], ["Pending offers at start", offers.pending_start], ["Pending offers at end", offers.pending_end]]);
    root.append(element("p", `Acceptance denominator: ${offers.acceptance_denominator}; withdrawals and pending offers are excluded. ${offers.acceptance_population}. Status: ${offers.acceptance_status}.`, "muted"));
    root.append(element("p", `${offers.accounting}. Fixed online roster; ${format_value(summary.online_hours)} online hours.`, "muted"));
  } else root.append(element("p", "Legacy fixed-supply fixture; no individual driver-offer records.", "muted"));
  if (earnings) {
    metrics(root, [["Gross driver pay", earnings.summary.total_driver_pay], ["Pay per presence hour", earnings.summary.pay_per_presence_hour], ["Settled completed trips", earnings.summary.settled_completed_trips]]);
    root.append(element("p", `${earnings.currency} · ${spec.compensation.contract.driver_fare_share * 100}% of displayed fare · completed trips only. ${earnings.income_denominator}. Gross pay is before costs.`, "muted"));
  } else root.append(element("p", "Driver pay was not evaluated for this run.", "muted"));
  json_details(root, "Frozen specification and checkpoint", data);
}

async function forecast() {
  const run_id = state.run_id;
  if (!run_id) return;
  const fields = Object.fromEntries(new FormData($("#scenario-form")));
  const result = await post_json("/api/scenario", {run_id, ...fields, zone: fields.zone ? Number(fields.zone) : null, delta_x: Number(fields.delta_x) / 100, delta_y: Number(fields.delta_y) / 100, n_sessions: Number(fields.n_sessions)});
  if (run_id !== state.run_id || state.view !== "scenario") return;
  const root = $("#results");
  root.replaceChildren(element("p", result.coverage_warning, "notice"));
  root.append(element("p", `Status: ${result.status} · Support: ${result.support_status || "unavailable"} · Interval: ${result.interval_status || "unavailable"}`, "muted"));
  if (result.reasons?.length) root.append(element("p", result.reasons.join(" · "), "notice"));
  if (!["out_of_support", "not_identified", "invalid_probability"].includes(result.status)) {
    metrics(root, [["Expected bookings", result.after_expected_bookings], ["Change in bookings", result.delta_expected_bookings], ["Quote sessions", Number(fields.n_sessions)]]);
    const rows = Object.entries(result.probabilities).map(([service, value]) => ({Service: service, "Before (%)": value.before_probability * 100, "After (%)": value.after_probability * 100, "Change (pp)": value.delta_percentage_points, "Expected before": value.before_expected_choices, "Expected after": value.after_expected_choices}));
    bars(root, rows, "Service", "After (%)", "Before (%)");
    const frame = element("div"); table(frame, rows); root.append(frame);
    root.append(element("p", `${result.interval_kind} · nominal ${Math.round(result.interval_level * 100)}%. Technical stability does not establish empirical coverage. Expected bookings are choices, not completed trips.`, "muted"));
    if (result.interval) json_details(root, "Uncertainty intervals", result.interval);
    json_details(root, "Effect matrix and interpretation", {theta: result.theta, scope: fields.zone || "All zones", units: "Choice probability per log price; shared cluster response"});
  }
  const button = element("button", "Export scenario JSON");
  button.type = "button";
  button.onclick = () => save_blob(new Blob([JSON.stringify(result, null, 2)], {type: "application/json"}), "scenario.json");
  root.append(button);
  json_details(root, "Full scenario result", result);
}

async function read_json_artifact(artifact) {
  return (await api(`/api/runs/${encodeURIComponent(state.run_id)}/download?${new URLSearchParams({artifact})}`)).json();
}

async function load_artifact() {
  const artifact = $("#artifact-select").value;
  const run_id = state.run_id;
  if (!artifact || !run_id) return;
  state.artifact = artifact;
  const container = $("#table-content");
  container.replaceChildren(element("p", "Loading artifact…", "muted"));
  $("#table-chart").replaceChildren();
  $("#table-summary").replaceChildren();
  $("#page-note").textContent = "";
  $("#previous").disabled = $("#next").disabled = true;
  if (!/\.(csv|parquet)$/.test(artifact)) {
    if (artifact.endsWith(".json")) {
      const data = await read_json_artifact(artifact);
      if (run_id === state.run_id && artifact === state.artifact) container.replaceChildren(element("pre", JSON.stringify(data, null, 2)));
    } else container.replaceChildren(element("p", "Archive ready to download.", "muted"));
    return;
  }
  const params = new URLSearchParams({artifact, offset: state.offset, limit: 100});
  if (["observed", "method"].includes(state.view)) for (const [key, value] of new FormData($("#table-filters"))) if (value) params.set(key, value);
  const data = await (await api(`/api/runs/${encodeURIComponent(run_id)}/table?${params}`)).json();
  if (run_id !== state.run_id || artifact !== state.artifact) return;
  state.total = data.total_rows;
  table(container, data.rows, data.columns);
  if (Object.keys(data.summary).length) metrics($("#table-summary"), Object.entries(data.summary));
  $("#page-note").textContent = `${data.total_rows ? state.offset + 1 : 0}–${Math.min(state.offset + 100, data.total_rows)} of ${data.total_rows.toLocaleString()} rows`;
  $("#previous").disabled = state.offset === 0;
  $("#next").disabled = state.offset + 100 >= state.total;
  render_table_chart($("#table-chart"), data);
}

function render_table_chart(chart, data) {
  chart.replaceChildren();
  const numeric = data.columns.filter((key) => data.rows.some((row) => typeof row[key] === "number"));
  const labels = data.columns.filter((key) => data.rows.some((row) => typeof row[key] === "string"));
  if (numeric.length && labels.length && data.rows.length) {
    const controls = element("div", undefined, "fields");
    const x_label = element("label", "Group"); const x = element("select"); x_label.append(x);
    const y_label = element("label", "Metric"); const y = element("select"); y_label.append(y);
    options_for(x, labels.map((value) => [value, value]), labels.includes("policy_id") ? "policy_id" : labels[0]);
    options_for(y, numeric.map((value) => [value, value]), numeric.find((value) => ["completed_trip_count", "theta", "target_mean"].includes(value)) || numeric[0]);
    const plot = element("div");
    const draw_chart = () => { plot.replaceChildren(); bars(plot, data.rows, x.value, y.value); };
    x.onchange = y.onchange = draw_chart;
    controls.append(x_label, y_label);
    chart.append(controls, element("p", "Chart shows at most 24 rows from the current table page; values are individual rows, not aggregated totals.", "muted"), plot);
    draw_chart();
  }
}

function save_blob(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = element("a"); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function update_action() {
  const action = $("#job-action").value;
  $("#train-fields").hidden = action !== "train";
  $("#demand-fields").hidden = action !== "prepare_demand";
  $("#source-field").hidden = action === "train";
  $("#requests-field").hidden = action !== "simulate";
  const matching = state.runs.filter((run) => action === "simulate" ? run.stages.includes("prepare_demand") : run.stages.some((stage) => ["fit", "freeze_choice"].includes(stage)));
  options_for($("#job-source"), matching.map((run) => [run.run_id, run.run_id]), state.run_id);
}

async function poll_job(attempt = 0) {
  if (!state.job_id) return;
  const record = await (await api(`/api/jobs/${encodeURIComponent(state.job_id)}`)).json();
  $("#job-status").hidden = false;
  $("#job-progress").textContent = `${record.action} · ${record.status}${record.error ? ` · ${record.error}` : ""} · ${record.run_id}`;
  $("#job-progress").dataset.status = record.status;
  $("#job-log").textContent = `${JSON.stringify(record.stages || {}, null, 2)}\n${record.log || "Waiting for worker output…"}`;
  $("#cancel-job").hidden = record.status !== "running";
  $("#open-job").hidden = record.status !== "succeeded";
  $("#start-job").disabled = record.status === "running";
  if (record.status === "running" && attempt < 310) setTimeout(() => poll_job(attempt + 1).catch((error) => message(error.message, true)), 2000);
  else if (record.status === "succeeded") await load_runs();
  else if (record.status === "running") message("Job polling stopped after the worker time budget. Refresh to check its status.", true);
}

document.querySelectorAll("nav button").forEach((button) => button.onclick = () => perform(button, () => change_view(button.dataset.view)));
$("#refresh").onclick = (event) => perform(event.currentTarget, () => load_runs());
$("#run-select").onchange = (event) => perform($("#refresh"), () => load_run(event.target.value));
$("#dgp-filter").onchange = $("#seed-filter").onchange = () => perform($("#refresh"), () => select_runs(state.run_id));
$("#scenario-form").onsubmit = (event) => { event.preventDefault(); perform(event.submitter, forecast); };
$("#artifact-select").onchange = () => { state.offset = 0; perform($("#download"), load_artifact); };
$("#previous").onclick = () => { state.offset = Math.max(0, state.offset - 100); perform($("#download"), load_artifact); };
$("#next").onclick = () => { state.offset += 100; perform($("#download"), load_artifact); };
$("#table-filters").onsubmit = (event) => { event.preventDefault(); state.offset = 0; perform(event.submitter, load_artifact); };
$("#reset-filters").onclick = () => { $("#table-filters").reset(); state.offset = 0; perform($("#download"), load_artifact); };
$("#download").onclick = (event) => perform(event.currentTarget, async () => {
  const params = new URLSearchParams({artifact: state.artifact});
  const filtered = ["observed", "method"].includes(state.view) && /\.(csv|parquet)$/.test(state.artifact);
  if (filtered) {
    params.set("download", "true");
    for (const [key, value] of new FormData($("#table-filters"))) if (value) params.set(key, value);
  }
  const response = await api(`/api/runs/${encodeURIComponent(state.run_id)}/${filtered ? "table" : "download"}?${params}`);
  save_blob(await response.blob(), state.artifact.split("/").pop());
});
$("#job-action").onchange = update_action;
$("#job-form").onsubmit = (event) => {
  event.preventDefault();
  perform(event.submitter, async () => {
    const fields = Object.fromEntries(new FormData(event.target));
    const record = await post_json("/api/jobs", {...fields, source_run_id: fields.action === "train" ? null : fields.source_run_id || null, seed: Number(fields.seed), bootstrap_draws: Number(fields.bootstrap_draws), delta_x: Number(fields.delta_x) / 100, delta_y: Number(fields.delta_y) / 100, upload_id: fields.action === "simulate" ? fields.upload_id || null : null});
    state.job_id = record.job_id;
    sessionStorage.setItem("gsm_job", state.job_id);
    await poll_job();
    setTimeout(() => { $("#start-job").disabled = true; }, 0);
  });
};
$("#cancel-job").onclick = (event) => perform(event.currentTarget, async () => { await post_json(`/api/jobs/${encodeURIComponent(state.job_id)}/cancel`, {}); await poll_job(); });
$("#open-job").onclick = (event) => perform(event.currentTarget, async () => {
  const run = state.runs.find((item) => item.run_id === state.job_id);
  const view = run ? view_for_run(run) : "scenario";
  await change_view(view, state.job_id);
});
$("#upload-form").onsubmit = (event) => {
  event.preventDefault();
  perform(event.submitter, async () => {
    const file = $("#csv-file").files[0];
    if (!file || file.size > 5 * 1024 * 1024) throw new Error("Choose a CSV up to 5 MiB.");
    const kind = $("#upload-kind").value;
    const data = await (await api(`/api/uploads?kind=${kind}`, {method: "POST", headers: {"Content-Type": "text/csv"}, body: file})).json();
    $("#upload-preview").hidden = false;
    $("#upload-note").textContent = `${file.name} · ${data.total_rows.toLocaleString()} rows · ${data.source_kind} · ${Object.values(data.missing_values).reduce((sum, value) => sum + value, 0)} missing values. Preview shows up to 100 rows.`;
    table($("#upload-table"), data.rows, data.columns);
    render_table_chart($("#upload-chart"), data);
    if (kind === "requests") {
      state.uploads.push([data.upload_id, file.name]);
      options_for($("#job-upload"), [["", "Generate Poisson arrivals"], ...state.uploads], data.upload_id);
    }
  });
};
$("#access-form").onsubmit = (event) => {
  event.preventDefault();
  sessionStorage.setItem("gsm_token", $("#access-token").value);
  perform(event.submitter, async () => { await load_runs(); $("#access-form").hidden = true; $("#access-token").value = ""; });
};

load_runs().then(async () => {
  if (state.job_id) await poll_job();
}).catch((error) => message(error.message, true));
