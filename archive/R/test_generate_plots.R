# Diagnostic version of generate_weekly_plots.R
# This version has better error checking

cat("=== Starting Plot Generation ===\n\n")

# Check working directory
cat("1. Checking working directory...\n")
cat("   Current directory:", getwd(), "\n")

# Check if required packages are installed
cat("\n2. Checking required packages...\n")
required_packages <- c("tidyverse", "jsonlite", "ggplot2", "dplyr", "readr")
for (pkg in required_packages) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    cat("   ✓", pkg, "is installed\n")
  } else {
    cat("   ✗", pkg, "is NOT installed - installing now...\n")
    install.packages(pkg)
  }
}

# Load packages
cat("\n3. Loading packages...\n")
tryCatch({
  library(tidyverse)
  library(jsonlite)
  cat("   ✓ Packages loaded successfully\n")
}, error = function(e) {
  cat("   ✗ Error loading packages:", e$message, "\n")
  stop("Cannot continue without required packages")
})

# Check if function file exists
cat("\n4. Checking for quad_plot_functions.R...\n")
if (file.exists("R/quad_plot_functions.R")) {
  cat("   ✓ File exists\n")
  tryCatch({
    source("R/quad_plot_functions.R")
    cat("   ✓ Functions loaded successfully\n")
  }, error = function(e) {
    cat("   ✗ Error sourcing file:", e$message, "\n")
    stop("Cannot continue without plotting functions")
  })
} else {
  cat("   ✗ File not found!\n")
  stop("R/quad_plot_functions.R not found")
}

# Check if data file exists
cat("\n5. Checking for data file...\n")
if (file.exists("data/weekly_historical_data.csv")) {
  cat("   ✓ Data file exists\n")
  tryCatch({
    weekly_data <- read_csv("data/weekly_historical_data.csv", show_col_types = FALSE)
    cat("   ✓ Data loaded:", nrow(weekly_data), "rows\n")
  }, error = function(e) {
    cat("   ✗ Error reading data:", e$message, "\n")
    stop("Cannot continue without data")
  })
} else {
  cat("   ✗ Data file not found!\n")
  stop("data/weekly_historical_data.csv not found")
}

# Get available weeks
cat("\n6. Checking available weeks...\n")
available_weeks <- sort(unique(weekly_data$week))
cat("   Found", length(available_weeks), "weeks:", paste(available_weeks, collapse = ", "), "\n")

# Create plots directory
cat("\n7. Creating plots directory...\n")
if (!dir.exists("plots")) {
  tryCatch({
    dir.create("plots")
    cat("   ✓ Created plots/ directory\n")
  }, error = function(e) {
    cat("   ✗ Error creating directory:", e$message, "\n")
    stop("Cannot create plots directory")
  })
} else {
  cat("   ℹ plots/ directory already exists\n")
}

# Generate plots
cat("\n8. Generating plots...\n")
for (week in available_weeks) {
  cat(sprintf("   Week %d... ", week))

  tryCatch({
    # Filter data for this week
    week_data <- weekly_data |> filter(week == !!week)

    # Create plot
    p <- create_quad_plot(week_data, week)

    # Save plot
    filename <- sprintf("plots/week_%d.png", week)
    ggsave(
      filename,
      plot = p,
      width = 10,
      height = 8,
      dpi = 300,
      bg = "white"
    )

    cat("✓\n")
  }, error = function(e) {
    cat("✗\n")
    cat("      Error:", e$message, "\n")
  })
}

# Generate weeks.json
cat("\n9. Creating weeks.json metadata...\n")
tryCatch({
  weeks_json <- toJSON(available_weeks, auto_unbox = FALSE)
  write(weeks_json, "plots/weeks.json")
  cat("   ✓ Saved weeks metadata\n")
}, error = function(e) {
  cat("   ✗ Error creating JSON:", e$message, "\n")
})

cat("\n=== DONE ===\n")
cat("Check the plots/ directory for generated files\n")
