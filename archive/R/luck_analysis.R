# Fantasy Football Luck Analysis - Advanced Visualizations
# Load required libraries
library(tidyverse)
library(patchwork)  # For combining plots
library(scales)     # For better formatting

# Load all the data files
standings <- read_csv("espn_standings.csv")
matchups <- read_csv("matchup_history.csv") 
luck <- read_csv("luck_analysis.csv")
future <- read_csv("future_schedule.csv")

# Clean up team names for consistent plotting
clean_team_names <- function(df, team_col = "team_name") {
  df |>
    mutate(
      !!team_col := str_remove(!!sym(team_col), "\\s*\\([^\\)]+\\)") |>
        str_trim() |>
        str_remove("^Team\\s+") |>  # Remove "Team " prefix
        str_trunc(15)  # Truncate long names
    )
}

standings <- clean_team_names(standings, "Team")
luck <- clean_team_names(luck, "team_name")

# 1. LUCK vs ACTUAL RECORD SCATTER PLOT
# ====================================
luck_plot <- luck |>
  mutate(
    luck_label = case_when(
      win_luck > 1 ~ "Very Lucky 🍀",
      win_luck == 1 ~ "Lucky 🙂", 
      win_luck == 0 ~ "Expected 😐",
      win_luck == -1 ~ "Unlucky 😞",
      win_luck < -1 ~ "Very Unlucky 💩"
    ),
    luck_color = case_when(
      win_luck > 1 ~ "#2E8B57",      # Sea green
      win_luck == 1 ~ "#90EE90",     # Light green  
      win_luck == 0 ~ "#FFD700",     # Gold
      win_luck == -1 ~ "#FFA500",    # Orange
      win_luck < -1 ~ "#DC143C"      # Crimson
    )
  ) |>
  ggplot(aes(x = expected_wins, y = actual_wins)) +
  geom_abline(intercept = 0, slope = 1, linetype = "dashed", color = "gray50", linewidth = 0.8) +
  geom_point(aes(color = luck_color), size = 4, alpha = 0.8) +
  scale_color_identity() +
  geom_text(aes(label = str_trunc(team_name, 12)), 
            vjust = -1.2, hjust = 0.5, size = 3.5, fontface = "bold") +
  labs(
    title = "Fantasy Football Luck Analysis",
    subtitle = "Actual Wins vs Expected Wins (based on scoring)",
    x = "Expected Wins (based on points scored vs league avg)",
    y = "Actual Wins",
    caption = "Teams above the line = lucky | Teams below the line = unlucky"
  ) +
  coord_cartesian(xlim = c(-0.5, 4.5), ylim = c(-0.5, 4.5)) +
  theme_minimal() +
  theme(
    plot.title = element_text(size = 14, face = "bold"),
    plot.subtitle = element_text(size = 11, color = "gray60"),
    axis.title = element_text(size = 11, face = "bold"),
    panel.grid.minor = element_blank()
  )

# 2. STRENGTH OF SCHEDULE ANALYSIS
# ===============================
sos_plot <- luck |>
  arrange(desc(strength_of_schedule)) |>
  mutate(team_name = fct_reorder(team_name, strength_of_schedule)) |>
  ggplot(aes(x = team_name, y = strength_of_schedule)) +
  geom_col(aes(fill = strength_of_schedule), alpha = 0.8) +
  geom_hline(yintercept = mean(luck$strength_of_schedule), 
             linetype = "dashed", color = "black") +
  scale_fill_gradient2(low = "#2E8B57", mid = "#FFD700", high = "#DC143C", 
                       midpoint = mean(luck$strength_of_schedule),
                       name = "SOS") +
  geom_text(aes(label = round(strength_of_schedule, 3)), 
            hjust = -0.1, size = 3, fontface = "bold") +
  labs(
    title = "Strength of Schedule Analysis",
    subtitle = "Average opponent win percentage",
    x = "Team",
    y = "Strength of Schedule (higher = harder)"
  ) +
  coord_flip() +
  theme_minimal() +
  theme(
    plot.title = element_text(size = 14, face = "bold"),
    plot.subtitle = element_text(size = 11, color = "gray60"),
    axis.title = element_text(size = 11, face = "bold"),
    panel.grid.minor = element_blank(),
    legend.position = "none"
  )

# 3. OPPONENT PERFORMANCE vs TEAM ANALYSIS  
# =======================================
opponent_perf_plot <- luck |>
  arrange(opponent_performance_vs_avg) |>
  mutate(
    team_name = fct_reorder(team_name, opponent_performance_vs_avg),
    perf_label = ifelse(opponent_performance_vs_avg < 0, "Lucky", "Unlucky")
  ) |>
  ggplot(aes(x = team_name, y = opponent_performance_vs_avg)) +
  geom_col(aes(fill = opponent_performance_vs_avg < 0), alpha = 0.8) +
  geom_hline(yintercept = 0, linetype = "solid", color = "black") +
  scale_fill_manual(values = c("TRUE" = "#2E8B57", "FALSE" = "#DC143C"),
                    labels = c("Opponents overperformed", "Opponents underperformed"),
                    name = "") +
  geom_text(aes(label = round(opponent_performance_vs_avg, 1)), 
            hjust = ifelse(luck$opponent_performance_vs_avg < 0, 1.2, -0.2), 
            size = 3, fontface = "bold") +
  labs(
    title = "Opponent Performance vs Their Season Average",
    subtitle = "Did opponents play better/worse than usual against you?",
    x = "Team",
    y = "Opponent Scoring Difference (negative = lucky)"
  ) +
  coord_flip() +
  theme_minimal() +
  theme(
    plot.title = element_text(size = 14, face = "bold"),
    plot.subtitle = element_text(size = 11, color = "gray60"),
    axis.title = element_text(size = 11, face = "bold"),
    panel.grid.minor = element_blank(),
    legend.position = "bottom"
  )

# 4. COMPREHENSIVE LUCK SCORECARD
# ==============================
luck_with_score <- luck |>
  mutate(
    total_luck_score = win_luck + 
                      scale(desc(strength_of_schedule))[,1] +  # Easier schedule = more luck
                      scale(desc(opponent_performance_vs_avg))[,1]  # Opponents underperforming = more luck
  ) |>
  arrange(desc(total_luck_score)) |>
  mutate(
    team_name = fct_reorder(team_name, total_luck_score),
    luck_tier = case_when(
      total_luck_score > 1 ~ "Very Lucky",
      total_luck_score > 0 ~ "Somewhat Lucky", 
      total_luck_score > -1 ~ "Average",
      total_luck_score > -2 ~ "Somewhat Unlucky",
      TRUE ~ "Very Unlucky"
    )
  )

luck_scorecard <- luck_with_score |>
  ggplot(aes(x = team_name, y = total_luck_score)) +
  geom_col(aes(fill = luck_tier), alpha = 0.8) +
  geom_hline(yintercept = 0, linetype = "solid", color = "black") +
  scale_fill_manual(values = c(
    "Very Lucky" = "#228B22",
    "Somewhat Lucky" = "#90EE90", 
    "Average" = "#FFD700",
    "Somewhat Unlucky" = "#FFA500",
    "Very Unlucky" = "#DC143C"
  ), name = "Luck Tier") +
  geom_text(aes(label = round(total_luck_score, 1)), 
            hjust = ifelse(luck_with_score$total_luck_score < 0, 1.2, -0.2), 
            size = 3, fontface = "bold") +
  labs(
    title = "Overall Luck Scorecard",
    subtitle = "Composite score: Win luck + Schedule difficulty + Opponent performance",
    x = "Team",
    y = "Total Luck Score (higher = luckier)"
  ) +
  coord_flip() +
  theme_minimal() +
  theme(
    plot.title = element_text(size = 14, face = "bold"),
    plot.subtitle = element_text(size = 11, color = "gray60"),
    axis.title = element_text(size = 11, face = "bold"),
    panel.grid.minor = element_blank(),
    legend.position = "bottom"
  )

# 5. FUTURE STRENGTH OF SCHEDULE
# =============================

# Calculate future SOS by joining with current standings
future_sos <- future |>
  clean_team_names("team_name") |>
  clean_team_names("opponent_name") |>
  left_join(
    standings |> select(opponent_name = Team, opponent_wins = Wins, opponent_losses = Losses),
    by = "opponent_name"
  ) |>
  filter(!is.na(opponent_wins)) |>
  mutate(opponent_games = opponent_wins + opponent_losses) |>
  group_by(team_name) |>
  summarize(
    remaining_games = n(),
    future_sos = mean(opponent_wins / opponent_games, na.rm = TRUE),
    .groups = "drop"
  ) |>
  arrange(desc(future_sos))

future_sos_plot <- future_sos |>
  mutate(team_name = fct_reorder(team_name, future_sos)) |>
  ggplot(aes(x = team_name, y = future_sos)) +
  geom_col(aes(fill = future_sos), alpha = 0.8) +
  geom_hline(yintercept = mean(future_sos$future_sos), 
             linetype = "dashed", color = "black") +
  scale_fill_gradient2(low = "#2E8B57", mid = "#FFD700", high = "#DC143C", 
                       midpoint = mean(future_sos$future_sos),
                       name = "Future SOS") +
  geom_text(aes(label = round(future_sos, 3)), 
            hjust = -0.1, size = 3, fontface = "bold") +
  labs(
    title = "Future Strength of Schedule",
    subtitle = "Remaining opponent win percentage",
    x = "Team",
    y = "Future SOS (higher = harder remaining schedule)"
  ) +
  coord_flip() +
  theme_minimal() +
  theme(
    plot.title = element_text(size = 14, face = "bold"),
    plot.subtitle = element_text(size = 11, color = "gray60"),
    axis.title = element_text(size = 11, face = "bold"),
    panel.grid.minor = element_blank(),
    legend.position = "none"
  )

# COMBINE ALL PLOTS
# ================
combined_plots <- (luck_plot + sos_plot) / (opponent_perf_plot + luck_scorecard)

# Display individual plots
print("=== LUCK vs ACTUAL WINS ===")
print(luck_plot)

print("\n=== STRENGTH OF SCHEDULE ===") 
print(sos_plot)

print("\n=== OPPONENT PERFORMANCE ===")
print(opponent_perf_plot) 

print("\n=== LUCK SCORECARD ===")
print(luck_scorecard)

print("\n=== FUTURE STRENGTH OF SCHEDULE ===")
print(future_sos_plot)

# Save plots
ggsave("luck_analysis_combined.png", combined_plots, 
       width = 16, height = 12, dpi = 300, bg = "white")

# Print summary insights
cat("\n", rep("=", 60), "\n")
cat("KEY INSIGHTS FROM LUCK ANALYSIS:\n")


luckiest <- luck |> slice_max(win_luck, n = 1)
unluckiest <- luck |> slice_min(win_luck, n = 1)
easiest_sos <- luck |> slice_min(strength_of_schedule, n = 1)
hardest_sos <- luck |> slice_max(strength_of_schedule, n = 1)

cat("🍀 LUCKIEST TEAM:", luckiest$team_name, "( +", luckiest$win_luck, "win luck )\n")
cat("💩 UNLUCKIEST TEAM:", unluckiest$team_name, "( ", unluckiest$win_luck, "win luck )\n")
cat("😎 EASIEST SCHEDULE:", easiest_sos$team_name, "( SOS:", round(easiest_sos$strength_of_schedule, 3), ")\n") 
cat("😰 HARDEST SCHEDULE:", hardest_sos$team_name, "( SOS:", round(hardest_sos$strength_of_schedule, 3), ")\n")