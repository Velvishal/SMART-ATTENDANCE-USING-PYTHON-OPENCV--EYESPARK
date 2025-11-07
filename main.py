from flask import Flask, request
import face_recognition
import numpy as np
import cv2
import os

app = Flask(__name__)

# --- Load Known Faces ---
known_face_encodings = []
known_face_names = []
path = 'image_folder'

print("Loading known faces...")
for filename in os.listdir(path):
    try:
        image = face_recognition.load_image_file(os.path.join(path, filename))
        # Get encoding (the first face found in the image)
        encoding = face_recognition.face_encodings(image)[0]
        known_face_encodings.append(encoding)
        # Get the name from the filename
        name = os.path.splitext(filename)[0]
        known_face_names.append(name)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
print(f"Loaded {len(known_face_names)} known faces.")

# --- API Endpoint for receiving images ---
@app.route('/upload', methods=['POST'])
def upload():
    print("Received an image from ESP32-CAM...")
    recognized_name = "Unknown"
    try:
        # Get image data from the request
        nparr = np.frombuffer(request.data, np.uint8)
        # Decode image
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Find faces in the uploaded image
        face_locations = face_recognition.face_locations(img)
        face_encodings = face_recognition.face_encodings(img, face_locations)

        # Loop through each face found in the image
        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            
            if True in matches:
                first_match_index = matches.index(True)
                recognized_name = known_face_names[first_match_index]
                print(f"Match found: {recognized_name}")
                break  # Stop after the first match
        
        if recognized_name == "Unknown":
            print("No match found.")

        # Return the result as plain text
        return recognized_name

    except Exception as e:
        print(f"Error processing image: {e}")
        return "Error", 500

# --- Start the Server ---
if __name__ == '__main__':
    # Use host='0.0.0.0' to make the server accessible from your ESP32
    print("Starting Flask server... a W S G I server instead.[0m")
    app.run(host='0.0.0.0', port=5000, debug=False)
