import cv2
import torch

class YOLO:
    def __init__(self, model_path):
        self.model = torch.hub.load('ultralytics/yolov5', 'custom', path=model_path)

    def detect(self, frame):
        results = self.model(frame)
        return results.pandas().xyxy[0].to_dict(orient='records')