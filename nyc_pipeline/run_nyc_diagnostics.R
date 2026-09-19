options(warn = 1)

ROOT <- normalizePath(getwd(), winslash = "/", mustWork = TRUE)
LOCAL_R_LIB <- Sys.getenv("PARK_CRIME_R_LIB", file.path(ROOT, "r_libs"))
if (dir.exists(LOCAL_R_LIB)) .libPaths(c(LOCAL_R_LIB, .libPaths()))

suppressPackageStartupMessages({
  library(data.table)
  library(fixest)
})

RESULTS_DIR <- file.path(ROOT, "results")
dt <- fread(file.path(ROOT, "data", "nyc_stacked_grid_panel.csv"))
OUTCOMES <- c("total_crime", "theft", "non_theft", "day_crime", "night_crime")

extract_fit <- function(fit, outcome, sample, model, omitted_park = "") {
  if (inherits(fit, "error")) {
    return(data.table(
      outcome = outcome, sample = sample, model = model,
      omitted_park = omitted_park, estimate = NA_real_, std_error = NA_real_,
      p_value = NA_real_, n_obs = NA_integer_, parks = NA_integer_,
      converged = FALSE, error = conditionMessage(fit)
    ))
  }
  ct <- as.data.table(coeftable(fit), keep.rownames = "term")
  row <- ct[term == "exposure_500"]
  if (nrow(row) != 1) {
    return(data.table(
      outcome = outcome, sample = sample, model = model,
      omitted_park = omitted_park, estimate = NA_real_, std_error = NA_real_,
      p_value = NA_real_, n_obs = nobs(fit), parks = NA_integer_,
      converged = FALSE, error = "coefficient unavailable"
    ))
  }
  data.table(
    outcome = outcome,
    sample = sample,
    model = model,
    omitted_park = omitted_park,
    estimate = as.numeric(row[["Estimate"]]),
    std_error = as.numeric(row[["Std. Error"]]),
    p_value = as.numeric(row[["Pr(>|z|)"]]),
    n_obs = nobs(fit),
    parks = uniqueN(fit$model_matrix_info$park_id),
    converged = if (is.null(fit$convStatus)) TRUE else isTRUE(fit$convStatus),
    error = ""
  )
}

fit_static <- function(data, outcome, trend = FALSE) {
  fixed_effects <- if (trend) {
    "stack_unit_id[half_index] + stack_half_id"
  } else {
    "stack_unit_id + stack_half_id"
  }
  tryCatch(
    fepois(
      as.formula(paste0(outcome, " ~ exposure_500 | ", fixed_effects)),
      data = data,
      vcov = ~grid_id,
      fixef.rm = "perfect_fit",
      warn = FALSE,
      notes = FALSE,
      mem.clean = TRUE
    ),
    error = function(e) e
  )
}

rows <- list()
for (outcome in OUTCOMES) {
  fit <- fit_static(dt, outcome)
  row <- extract_fit(fit, outcome, "all_main_events", "baseline_ppml")
  row[, parks := uniqueN(dt$park_id)]
  rows[[paste0("baseline_", outcome)]] <- row

  trend_fit <- fit_static(dt, outcome, trend = TRUE)
  trend_row <- extract_fit(
    trend_fit, outcome, "all_main_events", "unit_specific_linear_trend"
  )
  trend_row[, parks := uniqueN(dt$park_id)]
  rows[[paste0("trend_", outcome)]] <- trend_row
}

strict_classes <- c(
  "new_park_from_scratch",
  "new_pocket_parks",
  "new_park_opening",
  "first_public_opening"
)
strict_dt <- dt[opening_class %in% strict_classes]
for (outcome in OUTCOMES) {
  fit <- fit_static(strict_dt, outcome)
  row <- extract_fit(fit, outcome, "strict_first_openings", "baseline_ppml")
  row[, parks := uniqueN(strict_dt$park_id)]
  rows[[paste0("strict_", outcome)]] <- row
}

for (omitted in unique(dt$park_id)) {
  subset <- dt[park_id != omitted]
  park_name <- unique(dt[park_id == omitted, park_name])[1]
  for (outcome in OUTCOMES) {
    fit <- fit_static(subset, outcome)
    row <- extract_fit(
      fit,
      outcome,
      "leave_one_park_out",
      "baseline_ppml",
      omitted_park = park_name
    )
    row[, parks := uniqueN(subset$park_id)]
    rows[[paste(omitted, outcome, sep = "_")]] <- row
  }
}
diagnostics <- rbindlist(rows, fill = TRUE)
diagnostics[, stars := fifelse(
  p_value < 0.001, "***",
  fifelse(p_value < 0.01, "**", fifelse(p_value < 0.05, "*", ""))
)]
fwrite(diagnostics, file.path(RESULTS_DIR, "nyc_design_diagnostics.csv"))

pretrend_rows <- list()
for (omitted in c("none", unique(dt$park_id))) {
  subset <- if (omitted == "none") dt else dt[park_id != omitted]
  omitted_name <- if (omitted == "none") "" else unique(dt[park_id == omitted, park_name])[1]
  fit <- tryCatch(
    fepois(
      total_crime ~ i(event_time, baseline_exposure_500, ref = -1) |
        stack_unit_id + stack_half_id,
      data = subset,
      vcov = ~grid_id,
      fixef.rm = "perfect_fit",
      warn = FALSE,
      notes = FALSE,
      mem.clean = TRUE
    ),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    pretrend_rows[[omitted]] <- data.table(
      omitted_park = omitted_name,
      wald_statistic = NA_real_, p_value = NA_real_, n_obs = NA_integer_,
      converged = FALSE, error = conditionMessage(fit)
    )
    next
  }
  names <- names(coef(fit))
  lead_names <- names[grepl("event_time::-(3|2):", names)]
  b <- coef(fit)[lead_names]
  v <- vcov(fit)[lead_names, lead_names, drop = FALSE]
  statistic <- if (length(lead_names) == 2) as.numeric(t(b) %*% solve(v) %*% b) else NA_real_
  pretrend_rows[[omitted]] <- data.table(
    omitted_park = omitted_name,
    wald_statistic = statistic,
    p_value = if (is.na(statistic)) NA_real_ else pchisq(statistic, 2, lower.tail = FALSE),
    n_obs = nobs(fit),
    converged = if (is.null(fit$convStatus)) TRUE else isTRUE(fit$convStatus),
    error = ""
  )
}
fwrite(
  rbindlist(pretrend_rows, fill = TRUE),
  file.path(RESULTS_DIR, "nyc_total_crime_leave_one_out_pretrends.csv")
)

cat("diagnostic rows:", nrow(diagnostics), "\n")
