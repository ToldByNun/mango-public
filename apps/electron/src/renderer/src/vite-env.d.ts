/// <reference types="vite/client" />

declare module "*.module.css" {
  const classes: { readonly [key: string]: string };
  export default classes;
}

interface SpeechRecognitionResultList {
  length: number;
  [index: number]: { [index: number]: { transcript: string } | undefined; isFinal: boolean };
  item(index: number): { [index: number]: { transcript: string } | undefined; isFinal: boolean };
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}
