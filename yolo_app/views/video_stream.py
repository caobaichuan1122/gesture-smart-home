from django.http import StreamingHttpResponse
import cv2
from yolo_app.utils.yolo import YOLO


def video_stream(request):
    yolo = YOLO('path/to/yolov5s.pt')
    cap = cv2.VideoCapture(0)  # Open the camera

    def generate_frames():
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Perform YOLO inference
            results = yolo.detect(frame)

            # Draw the detection results on the frame
            for detection in results:
                x1, y1, x2, y2 = (int(detection['xmin']), int(detection['ymin']),
                                  int(detection['xmax']), int(detection['ymax']))
                label = detection['name']
                confidence = detection['confidence']
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

            # Convert the frame to JPEG format
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    return StreamingHttpResponse(generate_frames(), content_type='multipart/x-mixed-replace; boundary=frame')