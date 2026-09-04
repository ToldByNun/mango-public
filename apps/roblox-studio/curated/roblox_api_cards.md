# Roblox API vault

Obsidian-style notes for small local models. Agent tool: `rbx_api`.

## Instance.new

```lua
local part = Instance.new("Part")
part.Name = "Platform"
part.Size = Vector3.new(8, 1, 8)
part.Anchored = true
part.Parent = workspace
```

Paths in Mango: `game.Workspace.Platform`. Always set Parent last.

## GetService

```lua
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local CollectionService = game:GetService("CollectionService")
local DataStoreService = game:GetService("DataStoreService")
```

Prefer GetService over waiting for service children.

## Script types

| Class | Runs on | Parent |
|-------|---------|--------|
| Script | Server | ServerScriptService |
| LocalScript | Client | StarterPlayerScripts / StarterGui / character |
| ModuleScript | require() | ReplicatedStorage / ServerStorage |

ModuleScripts should `return` a table or function.

## Players

```lua
local Players = game:GetService("Players")

Players.PlayerAdded:Connect(function(player)
	player.CharacterAdded:Connect(function(character)
		-- character ready
	end)
end)

local localPlayer = Players.LocalPlayer -- client only
```

## RemoteEvent

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
re.OnClientEvent:Connect(function(payload)
	print(payload)
end)
```

Never trust client payload; validate on server.

## RemoteFunction

```lua
-- server
rf.OnServerInvoke = function(player, request)
	return { ok = true }
end

-- client
local result = rf:InvokeServer(request)
```

Prefer RemoteEvent for fire-and-forget; RemoteFunction blocks the caller.

## BindableEvent

Same-side messaging (server↔server or client↔client). Not for client↔server.

```lua
local be = Instance.new("BindableEvent")
be.Event:Connect(function(msg) print(msg) end)
be:Fire("hi")
```

## TweenService

```lua
local TweenService = game:GetService("TweenService")
local info = TweenInfo.new(0.5, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
local tween = TweenService:Create(part, info, { Transparency = 1, Position = goal })
tween:Play()
tween.Completed:Wait()
```

## CollectionService

```lua
local CollectionService = game:GetService("CollectionService")
CollectionService:AddTag(part, "Interactable")
for _, inst in CollectionService:GetTagged("Interactable") do
	print(inst:GetFullName())
end
CollectionService:GetInstanceAddedSignal("Interactable"):Connect(function(inst)
	-- handle
end)
```

## UserInputService

Client only:
```lua
local UserInputService = game:GetService("UserInputService")
UserInputService.InputBegan:Connect(function(input, processed)
	if processed then return end
	if input.KeyCode == Enum.KeyCode.E then
		-- interact
	end
end)
```

## ContextActionService

```lua
local ContextActionService = game:GetService("ContextActionService")
ContextActionService:BindAction("JumpBoost", function(_, state)
	if state == Enum.UserInputState.Begin then
		-- 
	end
	return Enum.ContextActionResult.Pass
end, false, Enum.KeyCode.Space)
```

## DataStore

Server only; always pcall:
```lua
local DataStoreService = game:GetService("DataStoreService")
local store = DataStoreService:GetDataStore("PlayerData_v1")

local ok, data = pcall(function()
	return store:GetAsync("player_" .. player.UserId)
end)
if not ok then warn(data) end

local ok2, err = pcall(function()
	store:SetAsync("player_" .. player.UserId, { coins = 10 })
end)
```

Use UpdateAsync for race-safe writes. Enable Studio API Access for local testing.

## ProximityPrompt

```lua
local prompt = Instance.new("ProximityPrompt")
prompt.ActionText = "Open"
prompt.ObjectText = "Door"
prompt.HoldDuration = 0
prompt.Parent = part
prompt.Triggered:Connect(function(player)
	-- server-side if prompt is in Workspace
end)
```

## RunService

```lua
local RunService = game:GetService("RunService")
if RunService:IsServer() then
	-- server
end
if RunService:IsClient() then
	-- client
end
RunService.Heartbeat:Connect(function(dt)
	-- every frame after physics
end)
```

## Attribute

```lua
part:SetAttribute("HP", 100)
local hp = part:GetAttribute("HP")
part:GetAttributeChangedSignal("HP"):Connect(function()
	print(part:GetAttribute("HP"))
end)
```

Prefer Attributes over StringValues for simple data.

## rbx_prop JSON shapes

- Vector3: `{ "X": 0, "Y": 10, "Z": 0 }`
- Color3: `{ "R": 1, "G": 0.2, "B": 0.2 }` (0–1)
- EnumItem: string name matching current enum, e.g. `"Neon"` for Material

## task / defer

```lua
task.wait(1)
task.spawn(function() end)
task.defer(function() end)
task.delay(2, function() end)
```

Prefer `task.*` over deprecated `wait` / `spawn` / `delay`.
