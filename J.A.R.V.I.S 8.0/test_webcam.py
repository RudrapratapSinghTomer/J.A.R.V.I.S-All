import cv2
import time

def test_webcam():
    print("Testing Webcam...")
    # Try DirectShow first
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("DirectShow failed, trying default...")
        cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("CRITICAL: Could not open webcam.")
        return False

    ret, frame = cap.read()
    if ret:
        print("Webcam frame captured successfully!")
        cv2.imwrite("webcam_test.png", frame)
        print("Saved to webcam_test.png")
    else:
        print("Failed to capture frame from webcam.")
    
    cap.release()
    return ret

if __name__ == "__main__":
    test_webcam()
