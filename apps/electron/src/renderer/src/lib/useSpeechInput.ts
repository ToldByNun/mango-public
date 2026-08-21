import { useCallback, useEffect, useRef, useState } from "react";

type SpeechRecognitionAlternative = { transcript: string };
type SpeechRecognitionResult = {
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternative | undefined;
};
type SpeechRecognitionResultList = {
  length: number;
  [index: number]: SpeechRecognitionResult | undefined;
};
type SpeechRecognitionEvent = {
  resultIndex: number;
  results: SpeechRecognitionResultList;
};

type SpeechCtor = new () => {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function browserSpeechCtor(): SpeechCtor | null {
  const w = window as Window & {
    SpeechRecognition?: SpeechCtor;
    webkitSpeechRecognition?: SpeechCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

async function ensureMicPermission(): Promise<boolean> {
  if (!navigator.mediaDevices?.getUserMedia) return true;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    for (const track of stream.getTracks()) track.stop();
    return true;
  } catch {
    return false;
  }
}

export function useSpeechInput(
  onText: (text: string) => void,
  onError: (message: string) => void,
): {
  listening: boolean;
  toggle: () => void;
} {
  const [listening, setListening] = useState(false);
  const recRef = useRef<InstanceType<SpeechCtor> | null>(null);
  const modeRef = useRef<"ipc" | "browser" | null>(null);

  const stop = useCallback(() => {
    if (modeRef.current === "ipc") {
      void window.mango.speech.stop();
    }
    recRef.current?.stop();
    recRef.current = null;
    modeRef.current = null;
    setListening(false);
  }, []);

  useEffect(() => {
    const offResult = window.mango.speech.onResult((text) => {
      if (text.trim()) onText(text);
      setListening(false);
      modeRef.current = null;
    });
    const offError = window.mango.speech.onError((message) => {
      onError(message);
      setListening(false);
      modeRef.current = null;
    });
    return () => {
      offResult();
      offError();
      stop();
    };
  }, [onError, onText, stop]);

  const startBrowser = useCallback(async () => {
    const Ctor = browserSpeechCtor();
    if (!Ctor) return false;
    const micOk = await ensureMicPermission();
    if (!micOk) {
      onError("Microphone permission denied.");
      return true;
    }
    const rec = new Ctor();
    rec.continuous = false;
    rec.interimResults = true;
    rec.lang = "de-DE";
    rec.onresult = (event: SpeechRecognitionEvent) => {
      let chunk = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (!result?.isFinal) continue;
        chunk += result[0]?.transcript ?? "";
      }
      if (chunk.trim()) onText(chunk);
    };
    rec.onerror = (event) => {
      onError(event.error ? `Speech error: ${event.error}` : "Speech recognition failed.");
      stop();
    };
    rec.onend = () => {
      recRef.current = null;
      modeRef.current = null;
      setListening(false);
    };
    recRef.current = rec;
    modeRef.current = "browser";
    rec.start();
    setListening(true);
    return true;
  }, [onError, onText, stop]);

  const toggle = useCallback(() => {
    if (listening) {
      stop();
      return;
    }

    void (async () => {
      try {
        const ipc = await window.mango.speech.start("de-DE");
        if (ipc.ok) {
          modeRef.current = "ipc";
          setListening(true);
          return;
        }
        const browserOk = await startBrowser();
        if (!browserOk) {
          onError("Voice input unavailable on this system.");
        }
      } catch (err) {
        onError(err instanceof Error ? err.message : "Voice input failed.");
        setListening(false);
        modeRef.current = null;
      }
    })();
  }, [listening, onError, startBrowser, stop]);

  return { listening, toggle };
}
