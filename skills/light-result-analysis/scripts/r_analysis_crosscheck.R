#!/usr/bin/env Rscript

# Base-R cross-check for one two-group comparison.  No optional package is
# required; the output is a one-row CSV so Python and R can be compared exactly.

parse_args <- function(args) {
  out <- list()
  i <- 1
  while (i <= length(args)) {
    key <- args[[i]]
    if (key == "--selftest") {
      out$selftest <- TRUE
      i <- i + 1
    } else {
      if (i == length(args)) stop(paste("missing value for", key))
      out[[sub("^--", "", key)]] <- args[[i + 1]]
      i <- i + 2
    }
  }
  out
}

analyze_two_groups <- function(input, group, metric, paired_by = NULL) {
  d <- read.csv(input, check.names = FALSE, stringsAsFactors = FALSE)
  needed <- c(group, metric)
  if (!is.null(paired_by)) needed <- c(needed, paired_by)
  missing <- setdiff(needed, names(d))
  if (length(missing) > 0) stop(paste("missing columns:", paste(missing, collapse = ",")))

  d <- d[complete.cases(d[, needed, drop = FALSE]), needed, drop = FALSE]
  groups <- sort(unique(as.character(d[[group]])))
  if (length(groups) != 2) stop("exactly two groups are required")

  if (!is.null(paired_by)) {
    a <- d[d[[group]] == groups[[1]], c(paired_by, metric), drop = FALSE]
    b <- d[d[[group]] == groups[[2]], c(paired_by, metric), drop = FALSE]
    if (anyDuplicated(a[[paired_by]]) || anyDuplicated(b[[paired_by]])) {
      stop("paired key must be unique within each group")
    }
    names(a)[2] <- "value_a"
    names(b)[2] <- "value_b"
    m <- merge(a, b, by = paired_by, all = FALSE)
    if (nrow(m) < 2) stop("fewer than two complete pairs")
    test <- t.test(m$value_a, m$value_b, paired = TRUE, conf.level = 0.95)
    diff <- m$value_a - m$value_b
    effect <- if (sd(diff) == 0) NA_real_ else mean(diff) / sd(diff)
    n <- nrow(m)
    design <- "paired"
  } else {
    x <- d[d[[group]] == groups[[1]], metric]
    y <- d[d[[group]] == groups[[2]], metric]
    if (length(x) < 2 || length(y) < 2) stop("fewer than two rows per group")
    test <- t.test(x, y, paired = FALSE, var.equal = FALSE, conf.level = 0.95)
    pooled <- sqrt(((length(x) - 1) * var(x) + (length(y) - 1) * var(y)) /
                   (length(x) + length(y) - 2))
    effect <- if (pooled == 0) NA_real_ else (mean(x) - mean(y)) / pooled
    n <- min(length(x), length(y))
    design <- "independent_welch"
  }

  data.frame(
    group1 = groups[[1]],
    group2 = groups[[2]],
    metric = metric,
    design = design,
    n = n,
    mean_diff = unname(test$estimate[[1]] - if (length(test$estimate) > 1) test$estimate[[2]] else 0),
    statistic = unname(test$statistic),
    df = unname(test$parameter),
    p = test$p.value,
    ci_low = test$conf.int[[1]],
    ci_high = test$conf.int[[2]],
    standardized_effect = effect,
    stringsAsFactors = FALSE
  )
}

selftest <- function() {
  path <- tempfile(fileext = ".csv")
  d <- data.frame(
    method = rep(c("a", "b"), each = 6),
    seed = rep(1:6, 2),
    score = c(.80, .82, .81, .83, .84, .85, .76, .77, .75, .785, .785, .80)
  )
  write.csv(d, path, row.names = FALSE)
  r <- analyze_two_groups(path, "method", "score", "seed")
  stopifnot(r$design == "paired", r$n == 6, abs(r$mean_diff - 0.05) < 1e-12)
  independent <- analyze_two_groups(path, "method", "score")
  stopifnot(
    independent$design == "independent_welch",
    independent$n == 6,
    abs(independent$mean_diff - 0.05) < 1e-12,
    is.finite(independent$p)
  )
  unlink(path)
  cat("[selftest] PASS r_analysis_crosscheck (base R paired + independent Welch t-tests)\n")
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
if (isTRUE(args$selftest)) {
  selftest()
  quit(status = 0)
}
required <- c("input", "group", "metric", "out")
missing <- required[!vapply(required, function(x) !is.null(args[[x]]), logical(1))]
if (length(missing) > 0) stop(paste("missing args:", paste(missing, collapse = ",")))
paired_by <- args[["paired-by"]]
result <- analyze_two_groups(args$input, args$group, args$metric, paired_by)
write.csv(result, args$out, row.names = FALSE, quote = TRUE)
cat(paste("wrote", args$out, "\n"))
