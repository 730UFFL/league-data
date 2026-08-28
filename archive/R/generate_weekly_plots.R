# Generate Weekly Quad Plots for Dashboard
# This script creates PNG files for each week's quad plot

library(tidyverse)
library(jsonlite)
source("R/quad_plot_functions.R")

# Load weekly historical data
cat("Loading weekly historical data...\n")
weekly_data <- read_csv("data/weekly_historical_data.csv", show_col_types = FALSE)

# Get available weeks
available_weeks <- sort(unique(weekly_data$week))
cat(sprintf("Found %d weeks of data: %s\n",
            length(available_weeks),
            paste(available_weeks, collapse = ", ")))

# Create plots directory if it doesn't exist
if (!dir.exists("plots")) {
  dir.create("plots")
  cat("Created plots/ directory\n")
}

# Generate plot for each week
cat("\nGenerating plots...\n")
for (week in available_weeks) {
  cat(sprintf("  Week %d... ", week))

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
}

# Generate weeks.json metadata file for dashboard
weeks_json <- toJSON(available_weeks, auto_unbox = FALSE)
write(weeks_json, "plots/weeks.json")
cat(sprintf("\nSaved weeks metadata to plots/weeks.json\n"))

cat(sprintf("\n✅ Successfully generated %d plots!\n", length(available_weeks)))
cat("Files created:\n")
for (week in available_weeks) {
  cat(sprintf("  - plots/week_%d.png\n", week))
}
cat("  - plots/weeks.json\n")
