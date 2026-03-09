from ultralytics import YOLO as UltralyticsYOLO


class YOLO:
    """Thin wrapper around the Ultralytics YOLO model."""

    def __init__(self, model_path='yolov5s.pt'):
        self.model = UltralyticsYOLO(model_path)

    def detect(self, frame):
        """
        Run inference on a BGR frame (numpy array).
        Returns a list of dicts with keys: name, confidence, xmin, ymin, xmax, ymax.
        """
        results = self.model(frame, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                detections.append({
                    'name': r.names[cls_id],
                    'confidence': float(box.conf[0]),
                    'xmin': float(box.xyxy[0][0]),
                    'ymin': float(box.xyxy[0][1]),
                    'xmax': float(box.xyxy[0][2]),
                    'ymax': float(box.xyxy[0][3]),
                })
        return detections
