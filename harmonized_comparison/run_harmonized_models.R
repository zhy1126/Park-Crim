options(warn = 1)

ROOT <- normalizePath(getwd(), winslash = "/", mustWork = TRUE)
LIB_DIR <- Sys.getenv("PARK_CRIME_R_LIB", file.path(ROOT, "r_libs"))
if (dir.exists(LIB_DIR)) .libPaths(c(LIB_DIR, .libPaths()))

suppressPackageStartupMessages({
  library(data.table)
  library(fixest)
  library(jsonlite)
})

DATA_DIR <- file.path(ROOT, "data")
RESULTS_DIR <- file.path(ROOT, "results")
ARTIFACTS_DIR <- file.path(ROOT, "artifacts")
dir.create(RESULTS_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(ARTIFACTS_DIR, recursive = TRUE, showWarnings = FALSE)

MODEL_WINDOW <- tolower(Sys.getenv("HARMONIZED_MODEL_WINDOW", "short"))
if (!MODEL_WINDOW %in% c("short", "long")) stop("HARMONIZED_MODEL_WINDOW must be short or long")
FILE_SUFFIX <- if (MODEL_WINDOW == "short") "" else "_long_m3_p3"
tagged_name <- function(filename) {
  sub("(\\.[^.]+)$", paste0(FILE_SUFFIX, "\\1"), filename)
}

PANEL_PATH <- file.path(
  DATA_DIR,
  tagged_name("harmonized_stacked_grid_panel_500m.csv")
)
LEDGER_PATH <- file.path(DATA_DIR, "harmonized_event_ledger.csv")
OUTCOMES <- c("total_crime", "theft", "non_theft", "day_crime", "night_crime")
CITIES <- c("SH", "NYC")
EVENT_TIMES <- if (MODEL_WINDOW == "short") c(-3L, -2L, -1L, 0L) else -3L:3L
DYNAMIC_PERIODS <- EVENT_TIMES[EVENT_TIMES != -1L]

star_code <- function(p) {
  if (is.na(p)) return("")
  if (p < 0.001) return("***")
  if (p < 0.01) return("**")
  if (p < 0.05) return("*")
  ""
}

is_converged <- function(fit) {
  status <- fit$convStatus
  if (is.null(status)) return(TRUE)
  isTRUE(status)
}

safe_inverse_wald <- function(beta, covariance) {
  if (length(beta) == 0L || any(!is.finite(beta)) || any(!is.finite(covariance))) {
    return(c(statistic = NA_real_, df = length(beta), p_value = NA_real_))
  }
  value <- tryCatch(
    as.numeric(t(beta) %*% solve(covariance, beta)),
    error = function(e) NA_real_
  )
  if (!is.finite(value)) {
    return(c(statistic = NA_real_, df = length(beta), p_value = NA_real_))
  }
  c(
    statistic = value,
    df = length(beta),
    p_value = pchisq(value, df = length(beta), lower.tail = FALSE)
  )
}

coefficient_row <- function(fit, term_name) {
  table <- as.data.table(coeftable(fit), keep.rownames = "term")
  p_column <- names(table)[ncol(table)]
  row <- table[term == term_name]
  if (nrow(row) != 1L) return(NULL)
  list(
    estimate = as.numeric(row[["Estimate"]]),
    std_error = as.numeric(row[["Std. Error"]]),
    p_value = as.numeric(row[[p_column]])
  )
}

sample_diagnostics <- function(data, outcome) {
  sums <- data[, .(outcome_sum = sum(get(outcome))), by = stack_unit_id]
  list(
    input_obs = nrow(data),
    input_stack_units = uniqueN(data$stack_unit_id),
    active_stack_units = sum(sums$outcome_sum > 0),
    all_zero_stack_units = sum(sums$outcome_sum == 0),
    all_zero_stack_unit_share = mean(sums$outcome_sum == 0),
    nonzero_observation_share = mean(data[[outcome]] > 0),
    outcome_mean = mean(data[[outcome]]),
    outcome_variance = var(data[[outcome]]),
    n_events = uniqueN(data$event_id),
    n_unique_grids = uniqueN(data$grid_cluster_id)
  )
}

fit_single_ppml <- function(data, outcome, treatment, city, sample_name,
                            design, vcov_name = "grid") {
  diag <- sample_diagnostics(data, outcome)
  base <- data.table(
    city_code = city,
    sample = sample_name,
    design = design,
    outcome = outcome,
    treatment = treatment,
    vcov = vcov_name,
    estimate = NA_real_,
    std_error = NA_real_,
    p_value = NA_real_,
    stars = "",
    incidence_rate_ratio = NA_real_,
    percent_effect_full_scale = NA_real_,
    percent_effect_one_sd = NA_real_,
    n_obs = NA_integer_,
    dropped_obs = NA_integer_,
    converged = FALSE,
    status = "failed",
    error = ""
  )
  for (name in names(diag)) set(base, j = name, value = diag[[name]])

  vcov_formula <- switch(
    vcov_name,
    grid = ~grid_cluster_id,
    park = ~park_cluster_id,
    grid_park = ~grid_cluster_id + park_cluster_id,
    stop("Unknown vcov_name: ", vcov_name)
  )
  formula <- as.formula(paste0(
    outcome, " ~ ", treatment,
    " | stack_unit_id + stack_period_id"
  ))
  fit <- tryCatch(
    fepois(
      formula,
      data = data,
      vcov = vcov_formula,
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
  value <- coefficient_row(fit, treatment)
  if (is.null(value)) {
    base[, `:=`(
      n_obs = nobs(fit),
      dropped_obs = input_obs - nobs(fit),
      error = "Treatment coefficient unavailable"
    )]
    return(list(row = base, fit = fit))
  }
  conv <- is_converged(fit)
  treatment_sd <- sd(data[[treatment]])
  base[, `:=`(
    estimate = value$estimate,
    std_error = value$std_error,
    p_value = value$p_value,
    stars = if (conv) star_code(value$p_value) else "",
    incidence_rate_ratio = exp(value$estimate),
    percent_effect_full_scale = 100 * (exp(value$estimate) - 1),
    percent_effect_one_sd = 100 * (exp(value$estimate * treatment_sd) - 1),
    n_obs = nobs(fit),
    dropped_obs = input_obs - nobs(fit),
    converged = conv,
    status = if (conv) "success" else "non_converged"
  )]
  list(row = base, fit = fit)
}

fit_pooled_ppml <- function(data, outcome, treatment, sample_name,
                            design, vcov_name = "grid") {
  work <- copy(data)
  term_sh <- paste0(treatment, "_SH")
  term_nyc <- paste0(treatment, "_NYC")
  work[, (term_sh) := get(treatment) * as.integer(city_code == "SH")]
  work[, (term_nyc) := get(treatment) * as.integer(city_code == "NYC")]
  vcov_formula <- switch(
    vcov_name,
    grid = ~grid_cluster_id,
    park = ~park_cluster_id,
    grid_park = ~grid_cluster_id + park_cluster_id,
    stop("Unknown vcov_name: ", vcov_name)
  )
  formula <- as.formula(paste0(
    outcome, " ~ ", term_sh, " + ", term_nyc,
    " | stack_unit_id + stack_period_id"
  ))
  fit <- tryCatch(
    fepois(
      formula,
      data = work,
      vcov = vcov_formula,
      fixef.rm = "perfect_fit",
      warn = FALSE,
      notes = FALSE,
      mem.clean = TRUE
    ),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    return(list(
      coefficients = data.table(
        sample = sample_name, design = design, outcome = outcome,
        vcov = vcov_name, city_code = CITIES, term = c(term_sh, term_nyc),
        estimate = NA_real_, std_error = NA_real_, p_value = NA_real_,
        stars = "", n_obs = NA_integer_, converged = FALSE,
        error = conditionMessage(fit)
      ),
      difference = data.table(
        sample = sample_name, design = design, outcome = outcome,
        vcov = vcov_name, estimate_nyc_minus_sh = NA_real_,
        std_error = NA_real_, p_value = NA_real_, n_obs = NA_integer_,
        converged = FALSE, error = conditionMessage(fit)
      ),
      fit = NULL
    ))
  }
  conv <- is_converged(fit)
  coef_rows <- rbindlist(lapply(
    list(SH = term_sh, NYC = term_nyc),
    function(term) {
      value <- coefficient_row(fit, term)
      if (is.null(value)) {
        return(data.table(
          term = term, estimate = NA_real_, std_error = NA_real_,
          p_value = NA_real_, stars = ""
        ))
      }
      data.table(
        term = term,
        estimate = value$estimate,
        std_error = value$std_error,
        p_value = value$p_value,
        stars = if (conv) star_code(value$p_value) else ""
      )
    }
  ), idcol = "city_code")
  coef_rows[, `:=`(
    sample = sample_name,
    design = design,
    outcome = outcome,
    vcov = vcov_name,
    n_obs = nobs(fit),
    converged = conv,
    error = ""
  )]
  setcolorder(
    coef_rows,
    c("sample", "design", "outcome", "vcov", "city_code", "term",
      "estimate", "std_error", "p_value", "stars", "n_obs",
      "converged", "error")
  )

  coefficients <- coef(fit)
  covariance <- vcov(fit)
  if (all(c(term_sh, term_nyc) %in% names(coefficients))) {
    difference <- coefficients[[term_nyc]] - coefficients[[term_sh]]
    difference_variance <- covariance[term_nyc, term_nyc] +
      covariance[term_sh, term_sh] - 2 * covariance[term_nyc, term_sh]
    difference_se <- if (is.finite(difference_variance) && difference_variance >= 0) {
      sqrt(difference_variance)
    } else {
      NA_real_
    }
    difference_p <- if (is.finite(difference_se) && difference_se > 0) {
      2 * pnorm(abs(difference / difference_se), lower.tail = FALSE)
    } else {
      NA_real_
    }
  } else {
    difference <- difference_se <- difference_p <- NA_real_
  }
  difference_row <- data.table(
    sample = sample_name,
    design = design,
    outcome = outcome,
    vcov = vcov_name,
    estimate_nyc_minus_sh = difference,
    std_error = difference_se,
    p_value = difference_p,
    stars = if (conv) star_code(difference_p) else "",
    n_obs = nobs(fit),
    converged = conv,
    error = ""
  )
  list(coefficients = coef_rows, difference = difference_row, fit = fit)
}

parse_event_term <- function(term) {
  value <- sub("^event_time::(-?[0-9]+):.*$", "\\1", term)
  suppressWarnings(as.integer(value))
}

fit_dynamic <- function(data, outcome, city, treatment_type = "continuous") {
  base_treatment <- if (treatment_type == "continuous") {
    "base_exposure_500"
  } else {
    "base_binary_500"
  }
  formula <- as.formula(paste0(
    outcome, " ~ i(event_time, ", base_treatment,
    ", ref = -1) | stack_unit_id + stack_period_id"
  ))
  fit <- tryCatch(
    fepois(
      formula,
      data = data,
      vcov = ~grid_cluster_id,
      fixef.rm = "perfect_fit",
      warn = FALSE,
      notes = FALSE,
      mem.clean = TRUE
    ),
    error = function(e) e
  )
  empty_times <- DYNAMIC_PERIODS
  if (inherits(fit, "error")) {
    return(list(
      rows = data.table(
        city_code = city, outcome = outcome,
        treatment_type = treatment_type, event_time = empty_times,
        estimate = NA_real_, std_error = NA_real_, p_value = NA_real_,
        stars = "", n_obs = NA_integer_, converged = FALSE,
        error = conditionMessage(fit)
      ),
      pretrend = data.table(
        city_code = city, outcome = outcome,
        treatment_type = treatment_type, wald_statistic = NA_real_,
        df = 2L, p_value = NA_real_, n_obs = NA_integer_,
        converged = FALSE, error = conditionMessage(fit)
      ),
      fit = NULL
    ))
  }
  conv <- is_converged(fit)
  table <- as.data.table(coeftable(fit), keep.rownames = "term")
  table <- table[grepl("^event_time::", term)]
  p_column <- names(table)[ncol(table)]
  table[, event_time := vapply(term, parse_event_term, integer(1))]
  rows <- table[, .(
    city_code = city,
    outcome = outcome,
    treatment_type = treatment_type,
    event_time,
    estimate = as.numeric(Estimate),
    std_error = as.numeric(`Std. Error`),
    p_value = as.numeric(get(p_column)),
    n_obs = nobs(fit),
    converged = conv,
    error = ""
  )]
  rows[, stars := if (conv) vapply(p_value, star_code, character(1)) else ""]
  setcolorder(
    rows,
    c("city_code", "outcome", "treatment_type", "event_time",
      "estimate", "std_error", "p_value", "stars", "n_obs",
      "converged", "error")
  )

  names_all <- names(coef(fit))
  lead_names <- names_all[grepl("event_time::-(3|2):", names_all)]
  joint <- if (length(lead_names) == 2L) {
    safe_inverse_wald(
      coef(fit)[lead_names],
      vcov(fit)[lead_names, lead_names, drop = FALSE]
    )
  } else {
    c(statistic = NA_real_, df = 2L, p_value = NA_real_)
  }
  pretrend <- data.table(
    city_code = city,
    outcome = outcome,
    treatment_type = treatment_type,
    wald_statistic = unname(joint[["statistic"]]),
    df = as.integer(unname(joint[["df"]])),
    p_value = unname(joint[["p_value"]]),
    n_obs = nobs(fit),
    converged = conv,
    error = ""
  )
  list(rows = rows, pretrend = pretrend, fit = fit)
}

fit_pooled_dynamic <- function(data, outcome, treatment_type = "continuous") {
  work <- copy(data)
  base <- if (treatment_type == "continuous") "base_exposure_500" else "base_binary_500"
  periods <- DYNAMIC_PERIODS
  terms <- character()
  metadata <- list()
  for (city_id in CITIES) {
    for (period in periods) {
      suffix <- if (period < 0) paste0("m", abs(period)) else paste0("p", period)
      term <- paste0("dyn_", city_id, "_", suffix)
      work[, (term) := get(base) * as.integer(city_code == city_id & event_time == period)]
      terms <- c(terms, term)
      metadata[[term]] <- list(city_code = city_id, event_time = period)
    }
  }
  formula <- as.formula(paste0(
    outcome, " ~ ", paste(terms, collapse = " + "),
    " | stack_unit_id + stack_period_id"
  ))
  fit <- tryCatch(
    fepois(
      formula,
      data = work,
      vcov = ~grid_cluster_id,
      fixef.rm = "perfect_fit",
      warn = FALSE,
      notes = FALSE,
      mem.clean = TRUE
    ),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    return(list(
      coefficients = data.table(
        outcome = outcome, treatment_type = treatment_type,
        city_code = rep(CITIES, each = length(periods)),
        event_time = rep(periods, times = length(CITIES)),
        estimate = NA_real_, std_error = NA_real_, p_value = NA_real_,
        stars = "", n_obs = NA_integer_, converged = FALSE,
        error = conditionMessage(fit)
      ),
      differences = data.table(
        outcome = outcome, treatment_type = treatment_type,
        event_time = periods, estimate_nyc_minus_sh = NA_real_,
        std_error = NA_real_, p_value = NA_real_, stars = "",
        n_obs = NA_integer_, converged = FALSE,
        error = conditionMessage(fit)
      ),
      fit = NULL
    ))
  }
  conv <- is_converged(fit)
  values <- coef(fit)
  covariance <- vcov(fit)
  rows <- rbindlist(lapply(terms, function(term) {
    value <- coefficient_row(fit, term)
    meta <- metadata[[term]]
    data.table(
      outcome = outcome,
      treatment_type = treatment_type,
      city_code = meta$city_code,
      event_time = meta$event_time,
      estimate = if (is.null(value)) NA_real_ else value$estimate,
      std_error = if (is.null(value)) NA_real_ else value$std_error,
      p_value = if (is.null(value)) NA_real_ else value$p_value,
      stars = if (!is.null(value) && conv) star_code(value$p_value) else "",
      n_obs = nobs(fit),
      converged = conv,
      error = ""
    )
  }))
  differences <- rbindlist(lapply(periods, function(period) {
    suffix <- if (period < 0) paste0("m", abs(period)) else paste0("p", period)
    sh <- paste0("dyn_SH_", suffix)
    nyc <- paste0("dyn_NYC_", suffix)
    if (all(c(sh, nyc) %in% names(values))) {
      difference <- values[[nyc]] - values[[sh]]
      variance <- covariance[nyc, nyc] + covariance[sh, sh] - 2 * covariance[nyc, sh]
      se <- if (is.finite(variance) && variance >= 0) sqrt(variance) else NA_real_
      p <- if (is.finite(se) && se > 0) 2 * pnorm(abs(difference / se), lower.tail = FALSE) else NA_real_
    } else {
      difference <- se <- p <- NA_real_
    }
    data.table(
      outcome = outcome,
      treatment_type = treatment_type,
      event_time = period,
      estimate_nyc_minus_sh = difference,
      std_error = se,
      p_value = p,
      stars = if (conv) star_code(p) else "",
      n_obs = nobs(fit),
      converged = conv,
      error = ""
    )
  }))
  list(coefficients = rows, differences = differences, fit = fit)
}

fit_placebo <- function(data, outcome, city, placebo_period) {
  work <- data[event_time < 0]
  term <- paste0("placebo_", if (placebo_period < 0) "m" else "p", abs(placebo_period))
  work[, (term) := base_exposure_500 * as.integer(event_time >= placebo_period)]
  result <- fit_single_ppml(
    work, outcome, term, city, "pre_period_only",
    paste0("continuous_placebo_at_", placebo_period), "grid"
  )$row
  result[, placebo_event_time := placebo_period]
  result
}

dt <- fread(PANEL_PATH)
ledger <- fread(LEDGER_PATH)

for (column in c(
  "city_code", "event_id", "grid_id", "stack_unit_id", "stack_period_id",
  "grid_cluster_id", "park_cluster_id"
)) {
  dt[, (column) := as.character(get(column))]
}
ledger_small <- ledger[, .(
  event_id, date_precision, source_type, source_url, source_note
)]
dt <- merge(dt, ledger_small, by = "event_id", all.x = TRUE, sort = FALSE)
dt[, event_time := as.integer(event_time)]
dt[, base_binary_500 := as.integer(distance_to_park_m <= 500)]

stopifnot(
  all(dt$event_time %in% EVENT_TIMES),
  all(dt$total_crime == dt$theft + dt$non_theft),
  all(dt$total_crime == dt$day_crime + dt$night_crime + dt$unknown_time),
  all(dt[, .N, by = stack_unit_id]$N == length(EVENT_TIMES))
)

samples <- list(
  core = dt[analysis_core == 1L],
  day_precision = dt[analysis_core == 1L & date_precision == "day"],
  rebuild_comparable = dt[analysis_rebuild_comparable == 1L],
  uncontaminated = dt[analysis_core_uncontaminated == 1L]
)

# Separate follow-up horizon from event composition. In the short-window run,
# re-estimate the same four-period model using only events that also have a
# complete [-3,+3] panel. This holds event composition fixed when the short and
# long estimates are compared.
if (MODEL_WINDOW == "short") {
  long_panel_path <- file.path(DATA_DIR, "harmonized_stacked_grid_panel_500m_long_m3_p3.csv")
  if (file.exists(long_panel_path)) {
    long_eligible_ids <- fread(long_panel_path)[analysis_core == 1L, unique(event_id)]
    samples$long_eligible_events <- dt[analysis_core == 1L & event_id %in% long_eligible_ids]
  }
}

# City-specific static models.
static_rows <- list()
index <- 1L
for (sample_name in names(samples)) {
  sample_dt <- samples[[sample_name]]
  for (city_id in CITIES) {
    city_dt <- sample_dt[city_code == city_id]
    if (nrow(city_dt) == 0L) next
    for (outcome in OUTCOMES) {
      for (design in c("continuous", "binary")) {
        treatment <- if (design == "continuous") "continuous_post_500" else "binary_post_500"
        result <- fit_single_ppml(
          city_dt, outcome, treatment, city_id, sample_name,
          paste0(design, "_park_opening_ppml"), "grid"
        )
        static_rows[[index]] <- result$row
        index <- index + 1L
      }
    }
  }
}

# Small-cluster sensitivity for the common core sample.
for (city_id in CITIES) {
  city_dt <- samples$core[city_code == city_id]
  for (outcome in OUTCOMES) {
    for (design in c("continuous", "binary")) {
      treatment <- if (design == "continuous") "continuous_post_500" else "binary_post_500"
      for (vcov_name in c("park", "grid_park")) {
        result <- fit_single_ppml(
          city_dt, outcome, treatment, city_id, "core",
          paste0(design, "_park_opening_ppml"), vcov_name
        )
        static_rows[[index]] <- result$row
        index <- index + 1L
      }
    }
  }
}
static_results <- rbindlist(static_rows, fill = TRUE)
fwrite(static_results, file.path(RESULTS_DIR, tagged_name("city_specific_static_ppml.csv")))

# Pooled models estimate separate city slopes and test their equality.
pooled_coefficients <- list()
pooled_differences <- list()
index <- 1L
for (sample_name in names(samples)) {
  sample_dt <- samples[[sample_name]]
  if (uniqueN(sample_dt$city_code) < 2L) next
  for (outcome in OUTCOMES) {
    for (design in c("continuous", "binary")) {
      treatment <- if (design == "continuous") "continuous_post_500" else "binary_post_500"
      for (vcov_name in if (sample_name == "core") c("grid", "grid_park") else "grid") {
        result <- fit_pooled_ppml(
          sample_dt, outcome, treatment, sample_name,
          paste0(design, "_park_opening_ppml"), vcov_name
        )
        pooled_coefficients[[index]] <- result$coefficients
        pooled_differences[[index]] <- result$difference
        index <- index + 1L
      }
    }
  }
}
fwrite(
  rbindlist(pooled_coefficients, fill = TRUE),
  file.path(RESULTS_DIR, tagged_name("pooled_city_specific_slopes.csv"))
)
fwrite(
  rbindlist(pooled_differences, fill = TRUE),
  file.path(RESULTS_DIR, tagged_name("pooled_city_difference_tests.csv"))
)

# Dynamic event studies and joint lead tests.
dynamic_rows <- list()
pretrend_rows <- list()
index <- 1L
for (city_id in CITIES) {
  city_dt <- samples$core[city_code == city_id]
  for (outcome in OUTCOMES) {
    for (treatment_type in c("continuous", "binary")) {
      result <- fit_dynamic(city_dt, outcome, city_id, treatment_type)
      dynamic_rows[[index]] <- result$rows
      pretrend_rows[[index]] <- result$pretrend
      index <- index + 1L
    }
  }
}
fwrite(rbindlist(dynamic_rows, fill = TRUE), file.path(RESULTS_DIR, tagged_name("dynamic_event_study.csv")))
fwrite(rbindlist(pretrend_rows, fill = TRUE), file.path(RESULTS_DIR, tagged_name("joint_pretrend_tests.csv")))

pooled_dynamic_rows <- list()
pooled_dynamic_differences <- list()
index <- 1L
for (outcome in OUTCOMES) {
  for (treatment_type in c("continuous", "binary")) {
    result <- fit_pooled_dynamic(samples$core, outcome, treatment_type)
    pooled_dynamic_rows[[index]] <- result$coefficients
    pooled_dynamic_differences[[index]] <- result$differences
    index <- index + 1L
  }
}
fwrite(
  rbindlist(pooled_dynamic_rows, fill = TRUE),
  file.path(RESULTS_DIR, tagged_name("pooled_dynamic_city_slopes.csv"))
)
fwrite(
  rbindlist(pooled_dynamic_differences, fill = TRUE),
  file.path(RESULTS_DIR, tagged_name("pooled_dynamic_city_difference_tests.csv"))
)

# Placebo openings use only observations before the true opening.
placebo_rows <- list()
index <- 1L
for (city_id in CITIES) {
  city_dt <- samples$core[city_code == city_id]
  for (outcome in OUTCOMES) {
    for (placebo_period in c(-2L, -1L)) {
      placebo_rows[[index]] <- fit_placebo(
        city_dt, outcome, city_id, placebo_period
      )
      index <- index + 1L
    }
  }
}
fwrite(rbindlist(placebo_rows, fill = TRUE), file.path(RESULTS_DIR, tagged_name("preperiod_placebo_tests.csv")))

# Leave-one-event-out influence analysis for both estimands.
loo_rows <- list()
index <- 1L
for (city_id in CITIES) {
  city_dt <- samples$core[city_code == city_id]
  for (omitted_event in unique(city_dt$event_id)) {
    subset <- city_dt[event_id != omitted_event]
    omitted_name <- unique(city_dt[event_id == omitted_event, park_name])[1]
    for (outcome in OUTCOMES) {
      for (design in c("continuous", "binary")) {
        treatment <- if (design == "continuous") "continuous_post_500" else "binary_post_500"
        result <- fit_single_ppml(
          subset, outcome, treatment, city_id, "leave_one_event_out",
          paste0(design, "_park_opening_ppml"), "grid"
        )$row
        result[, `:=`(
          omitted_event_id = omitted_event,
          omitted_park_name = omitted_name
        )]
        loo_rows[[index]] <- result
        index <- index + 1L
      }
    }
  }
}
fwrite(rbindlist(loo_rows, fill = TRUE), file.path(RESULTS_DIR, tagged_name("leave_one_event_out.csv")))

# Harmonized descriptive and support diagnostics.
diagnostic_rows <- list()
index <- 1L
for (city_id in CITIES) {
  city_dt <- samples$core[city_code == city_id]
  for (outcome in OUTCOMES) {
    diag <- sample_diagnostics(city_dt, outcome)
    row <- data.table(city_code = city_id, outcome = outcome)
    for (name in names(diag)) set(row, j = name, value = diag[[name]])
    diagnostic_rows[[index]] <- row
    index <- index + 1L
  }
}
fwrite(rbindlist(diagnostic_rows, fill = TRUE), file.path(RESULTS_DIR, tagged_name("outcome_support_diagnostics.csv")))

event_diagnostics <- samples$core[, .(
  city = first(city),
  park_name = first(park_name),
  opening_date = first(opening_date),
  date_precision = first(date_precision),
  event_family = first(event_family),
  source_grade = first(source_grade),
  park_area_ha = first(park_area_ha),
  stack_units = uniqueN(stack_unit_id),
  unique_grids = uniqueN(grid_id),
  observations = .N,
  total_cases = sum(total_crime),
  theft_cases = sum(theft),
  non_theft_cases = sum(non_theft),
  day_cases = sum(day_crime),
  night_cases = sum(night_crime),
  unknown_time_cases = sum(unknown_time),
  mean_distance_m = mean(distance_to_park_m),
  within_500m_stack_units = uniqueN(stack_unit_id[distance_to_park_m <= 500]),
  contaminated_stack_units = uniqueN(stack_unit_id[ever_competing_open_event == 1L])
), by = .(city_code, event_id)]
fwrite(event_diagnostics, file.path(RESULTS_DIR, tagged_name("event_level_diagnostics.csv")))

exposure_diagnostics <- samples$core[, .(
  observations = .N,
  stack_units = uniqueN(stack_unit_id),
  events = uniqueN(event_id),
  unique_grids = uniqueN(grid_id),
  within_500m_share = mean(distance_to_park_m <= 500),
  exposure_mean = mean(base_exposure_500),
  exposure_sd = sd(base_exposure_500),
  exposure_p10 = quantile(base_exposure_500, 0.10),
  exposure_p50 = quantile(base_exposure_500, 0.50),
  exposure_p90 = quantile(base_exposure_500, 0.90),
  contaminated_stack_unit_share = uniqueN(stack_unit_id[ever_competing_open_event == 1L]) /
    uniqueN(stack_unit_id)
), by = city_code]
fwrite(exposure_diagnostics, file.path(RESULTS_DIR, tagged_name("exposure_support_diagnostics.csv")))

run_audit <- list(
  run_timestamp = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
  estimator = "fixest::fepois",
  model_window = MODEL_WINDOW,
  panel_rows = nrow(dt),
  events = uniqueN(dt$event_id),
  shanghai_events = uniqueN(dt[city_code == "SH", event_id]),
  nyc_events = uniqueN(dt[city_code == "NYC", event_id]),
  core_model_rows = nrow(samples$core),
  core_model_events = uniqueN(samples$core$event_id),
  core_model_shanghai_events = uniqueN(samples$core[city_code == "SH", event_id]),
  core_model_nyc_events = uniqueN(samples$core[city_code == "NYC", event_id]),
  event_times = sort(unique(dt$event_time)),
  static_models = nrow(static_results),
  static_successes = sum(static_results$status == "success"),
  static_nonconverged = sum(static_results$status == "non_converged"),
  static_failed = sum(static_results$status == "failed"),
  pooled_models = length(pooled_coefficients),
  dynamic_models = length(dynamic_rows),
  placebo_models = length(placebo_rows),
  leave_one_event_out_models = length(loo_rows),
  identity_total_pass = all(dt$total_crime == dt$theft + dt$non_theft),
  identity_time_pass = all(dt$total_crime == dt$day_crime + dt$night_crime + dt$unknown_time),
  balanced_panel_pass = all(dt[, .N, by = stack_unit_id]$N == length(EVENT_TIMES))
)
writeLines(
  toJSON(run_audit, auto_unbox = TRUE, pretty = TRUE),
  file.path(ARTIFACTS_DIR, tagged_name("model_run_audit.json"))
)
cat(toJSON(run_audit, auto_unbox = TRUE), "\n")
