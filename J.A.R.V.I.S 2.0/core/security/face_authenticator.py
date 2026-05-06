import os
import cv2
import face_recognition
import numpy as np
import logging
from pathlib import Path

logger = logging.getLogger("jarvis.face_auth")


class FaceAuthenticator:
    def __init__(self, host_face_path="context/host_face_print.jpg"):
        self.host_face_path = Path(host_face_path)
        self.host_encoding = self._load_host_encoding()

    @property
    def is_enrolled(self) -> bool:
        return self.host_encoding is not None

    def _load_host_encoding(self):
        if self.host_face_path.exists():
            try:
                image = face_recognition.load_image_file(str(self.host_face_path))
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    logger.info("Host face encoding loaded.")
                    return encodings[0]
            except Exception as e:
                logger.error(f"Error loading host face print: {e}")
        return None

    def capture_and_verify(self):
        """Capture a frame from webcam and verify against host."""
        if self.host_encoding is None:
            logger.warning("No host face print found. Verification impossible.")
            return False, "no_face_print"

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("Could not open webcam.")
            return False, "camera_unavailable"

        try:
            ret, frame = cap.read()
            if not ret:
                return False, "frame_capture_failed"

            # Convert BGR (OpenCV) to RGB (face_recognition)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Find all faces in the frame
            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

            for face_encoding in face_encodings:
                # Compare face with host
                matches = face_recognition.compare_faces(
                    [self.host_encoding], face_encoding, tolerance=0.6
                )
                if True in matches:
                    return True, "match_found"

            return False, "no_match"
        finally:
            cap.release()

    def enroll_host(self):
        """Capture a frame and save it as the host face print."""
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return False, "camera_unavailable"

        logger.info("Enrolling host face. Please look at the camera...")
        try:
            # Take a few frames to let the camera adjust exposure
            for _ in range(10):
                ret, frame = cap.read()

            if ret:
                # Find face to ensure quality
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(rgb_frame)

                if face_locations:
                    cv2.imwrite(str(self.host_face_path), frame)
                    self.host_encoding = self._load_host_encoding()
                    logger.info(f"Host face enrolled at {self.host_face_path}")
                    return True, "enrolled"
                else:
                    return False, "no_face_detected"
            return False, "capture_failed"
        finally:
            cap.release()
