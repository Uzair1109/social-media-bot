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

    # Explicitly iterate over all tabs in the workbook
    for sheet in target_spreadsheet.worksheets():
        tab_name = sheet.title.strip()
        all_values = sheet.get_all_values()
        
        print(f"\n==========================================")
        print(f"Checking Worksheet: '{tab_name}' (Total Rows: {len(all_values)})")
        print(f"==========================================")
        
        if len(all_values) < 2:
            print(f"Skipping tab '{tab_name}' because it has no data rows.")
            continue
            
        row_to_process = None
        row_index_to_process = None
        
        # 1. Look for today's date first
        for idx, row in enumerate(all_values[1:], start=2):
            raw_date = str(row[0]).strip().lower() if len(row) > 0 else ""
            status = str(row[7]).strip().lower() if len(row) > 7 else ""
            
            if any(fmt in raw_date for fmt in today_formats) and status != "done":
                row_to_process = row
                row_index_to_process = idx
                print(f"Found match by date at row {idx}")
                break
                
        # 2. If no exact date match, pick the first row that is not 'Done'
        if not row_to_process:
            for idx, row in enumerate(all_values[1:], start=2):
                status = str(row[7]).strip().lower() if len(row) > 7 else ""
                if status != "done" and len(row) > 4 and row[4].strip() != "":
                    row_to_process = row
                    row_index_to_process = idx
                    print(f"Found pending row at row {idx}")
                    break

        if not row_to_process:
            print(f"No pending rows found in tab '{tab_name}'.")
            continue

        brand = row_to_process[1] if len(row_to_process) > 1 and row_to_process[1].strip() else tab_name
        topic = row_to_process[2] if len(row_to_process) > 2 else "Asset"
        prompt = row_to_process[4] if len(row_to_process) > 4 else "Professional product photo"

        print(f"Processing post for Brand: {brand}")
        print(f"Row Index: {row_index_to_process}")
        print(f"Topic: {topic}")

        image_url = generate_ai_image(prompt)
        if image_url:
            print(f"Generated Image URL: {image_url}")
            sheet.update_cell(row_index_to_process, 7, image_url)
            sheet.update_cell(row_index_to_process, 8, "Done")
            print(f"Updated row {row_index_to_process} in '{tab_name}' to Done.")
            total_processed += 1
        else:
            print(f"Skipping sheet update for '{tab_name}' due to generation error.")

    print(f"\n==========================================")
    print(f"Run completed. Total tabs processed: {total_processed}")
    print(f"==========================================")

if __name__ == "__main__":
    main()
