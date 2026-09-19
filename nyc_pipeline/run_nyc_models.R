options(warn = 1)

ROOT <- normalizePath(getwd(), winslash = "/", mustWork = TRUE)
LOCAL_R_LIB <- Sys.getenv("PARK_CRIME_R_LIB", file.path(ROOT, "r_libs"))
if (dir.exists(LOCAL_R_LIB)) .libPaths(c(LOCAL_R_LIB, .libPaths()))

suppressPackageStartupMessages({
  library(data.table)
  library(fixest)
})

DATA_DIR <- file.path(ROOT, "data")
RESULTS_DIR <- file.path(ROOT, "results")
ARTIFACTS_DIR <- file.path(ROOT, "artifacts")
dir.create(RESULTS_DIR, recursive = TRUE, showWarnings = FALSE)

PANEL <- file.path(DATA_DIR, "nyc_stacked_grid_panel.csv")
CONTAMINATION <- file.path(ARTIFACTS_DIR, "cross_park_exposure_audit.csv")
OUTCOMES <- c("total_crime", "theft", "non_theft", "day_crime", "night_crime")
LAMBDAS <- c(250L, 500L, 1000L)

stars <- function(p) {
  if (is.na(p)) return("")
  if (p < 0.001) return("***")
  if (p < 0.01) return("**")
  if (p < 0.05) return("*")
  ""
}

converged_status <- function(fit) {
  value <- fit$convStatus
  if (is.null(value)) return(TRUE)
  isTRUE(value)
}

fit_ppml <- function(dt, outcome, treatment, model, scale_value, sample_name = "main") {
  base <- data.table(
    city = "New York City",
    sample = sample_name,
    model = model,
    estimator = "fixest::fepois",
    outcome = outcome,
    treatment = treatment,
    scale_value = scale_value,
    estimate = NA_real_,
    std_error = NA_real_,
    p_value = NA_real_,
    stars = "",
    incidence_rate_ratio = NA_real_,
    percent_effect_one_unit = NA_real_,
    percent_effect_one_sd = NA_real_,
    n_obs = NA_integer_,
    full_n_obs = nrow(dt),
    n_grids = uniqueN(dt$grid_id),
    n_parks = uniqueN(dt$park_id),
    converged = FALSE,
    status = "failed",
    error = ""
  )

  fit <- tryCatch(
    fepois(
      as.formula(paste0(outcome, " ~ ", treatment, " | stack_unit_id + stack_half_id")),
      data = dt,
      vcov = ~grid_id,
      fixef.rm = "perfect_fit",
      warn = FALSE,
      notes = FALSE,
      mem.clean = TRUE
    ),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    base[, error := conditionMessage(fit)]
    return(list(row = base, fit = NULL))
  }

  table <- as.data.table(coeftable(fit), keep.rownames = "term")
  value <- table[term == treatment]
  if (nrow(value) != 1) {
    base[, error := "Treatment coefficient was not uniquely estimated"]
    return(list(row = base, fit = fit))
  }
  beta <- as.numeric(value[["Estimate"]])
  se <- as.numeric(value[["Std. Error"]])
  p <- as.numeric(value[["Pr(>|z|)"]])
  treatment_sd <- sd(dt[[treatment]])
  conv <- converged_status(fit)
  base[, `:=`(
    estimate = beta,
    std_error = se,
    p_value = p,
    stars = if (conv) stars(p) else "",
    incidence_rate_ratio = exp(beta),
    percent_effect_one_unit = 100 * (exp(beta) - 1),
    percent_effect_one_sd = 100 * (exp(beta * treatment_sd) - 1),
    n_obs = nobs(fit),
    converged = conv,
    status = if (conv) "success" else "non_converged"
  )]
  list(row = base, fit = fit)
}

dt <- fread(PANEL)
for (column in c("park_id", "grid_id", "stack_unit_id", "stack_half_id")) {
  dt[, (column) := as.character(get(column))]
}

main_rows <- list()
binary_rows <- list()
fit_store <- list()
for (outcome in OUTCOMES) {
  for (lambda in LAMBDAS) {
    treatment <- paste0("exposure_", lambda)
    key <- paste(outcome, treatment, sep = "__")
    result <- fit_ppml(dt, outcome, treatment, "continuous_exposure_ppml", lambda)
    main_rows[[key]] <- result$row
    fit_store[[key]] <- result$fit

    binary_treatment <- paste0("binary_", lambda)
    binary_key <- paste(outcome, binary_treatment, sep = "__")
    binary_result <- fit_ppml(
      dt, outcome, binary_treatment, "binary_threshold_ppml", lambda
    )
    row <- binary_result$row
    setnames(row, "scale_value", "threshold_m")
    binary_rows[[binary_key]] <- row
  }
}
main_results <- rbindlist(main_rows, fill = TRUE)
binary_results <- rbindlist(binary_rows, fill = TRUE)
fwrite(main_results, file.path(RESULTS_DIR, "nyc_main_ppml.csv"))
fwrite(binary_results, file.path(RESULTS_DIR, "nyc_binary_models.csv"))

# Dynamic continuous-exposure event study at the central lambda.
event_rows <- list()
pretrend_rows <- list()
for (outcome in OUTCOMES) {
  fit <- tryCatch(
    fepois(
      as.formula(paste0(
        outcome,
        " ~ i(event_time, baseline_exposure_500, ref = -1) | stack_unit_id + stack_half_id"
      )),
      data = dt,
      vcov = ~grid_id,
      fixef.rm = "perfect_fit",
      warn = FALSE,
      notes = FALSE,
      mem.clean = TRUE
    ),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    event_rows[[outcome]] <- data.table(
      outcome = outcome,
      event_time = c(-3L, -2L, 0L, 1L, 2L, 3L),
      estimate = NA_real_,
      std_error = NA_real_,
      p_value = NA_real_,
      converged = FALSE,
      n_obs = NA_integer_,
      error = conditionMessage(fit)
    )
    next
  }
  conv <- converged_status(fit)
  table <- as.data.table(coeftable(fit), keep.rownames = "term")
  table <- table[grepl("^event_time::", term)]
  table[, event_time := as.integer(sub("^event_time::(-?[0-9]+):.*$", "\\1", term))]
  event_rows[[outcome]] <- table[, .(
    outcome = outcome,
    event_time,
    estimate = as.numeric(Estimate),
    std_error = as.numeric(`Std. Error`),
    p_value = as.numeric(`Pr(>|z|)`),
    converged = conv,
    n_obs = nobs(fit),
    error = ""
  )]

  covariance <- vcov(fit)
  coefficient_names <- names(coef(fit))
  lead_names <- coefficient_names[grepl("event_time::-(3|2):", coefficient_names)]
  if (length(lead_names) == 2) {
    b <- coef(fit)[lead_names]
    v <- covariance[lead_names, lead_names, drop = FALSE]
    statistic <- as.numeric(t(b) %*% solve(v) %*% b)
    p_joint <- pchisq(statistic, df = 2, lower.tail = FALSE)
  } else {
    statistic <- NA_real_
    p_joint <- NA_real_
  }
  pretrend_rows[[outcome]] <- data.table(
    outcome = outcome,
    wald_statistic = statistic,
    df = 2L,
    p_value = p_joint,
    converged = conv,
    n_obs = nobs(fit)
  )
}
event_results <- rbindlist(event_rows, fill = TRUE)
event_results[, stars := fifelse(
  converged,
  fifelse(p_value < 0.001, "***", fifelse(p_value < 0.01, "**", fifelse(p_value < 0.05, "*", ""))),
  ""
)]
fwrite(event_results, file.path(RESULTS_DIR, "nyc_event_study.csv"))
fwrite(rbindlist(pretrend_rows, fill = TRUE), file.path(RESULTS_DIR, "nyc_pretrend_tests.csv"))

# Exclude opening-period grid cells already within 1,500 m of another opened
# focal park. This is a conservative SUTVA/overlapping-treatment diagnostic.
contamination <- fread(CONTAMINATION)
drop_units <- contamination[
  open_period_competing_park_count > 0,
  paste(park_id, grid_id, sep = "__")
]
dt[, audit_unit := paste(park_id, grid_id, sep = "__")]
clean_dt <- dt[!audit_unit %in% drop_units]
clean_rows <- list()
for (outcome in OUTCOMES) {
  result <- fit_ppml(
    clean_dt,
    outcome,
    "exposure_500",
    "continuous_exposure_ppml",
    500L,
    sample_name = "exclude_cross_park_exposure"
  )
  clean_rows[[outcome]] <- result$row
}
fwrite(
  rbindlist(clean_rows, fill = TRUE),
  file.path(RESULTS_DIR, "nyc_cross_park_contamination_robustness.csv")
)

diagnostics <- rbindlist(lapply(OUTCOMES, function(outcome) {
  sums <- dt[, .(sum_outcome = sum(get(outcome))), by = stack_unit_id]
  data.table(
    outcome = outcome,
    observations = nrow(dt),
    parks = uniqueN(dt$park_id),
    grids = uniqueN(dt$grid_id),
    stack_units = uniqueN(dt$stack_unit_id),
    nonzero_observation_share = mean(dt[[outcome]] > 0),
    always_zero_stack_units = sum(sums$sum_outcome == 0),
    always_zero_stack_unit_share = mean(sums$sum_outcome == 0),
    outcome_mean = mean(dt[[outcome]]),
    outcome_variance = var(dt[[outcome]])
  )
}))
fwrite(diagnostics, file.path(RESULTS_DIR, "nyc_sparsity_diagnostics.csv"))

summary <- list(
  rows = nrow(dt),
  parks = uniqueN(dt$park_id),
  grids = uniqueN(dt$grid_id),
  stack_units = uniqueN(dt$stack_unit_id),
  main_successes = sum(main_results$status == "success"),
  binary_successes = sum(binary_results$status == "success"),
  dynamic_outcomes = uniqueN(event_results$outcome),
  clean_rows = nrow(clean_dt),
  dropped_cross_park_units = length(drop_units)
)
writeLines(
  jsonlite::toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
  file.path(ARTIFACTS_DIR, "model_run_audit.json")
)
cat(jsonlite::toJSON(summary, auto_unbox = TRUE), "\n")
