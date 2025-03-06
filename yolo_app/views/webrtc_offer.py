from aiortc import RTCPeerConnection, VideoStreamTrack, RTCSessionDescription
from django.http import JsonResponse
import json

pcs = set()


async def webrtc_offer(request):
    params = json.loads(request.body)
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    # Add local video stream
    pc.addTrack(VideoStreamTrack())

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return JsonResponse({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })
