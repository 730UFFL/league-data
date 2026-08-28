library(httr2)
library(jsonlite)
library(dplyr)
library(readr)

get_espn_fantasy_standings <- function(league_id, year = 2025, espn_s2 = NULL, swid = NULL) {
  # ESPN Fantasy API endpoint
  base_url <- "https://fantasy.espn.com/apis/v3/games/ffl/seasons"
  url <- paste0(base_url, "/", year, "/segments/0/leagues/", league_id)
  
  # Create request
  req <- request(url) |>
    req_url_query(view = "mTeam") |>
    req_headers(`Content-Type` = "application/json")
  
  # Add authentication cookies if provided (for private leagues)
  if (!is.null(espn_s2) && !is.null(swid)) {
    req <- req |>
      req_headers(Cookie = paste0("ESPN_S2=", espn_s2, "; SWID=", swid))
  }
  
  # Make request
  tryCatch({
    resp <- req_perform(req)
    data <- resp |> resp_body_json()
    
    # Extract team data
    teams <- data$teams
    
    # Create standings dataframe
    standings <- map_dfr(teams, function(team) {
      tibble(
        RK = team$playoffSeed %||% 0,
        Team = paste0(team$location, " ", team$nickname, " (", team$primaryOwner, ")"),
        PF = round(team$record$overall$pointsFor, 2),
        PA = round(team$record$overall$pointsAgainst, 2),
        Wins = team$record$overall$wins,
        Losses = team$record$overall$losses,
        Ties = team$record$overall$ties %||% 0,
        Record = paste0(team$record$overall$wins, "-", 
                       team$record$overall$losses, "-", 
                       team$record$overall$ties %||% 0),
        Win_Pct = round(team$record$overall$percentage, 3),
        Moves = team$transactionCounter$acquisitions %||% 0
      )
    }) |>
    arrange(RK) |>
    mutate(RK = row_number())
    
    return(standings)
    
  }, error = function(e) {
    message("Error fetching ESPN data: ", e$message)
    return(NULL)
  })
}

# Usage:
 league_id <- "634388"
 espn_s2 <- "<redacted - see .env>"  # Optional for private leagues
 swid <- "<redacted - see .env>"        # Optional for private leagues

 standings <- get_espn_fantasy_standings(league_id, 2025, espn_s2, swid)
 write_csv(standings, "espn_standings.csv")