type VoiceHandle = {
  stop: () => void;
  send: (event: unknown) => void;
  flush: () => void;
};

export type LiveServerEvent = {
  type?: string;
  delta?: string;
  event?: {
    type?: string;
    item?: {
      type?: string;
      name?: string;
      arguments?: string;
      call_id?: string;
    };
  };
};

type OpenedSession = {
  session_id: number;
  transport: { sdp: string };
};

function waitForIce(connection: RTCPeerConnection): Promise<void> {
  if (connection.iceGatheringState === "complete") {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      connection.removeEventListener("icegatheringstatechange", onState);
      reject(new Error("Timed out while gathering ICE candidates."));
    }, 10_000);
    function onState() {
      if (connection.iceGatheringState !== "complete") return;
      window.clearTimeout(timeout);
      connection.removeEventListener("icegatheringstatechange", onState);
      resolve();
    }
    connection.addEventListener("icegatheringstatechange", onState);
  });
}

export async function connectVoice(
  openSession: (sdp: string) => Promise<OpenedSession>,
  onServerEvent: (event: LiveServerEvent) => void,
): Promise<VoiceHandle & { sessionId: number }> {
  const peer = new RTCPeerConnection();
  const audio = new Audio();
  audio.autoplay = true;
  peer.addEventListener("track", (event) => {
    audio.srcObject = new MediaStream([event.track]);
    audio.play().catch(() => undefined);
  });

  let mic: MediaStream;
  try {
    mic = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    peer.close();
    throw new Error("Microphone permission is required for voice coaching.");
  }
  for (const track of mic.getAudioTracks()) {
    peer.addTrack(track, mic);
  }

  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    mic.getTracks().forEach((track) => track.stop());
    channel.close();
    peer.close();
    audio.srcObject = null;
  };

  const channel = peer.createDataChannel("oai-events");
  const queued: LiveServerEvent[] = [];
  let deliver = false;
  channel.addEventListener("message", (message) => {
    try {
      const event = JSON.parse(message.data) as LiveServerEvent;
      if (event.type === "session.closed") {
        cleanup();
      }
      if (deliver) {
        onServerEvent(event);
      } else {
        queued.push(event);
      }
    } catch {
      /* ignore non-json events */
    }
  });

  try {
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    await waitForIce(peer);
    const sdp = peer.localDescription?.sdp;
    if (!sdp) {
      throw new Error("Missing local SDP offer.");
    }
    const opened = await openSession(sdp);
    await peer.setRemoteDescription({ type: "answer", sdp: opened.transport.sdp });
    return {
      sessionId: opened.session_id,
      send: (event: unknown) => {
        if (channel.readyState === "open") {
          channel.send(JSON.stringify(event));
        }
      },
      flush: () => {
        deliver = true;
        for (const event of queued.splice(0)) {
          onServerEvent(event);
        }
      },
      stop: () => {
        if (channel.readyState === "open") {
          channel.send(JSON.stringify({ type: "session.close" }));
          window.setTimeout(cleanup, 4000);
          return;
        }
        cleanup();
      },
    };
  } catch (error) {
    cleanup();
    throw error;
  }
}

export function functionResult(callId: string, output: string) {
  return {
    type: "response.item.create",
    item: {
      type: "function_call_output",
      call_id: callId,
      output,
    },
  };
}
