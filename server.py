import cv2
import numpy as np
import face_recognition
import os
from datetime import datetime, time
import pandas as pd
from flask import Flask, request, Response
import requests # For Telegram
import atexit   # <-- NEW: Import the atexit module

app = Flask(__name__)

# --- CONFIGURATION ---
KNOWN_FACES_DIR = 'image_folder'
ATTENDANCE_FILE = 'Attendance.csv'

# --- Time Window Configuration ---
START_TIME = time(8, 0, 0)      # 8:00 AM
END_TIME = time(23, 0, 0)     # 11:00 aM (for demo)
ON_TIME_LIMIT = time(8, 45, 0) # 8:45 AM

# --- TELEGRAM BOT CONFIG ---
BOT_TOKEN = "8515982295:AAEepLkkka1jI_exG-O1Vz3EALh7NGPNjck"
CHAT_ID = "7502020115"

# --- (A) LOAD KNOWN FACES ON STARTUP ---
print("Loading known faces...")
known_face_encodings = []
known_face_names = []

for name in os.listdir(KNOWN_FACES_DIR):
    image_path = os.path.join(KNOWN_FACES_DIR, name)
    if not os.path.isfile(image_path) or name.startswith('.'):
        continue
    try:
        known_image = face_recognition.load_image_file(image_path)
        encoding = face_recognition.face_encodings(known_image)[0]
        known_face_encodings.append(encoding)
        student_name = os.path.splitext(name)[0].upper() 
        known_face_names.append(student_name)
        print(f"Loaded encoding for: {student_name}")
    except Exception as e:
        print(f"Error loading {image_path}: {e} (Is there a face in the image?)")

# --- Create a UNIQUE list of names for the final report ---
unique_known_names = list(set(known_face_names))

print("Encodings complete. Server is ready.")
print(f"Server is running on http://0.0.0.0:5000")
print(f"Attendance logging active between {START_TIME} and {END_TIME}.")
print("Press CTRL+C to stop the server and send the final report.")


# --- (B) TELEGRAM BOT FUNCTION ---
def send_telegram_report(filename):
    """Sends the attendance CSV file to your Telegram chat."""
    if not os.path.exists(filename):
        print("Attendance file not found. Nothing to send.")
        return False
    print("Sending report to Telegram...")
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        with open(filename, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': CHAT_ID, 'caption': 'Here is the final attendance report.'}
            response = requests.post(url, data=data, files=files)
        
        if response.status_code == 200:
            print("Telegram report sent successfully!")
            return True
        else:
            print(f"Error sending to Telegram: {response.text}")
            return False
    except Exception as e:
        print(f"Error sending to Telegram: {e}")
        return False

# --- (C) ATTENDANCE LOGGING FUNCTION ---
def log_attendance(name, remark):
    """Logs the attendance to a CSV file."""
    status = "Present"
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    columns = ["Name", "Date", "Time", "Status", "Remark"]

    try:
        df = pd.read_csv(ATTENDANCE_FILE)
    except FileNotFoundError:
        df = pd.DataFrame(columns=columns)
        
    if df.empty or 'Name' not in df.columns:
        df = pd.DataFrame(columns=columns)
        
    # --- This logic is correct. "Already marked" is not a bug. ---
    if not ((df['Name'] == name) & (df['Date'] == date_str)).any():
        new_entry = pd.DataFrame([[name, date_str, time_str, status, remark]], columns=columns)
        df = pd.concat([df, new_entry], ignore_index=True)
        df.to_csv(ATTENDANCE_FILE, index=False)
        print(f"Logged attendance for {name} ({remark})")
    else:
        print(f"{name} already marked present today.")


# --- (D) THE 'TAKE ATTENDANCE' ROUTE ---
@app.route('/upload', methods=['POST'])
def handle_image_upload():
    
    now = datetime.now()
    current_time = now.time()

    if not (START_TIME <= current_time <= END_TIME):
        print(f"Scan received at {current_time}. TIME LIMIT REACHED.")
        return Response("TIME LIMIT REACHED", status=200)

    try:
        image_data = np.frombuffer(request.data, np.uint8)
        img = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        
        if img is None:
            print("Received empty image frame.")
            return Response("Error: Empty Frame", status=400)

        small_frame = cv2.resize(img, (0, 0), fx=0.25, fy=0.25)
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        recognized_name = "UNKNOWN"

        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
            best_match_index = np.argmin(face_distances)
            
            if matches[best_match_index]:
                recognized_name = known_face_names[best_match_index]
                print(f"Match found: {recognized_name}")
                
                if current_time <= ON_TIME_LIMIT:
                    remark = "ON-TIME"
                else:
                    remark = "LATE"
                
                log_attendance(recognized_name, remark)
                break
        
        if recognized_name == "UNKNOWN":
            print("No match found. Person is UNKNOWN.")

        return Response(recognized_name, status=200)

    except Exception as e:
        print(f"Error during processing: {e}")
        return Response(f"Error: {e}", status=500)

# --- (E) FUNCTION: Finalize Report with Absentees ---
def finalize_and_send_report():
    print("\nServer shutting down. Finalizing report...")
    
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    columns = ["Name", "Date", "Time", "Status", "Remark"]

    try:
        df = pd.read_csv(ATTENDANCE_FILE)
    except FileNotFoundError:
        df = pd.DataFrame(columns=columns)
        
    if df.empty or 'Name' not in df.columns:
        df = pd.DataFrame(columns=columns)

    # Get a list of everyone who was present *today*
    present_names_today = set(df[df['Date'] == date_str]['Name'])

    absent_entries = []
    # Check against the master list of unique known names
    for name in unique_known_names: 
        if name not in present_names_today:
            absent_entry = {"Name": name, "Date": date_str, "Time": "-", "Status": "Absent", "Remark": "-"}
            absent_entries.append(absent_entry)
            print(f"Marking {name} as Absent.")

    if absent_entries:
        absent_df = pd.DataFrame(absent_entries)
        df = pd.concat([df, absent_df], ignore_index=True)
    
    df.to_csv(ATTENDANCE_FILE, index=False)
    print("Final report saved locally.")
    
    # Send the final report to Telegram
    send_telegram_report(ATTENDANCE_FILE)

# --- (F) RUN THE SERVER WITH SHUTDOWN HOOK ---
# --- THIS IS THE FIX ---
if __name__ == '__main__':
    # Register the finalize_and_send_report function to run on script exit
    atexit.register(finalize_and_send_report)
    
    # Run the server
    app.run(host='0.0.0.0', port=5000, debug=False)
