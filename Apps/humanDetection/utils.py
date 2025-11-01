import cv2
import numpy as np
import logging

class HumanDetector:
    def __init__(self):
        try:
            self.hog = cv2.HOGDescriptor()
            self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        except Exception as e:
            raise
    
    def detect_humans(self, frame):
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            boxes, weights = self.hog.detectMultiScale(gray, winStride=(8,8))
            
            detections = []
            for i, (x, y, w, h) in enumerate(boxes):
                if weights[i] > 0.5:
                    detections.append({
                        'x': int(x),
                        'y': int(y),
                        'w': int(w),
                        'h': int(h),
                        'confidence': float(weights[i])
                    })
            return detections
        except Exception as e:
            return []
    
    def draw_detections(self, frame, detections):
        try:
            for detection in detections:
                x, y, w, h = detection['x'], detection['y'], detection['w'], detection['h']
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, f"Human: {detection['confidence']:.2f}", 
                           (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            return frame
        except Exception as e:
            return frame