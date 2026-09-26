type VoiceHandle = {
  stop: () => void;
  send: (event: unknown) => void;
};

type ServerEvent = {
  type?: string;
  name?: string;
  arguments?: string;
  call_id?: string;
  transcript?: string;
  delta?: string;
};

export async function connectVoice(
  clientSecret: string,
  onServerEvent: (event: ServerEvent) => void,
): Promise<VoiceHandle> {
  const peer = new RTCPeerConnection();
  const audio = new Audio();
  audio.autoplay = true;
  peer.ontrack = (event) => {
    audio.srcObject = event.streams[0];
  };

  let mic: MediaStream;
  try {
    mic = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    peer.close();
    throw new Error("Microphone permission is required for voice coaching.");
  }
  for (const track of mic.getTracks()) {
    peer.addTrack(track, mic);
  }

  const channel = peer.createDataChannel("oai-events");
  channel.onmessage = (message) => {
    try {
      onServerEvent(JSON.parse(message.data) as ServerEvent);
    } catch {
      /* ignore non-json events */
    }
  };

  const offer = await peer.createOffer();
  await peer.setLocalDescription(offer);
  const response = await fetch("https://api.openai.com/v1/realtime/calls", {
    method: "POST",
    body: offer.sdp,
    headers: {
      Authorization: `Bearer ${clientSecret}`,
      "Content-Type": "application/sdp",
    },
  });
  if (!response.ok) {
    mic.getTracks().forEach((track) => track.stop());
    peer.close();
    throw new Error("Live voice connection failed.");
  }
  const answer = await response.text();
  await peer.setRemoteDescription({ type: "answer", sdp: answer });

  return {
    send: (event: unknown) => {
      if (channel.readyState === "open") {
        channel.send(JSON.stringify(event));
      }
    },
    stop: () => {
      channel.close();
      mic.getTracks().forEach((track) => track.stop());
      peer.close();
      audio.srcObject = null;
    },
  };
}

export function functionReply(callId: string, output: string) {
  return {
    type: "conversation.item.create",
    item: {
      type: "function_call_output",
      call_id: callId,
      output,
    },
  };
}
