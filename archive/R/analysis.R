# Fantasy Football Quadrant Analysis - Using ESPN API Data
# Load required libraries
library(tidyverse)


# Load data from ESPN API CSV output
df <- read_csv("./data/espn_standings.csv") |>
  # Calculate league averages for reference
  mutate(
    PA = PA * -1, 
    avg_pf = mean(PF),
    avg_pa = mean(PA)
  ) |>
  # Create shortened team names dynamically from the Team column
  mutate(
    # Remove everything in parentheses and trim whitespace
    team_clean = str_remove(Team, "\\s*\\([^\\)]+\\)") |>
      str_trim(),
    # Create short names by taking first 2 words or full name if ≤2 words
    Short_Name = map_chr(team_clean, ~{
      words <- str_split(.x, "\\s+")[[1]]
      if(length(words) <= 3) {
        paste(words, collapse = " ")
      } else {
        paste(words[1:3], collapse = " ")
      }
    })
  ) |>
  # Create quadrant colors based on position relative to averages
  mutate(
    quadrant_color = case_when(
      PF > avg_pf & PA < avg_pa ~ "lightblue",  # Good offense, good defense
      PF > avg_pf & PA >= avg_pa ~ "blue",     # Good offense, bad defense  
      PF <= avg_pf & PA < avg_pa ~ "red",      # Bad offense, good defense
      PF <= avg_pf & PA >= avg_pa ~ "pink"     # Bad offense, bad defense
    )
  )

# Extract averages for plot reference lines
avg_pf <- df$avg_pf[1]  # All rows have same value, just take first
avg_pa <- df$avg_pa[1]

# Create the styled quadrant plot
p <- df |>
  ggplot(aes(x = PF, y = PA)) +
  
  # Add threshold lines (dashed black lines)
  geom_hline(yintercept = avg_pa, linetype = "dashed", color = "black", linewidth = 0.7) +
  geom_vline(xintercept = avg_pf, linetype = "dashed", color = "black", linewidth = 0.7) +
  
  # Add points with colors matching their quadrant
  geom_point(aes(color = quadrant_color), size = 3, alpha = 0.8) +
  scale_color_identity() +  # Use the actual color values
  
  # Add team labels
  geom_text(aes(label = Short_Name), vjust = -1.5, hjust = 0.5, size = 4, color = "black") +
  
  # Expand plot limits for better label visibility
  expand_limits(
    x = c(min(df$PF) - 10, max(df$PF) + 10),
    y = c(min(df$PA) - 10, max(df$PA) + 10)
  ) +
  
  # Labels and title
  labs(
    title = "730UFFL Quadrants",
    subtitle = "Team Performance by Points For vs Points Against",
    x = "Points For", 
    y = "Points Against",
    caption = "Blue = Elite (High Scoring, Low Points Against) | Red = Ass (Low Scoring, High Points Against)"
  ) +
  
  # Theme customization
  theme_minimal() +
  theme(
    plot.title = element_text(size = 16, face = "bold", hjust = 0.5),
    plot.subtitle = element_text(size = 12, hjust = 0.5, color = "gray60"),
    axis.title = element_text(size = 12, face = "bold"),
    axis.text = element_text(size = 10),
    panel.grid.minor = element_blank(),
    panel.grid.major = element_line(color = "gray90", linewidth = 0.5),
    plot.background = element_rect(fill = "white", color = NA),
    panel.background = element_rect(fill = "white", color = NA),
    plot.caption = element_text(size = 10, color = "gray60", hjust = 0.5),
    plot.margin = margin(20, 60, 20, 20)
  )

# Display the plot
print(p)

# Optional: Save the plot with high quality
# ggsave("fantasy_football_quadrants_styled.png", plot = p, 
#        width = 12, height = 8, dpi = 300, bg = "white")