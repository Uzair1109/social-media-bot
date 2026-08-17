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

    total_processed = 0

    for sheet in target_spreadsheet.worksheets():
        tab_name = sheet.title.strip()
        all_values = sheet.get_all_values()
        
        print("\n" + "=" * 50)
        print(f"Scanning Tab: '{tab_name}' ({len(all_values)} total rows)")
        print("=" * 50)
        
        if len(all_values) < 2:
            print(f"Skipping empty tab '{tab_name}'.")
            continue

        target_row_idx = None
        target_row_data = None

        # Find the first row where status is not 'done'
        for idx, row in enumerate(all_values[1:], start=2):
            status = str(row[7]).strip().lower() if len(row) > 7 else ""
            prompt_val = str(row[4]).strip() if len(row) > 4 else ""
            
            if status != "done" and len(prompt_val) > 0:
                target_row_idx = idx
                target_row_data = row
                break

        if not target_row_idx or not target_row_data:
            print(f"No pending rows found in tab '{tab_name}'.")
            continue

        brand = target_row_data[1].strip() if len(target_row_data) > 1 and target_row_data[1].strip() else tab_name
        topic = target_row_data[2].strip() if len(target_row_data) > 2 else "Asset"
        prompt = target_row_data[4].strip() if len(target_row_data) > 4 else "Professional photo"

        print(f"Generating for [{tab_name}] - Row {target_row_idx}: {topic}")
        image_url = generate_ai_image(prompt)
        
        if image_url:
            print(f"Generated Image URL: {image_url}")
            sheet.update_cell(target_row_idx, 7, image_url)
            sheet.update_cell(target_row_idx, 8, "Done")
            print(f"Updated row {target_row_idx} in '{tab_name}' to Done.")
            total_processed += 1
        else:
            print(f"Failed to generate asset for tab '{tab_name}'.")

    print("\n" + "=" * 50)
    print(f"Workflow Finished! Total assets generated: {total_processed}")
    print("=" * 50)

if __name__ == "__main__":
    main()
