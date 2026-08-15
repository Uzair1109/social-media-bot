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

# --- 2. GENERATE AI IMAGE ---
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
        print("❌ Error starting prediction:", prediction)
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
    
    print("🔍 Searching for available spreadsheets...")
    available_sheets = gc.openall()
    print(f"Found {len(available_sheets)} shared spreadsheet(s): {[s.title for s in available_sheets]}")
    
    if not available_sheets:
        print("❌ No spreadsheets found shared with this service account!")
        return
        
    # Match by title or fallback to the first available shared spreadsheet
    target_spreadsheet = None
    for s in available_sheets:
        if "Master_Social_Media_Calendar" in s.title or "Social" in s.title:
            target_spreadsheet = s
            break
            
    if not target_spreadsheet:
        target_spreadsheet = available_sheets[0]
        
    print(f"✅ Successfully connected to: '{target_spreadsheet.title}'")

    today_dt = datetime.datetime.now()
    today_formats = [
        today_dt.strftime("%b %d %Y").lower(),   # aug 15 2026
        today_dt.strftime("%b %d, %Y").lower(),  # aug 15, 2026
        today_dt.strftime("%Y-%m-%d").lower(),   # 2026-08-15
        "test"
    ]
    
    target_sheet = None
    target_row_idx = None
    target_row_data = None

    for sheet in target_spreadsheet.worksheets():
        all_values = sheet.get_all_values()
        if len(all_values) < 2:
            continue
            
        print(f"\n📑 Checking tab: '{sheet.title}' ({len(all_values)-1} rows)...")
        
        for idx, row in enumerate(all_values[1:], start=2):
            raw_date = str(row[0]).strip().lower() if len(row) > 0 else ""
            status = str(row[7]).strip().lower() if len(row) > 7 else ""
            
            if any(fmt in raw_date for fmt in today_formats) and status != "done":
                target_sheet = sheet
                target_row_idx = idx
                target_row_data = row
                break
                
        if target_sheet:
            break

    # Fallback to first non-Done row across tabs
    if not target_sheet:
        print("\n⚠️ No exact date match found for today. Picking first pending row to test...")
        for sheet in target_spreadsheet.worksheets():
            all_values = sheet.get_all_values()
            for idx, row in enumerate(all_values[1:], start=2):
                status = str(row[7]).strip().lower() if len(row) > 7 else ""
                if status != "done":
                    target_sheet = sheet
                    target_row_idx = idx
                    target_row_data = row
                    break
            if target_sheet:
                break

    if not target_sheet or not target_row_data:
        print("❌ No eligible rows found.")
        return

    brand = target_row_data[1] if len(target_row_data) > 1 else target_sheet.title
    topic = target_row_data[2] if len(target_row_data) > 2 else "Asset"
    prompt = target_row_data[4] if len(target_row_data) > 4 else "Professional photo"
    folder_id = target_row_data[6].strip() if len(target_row_data) > 6 else ""

    print(f"\n🎯 Processing Post:")
    print(f"   • Brand: {brand}")
    print(f"   • Topic: {topic}")
    print(f"   • Folder ID: {folder_id}")

    if not folder_id or folder_id == "YOUR_DRIVE_FOLDER_ID":
        print("❌ Error: Invalid Folder ID in Column G!")
        return

    # Generate Image & Upload
    image_path = generate_ai_image(prompt)
    if image_path:
        file_name = f"{today_dt.strftime('%Y-%m-%d')}_{brand.replace(' ', '_')}_{topic.replace(' ', '_')}.png"
        file_id = upload_to_drive(drive_service, image_path, folder_id, file_name)
        print(f"🎉 SUCCESS! File uploaded to Drive. ID: {file_id}")
        
        target_sheet.update_cell(target_row_idx, 8, "Done")
        print(f"✅ Row {target_row_idx} status updated to 'Done'.")

if __name__ == "__main__":
    main()
