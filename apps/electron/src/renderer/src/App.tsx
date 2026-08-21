import { AgentProvider } from "./context/AgentSession";
import { AppShell } from "./components/AppShell";
import { Titlebar } from "./components/Titlebar";
import "./styles/tokens.css";

export default function App(): JSX.Element {
  return (
    <AgentProvider>
      <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
        <Titlebar />
        <div style={{ flex: 1, minHeight: 0 }}>
          <AppShell />
        </div>
      </div>
    </AgentProvider>
  );
}
