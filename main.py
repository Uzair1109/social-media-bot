import datetime
import os
import json
import time
import gspread
from google.oauth2.service_account import Credentials
from openai import OpenAI

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_services():
    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    gc = gspread.authorize(creds)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return gc, client

def generate_dalle_image(client, prompt):
    print(f"Sending prompt to OpenAI DALL-E 3: '{prompt[:70]}...'")
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="hd",
            n=1
        )
        image_url = response.data[0].url
        print("AI Image generated successfully!")
        return image_url
    except Exception as e:
        print(f"OpenAI Generation Error: {e}")
        return None

def main():
    gc, openai_client = get_services()
    
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

    target_tab_names = ["Nirvan Exports", "Eclat by NRJ", "Flairlytics"]
    total_processed = 0

    for tab_target in target_tab_names:
        try:
            sheet = target_spreadsheet.worksheet(tab_target)
        except Exception as e:
            print(f"Could not open tab '{tab_target}': {e}")
            continue

        tab_name = sheet.title
        all_values = sheet.get_all_values()
        
        print("\n" + "=" * 50)
        print(f"Processing Tab: '{tab_name}' ({len(all_values)} rows)")
        print("=" * 50)
        
        if len(all_values) < 2:
            print(f"Skipping tab '{tab_name}' - insufficient rows.")
            continue

        target_row_idx = None
        target_row_data = None

        for idx, row in enumerate(all_values[1:], start=2):
            status = str(row[7]).strip().lower() if len(row) > 7 else ""
            prompt_val = str(row[4]).strip() if len(row) > 4 else ""
            
            if status != "done" and len(prompt_val) > 0:
                target_row_idx = idx
                target_row_data = row
                break

        if not target_row_idx or not target_row_data:
            print(f"No pending rows found for '{tab_name}'.")
            continue

        brand = str(target_row_data[1]).strip() if len(target_row_data) > 1 and target_row_data[1].strip() else tab_name
        topic = str(target_row_data[2]).strip() if len(target_row_data) > 2 else "Asset"
        prompt = str(target_row_data[4]).strip() if len(target_row_data) > 4 else "Professional photo"

        print(f"Generating for [{tab_name}] - Row {target_row_idx}: {topic}")
        image_url = generate_dalle_image(openai_client, prompt)
        
        if image_url:
            sheet.update_cell(target_row_idx, 7, image_url)
            sheet.update_cell(target_row_idx, 8, "Done")
            print(f"Updated row {target_row_idx} in '{tab_name}' to Done.")
            total_processed += 1
            time.sleep(2)

    print("\n" + "=" * 50)
    print(f"Workflow Finished! Total assets generated: {total_processed}")
    print("=" * 50)

if __name__ == "__main__":
    main()
