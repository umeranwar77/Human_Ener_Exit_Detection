import cv2
import numpy as np

class HumanDetector:
    def __init__(self):
        try:
            self.fgbg = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=50, detectShadows=True)
        except Exception as e:
            raise

    def detect_humans(self, frame):
        try:
            fgmask = self.fgbg.apply(frame)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
            fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_OPEN, kernel)
            fgmask = cv2.dilate(fgmask, kernel, iterations=2)
            contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            detections = []
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                aspect_ratio = h / float(w)
                area = w * h
        
                if area > 500 and aspect_ratio > 1.5:
                    detections.append({
                        'x': int(x),
                        'y': int(y),
                        'w': int(w),
                        'h': int(h),
                        'confidence': 1.0  
                    })
            
            return detections
        except Exception as e:
            return []

    def draw_detections(self, frame, detections):
        try:
            for detection in detections:
                x, y, w, h = detection['x'], detection['y'], detection['w'], detection['h']
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, f"Human", 
                            (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            return frame
        except Exception as e:
            return frame
