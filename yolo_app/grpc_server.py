import cv2
import grpc
from concurrent import futures
from .utils.yolo import YOLO
from . import yolo_pb2, yolo_pb2_grpc


class YOLOServiceServicer(yolo_pb2_grpc.YOLOServiceServicer):
    def __init__(self):
        self.yolo = YOLO('path/to/yolov5s.pt')

    def Detect(self, request, context):
        # Convert byte data to OpenCV frames
        import numpy as np
        frame = np.frombuffer(request.frame, dtype=np.uint8)
        frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)

        # Perform YOLO inference
        results = self.yolo.detect(frame)

        # Construct DetectionResponse
        detection_results = []
        for result in results:
            detection_results.append(yolo_pb2.DetectionResult(
                label=result['name'],
                confidence=result['confidence'],
                xmin=int(result['xmin']),
                ymin=int(result['ymin']),
                xmax=int(result['xmax']),
                ymax=int(result['ymax'])
            ))

        return yolo_pb2.DetectionResponse(results=detection_results)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    yolo_pb2_grpc.add_YOLOServiceServicer_to_server(YOLOServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
