import datetime
import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 1. AUTHENTICATION & SETUP ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_google_services():
    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    gc = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return gc, drive_service

# --- 2. GENERATE IMAGE VIA REPLICATE API (FLUX.1) ---
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
    
    print(f"🎨 Sending prompt to Flux AI: '{prompt[:60]}...'")
    response = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=data)
    prediction = response.json()
    
    poll_url = prediction.get("urls", {}).get("get")
    if not poll_url:
        print("❌ Error initiating image prediction:", prediction)
        return None

    while prediction.get("status") not in ["succeeded", "failed"]:
        response = requests.get(poll_url, headers=headers)
        prediction = response.json()
        
    if prediction.get("status") == "succeeded":
        image_url = prediction["output"]
        img_data = requests.get(image_url).content
        file_path = "output_asset.png"
        with open(file_path, "wb") as f:
            f.write(img_data)
        print("✅ AI Image generated successfully!")
        return file_path
    else:
        print("❌ AI Image generation failed:", prediction)
        return None

# --- 3. UPLOAD TO GOOGLE DRIVE ---
def upload_to_drive(drive_service, file_path, folder_id, file_name):
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype='image/png')
    uploaded_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    return uploaded_file.get('id')

# --- 4. MAIN WORKFLOW ---
def main():
    gc, drive_service = get_google_services()
    spreadsheet = gc.open("Master_Social_Media_Calendar")
    
    today_dt = datetime.datetime.now()
    possible_today_formats = [
        today_dt.strftime("%b %d %Y"),   # Aug 13 2026
        today_dt.strftime("%b %d, %Y"),  # Aug 13, 2026
        today_dt.strftime("%Y-%m-%d"),   # 2026-08-13
        "TEST"                           # Manual test trigger
    ]
    
    print(f"📅 Today's Date Search Formats: {possible_today_formats}")
    
    target_row = None
    target_sheet = None
    target_row_idx = None

    for sheet in spreadsheet.worksheets():
        records = sheet.get_all_records()
        print(f"\n📑 Checking sheet tab: '{sheet.title}' ({len(records)} rows)...")
        
        for row_idx, row in enumerate(records, start=2):
            raw_date = str(row.get("Date", "")).strip()
            status = str(row.get("Status", "")).strip()
            
            # Match date or check if status isn't done
            if (any(fmt.lower() in raw_date.lower() for fmt in possible_today_formats) or raw_date == "TEST") and status != "Done":
                target_row = row
                target_sheet = sheet
                target_row_idx = row_idx
                break
        
        if target_row:
            break

    # FALLBACK TEST: If no row matches today's date, pick the first non-Done row to test!
    if not target_row:
        print("\n⚠️ No exact date match found for today. Running TEST on the first pending post...")
        first_sheet = spreadsheet.worksheets()[0]
        records = first_sheet.get_all_records()
        for row_idx, row in enumerate(records, start=2):
            if str(row.get("Status", "")).strip() != "Done":
                target_row = row
                target_sheet = first_sheet
                target_row_idx = row_idx
                break

    if not target_row:
        print("❌ No eligible posts found across any tabs.")
        return

    # Extract details
    brand = target_row.get("Brand Name", target_sheet.title)
    topic = target_row.get("Content Topic", "Asset")
    prompt = target_row.get("Visual Direction & Hook", target_row.get("AI Image Prompt", ""))
    folder_id = str(target_row.get("Folder ID", "")).strip()

    print(f"\n🎯 Selected Post for Processing:")
    print(f"   • Tab: {target_sheet.title}")
    print(f"   • Brand: {brand}")
    print(f"   • Topic: {topic}")
    print(f"   • Folder ID: {folder_id}")

    if not folder_id or folder_id == "YOUR_DRIVE_FOLDER_ID":
        print("❌ Invalid Folder ID. Please update Column G in Google Sheets with your real Drive Folder ID!")
        return

    # Generate and Upload
    image_path = generate_ai_image(prompt)
    if image_path:
        file_name = f"{today_dt.strftime('%Y-%m-%d')}_{brand.replace(' ', '_')}_{topic.replace(' ', '_')}.png"
        file_id = upload_to_drive(drive_service, image_path, folder_id, file_name)
        print(f"🎉 SUCCESS! File uploaded to Google Drive. File ID: {file_id}")
        
        # Find column index for Status and update
        headers = [str(h).strip() for h in target_sheet.row_values(1)]
        status_col = headers.index("Status") + 1 if "Status" in headers else 8
        target_sheet.update_cell(target_row_idx, status_col, "Done")
        print(f"✅ Updated status to 'Done' in Row {target_row_idx} of sheet '{target_sheet.title}'.")

if __name__ == "__main__":
    main()
