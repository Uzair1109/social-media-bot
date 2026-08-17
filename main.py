import datetime
import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_gspread_client():
    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc

def generate_ai_image(prompt):
    api_token = os.environ["REPLICATE_API_TOKEN"]
    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "version": "black-forest-labs/flux-1.1-pro",
        "input": {
            "prompt": prompt,
            "aspect_ratio": "1:1",
            "output_format": "png",
            "output_quality": 95
        }
    }
    
    print(f"Sending prompt to Flux AI: '{prompt[:60]}...'")
    response = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=data)
    prediction = response.json()
    
    poll_url = prediction.get("urls", {}).get("get")
    if not poll_url:
        print("Error starting prediction:", prediction)
        return None

    while prediction.get("status") not in ["succeeded", "failed"]:
        response = requests.get(poll_url, headers=headers)
        prediction = response.json()
        
    if prediction.get("status") == "succeeded":
        image_url = prediction["output"]
        print("AI Image generated successfully!")
        return image_url
    else:
        print("AI Image generation failed:", prediction)
        return None

def main():
    gc = get_gspread_client()
    
    print("Searching for available spreadsheets...")
    available_sheets = gc.openall()
    if not available_sheets:
        print("No spreadsheets found shared with this service account!")
        return
        
    target_spreadsheet = None
    for s in available_sheets:
        if "Master_Social_Media_Calendar" in s.title or "Social" in s.title:
            target_spreadsheet = s
            break
            
    if not target_spreadsheet:
        target_spreadsheet = available_sheets[0]
        
    print(f"Connected to spreadsheet: '{target_spreadsheet.title}'")

    today_dt = datetime.datetime.now()
    today_formats = [
        today_dt.strftime("%b %d %Y").lower(),
        today_dt.strftime("%b %d, %Y").lower(),
        today_dt.strftime("%Y-%m-%d").lower(),
        "test"
    ]

    total_processed = 0
    worksheets = target_spreadsheet.worksheets()

    for sheet in worksheets:
        tab_name = sheet.title.strip()
        all_values = sheet.get_all_values()
        
        print("\n" + "=" * 50)
        print(f"Scanning Tab: '{tab_name}' ({len(all_values)} total rows)")
        print("=" * 50)
        
        if len(all_values) < 2:
            print(f"Skipping tab '{tab_name}' (insufficient rows).")
            continue

        header = [h.strip().lower() for h in all_values[0]]
        
        # Column indexes (1-based for gspread updates)
        date_col = next((i + 1 for i, h in enumerate(header) if "date" in h), 1)
        brand_col = next((i + 1 for i, h in enumerate(header) if "brand" in h), 2)
        topic_col = next((i + 1 for i, h in enumerate(header) if "topic" in h), 3)
        prompt_col = next((i + 1 for i, h in enumerate(header) if "prompt" in h or "direction" in h or "visual" in h), 5)
        link_col = next((i + 1 for i, h in enumerate(header) if "link" in h or "url" in h or "folder" in h or "asset" in h), 7)
        status_col = next((i + 1 for i, h in enumerate(header) if "status" in h), 8)

        target_row_idx = None
        target_row_data = None

        # Pass 1: Try matching today's date
        for idx, row in enumerate(all_values[1:], start=2):
            raw_date = str(row[date_col - 1]).strip().lower() if len(row) >= date_col else ""
            status = str(row[status_col - 1]).strip().lower() if len(row) >= status_col else ""
            
            if any(fmt in raw_date for fmt in today_formats) and status != "done":
                target_row_idx = idx
                target_row_data = row
                print(f"Found matching date in row {idx}")
                break

        # Pass 2: Fallback to first non-Done row with a prompt
        if not target_row_idx:
            for idx, row in enumerate(all_values[1:], start=2):
                status = str(row[status_col - 1]).strip().lower() if len(row) >= status_col else ""
                has_prompt = len(row) >= prompt_col and str(row[prompt_col - 1]).strip() != ""
                if status != "done" and has_prompt:
                    target_row_idx = idx
                    target_row_data = row
                    print(f"Found pending row {idx}")
                    break

        if not target_row_idx or not target_row_data:
            print(f"No pending rows to process in tab '{tab_name}'.")
            continue

        brand = str(target_row_data[brand_col - 1]).strip() if len(target_row_data) >= brand_col and str(target_row_data[brand_col - 1]).strip() else tab_name
        topic = str(target_row_data[topic_col - 1]).strip() if len(target_row_data) >= topic_col else "Asset"
        prompt = str(target_row_data[prompt_col - 1]).strip() if len(target_row_data) >= prompt_col else "Professional commercial photo"

        print(f"Processing row {target_row_idx} for Brand '{brand}': {topic}")
        image_url = generate_ai_image(prompt)
        
        if image_url:
            print(f"Generated Image URL: {image_url}")
            sheet.update_cell(target_row_idx, link_col, image_url)
            sheet.update_cell(target_row_idx, status_col, "Done")
            print(f"Successfully marked row {target_row_idx} in '{tab_name}' as Done.")
            total_processed += 1
        else:
            print(f"Failed to generate asset for tab '{tab_name}'.")

    print("\n" + "=" * 50)
    print(f"Workflow Finished! Total assets generated across all tabs: {total_processed}")
    print("=" * 50)

if __name__ == "__main__":
    main()
