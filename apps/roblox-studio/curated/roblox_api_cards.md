# Curated Roblox / Luau API cards (lightweight epistemic substitute)

Short usage cards for small local models. Prefer these over inventing APIs.

## Instance hierarchy

```lua
local part = Instance.new("Part")
part.Name = "Platform"
part.Parent = workspace
```

Paths in Mango tools: `game.Workspace.Platform`, `game.ServerScriptService.Main`.

## Script types

| Class | Runs on | Notes |
|-------|---------|--------|
| Script | Server | `ServerScriptService` / server-side containers |
| LocalScript | Client | `StarterPlayerScripts`, `StarterGui`, etc. |
| ModuleScript | require() | Return a table/function; no top-level side effects preferred |

## Players

```lua
local Players = game:GetService("Players")
Players.PlayerAdded:Connect(function(player)
	print(player.Name, "joined")
end)
```

## RemoteEvent (simple)

Server:
```lua
local re = Instance.new("RemoteEvent")
re.Name = "Ping"
re.Parent = game.ReplicatedStorage
re.OnServerEvent:Connect(function(player, payload)
	print(player.Name, payload)
end)
```

Client:
```lua
local re = game.ReplicatedStorage:WaitForChild("Ping")
re:FireServer("hello")
```

## TweenService

```lua
local TweenService = game:GetService("TweenService")
local info = TweenInfo.new(0.5, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
TweenService:Create(part, info, { Transparency = 1 }):Play()
```

## CollectionService tags

```lua
local CollectionService = game:GetService("CollectionService")
CollectionService:AddTag(part, "Interactable")
for _, inst in CollectionService:GetTagged("Interactable") do
	print(inst:GetFullName())
end
```

## DataStore (server only, sketch)

```lua
local DataStoreService = game:GetService("DataStoreService")
local store = DataStoreService:GetDataStore("PlayerData")
-- Always pcall GetAsync/SetAsync; never assume success.
```

## Common property shapes (JSON for rbx_prop)

- Vector3: `{ "X": 0, "Y": 10, "Z": 0 }`
- Color3: `{ "R": 1, "G": 0.2, "B": 0.2 }` (0–1)
- Enum: string name e.g. `"Enum.Material.Neon"` handled as material name `"Neon"` when current is EnumItem

## TestEZ (optional later)

Place specs under a known tree; run via Studio or CLI harness — not wired in MVP host.
