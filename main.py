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
        
    print(f"Successfully connected to: '{target_spreadsheet.title}'")

    today_dt = datetime.datetime.now()
    today_formats = [
        today_dt.strftime("%b %d %Y").lower(),
        today_dt.strftime("%b %d, %Y").lower(),
        today_dt.strftime("%Y-%m-%d").lower(),
        "test"
    ]

    total_processed = 0

    for sheet in target_spreadsheet.worksheets():
        all_values = sheet.get_all_values()
        if len(all_values) < 2:
            continue
            
        print(f"\nScanning tab: '{sheet.title}' ({len(all_values)-1} rows)...")
        tab_processed = 0
        
        for idx, row in enumerate(all_values[1:], start=2):
            raw_date = str(row[0]).strip().lower() if len(row) > 0 else ""
            status = str(row[7]).strip().lower() if len(row) > 7 else ""
            
            # Check for matching date or pending row
            is_date_match = any(fmt in raw_date for fmt in today_formats)
            
            if (is_date_match or tab_processed == 0) and status != "done":
                brand = row[1] if len(row) > 1 and row[1].strip() else sheet.title
                topic = row[2] if len(row) > 2 else "Asset"
                prompt = row[4] if len(row) > 4 else "Professional photo"
                
                print(f"\nProcessing Post for [{sheet.title}]:")
                print(f"Row: {idx}")
                print(f"Brand: {brand}")
                print(f"Topic: {topic}")
                
                image_url = generate_ai_image(prompt)
                if image_url:
                    print(f"Generated Image URL: {image_url}")
                    sheet.update_cell(idx, 7, image_url)
                    sheet.update_cell(idx, 8, "Done")
                    print(f"Row {idx} in '{sheet.title}' marked as 'Done'.")
                    
                tab_processed += 1
                total_processed += 1
                break

    print(f"\nExecution finished. Total assets processed: {total_processed}")

if __name__ == "__main__":
    main()
