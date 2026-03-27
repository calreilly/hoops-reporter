import os
import requests
import json
import time

# List of notable college basketball programs to fetch data for
TEAMS = [
    "Virginia Cavaliers men's basketball",
    "Syracuse Orange men's basketball",
    "Louisville Cardinals men's basketball",
    "Clemson Tigers men's basketball",
    "Miami Hurricanes men's basketball",
    "Illinois Fighting Illini men's basketball",
    "Wisconsin Badgers men's basketball",
    "Michigan State Spartans men's basketball",
    "Michigan Wolverines men's basketball",
    "Indiana Hoosiers men's basketball",
    "Ohio State Buckeyes men's basketball",
    "Iowa Hawkeyes men's basketball",
    "Maryland Terrapins men's basketball",
    "Auburn Tigers men's basketball",
    "Alabama Crimson Tide men's basketball",
    "Florida Gators men's basketball",
    "Arkansas Razorbacks men's basketball",
    "Texas A&M Aggies men's basketball",
    "Texas Longhorns men's basketball",
    "Texas Tech Red Raiders men's basketball",
    "UCLA Bruins men's basketball",
    "USC Trojans men's basketball",
    "Oregon Ducks men's basketball",
    "Villanova Wildcats men's basketball",
    "Creighton Bluejays men's basketball",
    "St. John's Red Storm men's basketball",
    "Saint Mary's Gaels men's basketball",
    "San Diego State Aztecs men's basketball",
    "Nevada Wolf Pack men's basketball",
    "New Mexico Lobos men's basketball",
    "Colorado State Rams men's basketball",
    "Utah State Aggies men's basketball",
    "Dayton Flyers men's basketball"
]

def fetch_wikipedia_summary(title):
    url = f"https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "extracts",
        "explaintext": True,
        "exsectionformat": "plain"
    }
    
    headers = {'User-Agent': 'HoopsReporterBot/1.0 (contact@example.com)'}
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    
    pages = data.get("query", {}).get("pages", {})
    for page_id, page_data in pages.items():
        if "extract" in page_data:
            return page_data["extract"]
    return None

def main():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    
    print(f"Starting batch seed of {len(TEAMS)} teams into {data_dir}...")
    
    for team in TEAMS:
        print(f"Fetching data for {team}...")
        content = fetch_wikipedia_summary(team)
        
        if content:
            # Clean up the filename
            filename = team.replace("'", "").replace(" men's basketball", "").replace(" ", "_").lower() + "_history.txt"
            filepath = os.path.join(data_dir, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  -> Saved to {filename}")
        else:
            print(f"  -> Failed to find Wikipedia article for {team}")
            
        time.sleep(1) # Be nice to the API
        
    print("\nBatch seed complete!")
    print("Restart your Hoops Reporter backend. The HybridRetriever will automatically ingest these new files on startup.")

if __name__ == "__main__":
    main()
